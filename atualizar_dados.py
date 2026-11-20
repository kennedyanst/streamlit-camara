"""Baixa, agrega e publica um snapshot das despesas da Câmara dos Deputados."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "dados"
CSV_PATH = DATA_DIR / "despesas_camara.csv"
SUMMARY_PATH = DATA_DIR / "resumo_dados.json"
SOURCE_URL = "https://www.camara.leg.br/cotas/Ano-{year}.csv.zip"
REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 3

SOURCE_COLUMNS = (
    "txNomeParlamentar",
    "nuDeputadoId",
    "sgUF",
    "sgPartido",
    "txtDescricao",
    "datEmissao",
    "numAno",
    "numMes",
    "vlrDocumento",
    "vlrGlosa",
    "vlrLiquido",
)

OUTPUT_COLUMNS = (
    "Ano",
    "Mês",
    "Deputado",
    "ID do Deputado",
    "UF",
    "Partido",
    "Categoria da despesa",
    "Documentos",
    "Valor dos documentos",
    "Valor glosado",
    "Valor líquido",
)

MONTH_NAMES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def _download_archive(year: int) -> tuple[bytes, str | None]:
    url = SOURCE_URL.format(year=year)
    request = Request(
        url,
        headers={"User-Agent": "PainelGastosCamara/1.0 (dados abertos)"},
    )
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                archive = response.read()
                if not archive:
                    raise ValueError("A fonte retornou um arquivo vazio.")
                return archive, response.headers.get("Last-Modified")
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            last_error = error
            if attempt == MAX_ATTEMPTS:
                break
            time.sleep(attempt * 2)
    raise RuntimeError(
        f"Não foi possível baixar os dados oficiais após {MAX_ATTEMPTS} tentativas."
    ) from last_error


def _normalizar_coluna(nome: Any) -> str:
    coluna = str(nome).strip()
    if coluna.startswith("ï»¿"):
        coluna = coluna[3:]
    return coluna.strip('"').strip()


def _normalizar_texto(valor: Any) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor)
    try:
        bytes_texto = texto.encode("cp1252")
    except UnicodeEncodeError:
        try:
            bytes_texto = texto.encode("latin-1")
        except UnicodeEncodeError:
            bytes_texto = texto.encode("utf-8")

    try:
        texto = bytes_texto.decode("utf-8")
    except UnicodeDecodeError:
        texto = bytes_texto.decode("cp1252", errors="replace")

    texto = texto.replace("\ufffd", " ")
    texto = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _ler_arquivo_csv(archive_bytes: bytes) -> pd.DataFrame:
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            arquivos_csv = [
                nome for nome in archive.namelist()
                if nome.lower().endswith(".csv")
            ]
            if len(arquivos_csv) != 1:
                raise ValueError(
                    "O ZIP da Câmara deve conter exatamente um arquivo CSV."
                )
            with archive.open(arquivos_csv[0]) as arquivo:
                dados = pd.read_csv(
                    arquivo,
                    sep=";",
                    dtype="string",
                    encoding="latin-1",
                    low_memory=False,
                )
    except zipfile.BadZipFile as error:
        raise ValueError("A fonte da Câmara não retornou um ZIP válido.") from error

    dados.columns = [_normalizar_coluna(nome) for nome in dados.columns]
    ausentes = [coluna for coluna in SOURCE_COLUMNS if coluna not in dados.columns]
    if ausentes:
        raise ValueError(
            f"O arquivo da Câmara não contém as colunas esperadas: {ausentes}"
        )
    return dados.loc[:, SOURCE_COLUMNS].copy()


def transformar_despesas(
    despesas: pd.DataFrame,
    year: int,
    source_last_modified: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Converte as transações em totais mensais sem incluir CPFs ou fornecedores."""
    dados = despesas.loc[:, SOURCE_COLUMNS].copy()
    dados["numAno"] = pd.to_numeric(dados["numAno"], errors="raise").astype("Int64")
    dados["numMes"] = pd.to_numeric(dados["numMes"], errors="raise").astype("Int64")
    dados = dados.loc[dados["numAno"].eq(year)].copy()
    if dados.empty:
        raise ValueError(f"A fonte não contém despesas para o ano {year}.")
    meses_invalidos = ~dados["numMes"].isin(MONTH_NAMES)
    if meses_invalidos.any():
        raise ValueError("A fonte contém registros com mês inválido ou ausente.")

    for coluna in ("vlrDocumento", "vlrGlosa", "vlrLiquido"):
        valores = dados[coluna].fillna("").str.strip().replace("", "0")
        dados[coluna] = pd.to_numeric(valores, errors="raise")

    dimensoes = {
        "numAno": "Ano",
        "numMes": "Mês",
        "txNomeParlamentar": "Deputado",
        "nuDeputadoId": "ID do Deputado",
        "sgUF": "UF",
        "sgPartido": "Partido",
        "txtDescricao": "Categoria da despesa",
    }
    for coluna in (
        "txNomeParlamentar",
        "nuDeputadoId",
        "sgUF",
        "sgPartido",
        "txtDescricao",
    ):
        dados[coluna] = (
            dados[coluna]
            .map(_normalizar_texto)
            .replace("", "Não informado")
        )

    agrupado = (
        dados.groupby(list(dimensoes), dropna=False, sort=False)
        .agg(
            Documentos=("numAno", "size"),
            **{
                "Valor dos documentos": ("vlrDocumento", "sum"),
                "Valor glosado": ("vlrGlosa", "sum"),
                "Valor líquido": ("vlrLiquido", "sum"),
            },
        )
        .reset_index()
        .rename(columns=dimensoes)
    )
    agrupado = agrupado.loc[:, OUTPUT_COLUMNS]
    agrupado = agrupado.sort_values(
        ["Ano", "Mês", "Deputado", "Categoria da despesa"],
        kind="stable",
    ).reset_index(drop=True)
    agrupado["Mês"] = agrupado["Mês"].map(
        lambda mes: MONTH_NAMES[int(mes)]
    )

    summary = {
        "fonte": "Câmara dos Deputados — Cota para Exercício da Atividade Parlamentar",
        "url_fonte": SOURCE_URL.format(year=year),
        "arquivo_fonte_modificado_em": source_last_modified,
        "ano": year,
        "registros_origem": int(len(dados)),
        "registros_agregados": int(len(agrupado)),
        "contagens": {
            "deputados": int(
                dados.loc[dados["nuDeputadoId"].ne("Não informado"), "nuDeputadoId"]
                .nunique()
            ),
            "categorias": int(dados["txtDescricao"].nunique()),
            "documentos": int(len(dados)),
        },
        "totais": {
            "valor_documentos": round(float(dados["vlrDocumento"].sum()), 2),
            "valor_glosado": round(float(dados["vlrGlosa"].sum()), 2),
            "valor_liquido": round(float(dados["vlrLiquido"].sum()), 2),
        },
    }
    return agrupado, summary


