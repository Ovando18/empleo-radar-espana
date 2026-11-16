"""Testes offline do EmpleoRadar España (sem acesso à internet)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from openpyxl import load_workbook

from src.data.spain_locations import (
    SPAIN_LOCATIONS, count_summary, find_province_by_city, get_cities, get_provinces,
)
from src.scrapers import aggregator as agg
from src.scrapers.models import (
    CONTRATO_FIJO_DISC, CONTRATO_INDEFINIDO, CONTRATO_PRACTICAS, CONTRATO_TEMPORAL,
    JORNADA_COMPLETA, JORNADA_ND, JORNADA_PARCIAL, JORNADA_TURNOS, MODALIDAD_HIBRIDO,
    MODALIDAD_REMOTO, STATUS_BLOCKED, STATUS_LINK_ONLY, STATUS_OK, JobOffer, SearchParams,
)
from src.scrapers.normalizer import (
    classify_contrato, classify_jornada, classify_modalidad, parse_date, parse_salary,
)
from src.scrapers.portals import PORTALS, build_deep_links, parse_indeed, parse_linkedin
from src.utils.exporter import to_csv_bytes, to_excel_bytes, to_pdf_bytes
from src.utils.translator import translate_pt_to_es

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Localizações
# ---------------------------------------------------------------------------
def test_territorial_structure():
    stats = count_summary()
    assert stats["regions"] == 19          # 17 CCAA + Ceuta + Melilla
    assert stats["provinces"] == 52        # 50 províncias + 2 cidades autônomas
    ine_codes = {info["ine"] for provs in SPAIN_LOCATIONS.values() for info in provs.values()}
    assert len(ine_codes) == 52 and ine_codes == {f"{i:02d}" for i in range(1, 53)}


def test_cascade_valenciana_alicante():
    assert get_provinces("Comunidad Valenciana") == ["Alicante", "Castellón", "Valencia"]
    cities = get_cities("Alicante")
    for c in ("Alicante", "Elche", "Benidorm", "Torrevieja", "Orihuela"):
        assert c in cities
    assert find_province_by_city("elche") == "Alicante"


# ---------------------------------------------------------------------------
# Tradução
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pt,es", [
    ("garçom", "camarero"),
    ("auxiliar de cozinha", "ayudante de cocina"),
    ("Engenheiro Civil", "ingeniero civil"),
    ("motorista de entregas meio período", "repartidor media jornada"),
])
def test_translate(pt, es):
    out, changed = translate_pt_to_es(pt)
    assert changed and out == es


def test_translate_keeps_unknown_terms():
    assert translate_pt_to_es("Python Developer") == ("Python Developer", False)


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Camarero media jornada fines de semana", JORNADA_PARCIAL),
    ("Contrato de 20 horas semanales", JORNADA_PARCIAL),
    ("Jornada de 30h/semana", JORNADA_PARCIAL),
    ("Administrativo jornada completa 40 horas semanales", JORNADA_COMPLETA),
    ("Operario de producción a turnos rotativos", JORNADA_TURNOS),
    ("Desarrollador Python", JORNADA_ND),
])
def test_classify_jornada(text, expected):
    assert classify_jornada(text) == expected


def test_classify_jornada_from_schema():
    assert classify_jornada("Dependiente", "PART_TIME") == JORNADA_PARCIAL
    assert classify_jornada("Dependiente", "FULL_TIME") == JORNADA_COMPLETA


def test_classify_contract_and_mode():
    assert classify_contrato("Contrato fijo discontinuo temporada") == CONTRATO_FIJO_DISC
    assert classify_contrato("Contrato indefinido") == CONTRATO_INDEFINIDO
    assert classify_contrato("Contrato temporal 6 meses") == CONTRATO_TEMPORAL
    assert classify_contrato("Becario en prácticas") == CONTRATO_PRACTICAS
    assert classify_modalidad("100% teletrabajo") == MODALIDAD_REMOTO
    assert classify_modalidad("Modelo híbrido 2 días oficina") == MODALIDAD_HIBRIDO


@pytest.mark.parametrize("text,jornada,expected", [
    ("18.000 - 22.000 € bruto/año", JORNADA_ND, (18000, 22000)),
    ("1.200 €/mes", JORNADA_ND, (14400, 14400)),
    ("10 €/hora", JORNADA_PARCIAL, (15600, 15600)),
    ("Salario: 25k-30k €", JORNADA_ND, (25000, 30000)),
    ("€30,000 - €40,000 per year", JORNADA_ND, (30000, 40000)),
    ("Jornada de 30h semanales", JORNADA_ND, (None, None)),
])
def test_parse_salary(text, jornada, expected):
    assert parse_salary(text, jornada) == expected


def test_parse_dates():
    assert parse_date("hace 2 días", NOW) == NOW - timedelta(days=2)
    assert parse_date("Hace 5 horas", NOW) == NOW - timedelta(hours=5)
    assert parse_date("3 days ago", NOW) == NOW - timedelta(days=3)
    assert parse_date("ayer", NOW) == NOW - timedelta(days=1)
    assert parse_date("2026-11-10", NOW) == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert parse_date("10/11/2026", NOW) == datetime(2026, 11, 10, tzinfo=timezone.utc)
    assert parse_date(1763290000000, NOW).year == 2025


# ---------------------------------------------------------------------------
# Deep links
# ---------------------------------------------------------------------------
def _params(**kw) -> SearchParams:
    base = dict(keyword="camarero", region="Comunidad Valenciana", province="Alicante",
                city="Benidorm", jornada=JORNADA_PARCIAL, date_range="7d", portals=list(PORTALS))
    base.update(kw)
    return SearchParams(**base)


def test_deep_links_all_portals():
    links = build_deep_links(_params())
    assert set(links) == set(PORTALS)
    assert all(u.startswith("https://") for u in links.values())
    assert "jt=parttime" in links["indeed"] and "fromage=7" in links["indeed"]
    assert "f_JT=P" in links["linkedin"] and "f_TPR=r604800" in links["linkedin"]
    assert "/ofertas-trabajo/alicante" in links["infojobs"]
    assert "en_alicante" in links["infoempleo"]
    assert "Benidorm" in links["jooble"]


def test_sector_keyword_used_when_empty():
    p = _params(keyword="", sector="Tecnologia / TI")
    assert "inform" in build_deep_links(p, ["indeed"])["indeed"]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------
LINKEDIN_HTML = """
<li><div class="base-card base-search-card job-search-card">
  <a class="base-card__full-link" href="https://es.linkedin.com/jobs/view/camarero-at-hotel-sol-123?refId=x"></a>
  <div class="base-search-card__info">
    <h3 class="base-search-card__title"> Camarero/a media jornada </h3>
    <h4 class="base-search-card__subtitle"><a>Hotel Sol</a></h4>
    <span class="job-search-card__location">Benidorm, Comunidad Valenciana, España</span>
    <span class="job-search-card__salary-info">1.100 € - 1.300 €/mes</span>
    <time class="job-search-card__listdate" datetime="2026-11-14">Hace 2 días</time>
  </div></div></li>
