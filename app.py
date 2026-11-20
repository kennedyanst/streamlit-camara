import base64
from email.utils import parsedate_to_datetime
from html import escape
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from atualizar_dados import CSV_PATH, SUMMARY_PATH
from exportacao import gerar_excel, gerar_pdf
from graficos import (
    MONTH_ORDER,
    construir_graficos,
    formatar_reais_br,
    formatar_reais_compacto,
)


ROOT = Path(__file__).resolve().parent
CSS_PATH = ROOT / "assets" / "estilos.css"
PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "displayModeBar": False,
}
FILTER_COLUMNS = (
    "UF",
    "Partido",
    "Deputado",
    "Categoria da despesa",
    "Mês",
)
SORT_OPTIONS = (
    "Maior valor líquido",
    "Menor valor líquido",
    "Mais documentos",
    "Maior valor glosado",
    "Ordem cronológica",
)
PT_MONTH_ABBR = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}

_EMBLEM_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28" fill="none">'
    '<rect x="4" y="5" width="4.4" height="15" rx="1.2" fill="#FFFFFF"/>'
    '<rect x="10.4" y="5" width="4.4" height="15" rx="1.2" fill="#FFFFFF" fill-opacity="0.88"/>'
    '<path d="M17.2 14.5C17.2 11.4 19.4 9.5 22.6 9.5H23.4V20H17.2V14.5Z" fill="#E9D289"/>'
    '<rect x="3" y="21.5" width="22" height="2.2" rx="1.1" fill="#FFFFFF"/>'
    "</svg>"
)
EMBLEM_DATA_URI = (
    "data:image/svg+xml;base64,"
    + base64.b64encode(_EMBLEM_SVG.encode("utf-8")).decode("ascii")
)

st.set_page_config(
    page_title="Despesas da Cota Parlamentar | Dados Abertos",
    page_icon="🏛️",
    layout="wide",
)
if CSS_PATH.is_file():
    st.html(CSS_PATH)


def _formatar_inteiro(valor: int) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _formatar_data_atualizacao(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    try:
        dt = parsedate_to_datetime(raw_value)
        return f"{dt.day:02d} {PT_MONTH_ABBR[dt.month]} {dt.year}"
    except (TypeError, ValueError, KeyError):
        return raw_value


def _sparkline_mensal_svg(dados: pd.DataFrame) -> str:
    if dados.empty:
        return ""
    mensal = dados.groupby("Mês", as_index=False)["Valor líquido"].sum()
    mensal["_ordem"] = mensal["Mês"].map({mes: i for i, mes in enumerate(MONTH_ORDER)})
    mensal = mensal.sort_values("_ordem", kind="stable")
    valores = mensal["Valor líquido"].astype(float).tolist()
    if len(valores) < 2:
        return ""

    minimo = min(valores)
    maximo = max(valores)
    amplitude = maximo - minimo if maximo != minimo else 1.0
    largura = 68.0
    altura = 26.0
    pad_x = 3.0
    pad_y = 4.0
    passo_x = (largura - 2 * pad_x) / (len(valores) - 1)

    pontos = []
    for indice, valor in enumerate(valores):
        x = pad_x + indice * passo_x
        y = altura - pad_y - ((valor - minimo) / amplitude) * (altura - 2 * pad_y)
        pontos.append(f"{x:.1f},{y:.1f}")

    ultimo_x, ultimo_y = pontos[-1].split(",")
    area = f"{pad_x:.1f},{altura - 1:.1f} " + " ".join(pontos) + f" {largura - pad_x:.1f},{altura - 1:.1f}"
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 68 28">'
        f'<polygon points="{area}" fill="rgba(0, 107, 63, 0.14)"/>'
        f'<polyline points="{" ".join(pontos)}" fill="none" stroke="#006B3F" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{ultimo_x}" cy="{ultimo_y}" r="2.6" fill="#005A32"/>'
        "</svg>"
    )
    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img class="camara-kpi-sparkline" src="{data_uri}" alt="" aria-hidden="true" />'