def validar_saida(dados: pd.DataFrame, summary: dict[str, Any]) -> None:
    ausentes = [coluna for coluna in OUTPUT_COLUMNS if coluna not in dados.columns]
    if ausentes:
        raise ValueError(f"Colunas de saída ausentes: {ausentes}")
    if dados.empty:
        raise ValueError("A agregação não gerou registros.")
    if dados.duplicated(
        [
            "Ano",
            "Mês",
            "Deputado",
            "ID do Deputado",
            "UF",
            "Partido",
            "Categoria da despesa",
        ]
    ).any():
        raise ValueError("A saída contém grupos agregados duplicados.")
    if summary["registros_origem"] != summary["contagens"]["documentos"]:
        raise ValueError("A contagem de documentos do resumo está inconsistente.")


def salvar_arquivos(
    dados: pd.DataFrame,
    summary: dict[str, Any],
    csv_path: Path = CSV_PATH,
    summary_path: Path = SUMMARY_PATH,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    csv_temp = csv_path.with_suffix(".csv.tmp")
    summary_temp = summary_path.with_suffix(".json.tmp")
    try:
        dados.to_csv(
            csv_temp,
            sep=";",
            encoding="utf-8-sig",
            index=False,
            float_format="%.2f",
        )
        summary_temp.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        csv_temp.replace(csv_path)
        summary_temp.replace(summary_path)
    finally:
        csv_temp.unlink(missing_ok=True)
        summary_temp.unlink(missing_ok=True)


def main() -> None:
    year = int(os.environ.get("ANO_DADOS", datetime.now(timezone.utc).year))
    archive, last_modified = _download_archive(year)
    source_data = _ler_arquivo_csv(archive)
    aggregated, summary = transformar_despesas(source_data, year, last_modified)
    validar_saida(aggregated, summary)
    salvar_arquivos(aggregated, summary)
    print(
        f"Snapshot {year} gerado: {summary['registros_origem']:,} documentos, "
        f"{len(aggregated):,} grupos agregados e "
        f"R$ {summary['totais']['valor_liquido']:,.2f} líquidos."
    )


if __name__ == "__main__":
    main()
