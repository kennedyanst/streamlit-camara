"""Gráficos analíticos do painel de despesas."""

from __future__ import annotations

from html import escape
import re
from textwrap import wrap
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from atualizar_dados import MONTH_NAMES


FONT_FAMILY = "Inter, Segoe UI, -apple-system, BlinkMacSystemFont, sans-serif"

MONTH_ORDER = list(MONTH_NAMES.values())
MONTH_LABELS = {
    "Janeiro": "Jan",
    "Fevereiro": "Fev",
    "Março": "Mar",
    "Abril": "Abr",
    "Maio": "Mai",
    "Junho": "Jun",
    "Julho": "Jul",
    "Agosto": "Ago",
    "Setembro": "Set",
    "Outubro": "Out",
    "Novembro": "Nov",
    "Dezembro": "Dez",
}
VALID_UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}

# Paleta institucional inspirada na identidade visual da Câmara dos Deputados.
COLORS = {
    "emerald": "#006B3F",
    "emerald_dark": "#005A32",
    "emerald_fill": "rgba(0, 107, 63, 0.11)",
    "teal": "#1E7F74",
    "forest": "#0D4A30",
    "slate_green": "#356859",
    "gold": "#C99700",
    "gold_dark": "#8A6500",
    "gold_soft": "rgba(253, 248, 231, 0.94)",
    "gold_border": "#E9D289",
    "text": "#11241B",
    "secondary": "#3D5449",
    "muted": "#64786E",
    "grid": "#E6EEEA",
    "tooltip_bg": "#0E291D",
}

REQUIRED_COLUMNS = {
    "Mês",
    "Deputado",
    "ID do Deputado",
    "UF",
    "Partido",
    "Categoria da despesa",
    "Documentos",
    "Valor líquido",
}

_UPPERCASE_TOKENS = {"RPA", "DF", "UF", "CEAP", "CPF", "CNPJ"}


def formatar_reais_br(valor: float) -> str:
    """Formata valor monetário no padrão brasileiro (ex.: R$ 1.234,56)."""
    sinal = "-" if valor < 0 else ""
    formatado = f"{abs(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {formatado}"


def formatar_reais_compacto(valor: float) -> str:
    """Formata valores em escala legível em português (mi, mil ou exato)."""
    sinal = "-" if valor < 0 else ""
    absoluto = abs(valor)
    if absoluto >= 1_000_000:
        numero = f"{absoluto / 1_000_000:.2f}".replace(".", ",")
        return f"{sinal}R$ {numero} mi"
    if absoluto >= 1_000:
        numero = f"{absoluto / 1_000:.1f}".replace(".", ",")
        return f"{sinal}R$ {numero} mil"
    numero = f"{absoluto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sinal}R$ {numero}"


def formatar_percentual_br(valor: float) -> str:
    """Formata participação percentual com vírgula decimal."""
    return f"{valor * 100:.1f}%".replace(".", ",")


def _limpar_rotulo_categoria(texto: Any) -> str:
    limpo = str(texto).strip().rstrip(".")
    limpo = re.sub(r"\s+,", ", ", limpo)
    limpo = re.sub(r"\s+", " ", limpo)
    if not limpo:
        return ""
    if limpo.isupper() and len(limpo) > 4:
        sentenca = limpo[0] + limpo[1:].lower()
        sentenca = re.sub(r"\bdistrito federal\b", "Distrito Federal", sentenca)
        for sigla in _UPPERCASE_TOKENS:
            sentenca = re.sub(rf"\b{sigla.lower()}\b", sigla, sentenca)
        return sentenca
    return limpo


