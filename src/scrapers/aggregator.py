"""
Motor de busca do EmpleoRadar España.

Fluxo:
  1. Monta deep links pré-filtrados para todos os portais selecionados (sempre).
  2. Coleta em paralelo (``asyncio`` + ``httpx``) com User-Agents rotativos,
     retentativas com backoff e detecção de bloqueio anti-bot.
  3. Usa APIs oficiais quando há credenciais em ``st.secrets`` (InfoJobs, Jooble).
  4. Faz o parsing em camadas: parser específico -> JSON-LD ``JobPosting`` ->
     heurística de links de oferta.
  5. Normaliza (jornada, modalidade, contrato, salário anual, data, localização),
     remove duplicadas e aplica os filtros da barra lateral.

Se um portal bloquear o servidor (comum em IPs de nuvem), o resultado daquele
portal vira ``blocked`` e o usuário continua com o deep link de 1 clique.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.data.spain_locations import (
    SPAIN_LOCATIONS, find_province_by_city, get_region_of_province, strip_accents,
)

from .models import (
    CONTRATO_ND, DATE_FILTER_DAYS, JORNADA_ALL, JORNADA_ND, MODALIDAD_ND,
    MODALIDAD_OPTIONS, MODALIDAD_REMOTO, STATUS_BLOCKED, STATUS_EMPTY, STATUS_ERROR,
    STATUS_LINK_ONLY, STATUS_OK, JobOffer, PortalResult, SearchParams,
)
from .normalizer import (
    classify_contrato, classify_jornada, classify_modalidad, clean_text, norm,
    parse_date, parse_salary, to_iso,
)
from .portals import PORTALS, Portal, _province_slug, build_deep_links, soup_of

# ---------------------------------------------------------------------------
# Configuração de rede
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1",
]

REQUEST_TIMEOUT = httpx.Timeout(12.0, connect=6.0)
PORTAL_TIMEOUT_S = 25.0
MAX_RETRIES = 2
MAX_CONCURRENCY = 6

_BLOCK_MARKERS = (
    "captcha", "cf-chl", "just a moment", "access denied", "px-captcha",
    "are you a robot", "verify you are human", "request unsuccessful", "incapsula",
    "datadome", "pardon our interruption", "attention required",
)


class BlockedError(Exception):
    """O portal respondeu com bloqueio anti-bot (403/429/captcha)."""


def _headers(referer: Optional[str] = None, accept_json: bool = False) -> Dict[str, str]:
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*" if accept_json else
                  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.7,pt;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
    }
    if referer:
        h["Referer"] = referer
    return h


def _looks_blocked(status: int, text: str) -> bool:
    if status in (401, 403, 429, 503, 999):  # 999 = resposta anti-bot do LinkedIn
        return True
    head = (text or "")[:6000].lower()
    # Páginas de desafio costumam ser curtas e conter marcadores típicos
    return len(head) < 6000 and any(m in head for m in _BLOCK_MARKERS)


async def fetch_text(client: httpx.AsyncClient, url: str, *, method: str = "GET",
                     json_body: Any = None, auth: Any = None, accept_json: bool = False) -> str:
    """GET/POST com retentativas, backoff exponencial e rotação de User-Agent."""
    last_exc: Optional[Exception] = None
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.request(
                method, url, headers=_headers(origin, accept_json), json=json_body, auth=auth,
            )
            if _looks_blocked(resp.status_code, resp.text):
                raise BlockedError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.text
        except BlockedError as exc:
            last_exc = exc
            if attempt >= 1:  # insistir muito só piora o bloqueio
                raise
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            last_exc = exc
        await asyncio.sleep(0.6 * (2 ** attempt) + random.random() * 0.4)
    assert last_exc is not None
    raise last_exc


# ---------------------------------------------------------------------------
# Parsers genéricos
# ---------------------------------------------------------------------------
def _iter_jsonld(obj: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(obj, list):
        for x in obj:
            yield from _iter_jsonld(x)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if "JobPosting" in types:
            yield obj
        for key in ("@graph", "itemListElement", "item", "mainEntity"):
            if key in obj:
                yield from _iter_jsonld(obj[key])


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def parse_jsonld_jobs(html: str, portal: Portal) -> List[JobOffer]:
    """Extrai ofertas de blocos <script type="application/ld+json"> (schema.org/JobPosting)."""
    soup = soup_of(html)
    jobs: List[JobOffer] = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for jp in _iter_jsonld(data):
            title = clean_text(jp.get("title") or jp.get("name"))
            if not title:
                continue
            org = _first(jp.get("hiringOrganization")) or {}
            loc = _first(jp.get("jobLocation")) or {}
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            addr = _first(addr) if isinstance(addr, list) else addr
            locality = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
            region = addr.get("addressRegion", "") if isinstance(addr, dict) else ""

            salary_text = ""
            bs = jp.get("baseSalary") or jp.get("estimatedSalary")
            bs = _first(bs)
            if isinstance(bs, dict):
                val = bs.get("value", {})
                val = _first(val) if isinstance(val, list) else val
                unit = (val.get("unitText") if isinstance(val, dict) else "") or bs.get("unitText", "")
                unit_es = {"HOUR": "hora", "MONTH": "mes", "YEAR": "año", "WEEK": "semana"}.get(str(unit).upper(), "")
                if isinstance(val, dict):
                    lo, hi = val.get("minValue"), val.get("maxValue")
                    single = val.get("value")
                else:
                    lo = hi = None
                    single = val
                if lo and hi:
                    salary_text = f"{lo} - {hi} € / {unit_es}".strip(" /")
                elif lo or hi or single:
                    salary_text = f"{lo or hi or single} € / {unit_es}".strip(" /")

            desc_html = jp.get("description") or ""
            desc = BeautifulSoup(desc_html, "html.parser").get_text(" ") if "<" in desc_html else desc_html
            emp_type = jp.get("employmentType")
            url = jp.get("url") or jp.get("sameAs") or ""
            if isinstance(url, list):
                url = url[0] if url else ""
            job = JobOffer(
                title=title,
                portal=portal.name,
                url=urljoin(portal.base_url, url) if url else "",
                company=clean_text(org.get("name") if isinstance(org, dict) else str(org)),
                location_raw=", ".join(x for x in (locality, region) if x),
                salary_text=salary_text,
                published_raw=str(jp.get("datePosted") or ""),
                summary=clean_text(desc, 400),
            )
            # Metadados estruturados têm prioridade na classificação
            et = " ".join(emp_type) if isinstance(emp_type, list) else (emp_type or "")
            job.jornada = classify_jornada(f"{title} {desc}", et)
            job.contrato = classify_contrato(f"{title} {desc}", et)
            job.modalidad = classify_modalidad(f"{title} {desc}", str(jp.get("jobLocationType") or ""))
            jobs.append(job)
    return jobs


_COMPANY_CLS = re.compile(r"company|empresa|employer|recruiter|subtitle|org", re.I)
_LOCATION_CLS = re.compile(r"location|ubicaci|localidad|city|ciudad|provincia|place|lugar", re.I)
_SALARY_CLS = re.compile(r"salary|salario|sueldo|wage|retribuc", re.I)
_DATE_CLS = re.compile(r"date|fecha|time|publicad|posted|hace", re.I)


def _find_text(container, cls_re: re.Pattern, exclude: str = "") -> str:
    for el in container.find_all(True, class_=cls_re):
        txt = clean_text(el.get_text(" "))
        if txt and txt != exclude and len(txt) < 120:
            return txt
    return ""


def parse_link_heuristic(html: str, portal: Portal, limit: int = 60) -> List[JobOffer]:
    """
    Fallback universal: encontra links que seguem o padrão de URL de oferta do
    portal e extrai título/empresa/local/salário do bloco HTML ao redor.
    """
    if not portal.link_patterns:
        return []
    patterns = [re.compile(p) for p in portal.link_patterns]
    soup = soup_of(html)
    seen: set[str] = set()
    jobs: List[JobOffer] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not any(p.search(href) for p in patterns):
            continue
        url = urljoin(portal.base_url, href).split("#")[0]
        if url in seen:
            continue
        title = clean_text(a.get("title") or a.get_text(" "))
        if len(title) < 4 or len(title) > 160 or title.lower() in ("ver oferta", "ver más", "inscribirme", "ver"):
            heading = a.find(["h2", "h3", "h4"])
            title = clean_text(heading.get_text(" ")) if heading else title
            if len(title) < 4 or len(title) > 160:
                continue
        seen.add(url)

        # Sobe até um contêiner "cartão" razoável
        container = a
        for _ in range(5):
            parent = container.parent
            if parent is None or parent.name in ("body", "html"):
                break
            container = parent
            if len(clean_text(container.get_text(" "))) > 160 or container.name in ("article", "li"):
                break
        ctx = clean_text(container.get_text(" "))
        if len(ctx) > 1500:
            ctx = title

        company = _find_text(container, _COMPANY_CLS, exclude=title)
        location = _find_text(container, _LOCATION_CLS, exclude=title)
        summary = ctx.replace(title, "", 1)
        for part in (company, location):  # evita repetir dados já exibidos no card
            if part:
                summary = summary.replace(part, "", 1)
        jobs.append(JobOffer(
            title=title,
            portal=portal.name,
            url=url,
            company=company,
            location_raw=location,
            salary_text=_find_text(container, _SALARY_CLS) or _salary_snippet(ctx),
            published_raw=_find_text(container, _DATE_CLS) or _date_snippet(ctx),
            summary=clean_text(summary.strip(" ·-|"), 320),
        ))
        if len(jobs) >= limit:
            break
    return jobs


def _salary_snippet(text: str) -> str:
    m = re.search(r"[^.·|]{0,40}\d[\d.,\s]*\s*(?:k\s*)?(?:€|eur)[^.·|]{0,30}", text, re.I)
    return clean_text(m.group(0)) if m else ""


def _date_snippet(text: str) -> str:
    m = re.search(r"(hace\s+\d+\s+\w+|hace\s+un[a]?\s+\w+|ayer|hoy|\d+\s+(?:days?|hours?)\s+ago|\d{1,2}/\d{1,2}/\d{4})", text, re.I)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# APIs oficiais (opcionais, via st.secrets)
# ---------------------------------------------------------------------------
async def fetch_infojobs_api(client: httpx.AsyncClient, p: SearchParams, creds: Dict[str, str]) -> List[JobOffer]:
    """API oficial InfoJobs (https://developer.infojobs.net) — requer client_id/secret."""
    since = {1: "_24_HOURS", 3: "_7_DAYS", 7: "_7_DAYS"}.get(DATE_FILTER_DAYS.get(p.date_range, 30), "_15_DAYS")
    query: Dict[str, Any] = {
        "q": " ".join(x for x in (p.effective_keyword, p.city or "") if x),
        "maxResults": min(50, p.max_per_portal),
        "order": "updated-desc",
        "sinceDate": since,
    }
    slug = _province_slug(p)
    if slug:
        query["province"] = slug
    url = "https://api.infojobs.net/api/9/offer?" + urlencode(query)
    text = await fetch_text(client, url, auth=(creds["client_id"], creds["client_secret"]), accept_json=True)
    data = json.loads(text)
    jobs: List[JobOffer] = []
    for o in data.get("offers", []):
        def val(key: str) -> str:
            v = o.get(key)
            return v.get("value", "") if isinstance(v, dict) else (v or "")
        salary = ""
        if val("salaryMin") or val("salaryMax"):
            salary = f"{val('salaryMin')} - {val('salaryMax')} {val('salaryPeriod')}".strip()
        job = JobOffer(
            title=clean_text(o.get("title")),
            portal="InfoJobs España",
            url=o.get("link", ""),
            company=clean_text((o.get("author") or {}).get("name", "")),
            location_raw=", ".join(x for x in (o.get("city", ""), val("province")) if x),
            salary_text=salary,
            published_raw=o.get("published") or o.get("updated") or "",
            summary=clean_text(f"{val('contractType')} · {val('workDay')} · {val('teleworking')} · "
                               f"{o.get('requirementMin', '')}", 320).strip(" ·"),
        )
        jobs.append(job)
    return jobs


async def fetch_jooble_api(client: httpx.AsyncClient, p: SearchParams, api_key: str) -> List[JobOffer]:
    """API oficial Jooble (https://jooble.org/api/about) — requer chave gratuita."""
    body = {"keywords": p.effective_keyword, "location": p.city or p.province or "España", "page": "1"}
    text = await fetch_text(client, f"https://jooble.org/api/{api_key}", method="POST",
                            json_body=body, accept_json=True)
    data = json.loads(text)
    jobs: List[JobOffer] = []
    for j in data.get("jobs", [])[: p.max_per_portal]:
        snippet = BeautifulSoup(j.get("snippet", ""), "html.parser").get_text(" ")
        jobs.append(JobOffer(
            title=clean_text(BeautifulSoup(j.get("title", ""), "html.parser").get_text(" ")),
            portal="Jooble España",
            url=j.get("link", ""),
            company=clean_text(j.get("company", "")),
            location_raw=clean_text(j.get("location", "")),
            salary_text=clean_text(j.get("salary", "")),
            published_raw=j.get("updated", ""),
            summary=clean_text(f"{snippet} {j.get('type', '')}", 320),
        ))
    return jobs


# ---------------------------------------------------------------------------
# Normalização / enriquecimento
# ---------------------------------------------------------------------------
_ALL_PROVINCES = {
    strip_accents(prov).lower(): prov for provs in SPAIN_LOCATIONS.values() for prov in provs
}
_PROVINCE_ALIASES = {
    "alacant": "Alicante", "castello": "Castellón", "castello de la plana": "Castellón",
    "valencia/valencia": "Valencia", "baleares": "Illes Balears", "islas baleares": "Illes Balears",
    "vizcaya": "Bizkaia", "biscay": "Bizkaia", "guipuzcoa": "Gipuzkoa", "araba": "Álava",
    "la coruna": "A Coruña", "coruna": "A Coruña", "gerona": "Girona", "lerida": "Lleida",
    "orense": "Ourense", "tenerife": "Santa Cruz de Tenerife", "gran canaria": "Las Palmas",
}


def _resolve_location(job: JobOffer) -> None:
    raw = job.location_raw or ""
    parts = [x.strip() for x in re.split(r"[,(/)\-–]| y ", raw) if x.strip()]
    if parts and not job.city:
        first = parts[0]
        if norm(first) not in ("espana", "spain", "remoto", "teletrabajo", "remote"):
            job.city = first
    if not job.province:
        for part in parts:
            key = strip_accents(part).lower()
            if key in _ALL_PROVINCES:
                job.province = _ALL_PROVINCES[key]
                break
            if key in _PROVINCE_ALIASES:
                job.province = _PROVINCE_ALIASES[key]
                break
        if not job.province and job.city:
            job.province = find_province_by_city(job.city) or ""


def enrich(job: JobOffer, p: SearchParams) -> JobOffer:
    """Classifica e normaliza uma oferta bruta."""
    text = " ".join([job.title, job.summary, job.salary_text, job.location_raw])
    if job.jornada == JORNADA_ND:
        job.jornada = classify_jornada(text)
    if job.modalidad == MODALIDAD_ND:
        job.modalidad = classify_modalidad(text)
    if job.contrato == CONTRATO_ND:
        job.contrato = classify_contrato(text)
    if job.salary_min_annual is None:
        smin, smax = parse_salary(job.salary_text or "", job.jornada)
        if smin is None:
            smin, smax = parse_salary(job.summary, job.jornada)
        job.salary_min_annual, job.salary_max_annual = smin, smax
    if not job.published and job.published_raw:
        job.published = to_iso(parse_date(job.published_raw))
    _resolve_location(job)
    if not job.province and p.province and job.modalidad != MODALIDAD_REMOTO:
        job.province = p.province  # resultado veio de uma busca já restrita à província
    job.sector = p.sector if p.sector != "Geral" else ""
    job.title = clean_text(job.title, 160)
    return job


def deduplicate(jobs: List[JobOffer]) -> List[JobOffer]:
    seen: Dict[str, JobOffer] = {}
    for j in jobs:
        key = f"{norm(j.title)}|{norm(j.company)}|{norm(j.city)}"
        current = seen.get(key)
        # mantém a versão com mais informação (salário/data)
        if current is None or (not current.salary_mid and j.salary_mid) or (not current.published and j.published):
            seen[key] = j
    return list(seen.values())


def apply_filters(jobs: List[JobOffer], p: SearchParams, now: Optional[datetime] = None) -> List[JobOffer]:
    now = now or datetime.now(timezone.utc)
    unk = p.include_unknown
    max_age = timedelta(days=DATE_FILTER_DAYS.get(p.date_range, 30))
    out: List[JobOffer] = []
    for j in jobs:
        if p.jornada != JORNADA_ALL and j.jornada != p.jornada and not (unk and j.jornada == JORNADA_ND):
            continue
        if p.modalidades and set(p.modalidades) != set(MODALIDAD_OPTIONS):
            if j.modalidad not in p.modalidades and not (unk and j.modalidad == MODALIDAD_ND):
                continue
        if p.contratos and j.contrato not in p.contratos and not (unk and j.contrato == CONTRATO_ND):
            continue
        if p.salary_min:
            best = j.salary_max_annual or j.salary_min_annual
            if best is None:
                if not unk:
                    continue
            elif best < p.salary_min:
                continue
        dt = j.published_dt
        if dt is None:
            if not unk:
                continue
        elif now - dt > max_age + timedelta(hours=12):
            continue
        # Localização: descarta somente quando sabemos com certeza que é outra província
        if p.province and j.province and j.province != p.province and j.modalidad != MODALIDAD_REMOTO:
            continue
        if p.region and not p.province and j.province:
            reg = get_region_of_province(j.province)
            if reg and reg != p.region and j.modalidad != MODALIDAD_REMOTO:
                continue
        out.append(j)
    return out


def sort_jobs(jobs: List[JobOffer], by: str = "date") -> List[JobOffer]:
    if by == "salary":
        return sorted(jobs, key=lambda j: (j.salary_mid or 0), reverse=True)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(jobs, key=lambda j: j.published_dt or epoch, reverse=True)


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
@dataclass
class AggregatedResult:
    jobs: List[JobOffer]
    total_raw: int
    portal_results: List[PortalResult]
    deep_links: Dict[str, str]
    searched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jobs": [j.to_dict() for j in self.jobs],
            "total_raw": self.total_raw,
            "portal_results": [r.to_dict() for r in self.portal_results],
            "deep_links": self.deep_links,
            "searched_at": self.searched_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AggregatedResult":
        prs = []
        for r in d.get("portal_results", []):
            prs.append(PortalResult(
                portal=r["portal"], status=r["status"],
                jobs=[JobOffer.from_dict(j) for j in r.get("jobs", [])],
                message=r.get("message", ""), deep_link=r.get("deep_link", ""),
                elapsed=r.get("elapsed", 0.0),
            ))
        return cls(
            jobs=[JobOffer.from_dict(j) for j in d.get("jobs", [])],
            total_raw=d.get("total_raw", 0), portal_results=prs,
            deep_links=d.get("deep_links", {}), searched_at=d.get("searched_at", ""),
        )


def _parse_portal_html(portal: Portal, html: str, p: SearchParams) -> List[JobOffer]:
    jobs: List[JobOffer] = []
    if portal.parse:
        jobs = portal.parse(html, p)
    if not jobs:
        jobs = parse_jsonld_jobs(html, portal)
    if not jobs:
        jobs = parse_link_heuristic(html, portal, limit=p.max_per_portal)
    return jobs


async def _run_portal(client: httpx.AsyncClient, sem: asyncio.Semaphore, portal: Portal,
                      p: SearchParams, secrets: Dict[str, Any]) -> PortalResult:
    link = portal.build_link(p)
    start = time.perf_counter()
    if not portal.scrape_supported:
        return PortalResult(portal.name, STATUS_LINK_ONLY,
                            message="Portal baseado em aplicação JavaScript; use o link direto.",
                            deep_link=link)
    async with sem:
        try:
            jobs: List[JobOffer] = []
            source = "HTML"
            if portal.key == "infojobs" and secrets.get("infojobs_client_id") and secrets.get("infojobs_client_secret"):
                jobs = await fetch_infojobs_api(client, p, {
                    "client_id": secrets["infojobs_client_id"],
                    "client_secret": secrets["infojobs_client_secret"],
                })
                source = "API oficial"
            elif portal.key == "jooble" and secrets.get("jooble_api_key"):
                jobs = await fetch_jooble_api(client, p, secrets["jooble_api_key"])
                source = "API oficial"
            else:
                urls = portal.fetch_urls(p)
                pages = await asyncio.gather(*(fetch_text(client, u) for u in urls), return_exceptions=True)
                errors = [x for x in pages if isinstance(x, Exception)]
                if errors and len(errors) == len(pages):
                    raise errors[0]
                for html in pages:
                    if isinstance(html, str):
                        jobs.extend(_parse_portal_html(portal, html, p))

            jobs = [enrich(j, p) for j in jobs if j.title and j.url.startswith("http")]
            jobs = deduplicate(jobs)[: p.max_per_portal]
            status = STATUS_OK if jobs else STATUS_EMPTY
            msg = f"{len(jobs)} vagas via {source}" if jobs else "Nenhuma vaga extraída; use o link direto."
            return PortalResult(portal.name, status, jobs, msg, link, time.perf_counter() - start)
        except BlockedError as exc:
            return PortalResult(portal.name, STATUS_BLOCKED, [],
                                f"Portal bloqueou a coleta automática ({exc}). Use o link direto.",
                                link, time.perf_counter() - start)
        except Exception as exc:  # noqa: BLE001 — nunca derrubar a busca inteira
            name = type(exc).__name__
            return PortalResult(portal.name, STATUS_ERROR, [],
                                f"Falha de conexão ({name}). Use o link direto.",
                                link, time.perf_counter() - start)


async def search_async(p: SearchParams, secrets: Optional[Dict[str, Any]] = None,
                       transport: Optional[httpx.AsyncBaseTransport] = None) -> AggregatedResult:
    """Executa a busca em todos os portais. ``transport`` permite testes offline (httpx.MockTransport)."""
    secrets = secrets or {}
    keys = [k for k in (p.portals or list(PORTALS)) if k in PORTALS]
    deep_links = build_deep_links(p, keys)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True, limits=limits,
                                 transport=transport) as client:
        async def guarded(portal: Portal) -> PortalResult:
            try:
                return await asyncio.wait_for(_run_portal(client, sem, portal, p, secrets), PORTAL_TIMEOUT_S)
            except asyncio.TimeoutError:
                return PortalResult(portal.name, STATUS_ERROR, [],
                                    "Tempo limite excedido. Use o link direto.", portal.build_link(p))
        results = await asyncio.gather(*(guarded(PORTALS[k]) for k in keys))

    all_jobs = [j for r in results for j in r.jobs]
    unique = deduplicate(all_jobs)
    filtered = sort_jobs(apply_filters(unique, p))
    return AggregatedResult(jobs=filtered, total_raw=len(unique),
                            portal_results=list(results), deep_links=deep_links)


def search(p: SearchParams, secrets: Optional[Dict[str, Any]] = None) -> AggregatedResult:
    """Wrapper síncrono seguro para o Streamlit (funciona com ou sem event loop ativo)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(search_async(p, secrets))

    box: Dict[str, Any] = {}

    def runner() -> None:
        try:
            box["result"] = asyncio.run(search_async(p, secrets))
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["result"]
