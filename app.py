"""
EmpleoRadar España — painel agregador e buscador de vagas de trabalho na Espanha.

Execute localmente com:
    streamlit run app.py
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data.spain_locations import (
    ALL_CITIES_LABEL, ALL_PROVINCES_LABEL, ALL_REGIONS_LABEL, count_summary,
    find_province_by_city, get_cities, get_provinces, get_region_of_province, get_regions,
)
from src.scrapers.aggregator import (
    AggregatedResult, apply_filters, deduplicate, search, sort_jobs,
)
from src.scrapers.models import (
    CONTRATO_OPTIONS, DATE_FILTER_OPTIONS, JORNADA_BADGES, JORNADA_COMPLETA,
    JORNADA_FILTER_OPTIONS, JORNADA_ND, JORNADA_PARCIAL, JORNADA_TURNOS, MODALIDAD_ND,
    MODALIDAD_OPTIONS, SECTOR_OPTIONS, STATUS_BLOCKED, STATUS_ERROR, STATUS_LABELS,
    STATUS_OK, CONTRATO_ND, JobOffer, SearchParams,
)
from src.scrapers.normalizer import format_relative, format_salary
from src.scrapers.portals import PORTALS, build_deep_links
from src.utils.exporter import export_filename, to_csv_bytes, to_excel_bytes, to_pdf_bytes
from src.utils.translator import translate_pt_to_es

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="EmpleoRadar España",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "EmpleoRadar España — agregador de vagas de trabalho na Espanha."},
)

RED, RED_DARK, GOLD, GOLD_DARK = "#AA151B", "#8C1116", "#F1BF00", "#D4A017"
GRAPHITE, SLATE, BORDER, ICE = "#1E293B", "#64748B", "#E2E8F0", "#F8F9FA"
CARDS_PER_PAGE = 12

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, select {{
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}}
.stApp {{ background: {ICE}; color: {GRAPHITE}; }}
[data-testid="stHeader"] {{ background: rgba(248,249,250,0.85); backdrop-filter: blur(6px); }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1480px; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] .sidebar-brand {{
    display:flex; align-items:center; gap:.6rem; padding:.2rem 0 .8rem 0;
    border-bottom: 1px solid {BORDER}; margin-bottom: .6rem;
}}
.sidebar-brand .logo {{
    width:34px; height:34px; border-radius:9px; background:{RED}; color:#fff;
    display:flex; align-items:center; justify-content:center; font-weight:800;
    box-shadow: inset 0 -3px 0 {GOLD};
}}
.sidebar-brand .name {{ font-weight:800; font-size:1.02rem; color:{GRAPHITE}; line-height:1.1; }}
.sidebar-brand .tag {{ font-size:.72rem; color:{SLATE}; }}
.side-title {{
    font-size:.72rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
    color:{SLATE}; margin: 1.1rem 0 .35rem 0; padding-left:.5rem; border-left:3px solid {GOLD};
}}
[data-baseweb="select"] > div, [data-baseweb="input"], .stTextInput input, .stNumberInput input {{
    border-color: {BORDER} !important; background:#FFFFFF !important;
}}
[data-baseweb="tag"] {{ background: #FBEAEA !important; color: {RED_DARK} !important; }}
[data-baseweb="tag"] svg {{ fill: {RED_DARK} !important; }}

/* Botões */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{
    border-radius: 9px !important; font-weight: 600 !important; border: 1px solid {BORDER} !important;
    transition: all .15s ease;
}}
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {{
    background: {RED} !important; border-color: {RED} !important; color: #fff !important;
}}
.stButton > button[kind="primary"]:hover, .stButton > button[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:focus, .stButton > button[kind="primary"]:active,
.stButton > button[data-testid="stBaseButton-primary"]:focus, .stButton > button[data-testid="stBaseButton-primary"]:active {{
    background: {RED_DARK} !important; border-color: {RED_DARK} !important; color: #fff !important;
}}
.stButton > button[kind="primary"] p, .stButton > button[data-testid="stBaseButton-primary"] p {{ color: #fff !important; }}
.stLinkButton > a:hover, .stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):hover, .stDownloadButton > button:hover {{
    border-color: {RED} !important; color: {RED} !important;
}}

/* Cabeçalho institucional */
.hero {{
    background: #FFFFFF; border: 1px solid {BORDER}; border-radius: 16px;
    padding: 1.5rem 1.8rem 1.3rem 1.8rem; position: relative; overflow: hidden;
    box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 8px 24px rgba(15,23,42,.04);
}}
.hero::before {{
    content:""; position:absolute; left:0; top:0; bottom:0; width:6px;
    background: linear-gradient(180deg, {RED} 0 25%, {GOLD} 25% 75%, {RED} 75% 100%);
}}
.hero .eyebrow {{ font-size:.75rem; font-weight:700; letter-spacing:.12em; color:{RED}; text-transform:uppercase; }}
.hero h1 {{ font-size:2.05rem; font-weight:800; color:{GRAPHITE}; margin:.15rem 0 .25rem 0; padding:0; letter-spacing:-.02em; }}
.hero h1 span {{ color:{RED}; }}
.hero p {{ color:{SLATE}; margin:0; font-size:.98rem; }}

.kpi-grid {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .9rem; margin: 1rem 0 .4rem 0; }}
@media (max-width: 900px) {{ .kpi-grid {{ grid-template-columns: repeat(2, minmax(0,1fr)); }} }}
.kpi {{
    background:#FFFFFF; border:1px solid {BORDER}; border-radius:14px; padding: .95rem 1.1rem;
    box-shadow: 0 1px 2px rgba(15,23,42,.04); border-top: 3px solid {RED};
}}
.kpi.gold {{ border-top-color: {GOLD}; }}
.kpi .label {{ font-size:.72rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:{SLATE}; }}
.kpi .value {{ font-size:1.65rem; font-weight:800; color:{GRAPHITE}; margin-top:.15rem; letter-spacing:-.02em; }}
.kpi .hint {{ font-size:.78rem; color:{SLATE}; margin-top:.1rem; }}

.search-summary {{
    background:#FFFFFF; border:1px solid {BORDER}; border-left: 4px solid {GOLD};
    border-radius: 10px; padding:.65rem 1rem; font-size:.9rem; color:{GRAPHITE}; margin:.5rem 0 1rem 0;
}}
.search-summary b {{ color:{RED}; }}

/* Abas */
.stTabs [data-baseweb="tab-list"] {{ gap:.25rem; border-bottom: 1px solid {BORDER}; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; color:{SLATE}; padding: .55rem .9rem; }}
.stTabs [aria-selected="true"] {{ color:{RED} !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:{RED} !important; }}

/* Cards de vagas (st.container(border=True)) */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background:#FFFFFF; border-radius: 14px !important; border-color:{BORDER} !important;
    box-shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 14px rgba(15,23,42,.035);
}}
.job-top {{ display:flex; justify-content:space-between; align-items:center; gap:.5rem; margin-bottom:.35rem; }}
.portal-chip {{
    font-size:.7rem; font-weight:700; color:{RED}; background:#FBEAEA; border-radius:999px;
    padding:.15rem .6rem; letter-spacing:.02em;
}}
.job-date {{ font-size:.75rem; color:{SLATE}; white-space:nowrap; }}
.job-title {{ font-size:1.04rem; font-weight:700; color:{GRAPHITE}; margin:.1rem 0 .25rem 0; line-height:1.3; }}
.job-meta {{ font-size:.84rem; color:{SLATE}; margin:.05rem 0; }}
.badges {{ display:flex; flex-wrap:wrap; gap:.35rem; margin:.55rem 0 .45rem 0; }}
.badge {{ font-size:.72rem; font-weight:600; padding:.18rem .55rem; border-radius:6px; border:1px solid {BORDER}; color:{GRAPHITE}; background:{ICE}; }}
.badge.b-parcial {{ background:#FFF7D6; border-color:{GOLD}; color:#7A5B00; }}
.badge.b-completa {{ background:#FBEAEA; border-color:#E8B4B6; color:{RED_DARK}; }}
.badge.b-turnos {{ background:#EEF2F7; border-color:#CBD5E1; color:#334155; }}
.badge.b-nd {{ color:{SLATE}; }}
.job-salary {{ font-size:.9rem; font-weight:700; color:{GRAPHITE}; margin:.2rem 0; }}
.job-salary.muted {{ color:{SLATE}; font-weight:500; }}
.job-summary {{ font-size:.83rem; color:#475569; margin:.3rem 0 .2rem 0; line-height:1.45; min-height: 2.4em; }}

/* Cards de portais */
.portal-card-title {{ font-weight:700; font-size:.98rem; color:{GRAPHITE}; }}
.portal-card-desc {{ font-size:.8rem; color:{SLATE}; min-height:2.3em; margin:.15rem 0 .4rem 0; }}
.status-pill {{ font-size:.72rem; font-weight:600; padding:.12rem .5rem; border-radius:999px; background:{ICE}; border:1px solid {BORDER}; }}

.empty-state {{
    background:#FFFFFF; border:1px dashed #CBD5E1; border-radius:14px; padding:2rem; text-align:center; color:{SLATE};
}}
.empty-state h3 {{ color:{GRAPHITE}; margin-bottom:.3rem; }}
.footer-note {{ text-align:center; font-size:.75rem; color:{SLATE}; margin-top:2.5rem; }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Estado e utilitários
# ---------------------------------------------------------------------------
def init_state() -> None:
    defaults: Dict[str, Any] = {
        "favorites": {},        # id -> dict da vaga
        "result": None,         # AggregatedResult.to_dict()
        "fetch_signature": None,
        "searched_params": None,
        "card_page": 1,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def safe_url(url: str) -> str:
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else ""


def load_secrets() -> Dict[str, str]:
    """Lê credenciais opcionais de st.secrets sem quebrar quando não existem."""
    mapping = {
        "INFOJOBS_CLIENT_ID": "infojobs_client_id",
        "INFOJOBS_CLIENT_SECRET": "infojobs_client_secret",
        "JOOBLE_API_KEY": "jooble_api_key",
    }
    out: Dict[str, str] = {}
    try:
        for src_key, dst_key in mapping.items():
            if src_key in st.secrets and str(st.secrets[src_key]).strip():
                out[dst_key] = str(st.secrets[src_key]).strip()
    except Exception:  # noqa: BLE001 — sem secrets.toml
        return {}
    return out


@st.cache_data(ttl=900, show_spinner=False, max_entries=64)
def run_search_cached(params_json: str, secrets_items: tuple) -> Dict[str, Any]:
    params = SearchParams(**json.loads(params_json))
    return search(params, dict(secrets_items)).to_dict()


def fetch_signature(p: SearchParams) -> str:
    """Campos que exigem nova coleta; os demais filtros são aplicados localmente."""
    return json.dumps({
        "kw": p.effective_keyword, "region": p.region, "province": p.province, "city": p.city,
        "date": p.date_range, "portals": sorted(p.portals), "jornada": p.jornada,
        "mod": sorted(p.modalidades), "max": p.max_per_portal,
    }, sort_keys=True, ensure_ascii=False)


def toggle_favorite(job: Dict[str, Any]) -> None:
    favs = st.session_state["favorites"]
    if job["id"] in favs:
        favs.pop(job["id"])
    else:
        favs[job["id"]] = job


# ---------------------------------------------------------------------------
# Barra lateral (filtros)
# ---------------------------------------------------------------------------
def sidebar_filters() -> tuple[SearchParams, bool, Optional[str]]:
    with st.sidebar:
        st.markdown(
            """<div class="sidebar-brand"><div class="logo">ER</div>
            <div><div class="name">EmpleoRadar</div><div class="tag">Buscador de vagas · España</div></div></div>""",
            unsafe_allow_html=True,
        )

        # ---------------- Localização ----------------
        st.markdown('<div class="side-title">📍 Localização</div>', unsafe_allow_html=True)
        region = st.selectbox("Comunidade Autônoma", [ALL_REGIONS_LABEL] + get_regions(), key="f_region")
        region_val = None if region == ALL_REGIONS_LABEL else region

        provinces = get_provinces(region_val)
        prov_options = [ALL_PROVINCES_LABEL] + provinces
        if st.session_state.get("f_province") not in prov_options:
            st.session_state["f_province"] = ALL_PROVINCES_LABEL
        province = st.selectbox("Província", prov_options, key="f_province")
        province_val = None if province == ALL_PROVINCES_LABEL else province

        city_val: Optional[str] = None
        if province_val:
            city_options = [ALL_CITIES_LABEL] + get_cities(province_val)
            if st.session_state.get("f_city") not in city_options:
                st.session_state["f_city"] = ALL_CITIES_LABEL
            city = st.selectbox("Cidade / Município", city_options, key="f_city")
            city_val = None if city == ALL_CITIES_LABEL else city
        free_city = st.text_input("Outro município (texto livre)", key="f_city_free",
                                  placeholder="Ex.: Callosa d'en Sarrià")
        if free_city.strip():
            city_val = free_city.strip()
            if not province_val:
                province_val = find_province_by_city(city_val)
        if province_val and not region_val:
            region_val = get_region_of_province(province_val)

        # ---------------- Jornada ----------------
        st.markdown('<div class="side-title">🕒 Carga horária / Jornada</div>', unsafe_allow_html=True)
        jornada = st.radio("Regime de jornada", list(JORNADA_FILTER_OPTIONS),
                           format_func=lambda k: JORNADA_FILTER_OPTIONS[k], key="f_jornada",
                           label_visibility="collapsed")

        # ---------------- Pesquisa ----------------
        st.markdown('<div class="side-title">🔎 Pesquisa</div>', unsafe_allow_html=True)
        raw_kw = st.text_input("Palavra-chave / Cargo", key="f_kw",
                               placeholder="Ex.: camarero, garçom, engenheiro civil")
        auto_translate = st.toggle("Traduzir PT → ES automaticamente", value=True, key="f_translate")
        sector = st.selectbox("Área / Setor", list(SECTOR_OPTIONS), key="f_sector")
        modalidades = st.multiselect("Modalidade de trabalho", MODALIDAD_OPTIONS,
                                     default=MODALIDAD_OPTIONS, key="f_mod")
        contratos = st.multiselect("Tipo de contrato", CONTRATO_OPTIONS, key="f_contract",
                                   placeholder="Todos os contratos")
        salary_min = st.slider("Salário mínimo (€/ano bruto)", 0, 80_000, 0, step=1_000,
                               key="f_salary", format="%d €")
        date_range = st.selectbox("Data de publicação", list(DATE_FILTER_OPTIONS),
                                  format_func=lambda k: DATE_FILTER_OPTIONS[k], index=2, key="f_date")

        # ---------------- Portais ----------------
        st.markdown('<div class="side-title">🌐 Portais</div>', unsafe_allow_html=True)
        portals = st.multiselect("Portais a consultar", list(PORTALS), default=list(PORTALS),
                                 format_func=lambda k: PORTALS[k].name, key="f_portals")
        specialized = [p.name for p in PORTALS.values() if p.sectors and sector in p.sectors]
        if specialized:
            st.caption(f"💡 Para **{sector}**, priorize: {', '.join(specialized)}.")

        with st.expander("⚙️ Opções avançadas"):
            include_unknown = st.checkbox(
                "Incluir vagas sem jornada/salário/data informados", value=True, key="f_unknown",
                help="Muitas vagas não declaram jornada ou salário. Desmarque para ver apenas vagas com o dado explícito.")
            max_per_portal = st.slider("Máximo de vagas por portal", 10, 50, 30, step=5, key="f_max")

        submitted = st.button("🔎  Buscar vagas", type="primary", width="stretch")
        stats = count_summary()
        st.caption(f"Base territorial: {stats['regions']} comunidades/cidades autônomas · "
                   f"{stats['provinces']} províncias · {stats['cities']} municípios.")

    # Tradução
    translation_note = None
    keyword = raw_kw.strip()
    if keyword and auto_translate:
        translated, changed = translate_pt_to_es(keyword)
        if changed:
            translation_note = f"“{keyword}” → “{translated}”"
            keyword = translated

    params = SearchParams(
        keyword=keyword, original_keyword=raw_kw.strip(), region=region_val, province=province_val,
        city=city_val, jornada=jornada, sector=sector, modalidades=modalidades, contratos=contratos,
        salary_min=int(salary_min), date_range=date_range, portals=portals or list(PORTALS),
        include_unknown=include_unknown, max_per_portal=int(max_per_portal),
    )
    return params, submitted, translation_note


# ---------------------------------------------------------------------------
# Componentes visuais
# ---------------------------------------------------------------------------
def render_header(jobs: List[JobOffer], has_result: bool) -> None:
    salaries = [j.salary_mid for j in jobs if j.salary_mid]
    avg = f"{sum(salaries) / len(salaries):,.0f} €".replace(",", ".") if salaries else "—"
    parcial = sum(1 for j in jobs if j.jornada == JORNADA_PARCIAL)
    completa = sum(1 for j in jobs if j.jornada == JORNADA_COMPLETA)
    total = str(len(jobs)) if has_result else "—"
    sal_hint = f"Base: {len(salaries)} vagas com salário" if salaries else "Sem salários declarados"
    st.markdown(
        f"""
        <div class="hero">
          <div class="eyebrow">Painel de vagas · Reino de España</div>
          <h1>Empleo<span>Radar</span> España</h1>
          <p>Agregador inteligente de vagas dos 10 principais portais de emprego da Espanha,
             com filtros territoriais oficiais e foco em jornada parcial (30h) e completa (40h).</p>
        </div>
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Vagas encontradas</div><div class="value">{total}</div>
               <div class="hint">Após filtros e remoção de duplicadas</div></div>
          <div class="kpi gold"><div class="label">Média salarial estimada</div><div class="value">{avg}</div>
               <div class="hint">{esc(sal_hint)} · €/ano bruto</div></div>
          <div class="kpi"><div class="label">Parcial (≤30h) vs Completa (40h)</div>
               <div class="value">{parcial if has_result else '—'} <span style="color:{SLATE};font-weight:500">/</span> {completa if has_result else '—'}</div>
               <div class="hint">Vagas com jornada identificada</div></div>
          <div class="kpi gold"><div class="label">Favoritas salvas</div>
               <div class="value">{len(st.session_state['favorites'])}</div>
               <div class="hint">Exportáveis em CSV, Excel e PDF</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def search_summary_html(p: SearchParams, note: Optional[str]) -> str:
    kw = p.effective_keyword or "todas as vagas"
    loc = ", ".join(x for x in (p.city, p.province, p.region) if x) or "toda a Espanha"
    jornada = JORNADA_FILTER_OPTIONS[p.jornada].split(" (")[0]
    extra = f" · 🔁 Tradução automática: {esc(note)}" if note else ""
    return (f'<div class="search-summary">Buscando <b>{esc(kw)}</b> em <b>{esc(loc)}</b> · '
            f'{esc(jornada)} · {esc(DATE_FILTER_OPTIONS[p.date_range])}{extra}</div>')


