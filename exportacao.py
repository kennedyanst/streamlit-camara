"""Exportações dos dados filtrados do painel."""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


MONETARY_COLUMNS = {"Valor dos documentos", "Valor glosado", "Valor líquido"}
INTEGER_COLUMNS = {"Ano", "Documentos"}


def _formatar_reais(valor: float) -> str:
    sinal = "-" if valor < 0 else ""
    formatado = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {formatado}"


def _formatar_inteiro(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".")


def gerar_excel(dados: pd.DataFrame) -> bytes:
    """Gera planilha Excel estilizada com filtros e formatos numéricos."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Despesas", index=False)
        planilha = writer.sheets["Despesas"]
        planilha.freeze_panes = "A2"
        planilha.auto_filter.ref = planilha.dimensions

        header_fill = PatternFill(start_color="005A32", end_color="005A32", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="left", vertical="center")
        planilha.row_dimensions[1].height = 24

        for col_idx, col_name in enumerate(dados.columns, start=1):
            celula_header = planilha.cell(row=1, column=col_idx)
            celula_header.fill = header_fill
            celula_header.font = header_font
            celula_header.alignment = header_align

            if col_name in MONETARY_COLUMNS:
                num_fmt = 'R$ #,##0.00'
            elif col_name in INTEGER_COLUMNS:
                num_fmt = '#,##0'
            else:
                num_fmt = None

            if num_fmt and len(dados) > 0:
                for row_idx in range(2, len(dados) + 2):
                    planilha.cell(row=row_idx, column=col_idx).number_format = num_fmt

            largura_base = len(str(col_name)) + 4
            if not dados.empty:
                amostra = dados[col_name].head(200).astype(str).map(len).max()
                largura_base = max(largura_base, int(amostra) + 3)
            planilha.column_dimensions[get_column_letter(col_idx)].width = min(max(largura_base, 12), 44)

    return buffer.getvalue()


def gerar_pdf(
    dados: pd.DataFrame,
    filtros: dict[str, list[str]],
    fonte: str,
) -> bytes:
    """Gera resumo analítico em PDF no padrão institucional da Câmara."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        title="Painel de gastos parlamentares",
        author="Painel de dados públicos",
        rightMargin=28,
        leftMargin=28,
        topMargin=26,
        bottomMargin=26,
    )
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "CamaraTitle",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#005A32"),
        alignment=0,
        spaceAfter=4,
    )
    estilo_meta = ParagraphStyle(
        "CamaraMeta",
        parent=estilos["Normal"],
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#4B6056"),
    )
    estilo_celula = ParagraphStyle(
        "CamaraCell",
        parent=estilos["BodyText"],
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#11241B"),
    )
    estilo_rodape = ParagraphStyle(
        "CamaraFooter",
        parent=estilos["Italic"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64786E"),
    )

    ativos = [
        f"<b>{escape(nome)}:</b> {escape(', '.join(valores))}"
        for nome, valores in filtros.items()
        if valores
    ]

    total_liquido = float(dados["Valor líquido"].sum()) if "Valor líquido" in dados.columns and not dados.empty else 0.0
    total_glosado = float(dados["Valor glosado"].sum()) if "Valor glosado" in dados.columns and not dados.empty else 0.0
    total_docs = int(dados["Documentos"].sum()) if "Documentos" in dados.columns and not dados.empty else 0

    historia = [
        Paragraph("Despesas da Cota Parlamentar — Resumo Analítico", estilo_titulo),
        Paragraph(
            f"Gerado em {datetime.now().astimezone():%d/%m/%Y %H:%M %Z} · Fonte: {escape(fonte)}",
            estilo_meta,
        ),
        Paragraph(
            "Filtros ativos: " + ("; ".join(ativos) if ativos else "nenhum (todos os registros)"),
            estilo_meta,
        ),
        Spacer(1, 8),
    ]

    resumo_kpis = Table(
        [
            [
                f"Valor líquido: {_formatar_reais(total_liquido)}",
                f"Valor glosado: {_formatar_reais(total_glosado)}",
                f"Documentos: {_formatar_inteiro(total_docs)}",
                f"Grupos no recorte: {_formatar_inteiro(len(dados))}",
            ]
        ],
        colWidths=[200, 185, 160, 175],
    )
    resumo_kpis.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDF4F0")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#005A32")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#CBE0D5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7E6DE")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    historia.append(resumo_kpis)
    historia.append(Spacer(1, 10))

    if dados.empty:
        historia.append(
            Paragraph(
                "Nenhum registro encontrado para os filtros selecionados.",
                estilo_meta,
            )
        )
    else:
        resumo = dados.sort_values("Valor líquido", ascending=False).head(40)
        colunas = [
            "Deputado",
            "UF",
            "Partido",
            "Categoria da despesa",
            "Mês",
            "Documentos",
            "Valor líquido",
        ]
        tabela_dados: list[list[object]] = [colunas]
        for linha in resumo.loc[:, colunas].itertuples(index=False, name=None):
            tabela_dados.append(
                [
                    Paragraph(escape(str(linha[0])), estilo_celula),
                    escape(str(linha[1])),
                    escape(str(linha[2])),
                    Paragraph(escape(str(linha[3])), estilo_celula),
                    escape(str(linha[4])),
                    _formatar_inteiro(int(linha[5])),
                    _formatar_reais(float(linha[6])),
                ]
            )
        tabela = Table(
            tabela_dados,
            colWidths=[135, 34, 66, 250, 62, 68, 105],
            repeatRows=1,
        )
        tabela.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#005A32")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("LEADING", (0, 0), (-1, -1), 9.5),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DCE5E0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (2, -1), "CENTER"),
                    ("ALIGN", (5, 0), (6, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F9F7")]),
                ]
            )
        )
        historia.append(tabela)
        historia.append(Spacer(1, 8))
        historia.append(
            Paragraph(
                "O PDF apresenta até 40 grupos com maior valor líquido. "
                "Use o Excel para consultar todos os resultados filtrados. "
                "CPFs, identificadores fiscais e fornecedores não compõem o snapshot público.",
                estilo_rodape,
            )
        )

    documento.build(historia)
    return buffer.getvalue()