def _base_figura(
    figura: go.Figure,
    altura: int,
    margem_esquerda: int = 24,
    margem_direita: int = 24,
) -> go.Figure:
    figura.update_layout(
        template="plotly_white",
        separators=",.",
        height=altura,
        autosize=True,
        margin={"l": margem_esquerda, "r": margem_direita, "t": 14, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font={"family": FONT_FAMILY, "size": 12, "color": COLORS["text"]},
        hoverlabel={
            "bgcolor": COLORS["tooltip_bg"],
            "bordercolor": COLORS["tooltip_bg"],
            "font": {"family": FONT_FAMILY, "color": "#FFFFFF", "size": 12},
            "namelength": -1,
        },
        hovermode="closest",
        showlegend=False,
    )
    figura.update_xaxes(
        showgrid=True,
        gridcolor=COLORS["grid"],
        gridwidth=1,
        zeroline=True,
        zerolinecolor="#D2DFD8",
        zerolinewidth=1,
        title=None,
        tickfont={"color": COLORS["muted"], "size": 11},
    )
    figura.update_yaxes(
        showgrid=False,
        zeroline=False,
        title=None,
        tickfont={"color": COLORS["secondary"], "size": 11},
    )
    return figura


def _rotulos_quebrados(valor: Any, limite: int = 30, formatar_categoria: bool = False) -> str:
    texto = _limpar_rotulo_categoria(valor) if formatar_categoria else str(valor)
    linhas = wrap(texto, width=limite, break_long_words=False) or [texto]
    if len(linhas) > 2:
        linhas = [linhas[0], f"{linhas[1][: max(1, limite - 1)].rstrip()}…"]
    return "<br>".join(escape(linha) for linha in linhas)


def _figura_vazia(mensagem: str = "Sem dados para os filtros selecionados.") -> go.Figure:
    figura = go.Figure()
    figura.add_annotation(
        text=escape(mensagem),
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"family": FONT_FAMILY, "size": 14, "color": COLORS["muted"]},
    )
    figura.update_xaxes(visible=False)
    figura.update_yaxes(visible=False)
    return _base_figura(figura, altura=280)


def _formatar_eixo_reais(
    figura: go.Figure,
    valores: list[float],
    formato: str = "~s",
    folga_rotulo: float = 1.32,
) -> None:
    config: dict[str, Any] = {
        "tickprefix": "R$ ",
        "tickformat": formato,
        "nticks": 4,
        "tickangle": 0,
        "automargin": True,
    }
    if valores:
        minimo = min(valores)
        maximo = max(valores)
        if minimo >= 0 and maximo > 0:
            config["range"] = [0, maximo * folga_rotulo]
        elif maximo > 0:
            config["range"] = [minimo * 1.15, maximo * folga_rotulo]
        else:
            config["rangemode"] = "tozero"
    else:
        config["rangemode"] = "tozero"
    figura.update_xaxes(**config)


def _figura_barras(
    dados: pd.DataFrame,
    coluna_rotulo: str,
    coluna_valor: str,
    coluna_documentos: str,
    cor: str,
    modo_valor: str = "total",
    margem_esquerda: int = 215,
    total_referencia: float | None = None,
    formatar_categoria: bool = False,
    limite_quebra: int = 30,
) -> go.Figure:
    if dados.empty:
        return _figura_vazia()

    ordenado = dados.sort_values(coluna_valor, ascending=False, kind="stable")
    rotulos = ordenado[coluna_rotulo].astype(str).tolist()
    valores = ordenado[coluna_valor].astype(float).tolist()
    documentos = ordenado[coluna_documentos].astype(int).tolist()
    total = (
        float(total_referencia)
        if total_referencia is not None
        else float(ordenado[coluna_valor].sum())
    )
    participacoes = [
        (valor / total) if total > 0 else 0.0
        for valor in valores
    ]

    if modo_valor == "media":
        hover = (
            "<b>%{customdata[0]}</b><br>"
            "Média líquida por documento: R$ %{x:,.2f}<br>"
            "Documentos: %{customdata[1]:,}<br>"
            "Valor líquido total: R$ %{customdata[2]:,.2f}"
            "<extra></extra>"
        )
        customdata = [
            [
                _limpar_rotulo_categoria(rotulo) if formatar_categoria else rotulo,
                qtd,
                float(total_linha),
            ]
            for rotulo, qtd, total_linha in zip(
                rotulos,
                documentos,
                ordenado["Valor líquido"].astype(float).tolist(),
            )
        ]
        textos_barras = [f" {formatar_reais_br(valor)}" for valor in valores]
        folga = 1.32
    else:
        hover = (
            "<b>%{customdata[0]}</b><br>"
            "Valor líquido: R$ %{x:,.2f}<br>"
            "Documentos: %{customdata[1]:,}<br>"
            "Participação no recorte: %{customdata[2]:.1%}"
            "<extra></extra>"
        )
        customdata = [
            [
                _limpar_rotulo_categoria(rotulo) if formatar_categoria else rotulo,
                qtd,
                share,
            ]
            for rotulo, qtd, share in zip(rotulos, documentos, participacoes)
        ]
        textos_barras = [
            f" {formatar_reais_compacto(valor)} ({formatar_percentual_br(share)})"
            for valor, share in zip(valores, participacoes)
        ]
        folga = 1.56

    figura = go.Figure(
        go.Bar(
            x=valores,
            y=rotulos,
            orientation="h",
            width=0.66,
            marker={"color": cor, "line": {"width": 0}, "cornerradius": 5},
            text=textos_barras,
            textposition="outside",
            textfont={"family": FONT_FAMILY, "size": 11, "color": COLORS["secondary"]},
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=hover,
        )
    )
    figura.update_yaxes(
        categoryorder="array",
        categoryarray=rotulos,
        tickmode="array",
        tickvals=rotulos,
        ticktext=[
            _rotulos_quebrados(
                rotulo,
                limite=limite_quebra,
                formatar_categoria=formatar_categoria,
            )
            for rotulo in rotulos
        ],
        autorange="reversed",
        automargin=True,
        ticklabelstandoff=6,
    )
    _formatar_eixo_reais(
        figura,
        valores,
        ",.0f" if modo_valor == "media" else "~s",
        folga_rotulo=folga,
    )
    altura = max(310, min(520, len(rotulos) * 44 + 74))
    return _base_figura(
        figura,
        altura,
        margem_esquerda=margem_esquerda,
        margem_direita=28,
    )


