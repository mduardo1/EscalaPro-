"""Relatório semanal em memória, com tabelas paginadas e texto escapado."""

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.clock import local_now

FONT_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("EscalaProSans", str(FONT_DIRECTORY / "DejaVuSans.ttf")))
pdfmetrics.registerFont(
    TTFont("EscalaProSans-Bold", str(FONT_DIRECTORY / "DejaVuSans-Bold.ttf"))
)


def weekly_pdf(company_name, start, end, schedules) -> BytesIO:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=17 * mm,
        bottomMargin=18 * mm,
        title="Escala semanal - EscalaPro",
        author="EscalaPro",
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "Brand",
        parent=styles["Title"],
        fontName="EscalaProSans-Bold",
        fontSize=24,
        leading=30,
        textColor=colors.HexColor("#2563EB"),
        alignment=0,
    )
    body = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontName="EscalaProSans",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#344054"),
        wordWrap="CJK",
    )
    subtitle = ParagraphStyle("SubtitleLocal", parent=body, fontSize=11, leading=16)
    header = ParagraphStyle(
        "HeaderCell",
        parent=body,
        fontName="EscalaProSans-Bold",
        textColor=colors.white,
        fontSize=9,
    )
    generated = local_now()
    company_style = ParagraphStyle(
        "Company", parent=styles["Heading2"], fontName="EscalaProSans-Bold"
    )
    content = [
        Paragraph("EscalaPro", heading),
        Spacer(1, 3 * mm),
        Paragraph(escape(company_name), company_style),
        Paragraph(
            f"Escala semanal | {start:%d/%m/%Y} a {end-timedelta(days=1):%d/%m/%Y}",
            subtitle,
        ),
        Paragraph(
            f"Gerado em {generated:%d/%m/%Y %H:%M} ({escape(str(generated.tzinfo))})",
            body,
        ),
        Spacer(1, 8 * mm),
    ]
    data = [
        [
            Paragraph(label, header)
            for label in ["Funcionário", "Setor", "Turno", "Início", "Fim", "Intervalo"]
        ]
    ]
    for row in schedules:
        values = [
            row["employee_name"],
            row["department"],
            row["shift_name"],
            datetime.fromisoformat(row["start_at"]).strftime("%d/%m/%Y %H:%M"),
            datetime.fromisoformat(row["end_at"]).strftime("%d/%m/%Y %H:%M"),
            f"{row['break_minutes']} min",
        ]
        data.append([Paragraph(escape(str(value)), body) for value in values])
    if len(data) == 1:
        content.append(
            Paragraph("Nenhuma atribuição programada para este período.", subtitle)
        )
    else:
        table = Table(
            data,
            colWidths=[58 * mm, 40 * mm, 45 * mm, 44 * mm, 44 * mm, 28 * mm],
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F1F5F9")],
                    ),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#1E40AF")),
                ]
            )
        )
        content.append(table)
    content.extend(
        [
            Spacer(1, 6 * mm),
            Paragraph(
                "Horários locais da empresa. Turnos que atravessam a meia-noite exibem a data de término. "
                "O relatório inclui atribuições que tocam a semana selecionada.",
                body,
            ),
        ]
    )

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
        canvas.line(17 * mm, 14 * mm, 280 * mm, 14 * mm)
        canvas.setFont("EscalaProSans", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(17 * mm, 10 * mm, "EscalaPro | Planejamento de equipes")
        canvas.drawRightString(280 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(content, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output
