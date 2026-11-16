"""
Normalização de dados das vagas: classifica jornada, modalidade e contrato a
partir do texto, converte salários para €/ano bruto e interpreta datas
relativas ("hace 2 días", "3 days ago", ISO 8601...).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from .models import (
    CONTRATO_AUTONOMO, CONTRATO_FIJO_DISC, CONTRATO_INDEFINIDO, CONTRATO_ND,
    CONTRATO_PRACTICAS, CONTRATO_TEMPORAL, JORNADA_COMPLETA, JORNADA_ND,
    JORNADA_PARCIAL, JORNADA_TURNOS, MODALIDAD_HIBRIDO, MODALIDAD_ND,
    MODALIDAD_PRESENCIAL, MODALIDAD_REMOTO,
)


def norm(text: Optional[str]) -> str:
    """Minúsculas, sem acentos, espaços colapsados."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def clean_text(text: Optional[str], limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()
    if limit and len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        return cut.rstrip(",.;:-") + "…"
    return text


# ---------------------------------------------------------------------------
# Jornada
# ---------------------------------------------------------------------------
_HOURS_RE = re.compile(
    r"(\d{1,2})(?:[.,]\d)?\s*(?:h\b|hrs?\b|horas?)\s*(?:/|a la|por|semanales|semana|weekly|per week|/sem)",
)
_HOURS_RE_ALT = re.compile(r"(?:jornada|contrato|horario)\s+de\s+(\d{1,2})\s*(?:h\b|horas)")

_PARCIAL_KW = (
    "media jornada", "jornada parcial", "tiempo parcial", "part time", "part-time",
    "parttime", "jornada reducida", "jornada de manana", "jornada de tarde",
    "solo fines de semana", "fines de semana", "fin de semana", "por horas",
    "a tiempo parcial", "parcial",
)
_COMPLETA_KW = (
    "jornada completa", "tiempo completo", "full time", "full-time", "fulltime",
    "40 horas", "40h", "40 h", "jornada continua completa",
)
_TURNOS_KW = (
    "turnos", "rotativ", "jornada intensiva", "horario intensivo", "horario flexible",
    "jornada flexible", "flexibilidad horaria", "turno de noche", "nocturno",
    "shift", "jornada partida", "intensiva",
)


def classify_jornada(text: str, employment_type: Optional[str] = None) -> str:
    """Classifica a jornada: parcial (≤30h), completa (40h), turnos ou não informada."""
    et = norm(" ".join(employment_type) if isinstance(employment_type, list) else employment_type)
    if "part" in et:
        return JORNADA_PARCIAL
    t = norm(text)

    for regex in (_HOURS_RE, _HOURS_RE_ALT):
        m = regex.search(t)
        if m:
            hours = int(m.group(1))
            if 1 <= hours <= 30:
                return JORNADA_PARCIAL
            if 35 <= hours <= 45:
                return JORNADA_COMPLETA

    if any(k in t for k in _PARCIAL_KW):
        return JORNADA_PARCIAL
    if any(k in t for k in _COMPLETA_KW) or "full" in et:
        return JORNADA_COMPLETA
    if any(k in t for k in _TURNOS_KW):
        return JORNADA_TURNOS
    return JORNADA_ND


# ---------------------------------------------------------------------------
# Modalidade
# ---------------------------------------------------------------------------
_HIBRIDO_KW = ("hibrido", "hybrid", "semipresencial", "teletrabajo parcial", "mixto")
_REMOTO_KW = (
    "teletrabajo", "remoto", "remote", "en remoto", "trabajo desde casa",
    "desde casa", "telecommute", "100% online", "home office",
)
_PRESENCIAL_KW = ("presencial", "on-site", "onsite", "en oficina", "in situ")


