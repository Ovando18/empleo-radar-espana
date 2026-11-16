"""Modelos de dados e rótulos compartilhados pelo motor de busca e pela interface."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Jornada (filtro crítico)
# ---------------------------------------------------------------------------
JORNADA_ALL = "all"
JORNADA_PARCIAL = "parcial"
JORNADA_COMPLETA = "completa"
JORNADA_TURNOS = "turnos"
JORNADA_ND = "nd"

JORNADA_FILTER_OPTIONS: Dict[str, str] = {
    JORNADA_ALL: "Todas as jornadas",
    JORNADA_PARCIAL: "Jornada Parcial / Até 30h semanais (Compatível com Visto de Estudante)",
    JORNADA_COMPLETA: "Jornada Completa / 40h semanais (Contrato Padrão)",
    JORNADA_TURNOS: "Por turnos / Intensiva / Flexível",
}

JORNADA_BADGES: Dict[str, str] = {
    JORNADA_PARCIAL: "Parcial · até 30h",
    JORNADA_COMPLETA: "Completa · 40h",
    JORNADA_TURNOS: "Turnos / Flexível",
    JORNADA_ND: "Jornada não informada",
}

# ---------------------------------------------------------------------------
# Modalidade, contrato, data, setor
# ---------------------------------------------------------------------------
MODALIDAD_PRESENCIAL = "Presencial"
MODALIDAD_HIBRIDO = "Híbrido"
MODALIDAD_REMOTO = "Teletrabajo / Remoto"
MODALIDAD_ND = "Não informada"
MODALIDAD_OPTIONS = [MODALIDAD_PRESENCIAL, MODALIDAD_HIBRIDO, MODALIDAD_REMOTO]

CONTRATO_INDEFINIDO = "Indefinido"
CONTRATO_TEMPORAL = "Temporal"
CONTRATO_FIJO_DISC = "Fijo Discontinuo"
CONTRATO_PRACTICAS = "Prácticas / Becario"
CONTRATO_AUTONOMO = "Autónomo"
CONTRATO_ND = "Não informado"
CONTRATO_OPTIONS = [
    CONTRATO_INDEFINIDO, CONTRATO_TEMPORAL, CONTRATO_FIJO_DISC,
    CONTRATO_PRACTICAS, CONTRATO_AUTONOMO,
]

DATE_FILTER_OPTIONS: Dict[str, str] = {
    "24h": "Últimas 24h",
    "3d": "Últimos 3 dias",
    "7d": "Última semana",
    "30d": "Último mês",
}
DATE_FILTER_DAYS: Dict[str, int] = {"24h": 1, "3d": 3, "7d": 7, "30d": 30}

# Setor -> termo de busca em espanhol usado quando a palavra-chave está vazia
SECTOR_OPTIONS: Dict[str, str] = {
    "Geral": "",
    "Engenharia & Construção": "ingeniero construcción",
    "Tecnologia / TI": "informática",
    "Educação": "profesor",
    "Administração": "administrativo",
    "Hotelaria / Turismo": "hostelería",
    "Logística": "logística",
    "Saúde": "sanidad",
}


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------
@dataclass
class SearchParams:
    keyword: str = ""                 # termo final (já em espanhol)
    original_keyword: str = ""        # termo digitado pelo usuário
    region: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    jornada: str = JORNADA_ALL
    sector: str = "Geral"
    modalidades: List[str] = field(default_factory=list)
    contratos: List[str] = field(default_factory=list)
    salary_min: int = 0
    date_range: str = "30d"
    portals: List[str] = field(default_factory=list)
    include_unknown: bool = True
    max_per_portal: int = 40

    @property
    def effective_keyword(self) -> str:
        """Palavra-chave final; se vazia, usa o termo do setor."""
        return (self.keyword or SECTOR_OPTIONS.get(self.sector, "")).strip()

    @property
    def location_label(self) -> str:
        return self.city or self.province or "España"

    def cache_key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)


@dataclass
class JobOffer:
    title: str
    portal: str
    url: str
    company: str = ""
    city: str = ""
    province: str = ""
    location_raw: str = ""
    salary_text: str = ""
    salary_min_annual: Optional[float] = None
    salary_max_annual: Optional[float] = None
    jornada: str = JORNADA_ND
    modalidad: str = MODALIDAD_ND
    contrato: str = CONTRATO_ND
    published: Optional[str] = None   # ISO 8601 (UTC)
    published_raw: str = ""
    summary: str = ""
    sector: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            base = f"{self.portal}|{self.url}|{self.title}|{self.company}".lower()
            self.id = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    @property
    def salary_mid(self) -> Optional[float]:
        vals = [v for v in (self.salary_min_annual, self.salary_max_annual) if v]
        return sum(vals) / len(vals) if vals else None

    @property
    def published_dt(self) -> Optional[datetime]:
        if not self.published:
            return None
        try:
            return datetime.fromisoformat(self.published)
        except ValueError:
            return None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["salary_mid"] = self.salary_mid
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobOffer":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in allowed})


# Status possíveis de cada portal na coleta
STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_BLOCKED = "blocked"
STATUS_ERROR = "error"
STATUS_LINK_ONLY = "link_only"

STATUS_LABELS = {
    STATUS_OK: "✅ Coletado",
    STATUS_EMPTY: "⚪ Sem resultados",
    STATUS_BLOCKED: "🛡️ Bloqueio anti-bot",
    STATUS_ERROR: "⚠️ Falha de conexão",
    STATUS_LINK_ONLY: "🔗 Apenas link direto",
}


@dataclass
class PortalResult:
    portal: str
    status: str
    jobs: List[JobOffer] = field(default_factory=list)
    message: str = ""
    deep_link: str = ""
    elapsed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "portal": self.portal,
            "status": self.status,
            "jobs": [j.to_dict() for j in self.jobs],
            "message": self.message,
            "deep_link": self.deep_link,
            "elapsed": round(self.elapsed, 2),
        }