def _limpar_filtros() -> None:
    for coluna in FILTER_COLUMNS:
        st.session_state[f"filtro_{coluna}"] = []


def _card_header_html(titulo: str, descricao: str) -> str:
    return (
        '<div class="camara-card-head">'
        f'<h3 class="camara-card-title">{escape(titulo)}</h3>'
        f'<p class="camara-card-caption">{escape(descricao)}</p>'
        "</div>"
    )


@st.cache_data(show_spinner="Carregando dados públicos...")
def carregar_dados(csv_path: Path, summary_path: Path, modified_ns: int):
    dados = pd.read_csv(
        csv_path,
        sep=";",
        encoding="utf-8-sig",
        dtype={"ID do Deputado": "string"},
    )
    resumo = json.loads(summary_path.read_text(encoding="utf-8"))
    if dados.empty:
        raise ValueError("O arquivo de despesas está vazio.")
    if not set(FILTER_COLUMNS).issubset(dados.columns):
        raise ValueError("O CSV não contém todas as colunas de filtro esperadas.")
    if resumo.get("registros_agregados") != len(dados):
        raise ValueError("O CSV e o resumo não correspondem à mesma atualização.")
    return dados, resumo


if not CSV_PATH.is_file() or not SUMMARY_PATH.is_file():
    st.error(
        "Os dados ainda não foram gerados. Execute `python atualizar_dados.py` "
        "ou rode o workflow do GitHub Actions."
    )
    st.stop()

dados, resumo = carregar_dados(
    CSV_PATH,
    SUMMARY_PATH,
    max(CSV_PATH.stat().st_mtime_ns, SUMMARY_PATH.stat().st_mtime_ns),
)

# Inicializa o estado dos filtros antes de renderizar o cabeçalho e o botão de limpeza
for coluna in FILTER_COLUMNS:
    st.session_state.setdefault(f"filtro_{coluna}", [])

selecoes_header = {
    coluna: list(st.session_state.get(f"filtro_{coluna}", []))
    for coluna in FILTER_COLUMNS
}
filtrado_header = dados
for coluna, valores in selecoes_header.items():
    if valores:
        filtrado_header = filtrado_header.loc[filtrado_header[coluna].isin(valores)]

data_atualizacao = _formatar_data_atualizacao(resumo.get("arquivo_fonte_modificado_em"))
pill_atualizacao = (
    f'<span class="camara-freshness-pill">Atualizado em {escape(data_atualizacao)}</span>'
    if data_atualizacao
    else ""
)

# ── Cabeçalho institucional + exportações sob demanda ──
with st.container(key="cabecalho"):
    col_brand, col_actions = st.columns([2.35, 1.05], vertical_alignment="center", gap="medium")
    with col_brand:
        st.html(
            '<div class="camara-header-brand">'
            '  <div class="camara-emblem" aria-hidden="true">'
            f'    <img src="{EMBLEM_DATA_URI}" alt="" />'
            "  </div>"
            '  <div class="camara-header-copy">'
            '    <div class="camara-header-title-row">'
            '      <h1 class="camara-header-title">Despesas da Cota Parlamentar</h1>'
            f"      {pill_atualizacao}"
            "    </div>"
            '    <p class="camara-header-subtitle">'
            f"      Dados Abertos · Câmara dos Deputados · Ano-base {escape(str(resumo['ano']))} · "
            f"      {escape(_formatar_inteiro(resumo['registros_origem']))} documentos na fonte oficial"
            "    </p>"
            "  </div>"
            "</div>"
        )
    with col_actions:
        btn_pdf_col, btn_excel_col = st.columns(2, gap="small")
        with btn_pdf_col:
            st.download_button(
                "Resumo PDF",
                data=lambda: gerar_pdf(filtrado_header, selecoes_header, resumo["fonte"]),
                file_name="resumo_gastos_camara.pdf",
                mime="application/pdf",
                type="secondary",
                icon=":material/description:",
                width="stretch",
            )
        with btn_excel_col:
            st.download_button(
                "Baixar Excel",
                data=lambda: gerar_excel(filtrado_header),
                file_name="despesas_camara_filtradas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                icon=":material/download:",
                width="stretch",
            )