def classify_modalidad(text: str, location_type: Optional[str] = None) -> str:
    t = norm(text)
    if any(k in t for k in _HIBRIDO_KW):
        return MODALIDAD_HIBRIDO
    if "telecommute" in norm(location_type) or any(k in t for k in _REMOTO_KW):
        return MODALIDAD_REMOTO
    if any(k in t for k in _PRESENCIAL_KW):
        return MODALIDAD_PRESENCIAL
    return MODALIDAD_ND


# ---------------------------------------------------------------------------
# Contrato
# ---------------------------------------------------------------------------
def classify_contrato(text: str, employment_type: Optional[str] = None) -> str:
    t = norm(text)
    et = norm(" ".join(employment_type) if isinstance(employment_type, list) else employment_type)
    if "fijo discontinuo" in t or "fijo-discontinuo" in t or "fijos discontinuos" in t:
        return CONTRATO_FIJO_DISC
    if "intern" in et or any(k in t for k in ("practicas", "becario", "beca ", "internship", "contrato formativo", "formacion en alternancia")):
        return CONTRATO_PRACTICAS
    if "contractor" in et or any(k in t for k in ("autonomo", "freelance", "mercantil", "por cuenta propia")):
        return CONTRATO_AUTONOMO
    if "temporary" in et or any(k in t for k in (
            "temporal", "obra y servicio", "eventual", "sustitucion", "interinidad",
            "circunstancias de la produccion", "campana", "de verano", "duracion determinada")):
        return CONTRATO_TEMPORAL
    if any(k in t for k in ("indefinido", "contrato fijo", "estable", "permanent", "plantilla")):
        return CONTRATO_INDEFINIDO
    return CONTRATO_ND


# ---------------------------------------------------------------------------
# Salário
# ---------------------------------------------------------------------------
_NUM = r"\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:[.,]\d{1,2})?"
_CUR = r"(?:€|eur\b|euros?\b)"
_RANGE_RE = re.compile(
    rf"({_NUM})\s*(k\b|mil\b)?\s*{_CUR}?\s*(?:-|–|—|a|hasta|y)\s*({_NUM})\s*(k\b|mil\b)?\s*{_CUR}"
)
_RANGE_PREFIX_RE = re.compile(rf"{_CUR}\s*({_NUM})\s*(k\b)?\s*(?:-|–|—|a|hasta)\s*{_CUR}?\s*({_NUM})\s*(k\b)?")
_SINGLE_RE = re.compile(rf"({_NUM})\s*(k\b|mil\b)?\s*{_CUR}")
_SINGLE_PREFIX_RE = re.compile(rf"{_CUR}\s*({_NUM})\s*(k\b)?")


def _to_number(raw: str, suffix: Optional[str]) -> Optional[float]:
    raw = raw.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", raw):
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", raw):
        raw = raw.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):  # 18,000 (formato inglês)
        raw = raw.replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if suffix and suffix.strip() in ("k", "mil"):
        value *= 1000
    return value


def _detect_period(text: str, value: float) -> str:
    t = norm(text)
    if re.search(r"(/|\bpor\s+|\bla\s+|\ba\s+la\s+)(h|hora)\b|\bhora\b|hourly|per hour|/h\b", t):
        return "hour"
    if re.search(r"\bmes\b|mensual|/mes|month|al mes|brutos? mes", t):
        return "month"
    if re.search(r"\bano\b|anual|/ano|year|brutos? ano|b/a|yearly|annual", t):
        return "year"
    if value < 100:
        return "hour"
    if value < 6000:
        return "month"
    return "year"


def annualize(value: float, period: str, weekly_hours: int = 40) -> float:
    if period == "hour":
        return value * weekly_hours * 52
    if period == "month":
        return value * 12
    return value


