import unittest

import pandas as pd

from graficos import (
    construir_graficos,
    formatar_reais_br,
    formatar_reais_compacto,
)


class TestConstruirGraficos(unittest.TestCase):
    def setUp(self) -> None:
        self.dados = pd.DataFrame(
            [
                {
                    "Mês": "Janeiro",
                    "Deputado": "Deputado A",
                    "ID do Deputado": "1",
                    "UF": "SP",
                    "Partido": "PT",
                    "Categoria da despesa": "Transporte",
                    "Documentos": 2,
                    "Valor líquido": 100.0,
                },
                {
                    "Mês": "Janeiro",
                    "Deputado": "Deputado A",
                    "ID do Deputado": "1",
                    "UF": "SP",
                    "Partido": "PT",
                    "Categoria da despesa": "Hospedagem",
                    "Documentos": 1,
                    "Valor líquido": 50.0,
                },
                {
                    "Mês": "Fevereiro",
                    "Deputado": "Deputado B",
                    "ID do Deputado": "2",
                    "UF": "RJ",
                    "Partido": "PP",
                    "Categoria da despesa": "Transporte",
                    "Documentos": 3,
                    "Valor líquido": 90.0,
                },
            ]
        )

    def test_cria_seis_visoes_com_totais_e_denominadores_corretos(self) -> None:
        graficos = construir_graficos(self.dados)

        self.assertEqual(
            set(graficos),
            {
                "mensal",
                "categorias",
                "ufs",
                "deputados",
                "partidos",
                "media_categoria",
            },
        )
        self.assertEqual(list(graficos["mensal"].data[0].x), ["Jan", "Fev"])
        self.assertEqual(list(graficos["mensal"].data[0].y), [150.0, 90.0])
        self.assertEqual(
            [row[0] for row in graficos["mensal"].data[0].customdata],
            ["Janeiro", "Fevereiro"],
        )
        self.assertEqual(list(graficos["categorias"].data[0].x), [190.0, 50.0])
        self.assertAlmostEqual(
            graficos["categorias"].data[0].customdata[0][2],
            190 / 240,
        )
        self.assertEqual(list(graficos["media_categoria"].data[0].x), [50.0, 38.0])
        self.assertEqual(list(graficos["partidos"].data[0].x), [150.0, 90.0])

    def test_inclui_padrao_br_media_mensal_e_contexto_parlamentar(self) -> None:
        graficos = construir_graficos(self.dados)

        self.assertEqual(graficos["mensal"].layout.separators, ",.")
        self.assertEqual(len(graficos["mensal"].layout.shapes), 1)
        self.assertTrue(
            any("Média mensal" in a.text for a in graficos["mensal"].layout.annotations)
        )
        self.assertEqual(
            list(graficos["deputados"].data[0].y),
            ["Deputado A (SP · PT)", "Deputado B (RJ · PP)"],
        )
        self.assertEqual(formatar_reais_br(1234.56), "R$ 1.234,56")
        self.assertEqual(formatar_reais_br(-50.0), "-R$ 50,00")
        self.assertEqual(formatar_reais_compacto(15_430_000.0), "R$ 15,43 mi")

    def test_graficos_de_filtros_vazios_apresentam_mensagem(self) -> None:
        graficos = construir_graficos(self.dados.iloc[0:0])

        self.assertEqual(len(graficos), 6)
        self.assertTrue(
            all(figura.layout.annotations[0].text.startswith("Sem dados")
                for figura in graficos.values())
        )

    def test_rejeita_dataframe_sem_campos_analiticos(self) -> None:
        with self.assertRaisesRegex(ValueError, "Colunas necessárias"):
            construir_graficos(pd.DataFrame())


if __name__ == "__main__":
    unittest.main()