# ── Barra de filtros compacta ──
tem_filtro_ativo = any(bool(st.session_state.get(f"filtro_{coluna}")) for coluna in FILTER_COLUMNS)

with st.container(key="filtros", border=True):
    topo_esq, topo_dir = st.columns([4, 1], vertical_alignment="center")
    with topo_esq:
        st.html(
            '<h2 class="camara-filter-title">Refine sua análise</h2>'
            '<p class="camara-filter-subtitle">'
            "Combine uma ou mais dimensões. Sem seleção, todo o ano-base é exibido."
            "</p>"
        )
    with topo_dir:
        st.button(
            "Limpar filtros",
            type="tertiary",
            on_click=_limpar_filtros,
            disabled=not tem_filtro_ativo,
            width="stretch",
        )

    controles = st.columns(5, gap="small")
    selecoes: dict[str, list[str]] = {}
    for coluna, controle in zip(FILTER_COLUMNS, controles):
        opcoes = dados[coluna].dropna().unique().tolist()
        if coluna == "Mês":
            opcoes = [mes for mes in MONTH_ORDER if mes in opcoes]
        else:
            opcoes = sorted(opcoes, key=lambda valor: str(valor).casefold())
        with controle:
            selecoes[coluna] = st.multiselect(
                coluna,
                opcoes,
                placeholder="Todos",
                key=f"filtro_{coluna}",
            )

    filtrado = dados
    for coluna, valores in selecoes.items():
        if valores:
            filtrado = filtrado.loc[filtrado[coluna].isin(valores)]

    chips = []
    for coluna, valores in selecoes.items():
        if valores:
            rotulo_valores = (
                ", ".join(valores[:2]) + (f" +{len(valores) - 2}" if len(valores) > 2 else "")
            )
            chips.append(
                f'<span class="camara-chip"><strong>{escape(coluna)}:</strong> {escape(rotulo_valores)}</span>'
            )
    if chips:
        st.html(
            '<div class="camara-active-chips">'
            + "".join(chips)
            + f'<span class="camara-chip-count">{escape(_formatar_inteiro(len(filtrado)))} '
            f'de {escape(_formatar_inteiro(len(dados)))} grupos</span>'
            "</div>"
        )

# ── Cálculo dos indicadores do recorte ──
total_liquido = float(filtrado["Valor líquido"].sum())
total_documentos_valor = float(filtrado["Valor dos documentos"].sum())
total_glosado = float(filtrado["Valor glosado"].sum())
total_documentos = int(filtrado["Documentos"].sum())
total_deputados = int(
    filtrado.loc[filtrado["ID do Deputado"].ne("Não informado"), "ID do Deputado"].nunique()
)
total_categorias = int(filtrado["Categoria da despesa"].nunique())
ticket_medio = (total_liquido / total_documentos) if total_documentos > 0 else 0.0
pct_glosado = (total_glosado / total_documentos_valor * 100) if total_documentos_valor > 0 else 0.0

valor_liquido_principal = (
    formatar_reais_compacto(total_liquido)
    if abs(total_liquido) >= 1_000_000
    else formatar_reais_br(total_liquido)
)
valor_liquido_legenda = (
    f"{formatar_reais_br(total_liquido)} após glosas"
    if abs(total_liquido) >= 1_000_000
    else "Total líquido após glosas"
)
valor_glosado_principal = (
    formatar_reais_compacto(total_glosado)
    if abs(total_glosado) >= 1_000_000
    else formatar_reais_br(total_glosado)
)
pct_glosa_texto = f"{pct_glosado:.2f}% dos documentos".replace(".", ",")
ticket_texto = (
    f"Ticket médio: {formatar_reais_br(ticket_medio)}"
    if total_documentos > 0
    else "Sem documentos no recorte"
)
categorias_texto = (
    f"{total_categorias} categoria registrada"
    if total_categorias == 1
    else f"{total_categorias} categorias registradas"
)
sparkline_svg = _sparkline_mensal_svg(filtrado)