def _grafico_mensal(dados: pd.DataFrame) -> go.Figure:
    mensal = (
        dados.groupby("Mês", as_index=False)
        .agg(
            **{
                "Valor líquido": ("Valor líquido", "sum"),
                "Documentos": ("Documentos", "sum"),
            }
        )
    )
    if mensal.empty:
        return _figura_vazia()

    mensal["_ordem"] = mensal["Mês"].map({mes: i for i, mes in enumerate(MONTH_ORDER)})
    mensal = mensal.sort_values("_ordem", kind="stable")
    rotulos_mes = [MONTH_LABELS[mes] for mes in mensal["Mês"]]
    valores = mensal["Valor líquido"].astype(float).tolist()

    figura = go.Figure(
        go.Scatter(
            x=rotulos_mes,
            y=valores,
            customdata=[
                [mes, int(documentos)]
                for mes, documentos in zip(mensal["Mês"], mensal["Documentos"])
            ],
            mode="lines+markers",
            line={"color": COLORS["emerald"], "width": 2.8},
            marker={
                "color": "#FFFFFF",
                "size": 8.5,
                "line": {"color": COLORS["emerald"], "width": 2.4},
            },
            fill="tozeroy",
            fillcolor=COLORS["emerald_fill"],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Valor líquido: R$ %{y:,.2f}<br>"
                "Documentos: %{customdata[1]:,}"
                "<extra></extra>"
            ),
        )
    )

    if len(valores) >= 2:
        media_mensal = sum(valores) / len(valores)
        figura.add_hline(
            y=media_mensal,
            line_dash="dot",
            line_width=1.6,
            line_color=COLORS["gold"],
            annotation_text=f"Média mensal: {formatar_reais_compacto(media_mensal)}",
            annotation_position="top right",
            annotation_font={
                "family": FONT_FAMILY,
                "size": 11,
                "color": COLORS["gold_dark"],
            },
            annotation_bgcolor=COLORS["gold_soft"],
            annotation_bordercolor=COLORS["gold_border"],
            annotation_borderwidth=1,
            annotation_borderpad=4,
            annotation_yshift=6,
        )

    x_axis_config: dict[str, Any] = {
        "type": "category",
        "categoryorder": "array",
        "categoryarray": rotulos_mes,
        "tickmode": "array",
        "tickvals": rotulos_mes,
        "ticktext": rotulos_mes,
        "tickangle": 0,
        "showgrid": False,
        "zeroline": False,
        "ticklabelstandoff": 6,
    }
    if len(rotulos_mes) >= 2:
        x_axis_config["range"] = [-0.35, len(rotulos_mes) - 0.65]
    figura.update_xaxes(**x_axis_config)

    figura.update_yaxes(
        tickprefix="R$ ",
        tickformat="~s",
        rangemode="tozero",
        showgrid=True,
        gridcolor=COLORS["grid"],
        nticks=5,
        tickfont={"color": COLORS["muted"], "size": 11},
        ticklabelstandoff=8,
        automargin=True,
    )
    figura = _base_figura(figura, altura=335, margem_esquerda=16, margem_direita=24)
    figura.update_layout(hovermode="x unified", margin={"l": 16, "r": 24, "t": 22, "b": 34})
    return figura


