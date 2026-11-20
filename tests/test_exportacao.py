from io import BytesIO
import unittest

from openpyxl import load_workbook
import pandas as pd

from exportacao import gerar_excel, gerar_pdf


class TestExportacao(unittest.TestCase):
    def setUp(self) -> None:
        self.dados = pd.DataFrame(
            [
                {
                    "Ano": 2026,
                    "Mês": "Janeiro",
                    "Deputado": "Deputado A",
                    "ID do Deputado": "1",
                    "UF": "SP",
                    "Partido": "PT",
                    "Categoria da despesa": "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR.",
                    "Documentos": 4,
                    "Valor dos documentos": 12500.0,
                    "Valor glosado": 500.0,
                    "Valor líquido": 12000.0,
                },
                {
                    "Ano": 2026,
                    "Mês": "Fevereiro",
                    "Deputado": "Deputado B",
                    "ID do Deputado": "2",
                    "UF": "RJ",
                    "Partido": "PP",
                    "Categoria da despesa": "PASSAGEM AÉREA - REEMBOLSO",
                    "Documentos": 1,
                    "Valor dos documentos": 0.0,
                    "Valor glosado": 0.0,
                    "Valor líquido": -250.5,
                },
            ]
        )

    def test_gerar_excel_cria_planilha_valida_e_estilizada(self) -> None:
        conteudo = gerar_excel(self.dados)
        self.assertGreater(len(conteudo), 0)

        wb = load_workbook(BytesIO(conteudo))
        self.assertEqual(wb.sheetnames, ["Despesas"])
        planilha = wb["Despesas"]
        self.assertEqual(planilha.freeze_panes, "A2")
        self.assertEqual(planilha.max_row, 3)
        self.assertEqual(planilha["A1"].fill.start_color.rgb[-6:], "005A32")

    def test_gerar_pdf_com_dados_e_filtros_ativos(self) -> None:
        conteudo = gerar_pdf(
            self.dados,
            {"UF": ["SP", "RJ"], "Partido": []},
            "Câmara dos Deputados — CEAP",
        )
        self.assertTrue(conteudo.startswith(b"%PDF-"))
        self.assertGreater(len(conteudo), 1000)

    def test_exportacoes_tratam_dataframe_vazio(self) -> None:
        vazio = self.dados.iloc[0:0]
        excel_bytes = gerar_excel(vazio)
        pdf_bytes = gerar_pdf(vazio, {"UF": ["AC"]}, "Câmara dos Deputados — CEAP")

        self.assertGreater(len(excel_bytes), 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
