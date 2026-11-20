from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from atualizar_dados import CSV_PATH, SUMMARY_PATH


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@unittest.skipUnless(
    CSV_PATH.is_file() and SUMMARY_PATH.is_file(),
    "Snapshot ainda não gerado em dados/.",
)
class TestApp(unittest.TestCase):
    def test_carrega_painel_aplica_e_limpa_filtros(self) -> None:
        at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.multiselect), 5)

        at.multiselect(key="filtro_UF").select("SP").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["filtro_UF"], ["SP"])

        at.text_input(key="busca_tabela").set_value("COMBUSTÍVEIS").run()
        self.assertFalse(at.exception)

        at.selectbox(key="ordem_tabela").select("Ordem cronológica").run()
        self.assertFalse(at.exception)

        at.button[0].click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["filtro_UF"], [])


if __name__ == "__main__":
    unittest.main()
