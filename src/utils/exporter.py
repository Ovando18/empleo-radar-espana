"""Exportação das vagas para CSV, Excel (.xlsx) estilizado e relatório PDF."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import pandas as pd
from fpdf import FPDF
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.scrapers.models import JORNADA_BADGES, JobOffer
from src.scrapers.normalizer import format_relative, format_salary

RED = (170, 21, 27)        # #AA151B
GOLD = (241, 191, 0)       # #F1BF00
GRAPHITE = (30, 41, 59)    # #1E293B
SLATE = (100, 116, 139)    # #64748B
BORDER = (226, 232, 240)   # #E2E8F0
ICE = (248, 249, 250)      # #F8F9FA

EXPORT_COLUMNS = {
    "title": "Cargo",
    "company": "Empresa",
    "city": "Cidade",
    "province": "Província",
    "portal": "Portal",
    "jornada_label": "Jornada",
    "modalidad": "Modalidade",
    "contrato": "Contrato",
    "salary_label": "Salário estimado (€/ano)",
    "salary_text": "Salário (texto original)",
    "published_label": "Publicação",
    "summary": "Resumo",
    "url": "Link da vaga",
}


def jobs_to_dataframe(jobs: Sequence[JobOffer]) -> pd.DataFrame:
    rows = []
    for j in jobs:
        d = j.to_dict()
        d["jornada_label"] = JORNADA_BADGES.get(j.jornada, j.jornada)
        d["salary_label"] = format_salary(j.salary_min_annual, j.salary_max_annual)
        d["published_label"] = format_relative(j.published)
        rows.append(d)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=list(EXPORT_COLUMNS.values()))
    return df[list(EXPORT_COLUMNS)].rename(columns=EXPORT_COLUMNS)


def to_csv_bytes(jobs: Sequence[JobOffer]) -> bytes:
    # BOM UTF-8 para o Excel abrir acentos corretamente
    return jobs_to_dataframe(jobs).to_csv(index=False, sep=";").encode("utf-8-sig")


def to_excel_bytes(jobs: Sequence[JobOffer], sheet_name: str = "Vagas") -> bytes:
    df = jobs_to_dataframe(jobs)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name, startrow=2)
        ws = writer.sheets[sheet_name]

        ws["A1"] = "EmpleoRadar España — Relatório de vagas"
        ws["A1"].font = Font(bold=True, size=14, color="AA151B")
        ws["A2"] = f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} · {len(df)} vagas"
        ws["A2"].font = Font(italic=True, size=9, color="64748B")

        header_fill = PatternFill("solid", fgColor="AA151B")
        thin = Side(style="thin", color="E2E8F0")
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=3, column=col_idx)
            cell.fill = header_fill
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
            if col_name == "Resumo":
                width = 60
            else:
                p90 = int(df[col_name].astype(str).str.len().quantile(0.9)) if len(df) else 10
                width = min(45, max(12, p90 + 2, len(col_name) + 2))
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        link_col = list(df.columns).index("Link da vaga") + 1
        zebra = PatternFill("solid", fgColor="F8F9FA")
        for r in range(4, 4 + len(df)):
            for c in range(1, len(df.columns) + 1):
                cell = ws.cell(row=r, column=c)
                cell.border = Border(bottom=thin)
                cell.alignment = Alignment(vertical="top", wrap_text=(c != link_col))
                if r % 2 == 1:
                    cell.fill = zebra
            link_cell = ws.cell(row=r, column=link_col)
            if str(link_cell.value or "").startswith("http"):
                link_cell.hyperlink = link_cell.value
                link_cell.value = "Abrir vaga"
                link_cell.font = Font(color="AA151B", underline="single")

        ws.freeze_panes = "B4"
        if len(df):
            ws.auto_filter.ref = f"A3:{get_column_letter(len(df.columns))}{3 + len(df)}"
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
_PDF_REPLACEMENTS = {
    "€": "EUR", "–": "-", "—": "-", "…": "...", "“": '"', "”": '"', "‘": "'", "’": "'",
    "•": "-", "·": "-", " ": " ", "≤": "<=", "≥": ">=",
}


def _pdf_safe(text: Optional[str]) -> str:
    """As fontes nativas do PDF usam Latin-1; troca caracteres fora desse conjunto."""
    text = str(text or "")
    for k, v in _PDF_REPLACEMENTS.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


class _ReportPDF(FPDF):
    def header(self) -> None:  # noqa: D401
        self.set_fill_color(*RED)
        self.rect(0, 0, self.w, 16, "F")
        self.set_fill_color(*GOLD)
        self.rect(0, 16, self.w, 1.6, "F")
        self.set_xy(10, 4)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 8, "EmpleoRadar España", new_x="LMARGIN", new_y="NEXT")
        self.set_y(22)

    def footer(self) -> None:  # noqa: D401
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*SLATE)
        self.cell(0, 6, _pdf_safe(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} - página {self.page_no()}/{{nb}}"),
                  align="C")


def to_pdf_bytes(jobs: Sequence[JobOffer], filters_summary: Optional[Dict[str, str]] = None,
                 title: str = "Relatório consolidado de vagas") -> bytes:
    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(12, 22, 12)
    pdf.add_page()
    epw = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_text_color(*GRAPHITE)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _pdf_safe(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*SLATE)
    pdf.cell(0, 5, _pdf_safe(f"{len(jobs)} vagas selecionadas"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Resumo dos filtros
    if filters_summary:
        pdf.set_fill_color(*ICE)
        pdf.set_draw_color(*BORDER)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*GRAPHITE)
        pdf.cell(epw, 6, "Critérios da busca", border="LTR", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        lines = [f"{k}: {v}" for k, v in filters_summary.items() if v]
        pdf.multi_cell(epw, 4.6, _pdf_safe("\n".join(lines)), border="LRB", fill=True,
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    # Indicadores rápidos
    sal = [j.salary_mid for j in jobs if j.salary_mid]
    parcial = sum(1 for j in jobs if j.jornada == "parcial")
    completa = sum(1 for j in jobs if j.jornada == "completa")
    kpis = [
        ("Vagas", str(len(jobs))),
        ("Média salarial", f"{sum(sal) / len(sal):,.0f} EUR/ano".replace(",", ".") if sal else "-"),
        ("Parcial (<=30h)", str(parcial)),
        ("Completa (40h)", str(completa)),
    ]
    box_w = (epw - 3 * 3) / 4
    y0 = pdf.get_y()
    for i, (label, value) in enumerate(kpis):
        x = pdf.l_margin + i * (box_w + 3)
        pdf.set_draw_color(*BORDER)
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(x, y0, box_w, 15, "DF")
        pdf.set_fill_color(*RED)
        pdf.rect(x, y0, 1.2, 15, "F")
        pdf.set_xy(x + 3, y0 + 2)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*SLATE)
        pdf.cell(box_w - 4, 4, _pdf_safe(label.upper()))
        pdf.set_xy(x + 3, y0 + 7)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*GRAPHITE)
        pdf.cell(box_w - 4, 6, _pdf_safe(value))
    pdf.set_y(y0 + 20)

    # Lista de vagas
    for idx, j in enumerate(jobs, start=1):
        if pdf.get_y() > pdf.h - 45:
            pdf.add_page()
        y_start = pdf.get_y()
        pdf.set_x(pdf.l_margin + 3)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*GRAPHITE)
        pdf.multi_cell(epw - 3, 5.2, _pdf_safe(f"{idx}. {j.title}"), new_x="LMARGIN", new_y="NEXT")

        location = ", ".join(x for x in dict.fromkeys([j.city, j.province]) if x)
        meta = " - ".join(x for x in (j.company, location, j.portal) if x)
        pdf.set_x(pdf.l_margin + 3)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(epw - 3, 4.4, _pdf_safe(meta), new_x="LMARGIN", new_y="NEXT")

        tags = [JORNADA_BADGES.get(j.jornada, ""), j.modalidad, j.contrato,
                format_salary(j.salary_min_annual, j.salary_max_annual) or j.salary_text,
                format_relative(j.published)]
        pdf.set_x(pdf.l_margin + 3)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*RED)
        pdf.multi_cell(epw - 3, 4.4, _pdf_safe(" | ".join(t for t in tags if t and "não informad" not in t.lower())),
                       new_x="LMARGIN", new_y="NEXT")

        if j.summary:
            pdf.set_x(pdf.l_margin + 3)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*GRAPHITE)
            pdf.multi_cell(epw - 3, 4.2, _pdf_safe(j.summary[:320]), new_x="LMARGIN", new_y="NEXT")

        if j.url.startswith("http"):
            pdf.set_x(pdf.l_margin + 3)
            pdf.set_font("Helvetica", "U", 8)
            pdf.set_text_color(*RED)
            pdf.cell(epw - 3, 4.6, "Abrir vaga original", link=j.url, new_x="LMARGIN", new_y="NEXT")

        pdf.set_fill_color(*GOLD)
        pdf.rect(pdf.l_margin, y_start + 0.5, 0.9, max(4, pdf.get_y() - y_start - 1), "F")
        pdf.ln(1.5)
        pdf.set_draw_color(*BORDER)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + epw, pdf.get_y())
        pdf.ln(2.5)

    if not jobs:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*SLATE)
        pdf.cell(0, 10, "Nenhuma vaga selecionada.", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def export_filename(prefix: str, ext: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.{ext}"


def summarize_filters(labels: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in labels.items() if v}


__all__: List[str] = [
    "jobs_to_dataframe", "to_csv_bytes", "to_excel_bytes", "to_pdf_bytes",
    "export_filename", "summarize_filters",
]
