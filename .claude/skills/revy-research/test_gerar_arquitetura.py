import json
import unittest
from pathlib import Path

import arq_modelo
import arquitetura
import varredura


FRESCOR_FALSO = {
    "sha": "abc1234",
    "inventario": {
        "chatbot-api": [
            {"secao": "rota", "chave": "GET /health/live",
             "simbolo": "/health/live", "arquivo": "app/main.py", "linha": 523},
            {"secao": "worker", "chave": "FollowupWorker",
             "simbolo": "FollowupWorker", "arquivo": "app/followup_job.py",
             "linha": 64},
        ],
    },
}
NOS_FALSOS = {"chatbot-api": {"titulo": "Chatbot API", "papel": "conversa"}}


class TestCarregar(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_no_minimo_vira_modelo_com_as_entradas_do_frescor(self):
        m = arq_modelo.carregar(self.raiz, FRESCOR_FALSO, NOS_FALSOS)
        self.assertEqual(len(m.nos), 1)
        self.assertEqual(m.nos[0].titulo, "Chatbot API")
        self.assertEqual(len(m.nos[0].entradas), 2)

    def test_produto_que_nao_existe_no_frescor_falha_nomeando_o_produto(self):
        nos = {"produto-fantasma": {"titulo": "Fantasma", "papel": "nada"}}
        with self.assertRaises(arq_modelo.ReferenciaMorta) as ctx:
            arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertIn("produto-fantasma", str(ctx.exception))

    def test_decisao_que_nao_existe_falha_nomeando_o_arquivo(self):
        nos = {"chatbot-api": {"titulo": "Chatbot API", "papel": "conversa",
                               "decisoes": ["2099-01-01-nunca-escrita.md"]}}
        with self.assertRaises(arq_modelo.ReferenciaMorta) as ctx:
            arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertIn("2099-01-01-nunca-escrita.md", str(ctx.exception))

    def test_modelo_e_ordenado_por_chave_sempre(self):
        nos = {
            "chatbot-api": {"titulo": "B", "papel": "x"},
            "estoque-api": {"titulo": "A", "papel": "y"},
        }
        frescor = {"sha": "a", "inventario": {"chatbot-api": [], "estoque-api": []}}
        m = arq_modelo.carregar(self.raiz, frescor, nos)
        self.assertEqual([n.chave for n in m.nos], ["chatbot-api", "estoque-api"])


class TestArquiteturaReal(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()
        frescor_path = (Path(__file__).resolve().parent / "mapa" / "_frescor.json")
        self.frescor = json.loads(frescor_path.read_text(encoding="utf-8"))

    def test_o_arquivo_real_carrega_sem_referencia_morta(self):
        m = arq_modelo.carregar(
            self.raiz, self.frescor, arquitetura.NOS,
            arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS)
        self.assertGreaterEqual(len(m.nos), 6)

    def test_todo_produto_do_frescor_tem_no(self):
        faltando = set(self.frescor["inventario"]) - set(arquitetura.NOS)
        self.assertEqual(faltando, set(), f"produto sem no: {faltando}")

    def test_app2037_carrega_seis_produtos(self):
        # O fato de infra que hoje nao esta desenhado em lugar nenhum: uma
        # maquina que cai leva seis coisas junto.
        self.assertEqual(len(arquitetura.VMS["app2037"]["contem"]), 6)

    def test_todo_no_tem_titulo_e_papel(self):
        for chave, no in arquitetura.NOS.items():
            self.assertIn("titulo", no, chave)
            self.assertIn("papel", no, chave)


if __name__ == "__main__":
    unittest.main()
