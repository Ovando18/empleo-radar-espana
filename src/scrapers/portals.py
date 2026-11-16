"""
Definição dos 10 portais integrados.

Cada portal declara:
  - ``build_link(params)``: URL de busca pré-filtrada (deep link) para abrir no navegador
  - ``fetch_url(params)``: URL(s) que o servidor tenta coletar (pode ser uma API/endpoint)
  - ``parse(html, params)``: parser específico; se não houver resultados, o motor
    aplica os parsers genéricos (JSON-LD ``JobPosting`` e heurística de links).

Todos os templates de URL estão centralizados aqui para facilitar manutenção
quando um portal mudar o formato das suas buscas.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import quote, quote_plus, urlencode, urljoin

from bs4 import BeautifulSoup

from src.data.spain_locations import get_province_info, slugify

from .models import (
    DATE_FILTER_DAYS, JORNADA_COMPLETA, JORNADA_PARCIAL, JORNADA_TURNOS,
    MODALIDAD_HIBRIDO, MODALIDAD_PRESENCIAL, MODALIDAD_REMOTO, JobOffer, SearchParams,
)
from .normalizer import clean_text

try:  # lxml é mais rápido; html.parser é o fallback universal
    import lxml  # noqa: F401
    HTML_PARSER = "lxml"
except ImportError:  # pragma: no cover
    HTML_PARSER = "html.parser"


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", HTML_PARSER)


# ---------------------------------------------------------------------------
# Auxiliares de montagem de URL
# ---------------------------------------------------------------------------
def _kw(p: SearchParams) -> str:
    return p.effective_keyword


def _jornada_hint(p: SearchParams) -> str:
    """Termo extra para portais sem filtro nativo de jornada."""
    return {
        JORNADA_PARCIAL: "media jornada",
        JORNADA_COMPLETA: "jornada completa",
        JORNADA_TURNOS: "turnos",
    }.get(p.jornada, "")


def _kw_with_hint(p: SearchParams) -> str:
    return " ".join(x for x in (_kw(p), _jornada_hint(p)) if x).strip()


def _province_slug(p: SearchParams) -> str:
    info = get_province_info(p.province)
    return info["slug"] if info else ""


def _location_text(p: SearchParams, with_country: bool = False) -> str:
    parts = [x for x in (p.city, p.province if p.province != p.city else None) if x]
    if with_country:
        parts.append("España")
    return ", ".join(parts) if parts else ("España" if with_country else "")


def _days(p: SearchParams) -> int:
    return DATE_FILTER_DAYS.get(p.date_range, 30)


# ---------------------------------------------------------------------------
# Construtores de deep links (um por portal)
# ---------------------------------------------------------------------------
def link_infojobs(p: SearchParams) -> str:
    since = {1: "_24_HOURS", 3: "_7_DAYS", 7: "_7_DAYS", 30: "_15_DAYS"}.get(_days(p), "ANY")
    kw = " ".join(x for x in (_kw_with_hint(p), p.city or "") if x)
    params = {"keyword": kw, "sortBy": "PUBLICATION_DATE", "sinceDate": since}
    if p.modalidades == [MODALIDAD_REMOTO]:
        params["teleworkingIds"] = "2"
    slug = _province_slug(p)
    base = f"https://www.infojobs.net/ofertas-trabajo/{slug}" if slug else "https://www.infojobs.net/jobsearch/search-results/list.xhtml"
    return f"{base}?{urlencode(params)}"


def link_indeed(p: SearchParams) -> str:
    params = {"q": _kw(p), "l": _location_text(p) or "España", "sort": "date", "fromage": str(_days(p))}
    if p.jornada == JORNADA_PARCIAL:
        params["jt"] = "parttime"
    elif p.jornada == JORNADA_COMPLETA:
        params["jt"] = "fulltime"
    if p.modalidades == [MODALIDAD_REMOTO]:
        params["sc"] = "0kf:attr(DSQF7);"
    return "https://es.indeed.com/jobs?" + urlencode(params)


_LINKEDIN_TPR = {1: "r86400", 3: "r259200", 7: "r604800", 30: "r2592000"}
_LINKEDIN_WT = {MODALIDAD_PRESENCIAL: "1", MODALIDAD_REMOTO: "2", MODALIDAD_HIBRIDO: "3"}


def _linkedin_params(p: SearchParams) -> Dict[str, str]:
    params = {
        "keywords": _kw(p),
        "location": _location_text(p, with_country=True),
        "f_TPR": _LINKEDIN_TPR.get(_days(p), "r2592000"),
        "sortBy": "DD",
    }
    if p.jornada == JORNADA_PARCIAL:
        params["f_JT"] = "P"
    elif p.jornada == JORNADA_COMPLETA:
        params["f_JT"] = "F"
    wt = [_LINKEDIN_WT[m] for m in p.modalidades if m in _LINKEDIN_WT]
    if wt and len(wt) < 3:
        params["f_WT"] = ",".join(wt)
    return params


def link_linkedin(p: SearchParams) -> str:
    return "https://www.linkedin.com/jobs/search/?" + urlencode(_linkedin_params(p))


def link_empleate(p: SearchParams) -> str:
    text = " ".join(x for x in (_kw_with_hint(p), p.city or p.province or "") if x)
    return "https://www.empleate.gob.es/empleo/#/trabajo?search=" + quote(text)


def link_infoempleo(p: SearchParams) -> str:
    slug = _province_slug(p)
    kw = slugify(_kw_with_hint(p))
    path = "https://www.infoempleo.com/trabajo/"
    if kw:
        path += f"{kw}/"
    if slug:
        path += f"en_{slug}/"
    return path


def link_jooble(p: SearchParams) -> str:
    params = {"ukw": _kw_with_hint(p), "rgns": _location_text(p) or "España"}
    return "https://es.jooble.org/SearchResult?" + urlencode(params)


def link_randstad(p: SearchParams) -> str:
    params = {"q": _kw_with_hint(p)}
    loc = p.city or p.province
    if loc:
        params["location"] = loc
    return "https://www.randstad.es/candidatos/ofertas-empleo/?" + urlencode(params)


def link_jobtoday(p: SearchParams) -> str:
    params = {"keyword": _kw(p), "location": p.city or p.province or "España"}
    return "https://jobtoday.com/es/trabajos?" + urlencode(params)


def link_tecnoempleo(p: SearchParams) -> str:
    te = " ".join(x for x in (_kw(p), p.city or p.province or "") if x)
    return "https://www.tecnoempleo.com/ofertas-trabajo/?te=" + quote_plus(te)


def link_turijobs(p: SearchParams) -> str:
    slug = _province_slug(p)
    base = f"https://www.turijobs.com/ofertas-trabajo-{slug}" if slug else "https://www.turijobs.com/ofertas-trabajo"
    kw = _kw_with_hint(p)
    return f"{base}?{urlencode({'q': kw})}" if kw else base


# ---------------------------------------------------------------------------
# Parsers específicos
# ---------------------------------------------------------------------------
def parse_linkedin(html: str, p: SearchParams) -> List[JobOffer]:
    """Endpoint público 'jobs-guest' do LinkedIn (lista de <li> com base-card)."""
    soup = soup_of(html)
    jobs: List[JobOffer] = []
    for card in soup.select("div.base-card, div.base-search-card, li div.job-search-card"):
        title_el = card.select_one(".base-search-card__title, h3")
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not title_el or not link_el:
            continue
        href = link_el.get("href", "").split("?")[0]
        company_el = card.select_one(".base-search-card__subtitle, h4")
        loc_el = card.select_one(".job-search-card__location")
        time_el = card.select_one("time")
        salary_el = card.select_one(".job-search-card__salary-info")
        benefits_el = card.select_one(".job-posting-benefits__text, .result-benefits__text")
        jobs.append(JobOffer(
            title=clean_text(title_el.get_text()),
            portal="LinkedIn Jobs",
            url=href,
            company=clean_text(company_el.get_text()) if company_el else "",
            location_raw=clean_text(loc_el.get_text()) if loc_el else "",
            salary_text=clean_text(salary_el.get_text()) if salary_el else "",
            published_raw=(time_el.get("datetime") or time_el.get_text()) if time_el else "",
            summary=clean_text(benefits_el.get_text()) if benefits_el else "",
        ))
    return jobs


_INDEED_JSON_RE = re.compile(
    r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});\s*\n', re.S)


def parse_indeed(html: str, p: SearchParams) -> List[JobOffer]:
    """Indeed embute os resultados num JSON 'mosaic-provider-jobcards'."""
    jobs: List[JobOffer] = []
    m = _INDEED_JSON_RE.search(html or "")
    if m:
        try:
            data = json.loads(m.group(1))
            results = data["metaData"]["mosaicProviderJobCardsModel"]["results"]
        except (ValueError, KeyError, TypeError):
            results = []
        for r in results:
            jk = r.get("jobkey")
            if not jk or not r.get("title"):
                continue
            snippet = BeautifulSoup(r.get("snippet", ""), "html.parser").get_text(" ")
            attr_labels = [str(x) for x in (r.get("jobTypes") or [])]
            for tax in r.get("taxonomyAttributes") or []:
                for a in tax.get("attributes") or []:
                    attr_labels.append(a.get("label", ""))
            attrs = " ".join(attr_labels)
            jobs.append(JobOffer(
                title=clean_text(r.get("displayTitle") or r.get("title")),
                portal="Indeed España",
                url=f"https://es.indeed.com/viewjob?jk={jk}",
                company=clean_text(r.get("company", "")),
                location_raw=clean_text(r.get("formattedLocation", "")),
                salary_text=clean_text((r.get("salarySnippet") or {}).get("text", "")
                                       or (r.get("extractedSalary") or {}).get("text", "")),
                published_raw=r.get("pubDate") or r.get("formattedRelativeTime", ""),
                summary=clean_text(f"{snippet} {attrs}", 400),
            ))
        return jobs

    # Fallback: cartões HTML
    soup = soup_of(html)
    for card in soup.select("div.job_seen_beacon, td.resultContent, div.cardOutline"):
        a = card.select_one("h2 a[data-jk], a.jcs-JobTitle")
        if not a:
            continue
        jk = a.get("data-jk")
        url = f"https://es.indeed.com/viewjob?jk={jk}" if jk else urljoin("https://es.indeed.com", a.get("href", ""))
        company = card.select_one("[data-testid='company-name'], .companyName")
        loc = card.select_one("[data-testid='text-location'], .companyLocation")
        salary = card.select_one(".salary-snippet-container, [data-testid='attribute_snippet_testid']")
        jobs.append(JobOffer(
            title=clean_text(a.get_text()),
            portal="Indeed España",
            url=url,
            company=clean_text(company.get_text()) if company else "",
            location_raw=clean_text(loc.get_text()) if loc else "",
            salary_text=clean_text(salary.get_text()) if salary else "",
            summary=clean_text(card.get_text(" "), 300),
        ))
    return jobs


# ---------------------------------------------------------------------------
# Registro de portais
# ---------------------------------------------------------------------------
@dataclass
class Portal:
    key: str
    name: str
    description: str
    build_link: Callable[[SearchParams], str]
    fetch_urls: Callable[[SearchParams], List[str]]
    base_url: str
    link_patterns: List[str] = field(default_factory=list)
    parse: Optional[Callable[[str, SearchParams], List[JobOffer]]] = None
    scrape_supported: bool = True
    sectors: List[str] = field(default_factory=list)  # vazio = todos
    color: str = "#AA151B"


def _linkedin_fetch(p: SearchParams) -> List[str]:
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
    pages = max(1, min(4, (p.max_per_portal + 9) // 10))
    return [base + urlencode({**_linkedin_params(p), "start": str(i * 10)}) for i in range(pages)]


PORTALS: Dict[str, Portal] = {
    "infojobs": Portal(
        key="infojobs", name="InfoJobs España",
        description="Líder nacional em volume de vagas.",
        build_link=link_infojobs,
        fetch_urls=lambda p: [link_infojobs(p)],
        base_url="https://www.infojobs.net",
        link_patterns=[r"/of-i[0-9a-f]{6,}"],
    ),
    "indeed": Portal(
        key="indeed", name="Indeed España",
        description="Metabuscador global com forte presença na Espanha.",
        build_link=link_indeed,
        fetch_urls=lambda p: [link_indeed(p)],
        base_url="https://es.indeed.com",
        link_patterns=[r"/viewjob\?jk=", r"/rc/clk\?jk=", r"/pagead/clk"],
        parse=parse_indeed,
    ),
    "linkedin": Portal(
        key="linkedin", name="LinkedIn Jobs",
        description="Vagas qualificadas e corporativas (endpoint público de convidado).",
        build_link=link_linkedin,
        fetch_urls=_linkedin_fetch,
        base_url="https://www.linkedin.com",
        link_patterns=[r"/jobs/view/"],
        parse=parse_linkedin,
    ),
    "empleate": Portal(
        key="empleate", name="Empléate (SEPE)",
        description="Portal oficial do Serviço Público de Emprego Estatal.",
        build_link=link_empleate,
        fetch_urls=lambda p: [],
        base_url="https://www.empleate.gob.es",
        scrape_supported=False,  # aplicação SPA: apenas deep link
    ),
    "infoempleo": Portal(
        key="infoempleo", name="Infoempleo",
        description="Portal generalista com boa cobertura regional.",
        build_link=link_infoempleo,
        fetch_urls=lambda p: [link_infoempleo(p)],
        base_url="https://www.infoempleo.com",
        link_patterns=[r"/ofertasdetrabajo/[^/]+/[^/]+/\d+"],
    ),
    "jooble": Portal(
        key="jooble", name="Jooble España",
        description="Agregador que reúne ofertas de centenas de sites.",
        build_link=link_jooble,
        fetch_urls=lambda p: [link_jooble(p)],
        base_url="https://es.jooble.org",
        link_patterns=[r"/desc/\d+", r"/away/\d+"],
    ),
    "randstad": Portal(
        key="randstad", name="Randstad España",
        description="ETT líder: indústria, logística, atendimento e escritórios.",
        build_link=link_randstad,
        fetch_urls=lambda p: [link_randstad(p)],
        base_url="https://www.randstad.es",
        link_patterns=[r"/ofertas-empleo/[^?#]*\d{5,}", r"/oferta/[^?#]+"],
    ),
    "jobtoday": Portal(
        key="jobtoday", name="Job Today",
        description="Vagas operacionais e de contratação rápida (hotelaria, varejo).",
        build_link=link_jobtoday,
        fetch_urls=lambda p: [link_jobtoday(p)],
        base_url="https://jobtoday.com",
        link_patterns=[r"/es/(?:trabajo|empleo|job)/[^?#]+"],
    ),
    "tecnoempleo": Portal(
        key="tecnoempleo", name="Tecnoempleo",
        description="Especializado em TI, Telecom e Engenharia.",
        build_link=link_tecnoempleo,
        fetch_urls=lambda p: [link_tecnoempleo(p)],
        base_url="https://www.tecnoempleo.com",
        link_patterns=[r"/rf-[0-9a-z]{6,}"],
        sectors=["Tecnologia / TI", "Engenharia & Construção"],
    ),
    "turijobs": Portal(
        key="turijobs", name="Turijobs",
        description="Especializado em Turismo e Hotelaria.",
        build_link=link_turijobs,
        fetch_urls=lambda p: [link_turijobs(p)],
        base_url="https://www.turijobs.com",
        link_patterns=[r"/oferta-trabajo[^?#]*-\d{4,}", r"/ofertas-trabajo/[^?#]+/\d{4,}", r"/oferta/\d+"],
        sectors=["Hotelaria / Turismo"],
    ),
}

PORTAL_NAMES: Dict[str, str] = {k: v.name for k, v in PORTALS.items()}


def build_deep_links(params: SearchParams, portal_keys: Optional[List[str]] = None) -> Dict[str, str]:
    keys = portal_keys or list(PORTALS)
    return {k: PORTALS[k].build_link(params) for k in keys if k in PORTALS}