# ── Faixa executiva de KPIs (4 colunas unificadas) ──
with st.container(key="metricas"):
    st.html(
        '<div class="camara-kpi-strip">'
        '  <div class="camara-kpi-grid">'
        '    <div class="camara-kpi-card camara-kpi-card--primary">'
        '      <span class="camara-kpi-label">Valor Líquido</span>'
        '      <div class="camara-kpi-value-row">'
        f'        <span class="camara-kpi-value">{escape(valor_liquido_principal)}</span>'
        f"        {sparkline_svg}"
        "      </div>"
        f'      <span class="camara-kpi-caption">{escape(valor_liquido_legenda)}</span>'
        "    </div>"
        '    <div class="camara-kpi-card">'
        '      <span class="camara-kpi-label">Valor Glosado</span>'
        '      <div class="camara-kpi-value-row">'
        f'        <span class="camara-kpi-value">{escape(valor_glosado_principal)}</span>'
        "      </div>"
        f'      <span class="camara-kpi-badge">{escape(pct_glosa_texto)}</span>'
        "    </div>"
        '    <div class="camara-kpi-card">'
        '      <span class="camara-kpi-label">Documentos</span>'
        '      <div class="camara-kpi-value-row">'
        f'        <span class="camara-kpi-value">{escape(_formatar_inteiro(total_documentos))}</span>'
        "      </div>"
        f'      <span class="camara-kpi-caption">{escape(ticket_texto)}</span>'
        "    </div>"
        '    <div class="camara-kpi-card">'
        '      <span class="camara-kpi-label">Parlamentares</span>'
        '      <div class="camara-kpi-value-row">'
        f'        <span class="camara-kpi-value">{escape(_formatar_inteiro(total_deputados))}</span>'
        "      </div>"
        f'      <span class="camara-kpi-caption">{escape(categorias_texto)}</span>'
        "    </div>"
        "  </div>"
        "</div>"
    )

# ── Seção analítica (6 gráficos Plotly) ──
graficos = construir_graficos(filtrado)