def jornada_badge(code: str) -> str:
    cls = {JORNADA_PARCIAL: "b-parcial", JORNADA_COMPLETA: "b-completa",
           JORNADA_TURNOS: "b-turnos"}.get(code, "b-nd")
    return f'<span class="badge {cls}">{esc(JORNADA_BADGES.get(code, code))}</span>'


def render_job_card(job: JobOffer, key_prefix: str) -> None:
    with st.container(border=True):
        location = ", ".join(x for x in dict.fromkeys([job.city, job.province]) if x) or job.location_raw or "Espanha"
        salary = format_salary(job.salary_min_annual, job.salary_max_annual)
        salary_html = (f'<div class="job-salary">💶 {esc(salary)}</div>' if salary else
                       f'<div class="job-salary muted">💶 {esc(job.salary_text) if job.salary_text else "Salário não informado"}</div>')
        badges = [jornada_badge(job.jornada)]
        if job.modalidad != MODALIDAD_ND:
            badges.append(f'<span class="badge">{esc(job.modalidad)}</span>')
        if job.contrato != CONTRATO_ND:
            badges.append(f'<span class="badge">{esc(job.contrato)}</span>')
        summary = esc(job.summary[:220] + ("…" if len(job.summary) > 220 else "")) if job.summary else ""
        st.markdown(
            f"""
            <div class="job-top"><span class="portal-chip">{esc(job.portal)}</span>
                 <span class="job-date">🕒 {esc(format_relative(job.published))}</span></div>
            <div class="job-title">{esc(job.title)}</div>
            <div class="job-meta">🏢 {esc(job.company) or "Empresa não informada"}</div>
            <div class="job-meta">📍 {esc(location)}</div>
            <div class="badges">{''.join(badges)}</div>
            {salary_html}
            <div class="job-summary">{summary}</div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        url = safe_url(job.url)
        if url:
            c1.link_button("Ver vaga original ↗", url, width="stretch")
        is_fav = job.id in st.session_state["favorites"]
        c2.button("★ Remover" if is_fav else "☆ Salvar", key=f"{key_prefix}_{job.id}",
                  on_click=toggle_favorite, args=(job.to_dict(),), width="stretch")


def empty_state(title: str, text: str) -> None:
    st.markdown(f'<div class="empty-state"><h3>{esc(title)}</h3><p>{esc(text)}</p></div>',
                unsafe_allow_html=True)


def render_cards_tab(jobs: List[JobOffer], has_result: bool) -> None:
    if not has_result:
        empty_state("Pronto para buscar",
                    "Defina localização, jornada e palavra-chave na barra lateral e clique em “Buscar vagas”. "
                    "Os links diretos de cada portal já estão disponíveis na aba “Links diretos”.")
        return
    if not jobs:
        empty_state("Nenhuma vaga coletada com esses filtros",
                    "Alguns portais bloqueiam coleta automática em servidores na nuvem. "
                    "Use a aba “Links diretos” para abrir a busca exata em cada portal com 1 clique.")
        return

    c1, c2, c3 = st.columns([2, 2, 1])
    order = c1.selectbox("Ordenar por", ["Mais recentes", "Maior salário"], key="card_order")
    portal_filter = c2.multiselect("Filtrar portal", sorted({j.portal for j in jobs}), key="card_portal",
                                   placeholder="Todos os portais")
    view = sort_jobs(jobs, "salary" if order == "Maior salário" else "date")
    if portal_filter:
        view = [j for j in view if j.portal in portal_filter]
    pages = max(1, math.ceil(len(view) / CARDS_PER_PAGE))
    if st.session_state.get("card_page", 1) > pages:
        st.session_state["card_page"] = pages
    page = int(c3.number_input("Página", min_value=1, max_value=pages, step=1, key="card_page"))
    st.caption(f"Exibindo {min(len(view), (page - 1) * CARDS_PER_PAGE + 1)}–"
               f"{min(len(view), page * CARDS_PER_PAGE)} de {len(view)} vagas")

    chunk = view[(page - 1) * CARDS_PER_PAGE: page * CARDS_PER_PAGE]
    for i in range(0, len(chunk), 3):
        cols = st.columns(3)
        for col, job in zip(cols, chunk[i:i + 3]):
            with col:
                render_job_card(job, "card")


def jobs_table(jobs: List[JobOffer]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Cargo": j.title,
        "Empresa": j.company,
        "Cidade": j.city,
        "Província": j.province,
        "Portal": j.portal,
        "Jornada": JORNADA_BADGES.get(j.jornada, j.jornada),
        "Modalidade": j.modalidad,
        "Contrato": j.contrato,
        "Salário mín. (€/ano)": j.salary_min_annual,
        "Salário máx. (€/ano)": j.salary_max_annual,
        "Publicada em": pd.to_datetime(j.published, utc=True, errors="coerce") if j.published else pd.NaT,
        "Link": safe_url(j.url),
    } for j in jobs])


def render_export_buttons(jobs: List[JobOffer], prefix: str, p: SearchParams, key: str) -> None:
    if not jobs:
        return
    filters = {
        "Palavra-chave": p.effective_keyword or "(todas)",
        "Localização": ", ".join(x for x in (p.city, p.province, p.region) if x) or "Toda a Espanha",
        "Jornada": JORNADA_FILTER_OPTIONS[p.jornada],
        "Modalidade": ", ".join(p.modalidades) if p.modalidades else "Todas",
        "Contrato": ", ".join(p.contratos) if p.contratos else "Todos",
        "Salário mínimo": f"{p.salary_min:,} EUR/ano".replace(",", ".") if p.salary_min else "",
        "Publicação": DATE_FILTER_OPTIONS[p.date_range],
    }
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇️ CSV", to_csv_bytes(jobs), export_filename(prefix, "csv"), "text/csv",
                       width="stretch", key=f"{key}_csv")
    c2.download_button("⬇️ Excel (.xlsx)", to_excel_bytes(jobs), export_filename(prefix, "xlsx"),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch", key=f"{key}_xlsx")
    c3.download_button("⬇️ Relatório PDF", to_pdf_bytes(jobs, filters), export_filename(prefix, "pdf"),
                       "application/pdf", width="stretch", key=f"{key}_pdf")


def render_table_tab(jobs: List[JobOffer], has_result: bool, p: SearchParams) -> None:
    if not has_result or not jobs:
        empty_state("Sem dados para a tabela", "Faça uma busca para preencher a tabela analítica.")
        return
    order = st.radio("Ordenação", ["Data de publicação", "Salário"], horizontal=True, key="table_order")
    data = jobs_table(sort_jobs(jobs, "salary" if order == "Salário" else "date"))
    st.dataframe(
        data, width="stretch", hide_index=True, height=520,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="Abrir ↗"),
            "Salário mín. (€/ano)": st.column_config.NumberColumn(format="%.0f €"),
            "Salário máx. (€/ano)": st.column_config.NumberColumn(format="%.0f €"),
            "Publicada em": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm"),
            "Cargo": st.column_config.TextColumn(width="large"),
        },
    )
    st.markdown("**Exportar resultados filtrados**")
    render_export_buttons(jobs, "empleoradar_resultados", p, "res")


def _style_fig(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=50, b=10),
        font=dict(family="Inter, sans-serif", color=GRAPHITE, size=12),
        title_font=dict(size=15, color=GRAPHITE), paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        showlegend=False,
    )
    fig.update_xaxes(gridcolor=BORDER, zeroline=False)
    fig.update_yaxes(gridcolor=BORDER, zeroline=False)
    return fig


def render_analysis_tab(jobs: List[JobOffer], has_result: bool) -> None:
    if not has_result or not jobs:
        empty_state("Sem dados para análise", "Os gráficos aparecem após uma busca com resultados.")
        return
    df = pd.DataFrame([{"portal": j.portal, "cidade": j.city or j.province or "Não informada",
                        "jornada": JORNADA_BADGES.get(j.jornada, j.jornada), "salario": j.salary_mid}
                       for j in jobs])
    c1, c2 = st.columns(2)
    with c1:
        by_portal = df.groupby("portal").size().reset_index(name="vagas").sort_values("vagas")
        fig = px.bar(by_portal, x="vagas", y="portal", orientation="h", title="Vagas por portal",
                     text="vagas", color_discrete_sequence=[RED])
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(_style_fig(fig), width="stretch")
    with c2:
        order = [JORNADA_BADGES[k] for k in (JORNADA_PARCIAL, JORNADA_COMPLETA, JORNADA_TURNOS, JORNADA_ND)]
        by_j = df.groupby("jornada").size().reindex(order).dropna().reset_index(name="vagas")
        colors = {JORNADA_BADGES[JORNADA_PARCIAL]: GOLD, JORNADA_BADGES[JORNADA_COMPLETA]: RED,
                  JORNADA_BADGES[JORNADA_TURNOS]: "#475569", JORNADA_BADGES[JORNADA_ND]: "#CBD5E1"}
        fig = go.Figure(go.Pie(labels=by_j["jornada"], values=by_j["vagas"], hole=.58,
                               marker=dict(colors=[colors[x] for x in by_j["jornada"]],
                                           line=dict(color="#FFFFFF", width=2)),
                               textinfo="percent", sort=False))
        fig.update_layout(title="Proporção por jornada (30h × 40h)")
        fig = _style_fig(fig)
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.05))
        st.plotly_chart(fig, width="stretch")

    c3, c4 = st.columns(2)
    with c3:
        by_city = df.groupby("cidade").size().reset_index(name="vagas").sort_values("vagas").tail(12)
        fig = px.bar(by_city, x="vagas", y="cidade", orientation="h", title="Top cidades",
                     text="vagas", color_discrete_sequence=[GOLD_DARK])
        fig.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(_style_fig(fig, 380), width="stretch")
    with c4:
        sal = df.dropna(subset=["salario"])
        if len(sal) >= 2:
            fig = px.box(sal, x="jornada", y="salario", points="all", title="Salário estimado por jornada (€/ano)",
                         color="jornada", color_discrete_map=colors)
            st.plotly_chart(_style_fig(fig, 380), width="stretch")
        else:
            st.info("Poucas vagas com salário declarado para montar a distribuição salarial.")


def render_links_tab(p: SearchParams, result: Optional[AggregatedResult]) -> None:
    st.markdown("Links de busca **pré-filtrados** (palavra-chave, localização e jornada) para abrir "
                "diretamente em cada portal — funcionam mesmo quando o portal bloqueia coleta automática.")
    links = build_deep_links(p, p.portals)
    statuses = {r.portal: r for r in result.portal_results} if result else {}
    keys = list(links)
    for i in range(0, len(keys), 3):
        cols = st.columns(3)
        for col, k in zip(cols, keys[i:i + 3]):
            portal = PORTALS[k]
            r = statuses.get(portal.name)
            pill = (f'<span class="status-pill">{esc(STATUS_LABELS.get(r.status, r.status))}'
                    f'{" · " + str(len(r.jobs)) + (" vaga" if len(r.jobs) == 1 else " vagas") if r.status == STATUS_OK else ""}</span>') if r else ""
            with col:
                with st.container(border=True):
                    st.markdown(f'<div class="portal-card-title">{esc(portal.name)} {pill}</div>'
                                f'<div class="portal-card-desc">{esc(portal.description)}</div>',
                                unsafe_allow_html=True)
                    st.link_button(f"Abrir busca no {portal.name} ↗", links[k], width="stretch")


def render_favorites_tab(p: SearchParams) -> None:
    favs = [JobOffer.from_dict(d) for d in st.session_state["favorites"].values()]
    if not favs:
        empty_state("Nenhuma vaga salva", "Clique em “☆ Salvar” nos cards para montar sua lista de favoritas.")
        return
    st.markdown(f"**{len(favs)} vaga(s) salva(s) nesta sessão**")
    render_export_buttons(favs, "empleoradar_favoritas", p, "fav")
    if st.button("🗑️ Limpar favoritas", key="clear_favs"):
        st.session_state["favorites"] = {}
        st.rerun()
    for i in range(0, len(favs), 3):
        cols = st.columns(3)
        for col, job in zip(cols, favs[i:i + 3]):
            with col:
                render_job_card(job, "fav")


def render_status_tab(result: Optional[AggregatedResult]) -> None:
    if not result:
        empty_state("Nenhuma coleta executada", "O status por portal aparece após a primeira busca.")
        return
    df = pd.DataFrame([{
        "Portal": r.portal, "Status": STATUS_LABELS.get(r.status, r.status), "Vagas": len(r.jobs),
        "Tempo (s)": r.elapsed, "Detalhe": r.message, "Link direto": r.deep_link,
    } for r in result.portal_results])
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"Link direto": st.column_config.LinkColumn(display_text="Abrir ↗")})
    blocked = sum(1 for r in result.portal_results if r.status in (STATUS_BLOCKED, STATUS_ERROR))
    if blocked:
        st.info(f"{blocked} portal(is) bloquearam ou não responderam à coleta automática — isso é esperado em "
                "servidores de nuvem (Streamlit Cloud). Os links diretos continuam funcionando normalmente. "
                "Para InfoJobs e Jooble, configure as APIs oficiais gratuitas em *Secrets* (veja o README).")
    st.caption(f"Coleta realizada em {pd.to_datetime(result.searched_at).strftime('%d/%m/%Y %H:%M')} UTC · "
               f"resultados em cache por 15 minutos.")


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------
def main() -> None:
    init_state()
    params, submitted, translation_note = sidebar_filters()
    secrets = load_secrets()

    if submitted:
        with st.spinner(f"Consultando {len(params.portals)} portais em paralelo…"):
            st.session_state["result"] = run_search_cached(
                params.cache_key(), tuple(sorted(secrets.items())))
        st.session_state["fetch_signature"] = fetch_signature(params)
        st.session_state["card_page"] = 1

    result = AggregatedResult.from_dict(st.session_state["result"]) if st.session_state["result"] else None
    jobs: List[JobOffer] = []
    if result:
        # Filtros "leves" (jornada, contrato, salário...) são reaplicados localmente sem nova coleta
        all_jobs = deduplicate([j for r in result.portal_results for j in r.jobs])
        jobs = sort_jobs(apply_filters(all_jobs, params))

    render_header(jobs, result is not None)
    st.markdown(search_summary_html(params, translation_note), unsafe_allow_html=True)
    if result and st.session_state["fetch_signature"] != fetch_signature(params):
        st.warning("Você alterou palavra-chave, localização, jornada, modalidade, portais ou período. Clique em **Buscar vagas** "
                   "para atualizar a coleta (os demais filtros já foram aplicados).", icon="🔄")

    fav_count = len(st.session_state["favorites"])
    tabs = st.tabs(["🗂️ Cards detalhados", "📋 Tabela analítica", "📈 Análise rápida",
                    "🔗 Links diretos", f"⭐ Favoritas ({fav_count})", "🛰️ Status da coleta"])
    with tabs[0]:
        render_cards_tab(jobs, result is not None)
    with tabs[1]:
        render_table_tab(jobs, result is not None, params)
    with tabs[2]:
        render_analysis_tab(jobs, result is not None)
    with tabs[3]:
        render_links_tab(params, result)
    with tabs[4]:
        render_favorites_tab(params)
    with tabs[5]:
        render_status_tab(result)

    st.markdown(
        '<div class="footer-note">EmpleoRadar España · Os dados pertencem aos respectivos portais; '
        'confirme sempre as condições na vaga original. Estimativas salariais anualizadas '
        '(mensal × 12; por hora × horas semanais × 52).</div>',
        unsafe_allow_html=True,
    )


main()