"""

JSONLD_HTML = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"JobPosting","title":"Recepcionista de hotel",
"hiringOrganization":{"@type":"Organization","name":"Meliá"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Torrevieja","addressRegion":"Alicante"}},
"baseSalary":{"@type":"MonetaryAmount","currency":"EUR","value":{"@type":"QuantitativeValue","minValue":18000,"maxValue":21000,"unitText":"YEAR"}},
"employmentType":"FULL_TIME","datePosted":"2026-11-15","url":"/oferta/recepcionista-123456",
"description":"<p>Contrato indefinido. Inglés alto.</p>"}]}
</script></head><body></body></html>"""

HEURISTIC_HTML = """
<ul>
 <li class="offer"><a href="/alicante/dependiente/of-i0a1b2c3d4e5f">Dependiente/a tienda de moda</a>
   <span class="company-name">Moda Levante SL</span><span class="location">Elche</span>
   <span>Jornada parcial 25 horas semanales · 900 €/mes · Hace 3 días</span></li>
 <li class="offer"><a href="/alicante/mozo/of-iffeeddccbbaa">Mozo de almacén</a>
   <span class="company-name">LogiSur</span><span class="location">Alicante</span>
   <span>Jornada completa · turnos · Contrato temporal</span></li>
 <li><a href="/empresa/xyz">Página de empresa (não é vaga)</a></li>
</ul>
"""

INDEED_HTML = (
    "<script>window.mosaic.providerData[\"mosaic-provider-jobcards\"]="
    + json.dumps({"metaData": {"mosaicProviderJobCardsModel": {"results": [{
        "jobkey": "abc123", "title": "Cajero/a", "company": "Supermercados X",
        "formattedLocation": "Orihuela, Alicante provincia", "snippet": "<li>Media jornada</li>",
        "salarySnippet": {"text": "9,50 € por hora"}, "pubDate": 1763200000000, "jobTypes": ["Media jornada"],
    }]}}})
    + ";\n</script>"
)


def test_parse_linkedin():
    jobs = parse_linkedin(LINKEDIN_HTML, _params())
    assert len(jobs) == 1
    j = agg.enrich(jobs[0], _params())
    assert j.title == "Camarero/a media jornada" and j.company == "Hotel Sol"
    assert j.city == "Benidorm" and j.province == "Alicante"
    assert j.jornada == JORNADA_PARCIAL
    assert (j.salary_min_annual, j.salary_max_annual) == (13200, 15600)
    assert j.url == "https://es.linkedin.com/jobs/view/camarero-at-hotel-sol-123"


def test_parse_jsonld():
    jobs = agg.parse_jsonld_jobs(JSONLD_HTML, PORTALS["randstad"])
    assert len(jobs) == 1
    j = agg.enrich(jobs[0], _params())
    assert j.company == "Meliá" and j.city == "Torrevieja" and j.province == "Alicante"
    assert j.jornada == JORNADA_COMPLETA and j.contrato == CONTRATO_INDEFINIDO
    assert (j.salary_min_annual, j.salary_max_annual) == (18000, 21000)
    assert j.url == "https://www.randstad.es/oferta/recepcionista-123456"