def parse_salary(text: str, jornada: str = JORNADA_ND) -> Tuple[Optional[float], Optional[float]]:
    """Extrai salário mínimo/máximo e converte para €/ano bruto."""
    if not text:
        return None, None
    t = text.replace("\xa0", " ").lower()
    values: list[float] = []
    m = _RANGE_RE.search(t) or _RANGE_PREFIX_RE.search(t)
    if m:
        a = _to_number(m.group(1), m.group(2))
        b = _to_number(m.group(3), m.group(4))
        values = [v for v in (a, b) if v]
        # "18-22k €": o primeiro número herda o sufixo do segundo
        if len(values) == 2 and values[0] < 1000 <= values[1] and values[0] * 1000 <= values[1] * 2:
            values[0] *= 1000
    else:
        m = _SINGLE_RE.search(t) or _SINGLE_PREFIX_RE.search(t)
        if m:
            v = _to_number(m.group(1), m.group(2))
            if v:
                values = [v]
    if not values:
        return None, None

    window = t[max(0, m.start() - 20): m.end() + 40] if m else t
    weekly = 30 if jornada == JORNADA_PARCIAL else 40
    period = _detect_period(window, max(values))
    annual = [annualize(v, period, weekly) for v in values]
    annual = [round(a, 0) for a in annual if 2_000 <= a <= 400_000]
    if not annual:
        return None, None
    return min(annual), max(annual)


def format_salary(min_a: Optional[float], max_a: Optional[float]) -> str:
    def fmt(v: float) -> str:
        return f"{v:,.0f}".replace(",", ".")
    if min_a and max_a and min_a != max_a:
        return f"{fmt(min_a)} – {fmt(max_a)} €/ano"
    if min_a or max_a:
        return f"{fmt(min_a or max_a)} €/ano"  # type: ignore[arg-type]
    return ""


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------
_UNITS = {
    "segundo": "seconds", "second": "seconds", "sec": "seconds",
    "minuto": "minutes", "minute": "minutes", "min": "minutes",
    "hora": "hours", "hour": "hours", "h": "hours",
    "dia": "days", "day": "days", "d": "days",
    "semana": "weeks", "week": "weeks",
    "mes": "months", "month": "months",
}


def parse_date(value, now: Optional[datetime] = None) -> Optional[datetime]:
    """Converte datas ISO, timestamps (ms) ou expressões relativas para datetime UTC."""
    now = now or datetime.now(timezone.utc)
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10**11 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    raw = str(value).strip()

    # ISO 8601
    iso = raw.replace("Z", "+00:00")
    for candidate in (iso, iso[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # dd/mm/aaaa
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=timezone.utc)
        except ValueError:
            return None

    t = norm(raw)
    if any(k in t for k in ("hoy", "today", "just posted", "recien", "ahora", "nueva", "new")):
        return now
    if any(k in t for k in ("ayer", "yesterday")):
        return now - timedelta(days=1)
    if re.search(r"(mas de|\+)\s*30|30\+", t):
        return now - timedelta(days=31)
    m = re.search(r"(\d+|un|una|an|a)\s*(segundo|second|sec|minuto|minute|min|hora|hour|h|dia|day|d|semana|week|mes|month)s?\b", t)
    if m:
        qty_raw = m.group(1)
        qty = 1 if qty_raw in ("un", "una", "an", "a") else int(qty_raw)
        unit = _UNITS[m.group(2)]
        if unit == "months":
            return now - timedelta(days=30 * qty)
        return now - timedelta(**{unit: qty})
    return None


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def format_relative(iso: Optional[str], now: Optional[datetime] = None) -> str:
    if not iso:
        return "Data não informada"
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return "Data não informada"
    now = now or datetime.now(timezone.utc)
    delta = now - dt
    if delta.total_seconds() < 3600:
        return "Há menos de 1 hora"
    if delta.days < 1:
        h = int(delta.total_seconds() // 3600)
        return f"Há {h} hora{'s' if h > 1 else ''}"
    if delta.days == 1:
        return "Ontem"
    if delta.days < 31:
        return f"Há {delta.days} dias"
    return dt.strftime("%d/%m/%Y")
