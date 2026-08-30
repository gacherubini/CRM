import json
import unittest
from pathlib import Path

import arq_layout
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


class TestRecursivo(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_no_com_dentro_de_dois_niveis_carrega_e_filhos_de_filhos_existe(self):
        nos = {
            "chatbot-api": {
                "titulo": "Chatbot API", "papel": "conversa",
                "dentro": {
                    "canais": {
                        "titulo": "Canais", "papel": "entrada",
                        "dentro": {
                            "whatsapp": {"titulo": "WhatsApp", "papel": "canal"},
                        },
                    },
                },
            },
        }
        m = arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertEqual(len(m.nos[0].filhos), 1)
        self.assertEqual(m.nos[0].filhos[0].chave, "canais")
        self.assertEqual(len(m.nos[0].filhos[0].filhos), 1)
        self.assertEqual(m.nos[0].filhos[0].filhos[0].chave, "whatsapp")

    def test_sub_no_fora_do_frescor_carrega_sem_referencia_morta(self):
        nos = {
            "chatbot-api": {
                "titulo": "Chatbot API", "papel": "conversa",
                "dentro": {
                    "evolution": {"titulo": "Evolution", "papel": "canal"},
                },
            },
        }
        # Nao deve levantar: "evolution" nunca vai existir em _frescor.json,
        # e nao deveria precisar — e estrutura de dominio, nao produto.
        m = arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertEqual(m.nos[0].filhos[0].chave, "evolution")

    def test_sub_no_com_modulo_recebe_a_entrada_e_ela_some_da_raiz(self):
        nos = {
            "chatbot-api": {
                "titulo": "Chatbot API", "papel": "conversa",
                "dentro": {
                    "workers": {"titulo": "Workers", "papel": "fundo",
                                "modulo": "app/followup_job.py"},
                },
            },
        }
        m = arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        raiz = m.nos[0]
        workers = raiz.filhos[0]
        self.assertEqual([e.chave for e in workers.entradas], ["FollowupWorker"])
        self.assertEqual([e.chave for e in raiz.entradas], ["GET /health/live"])

    def test_sub_no_com_decisao_inexistente_ainda_levanta_referencia_morta(self):
        nos = {
            "chatbot-api": {
                "titulo": "Chatbot API", "papel": "conversa",
                "dentro": {
                    "evolution": {"titulo": "Evolution", "papel": "canal",
                                  "decisoes": ["2099-01-01-nunca-escrita.md"]},
                },
            },
        }
        with self.assertRaises(arq_modelo.ReferenciaMorta) as ctx:
            arq_modelo.carregar(self.raiz, FRESCOR_FALSO, nos)
        self.assertIn("2099-01-01-nunca-escrita.md", str(ctx.exception))


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


class TestLayout(unittest.TestCase):
    def _modelo(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "worker", "chave": "FollowupWorker", "simbolo": "F",
             "arquivo": "app/followup_job.py", "linha": 64}]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa", "dentro": {
            "canais": {"titulo": "Canais", "papel": "entrada", "dentro": {
                "loja-a": {"titulo": "WhatsApp loja A", "papel": "canal"}}}}}}
        return arq_modelo.carregar(raiz, frescor, nos)

    def test_e_deterministico_byte_a_byte(self):
        self.assertEqual(arq_layout.dispor(self._modelo()),
                         arq_layout.dispor(self._modelo()))

    def test_desce_ate_o_neto(self):
        niveis = {c.nivel for c in arq_layout.dispor(self._modelo()).caixas}
        self.assertIn(3, niveis, "o neto (loja-a) nao virou caixa")

    def test_filho_cabe_dentro_do_pai_em_todo_nivel(self):
        cena = arq_layout.dispor(self._modelo())
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if not c.pai or c.pai not in por_chave:
                continue
            p = por_chave[c.pai]
            self.assertGreaterEqual(c.x, p.x, c.chave)
            self.assertGreaterEqual(c.y, p.y, c.chave)
            self.assertLessEqual(c.x + c.w, p.x + p.w + 0.01, c.chave)
            self.assertLessEqual(c.y + c.h, p.y + p.h + 0.01, c.chave)

    def test_o_limiar_e_alcancavel_clicando_no_pai(self):
        # O bug real: k_min acima do k que clicar no pai atinge deixa o
        # interior invisivel para sempre.
        cena = arq_layout.dispor(self._modelo())
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if not c.pai or c.pai not in por_chave:
                continue
            k_do_pai_cheio = cena.largura / por_chave[c.pai].w
            self.assertLess(c.k_min, k_do_pai_cheio, f"{c.chave} nunca acende")

    def test_id_de_caixa_e_unico(self):
        chaves = [c.chave for c in arq_layout.dispor(self._modelo()).caixas]
        self.assertEqual(len(chaves), len(set(chaves)))


if __name__ == "__main__":
    unittest.main()