def _rotulo_parlamentar(linha: pd.Series) -> str:
    nome = str(linha["Deputado"]).strip()
    uf = str(linha["UF"]).strip()
    partido = str(linha["Partido"]).strip()
    detalhes = [
        item for item in (uf, partido)
        if item and item != "Não informado"
    ]
    if detalhes:
        return f"{nome} ({' · '.join(detalhes)})"
    return nome


def construir_graficos(dados: pd.DataFrame) -> dict[str, go.Figure]:
    """Cria seis gráficos, preservando unidades e denominadores explícitos."""
    ausentes = sorted(REQUIRED_COLUMNS.difference(dados.columns))
    if ausentes:
        raise ValueError(f"Colunas necessárias aos gráficos ausentes: {ausentes}")
    if dados.empty:
        return {
            chave: _figura_vazia()
            for chave in (
                "mensal",
                "categorias",
                "ufs",
                "deputados",
                "partidos",
                "media_categoria",
            )
        }

    por_categoria = (
        dados.groupby("Categoria da despesa", as_index=False)
        .agg(
            **{
                "Valor líquido": ("Valor líquido", "sum"),
                "Documentos": ("Documentos", "sum"),
            }
        )
    )

    por_uf = (
        dados.loc[dados["UF"].isin(VALID_UFS)]
        .groupby("UF", as_index=False)
        .agg(
            **{
                "Valor líquido": ("Valor líquido", "sum"),
                "Documentos": ("Documentos", "sum"),
            }
        )
        .nlargest(10, "Valor líquido")
    )

    por_deputado = (
        dados.loc[dados["ID do Deputado"].ne("Não informado")]
        .groupby(["ID do Deputado", "Deputado", "UF"], as_index=False)
        .agg(
            **{
                "Valor líquido": ("Valor líquido", "sum"),
                "Documentos": ("Documentos", "sum"),
                "Partido": (
                    "Partido",
                    lambda serie: " / ".join(
                        sorted(
                            {
                                str(v).strip()
                                for v in serie.dropna()
                                if str(v).strip() and str(v).strip() != "Não informado"
                            }
                        )
                    )
                    or "Não informado",
                ),
            }
        )
        .nlargest(10, "Valor líquido")
    )
    if not por_deputado.empty:
        por_deputado["Parlamentar"] = por_deputado.apply(_rotulo_parlamentar, axis=1)
    else:
        por_deputado["Parlamentar"] = pd.Series(dtype="string")

    por_partido = (
        dados.loc[dados["Partido"].ne("Não informado")]
        .groupby("Partido", as_index=False)
        .agg(
            **{
                "Valor líquido": ("Valor líquido", "sum"),
                "Documentos": ("Documentos", "sum"),
            }
        )
        .nlargest(10, "Valor líquido")
    )

    media_categoria = por_categoria.loc[
        por_categoria["Documentos"].gt(0)
    ].copy()
    media_categoria["Média líquida"] = (
        media_categoria["Valor líquido"] / media_categoria["Documentos"]
    )
    media_categoria = media_categoria.nlargest(8, "Média líquida")
    total_recorte = float(dados["Valor líquido"].sum())

    return {
        "mensal": _grafico_mensal(dados),
        "categorias": _figura_barras(
            por_categoria.nlargest(8, "Valor líquido"),
            "Categoria da despesa",
            "Valor líquido",
            "Documentos",
            COLORS["emerald"],
            modo_valor="participacao",
            margem_esquerda=16,
            total_referencia=total_recorte,
            formatar_categoria=True,
            limite_quebra=24,
        ),
        "ufs": _figura_barras(
            por_uf,
            "UF",
            "Valor líquido",
            "Documentos",
            COLORS["teal"],
            modo_valor="participacao",
            margem_esquerda=16,
            total_referencia=total_recorte,
            limite_quebra=10,
        ),
        "deputados": _figura_barras(
            por_deputado,
            "Parlamentar",
            "Valor líquido",
            "Documentos",
            COLORS["forest"],
            modo_valor="participacao",
            margem_esquerda=16,
            total_referencia=total_recorte,
            limite_quebra=26,
        ),
        "partidos": _figura_barras(
            por_partido,
            "Partido",
            "Valor líquido",
            "Documentos",
            COLORS["slate_green"],
            modo_valor="participacao",
            margem_esquerda=16,
            total_referencia=total_recorte,
            limite_quebra=18,
        ),
        "media_categoria": _figura_barras(
            media_categoria,
            "Categoria da despesa",
            "Média líquida",
            "Documentos",
            COLORS["gold"],
            modo_valor="media",
            margem_esquerda=16,
            formatar_categoria=True,
            limite_quebra=32,
        ),
    }