with st.container(key="secao-analitica"):
    st.html(
        '<div class="camara-section-head">'
        '  <p class="camara-section-kicker">Panorama analítico</p>'
        '  <h2 class="camara-section-title">Distribuição e evolução das despesas</h2>'
        '  <p class="camara-section-desc">'
        "    Todos os gráficos respondem aos filtros ativos. Passe o cursor sobre pontos e barras para consultar detalhes."
        "  </p>"
        "</div>"
    )

    with st.container(key="grafico-mensal", border=True):
        st.html(
            _card_header_html(
                "Evolução mensal do gasto líquido",
                "Série cronológica após glosas · Linha pontilhada indica a média mensal do recorte.",
            )
        )
        st.plotly_chart(
            graficos["mensal"],
            width="stretch",
            theme=None,
            config=PLOTLY_CONFIG,
            key="chart-evolucao-mensal",
        )

    coluna_categoria, coluna_uf = st.columns(2, gap="medium")
    with coluna_categoria:
        with st.container(key="grafico-categorias", border=True):
            st.html(
                _card_header_html(
                    "Categorias com maior despesa líquida (Top 8)",
                    "Participação calculada sobre o valor líquido total do recorte filtrado.",
                )
            )
            st.plotly_chart(
                graficos["categorias"],
                width="stretch",
                theme=None,
                config=PLOTLY_CONFIG,
                key="chart-categorias",
            )
    with coluna_uf:
        with st.container(key="grafico-ufs", border=True):
            st.html(
                _card_header_html(
                    "Despesa líquida por UF (Top 10)",
                    "Considera apenas UFs válidas; registros sem UF informada não entram no ranking.",
                )
            )
            st.plotly_chart(
                graficos["ufs"],
                width="stretch",
                theme=None,
                config=PLOTLY_CONFIG,
                key="chart-ufs",
            )

    coluna_deputados, coluna_partidos = st.columns(2, gap="medium")
    with coluna_deputados:
        with st.container(key="grafico-deputados", border=True):
            st.html(
                _card_header_html(
                    "Parlamentares com maior despesa líquida (Top 10)",
                    "Agrupado por identificador público do deputado (UF · Partido) no recorte selecionado.",
                )
            )
            st.plotly_chart(
                graficos["deputados"],
                width="stretch",
                theme=None,
                config=PLOTLY_CONFIG,
                key="chart-deputados",
            )
    with coluna_partidos:
        with st.container(key="grafico-partidos", border=True):
            st.html(
                _card_header_html(
                    "Despesa líquida por partido (Top 10)",
                    "Participação percentual calculada sobre todo o valor líquido filtrado.",
                )
            )
            st.plotly_chart(
                graficos["partidos"],
                width="stretch",
                theme=None,
                config=PLOTLY_CONFIG,
                key="chart-partidos",
            )

    with st.container(key="grafico-media-categoria", border=True):
        st.html(
            _card_header_html(
                "Maior valor líquido médio por documento",
                "Top 8 categorias por ticket médio de documento no recorte selecionado.",
            )
            + '<div class="camara-method-banner" role="note">'
            '  <span class="camara-method-icon" aria-hidden="true">i</span>'
            '  <span><strong>Métrica descritiva:</strong> média = valor líquido agregado ÷ documentos. '
            "  Compara valores declarados na CEAP e não indica desempenho, qualidade ou irregularidade.</span>"
            "</div>"
        )
        st.plotly_chart(
            graficos["media_categoria"],
            width="stretch",
            theme=None,
            config=PLOTLY_CONFIG,
            key="chart-media-categoria",
        )