def test_parse_heuristic_links():
    jobs = agg.parse_link_heuristic(HEURISTIC_HTML, PORTALS["infojobs"])
    assert [j.title for j in jobs] == ["Dependiente/a tienda de moda", "Mozo de almacén"]
    first = agg.enrich(jobs[0], _params())
    assert first.company == "Moda Levante SL" and first.city == "Elche"
    assert first.jornada == JORNADA_PARCIAL and first.salary_min_annual == 10800
    second = agg.enrich(jobs[1], _params())
    assert second.jornada == JORNADA_COMPLETA and second.contrato == CONTRATO_TEMPORAL


def test_parse_indeed_json():
    jobs = parse_indeed(INDEED_HTML, _params())
    assert len(jobs) == 1
    j = agg.enrich(jobs[0], _params())
    assert j.url == "https://es.indeed.com/viewjob?jk=abc123"
    assert j.jornada == JORNADA_PARCIAL and j.province == "Alicante"
    assert j.salary_min_annual == pytest.approx(9.5 * 30 * 52)


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------
def _job(**kw) -> JobOffer:
    base = dict(title="Vaga", portal="Teste", url="https://x.es/1", province="Alicante",
                published=(NOW - timedelta(days=1)).isoformat())
    base.update(kw)
    return JobOffer(**base)


def test_filters():
    jobs = [
        _job(title="A", jornada=JORNADA_PARCIAL, salary_min_annual=15000, salary_max_annual=15000),
        _job(title="B", jornada=JORNADA_COMPLETA, salary_min_annual=25000, salary_max_annual=28000),
        _job(title="C", jornada=JORNADA_ND),
        _job(title="D", jornada=JORNADA_PARCIAL, published=(NOW - timedelta(days=20)).isoformat()),
        _job(title="E", jornada=JORNADA_PARCIAL, province="Madrid"),
    ]
    p = SearchParams(province="Alicante", jornada=JORNADA_PARCIAL, date_range="7d")
    assert [j.title for j in agg.apply_filters(jobs, p, NOW)] == ["A", "C"]
    p.include_unknown = False
    assert [j.title for j in agg.apply_filters(jobs, p, NOW)] == ["A"]
    p2 = SearchParams(province="Alicante", salary_min=20000, include_unknown=False)
    assert [j.title for j in agg.apply_filters(jobs, p2, NOW)] == ["B"]


def test_deduplicate_prefers_richer():
    a = _job(title="Camarero", company="Bar", city="Elche", salary_min_annual=None)
    b = _job(title="camarero", company="bar", city="Elche", url="https://y.es/2",
             salary_min_annual=15000, salary_max_annual=16000)
    out = agg.deduplicate([a, b])
    assert len(out) == 1 and out[0].salary_min_annual == 15000


# ---------------------------------------------------------------------------
# Pipeline completo com transporte simulado
# ---------------------------------------------------------------------------
def test_full_search_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if "linkedin" in host:
            return httpx.Response(200, text=LINKEDIN_HTML if request.url.params.get("start") == "0" else "")
        if "infojobs" in host:
            return httpx.Response(200, text=HEURISTIC_HTML)
        if "randstad" in host:
            return httpx.Response(200, text=JSONLD_HTML)
        if "indeed" in host:
            return httpx.Response(403, text="<title>Just a moment...</title> captcha")
        return httpx.Response(200, text="<html><body>sem vagas</body></html>")

    p = _params(jornada="all", date_range="30d")
    result = asyncio.run(agg.search_async(p, transport=httpx.MockTransport(handler)))
    status = {r.portal: r.status for r in result.portal_results}
    assert status["LinkedIn Jobs"] == STATUS_OK
    assert status["InfoJobs España"] == STATUS_OK
    assert status["Randstad España"] == STATUS_OK
    assert status["Indeed España"] == STATUS_BLOCKED
    assert status["Empléate (SEPE)"] == STATUS_LINK_ONLY
    assert len(result.jobs) == 4
    assert len(result.deep_links) == 10
    # Ida e volta pelo formato de cache
    again = agg.AggregatedResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert [j.id for j in again.jobs] == [j.id for j in result.jobs]


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------
def test_exports(tmp_path):
    jobs = [agg.enrich(j, _params()) for j in parse_linkedin(LINKEDIN_HTML, _params())]
    jobs.append(_job(title="Ingeniero — 30.000 € “senior”", summary="Texto com ñ, ç e €"))
    csv = to_csv_bytes(jobs).decode("utf-8-sig")
    assert "Camarero/a media jornada" in csv.splitlines()[1]

    xlsx = tmp_path / "out.xlsx"
    xlsx.write_bytes(to_excel_bytes(jobs))
    ws = load_workbook(xlsx).active
    assert ws["A4"].value == "Camarero/a media jornada"
    assert ws.cell(row=4, column=13).hyperlink is not None

    pdf = to_pdf_bytes(jobs, {"Localização": "Benidorm, Alicante"})
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000
