import unittest

import pandas as pd

from atualizar_dados import (
    OUTPUT_COLUMNS,
    SOURCE_COLUMNS,
    transformar_despesas,
    validar_saida,
)


def linha(
    deputado: str,
    deputado_id: str,
    mes: str,
    valor: str,
    categoria: str = "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR",
) -> dict[str, str]:
    return {
        "txNomeParlamentar": deputado,
        "nuDeputadoId": deputado_id,
        "sgUF": "DF",
        "sgPartido": "PV",
        "txtDescricao": categoria,
        "datEmissao": f"2026-{mes}-15T00:00:00",
        "numAno": "2026",
        "numMes": mes.lstrip("0"),
        "vlrDocumento": valor,
        "vlrGlosa": "10.00",
        "vlrLiquido": str(float(valor) - 10),
    }


class TestTransformarDespesas(unittest.TestCase):
    def test_agrega_despesas_e_omite_identificadores_pessoais(self) -> None:
        source = pd.DataFrame(
            [
                linha("Deputado A", "1", "01", "110.00"),
                linha("Deputado A", "1", "01", "90.00"),
                linha("Deputado B", "2", "02", "50.00", "PASSAGENS AÉREAS"),
            ],
            columns=SOURCE_COLUMNS,
        )
        result, summary = transformar_despesas(source, 2026)
        validar_saida(result, summary)

        self.assertEqual(len(result), 2)
        self.assertEqual(int(result["Documentos"].sum()), 3)
        self.assertEqual(float(result["Valor líquido"].sum()), 220.0)
        self.assertEqual(summary["contagens"]["deputados"], 2)
        self.assertEqual(tuple(result.columns), OUTPUT_COLUMNS)
        self.assertNotIn("cpf", result.columns)
        self.assertNotIn("txtCNPJCPF", result.columns)
        self.assertNotIn("Fornecedor", result.columns)

    def test_filtra_ano_solicitado(self) -> None:
        source = pd.DataFrame(
            [
                linha("Deputado A", "1", "01", "110.00"),
                {**linha("Deputado B", "2", "01", "50.00"), "numAno": "2025"},
            ],
            columns=SOURCE_COLUMNS,
        )
        result, summary = transformar_despesas(source, 2026)

        self.assertEqual(len(result), 1)
        self.assertEqual(summary["registros_origem"], 1)

    def test_remove_caracteres_de_codificacao_invalidos(self) -> None:
        source = pd.DataFrame(
            [
                linha(
                    "Deputado\ufffd A",
                    "1",
                    "01",
                    "110.00",
                    "DIVULGAÃ‡ÃƒO DA ATIVIDADE PARLAMENTAR",
                )
            ],
            columns=SOURCE_COLUMNS,
        )
        result, _ = transformar_despesas(source, 2026)

        self.assertEqual(result.iloc[0]["Deputado"], "Deputado A")
        self.assertEqual(
            result.iloc[0]["Categoria da despesa"],
            "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR",
        )

    def test_preserva_texto_cp1252_legivel(self) -> None:
        source = pd.DataFrame(
            [linha("MANUTENÇÃO", "1", "01", "110.00", "PASSAGENS AÉREAS")],
            columns=SOURCE_COLUMNS,
        )
        result, _ = transformar_despesas(source, 2026)

        self.assertEqual(result.iloc[0]["Deputado"], "MANUTENÇÃO")
        self.assertEqual(result.iloc[0]["Categoria da despesa"], "PASSAGENS AÉREAS")

    def test_erro_quando_nao_ha_dados_para_o_ano(self) -> None:
        source = pd.DataFrame([linha("Deputado A", "1", "01", "110.00")], columns=SOURCE_COLUMNS)
        with self.assertRaisesRegex(ValueError, "não contém despesas"):
            transformar_despesas(source, 2025)

    def test_erro_quando_mes_invalido(self) -> None:
        source = pd.DataFrame(
            [{**linha("Deputado A", "1", "01", "110.00"), "numMes": "13"}],
            columns=SOURCE_COLUMNS,
        )
        with self.assertRaisesRegex(ValueError, "mês inválido"):
            transformar_despesas(source, 2026)


if __name__ == "__main__":
    unittest.main()