# ── Tabela analítica com busca e ordenação ──
with st.container(key="tabela", border=True):
    col_tbl_head, col_tbl_search, col_tbl_sort = st.columns(
        [1.7, 1.15, 0.85],
        vertical_alignment="center",
        gap="small",
    )
    with col_tbl_search:
        busca_tabela = st.text_input(
            "Buscar na tabela",
            placeholder="Buscar deputado, categoria, partido ou UF...",
            label_visibility="collapsed",
            icon=":material/search:",
            key="busca_tabela",
        )
    with col_tbl_sort:
        ordem_tabela = st.selectbox(
            "Ordenar por",
            SORT_OPTIONS,
            label_visibility="collapsed",
            key="ordem_tabela",
        )

    tabela_exibicao = filtrado.copy()
    termo = busca_tabela.strip()
    if termo and not tabela_exibicao.empty:
        colunas_busca = ["Deputado", "Categoria da despesa", "Partido", "UF", "Mês"]
        mascara = pd.Series(False, index=tabela_exibicao.index)
        for col in colunas_busca:
            mascara = mascara | tabela_exibicao[col].astype(str).str.contains(
                termo, case=False, regex=False, na=False
            )
        tabela_exibicao = tabela_exibicao.loc[mascara].copy()

    with col_tbl_head:
        st.html(
            _card_header_html(
                "Detalhamento das despesas agregadas",
                f"{_formatar_inteiro(len(tabela_exibicao))} grupos por parlamentar, mês e categoria · "
                "Snapshot público sem CPF ou fornecedores.",
            )
        )

    if not tabela_exibicao.empty:
        if ordem_tabela == "Maior valor líquido":
            tabela_exibicao = tabela_exibicao.sort_values("Valor líquido", ascending=False, kind="stable")
        elif ordem_tabela == "Menor valor líquido":
            tabela_exibicao = tabela_exibicao.sort_values("Valor líquido", ascending=True, kind="stable")
        elif ordem_tabela == "Mais documentos":
            tabela_exibicao = tabela_exibicao.sort_values("Documentos", ascending=False, kind="stable")
        elif ordem_tabela == "Maior valor glosado":
            tabela_exibicao = tabela_exibicao.sort_values("Valor glosado", ascending=False, kind="stable")
        else:
            ordem_mes = {mes: i for i, mes in enumerate(MONTH_ORDER)}
            tabela_exibicao["_ordem_mes"] = tabela_exibicao["Mês"].map(ordem_mes)
            tabela_exibicao = (
                tabela_exibicao.sort_values(
                    ["Ano", "_ordem_mes", "Deputado", "Categoria da despesa"],
                    kind="stable",
                )
                .drop(columns=["_ordem_mes"])
            )

        if total_liquido > 0:
            participacao_serie = (tabela_exibicao["Valor líquido"].clip(lower=0) / total_liquido) * 100.0
            max_participacao = float(participacao_serie.max())
            if max_participacao <= 0:
                max_participacao = 1.0
        else:
            participacao_serie = pd.Series(0.0, index=tabela_exibicao.index)
            max_participacao = 1.0
        tabela_exibicao["Participação"] = participacao_serie
    else:
        tabela_exibicao["Participação"] = pd.Series(dtype="float64")
        max_participacao = 1.0

    colunas_exibidas = [
        "Mês",
        "Deputado",
        "UF",
        "Partido",
        "Categoria da despesa",
        "Documentos",
        "Valor dos documentos",
        "Valor glosado",
        "Valor líquido",
        "Participação",
    ]

    st.dataframe(
        tabela_exibicao,
        column_order=colunas_exibidas,
        hide_index=True,
        width="stretch",
        height=500,
        column_config={
            "Mês": st.column_config.TextColumn(width="small"),
            "UF": st.column_config.TextColumn(width="small"),
            "Partido": st.column_config.TextColumn(width="small"),
            "Documentos": st.column_config.NumberColumn(format="%,d", width="small"),
            "Valor dos documentos": st.column_config.NumberColumn(format="R$ %,.2f"),
            "Valor glosado": st.column_config.NumberColumn(format="R$ %,.2f"),
            "Valor líquido": st.column_config.NumberColumn(format="R$ %,.2f"),
            "Participação": st.column_config.ProgressColumn(
                label="Participação",
                help="Participação percentual de cada grupo sobre o valor líquido total do recorte.",
                format="%.2f%%",
                min_value=0.0,
                max_value=max_participacao,
                color="#006B3F",
                width="small",
            ),
            "ID do Deputado": None,
            "Ano": None,
        },
    )

# ── Rodapé institucional ──
atualizacao_rodape = (
    f"<span>Última modificação informada pela fonte: <strong>{escape(resumo['arquivo_fonte_modificado_em'])}</strong></span>"
    if resumo.get("arquivo_fonte_modificado_em")
    else ""
)
st.html(
    '<footer class="camara-footer">'
    '  <div class="camara-footer-meta">'
    f'    <span>Fonte: <a href="{escape(resumo["url_fonte"])}" target="_blank" rel="noopener noreferrer">'
    f'    {escape(resumo["fonte"])}</a> · Dados agregados por parlamentar, mês e categoria. '
    "    CPFs, identificadores fiscais e fornecedores não são incluídos no snapshot publicado.</span>"
    f"    {atualizacao_rodape}"
    "  </div>"
    "  <div>"
    "    Nota metodológica: o valor líquido reflete glosas e eventuais restituições registradas na CEAP. "
    "    A arquitetura deste MVP foi inspirada em um projeto real que desenvolvi para a Embrapii. "
    "    Este painel é independente e utiliza somente dados públicos da Câmara dos Deputados."
    "  </div>"
    "</footer>"
)
