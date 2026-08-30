import json
import re
import tempfile
import unittest
from pathlib import Path

import arq_layout
import arq_modelo
import arq_render
import arquitetura
import gerar_arquitetura
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


def _todas_entradas(no, acc=None):
    # Entrada sem `modulo` casado a mao vira no automatico (Task 8) — nao
    # fica mais em `no.entradas` direto, entao os testes que so querem saber
    # "a entrada chegou em algum lugar da arvore" precisam somar recursivo.
    acc = acc if acc is not None else []
    acc.extend(no.entradas)
    for f in no.filhos:
        _todas_entradas(f, acc)
    return acc


class TestCarregar(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_no_minimo_vira_modelo_com_as_entradas_do_frescor(self):
        m = arq_modelo.carregar(self.raiz, FRESCOR_FALSO, NOS_FALSOS)
        self.assertEqual(len(m.nos), 1)
        self.assertEqual(m.nos[0].titulo, "Chatbot API")
        self.assertEqual(len(_todas_entradas(m.nos[0])), 2)

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


FRESCOR_VAZIO = {"sha": "abc1234", "inventario": {"chatbot-api": []}}


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
        # Frescor vazio: o foco aqui e' a recursao de `dentro`, nao os nos
        # automaticos da Task 8 (que so entram quando sobra entrada sem
        # `modulo` casado a mao).
        m = arq_modelo.carregar(self.raiz, FRESCOR_VAZIO, nos)
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
        m = arq_modelo.carregar(self.raiz, FRESCOR_VAZIO, nos)
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
        workers = next(f for f in raiz.filhos if f.chave == "workers")
        self.assertEqual([e.chave for e in workers.entradas], ["FollowupWorker"])
        # A raiz nao fica com a entrada direto — quem nao casou `modulo`
        # (GET /health/live, de app/main.py) vira no automatico (Task 8).
        self.assertEqual(raiz.entradas, ())
        self.assertEqual(
            [e.chave for e in _todas_entradas(raiz) if e.chave != "FollowupWorker"],
            ["GET /health/live"],
        )

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


class TestNosAutomaticos(unittest.TestCase):
    def _carrega(self, arquivos):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "rota", "chave": f"GET /{i}", "simbolo": f"s{i}",
             "arquivo": a, "linha": i + 1}
            for i, a in enumerate(arquivos)]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"}}
        return arq_modelo.carregar(raiz, frescor, nos)

    def _todos(self, no, acc=None):
        acc = acc if acc is not None else []
        acc.append(no)
        for f in no.filhos:
            self._todos(f, acc)
        return acc

    def test_diretorio_vira_no(self):
        m = self._carrega(["app/loja/vendas.py", "app/loja/metas.py",
                           "app/canais/whatsapp.py"])
        titulos = {n.titulo for n in self._todos(m.nos[0])}
        self.assertIn("loja", titulos)
        self.assertIn("canais", titulos)

    def test_arquivo_vira_folha_com_as_entradas(self):
        m = self._carrega(["app/loja/vendas.py", "app/loja/vendas.py"])
        folhas = [n for n in self._todos(m.nos[0]) if n.papel == "arquivo"]
        self.assertEqual(len(folhas), 1)
        self.assertEqual(len(folhas[0].entradas), 2)

    def test_nenhuma_entrada_fica_solta_na_raiz_do_produto(self):
        # E o defeito que motivou esta task: 154 entradas paradas no produto.
        m = self._carrega(["app/loja/vendas.py", "app/canais/whatsapp.py",
                           "app/main.py"])
        self.assertEqual(len(m.nos[0].entradas), 0)

    def test_diretorio_de_filho_unico_colapsa(self):
        m = self._carrega(["app/a/b/c.py"])
        auto = [n for n in self._todos(m.nos[0]) if n.auto]
        self.assertLessEqual(len(auto), 2, [n.chave for n in auto])

    def test_no_escrito_a_mao_nao_vem_marcado_como_auto(self):
        m = self._carrega(["app/main.py"])
        self.assertFalse(m.nos[0].auto)

    def test_continua_deterministico(self):
        a = self._carrega(["app/loja/vendas.py", "app/canais/whatsapp.py"])
        b = self._carrega(["app/canais/whatsapp.py", "app/loja/vendas.py"])
        self.assertEqual([n.chave for n in self._todos(a.nos[0])],
                         [n.chave for n in self._todos(b.nos[0])])


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


class TestVMs(unittest.TestCase):
    # A correcao determinada pelo dono: desenhar a VM foi escolha explicita
    # dele (blast radius — app2037 carrega seis produtos), nao decisao de
    # implementador dropar. dispor() precisa emitir uma Caixa tipo "vm" por
    # VM, com os produtos do seu `contem` geometricamente dentro dela.
    def test_toda_vm_vira_caixa_e_todo_produto_de_contem_cai_dentro_dela(self):
        raiz = varredura.raiz_repo()
        frescor_path = Path(__file__).resolve().parent / "mapa" / "_frescor.json"
        frescor = json.loads(frescor_path.read_text(encoding="utf-8"))
        modelo = arq_modelo.carregar(
            raiz, frescor, arquitetura.NOS,
            arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS)
        cena = arq_layout.dispor(modelo)
        por_chave = {c.chave: c for c in cena.caixas}

        for chave_vm, bruto_vm in arquitetura.VMS.items():
            self.assertIn(chave_vm, por_chave, chave_vm)
            caixa_vm = por_chave[chave_vm]
            self.assertEqual(caixa_vm.tipo, "vm", chave_vm)
            for produto in bruto_vm["contem"]:
                chave_dentro = f"{chave_vm}.{produto}"
                self.assertIn(chave_dentro, por_chave, chave_dentro)
                p = por_chave[chave_dentro]
                self.assertGreaterEqual(p.x, caixa_vm.x, chave_dentro)
                self.assertGreaterEqual(p.y, caixa_vm.y, chave_dentro)
                self.assertLessEqual(p.x + p.w, caixa_vm.x + caixa_vm.w + 0.01,
                                     chave_dentro)
                self.assertLessEqual(p.y + p.h, caixa_vm.y + caixa_vm.h + 0.01,
                                     chave_dentro)


class TestRender(unittest.TestCase):
    def _html(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "worker", "chave": "FollowupWorker", "simbolo": "F",
             "arquivo": "app/followup_job.py", "linha": 64}]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa", "dentro": {
            "canais": {"titulo": "Canais", "papel": "entrada"}}}}
        modelo = arq_modelo.carregar(raiz, frescor, nos)
        return arq_render.render(arq_layout.dispor(modelo), modelo, "/* js */")

    def test_e_auto_contido_sem_nenhuma_url_externa(self):
        # "http" cru no HTML nao e' erro: o _frescor.json real carrega
        # "https://" como TEXTO dentro de descricao de flag — isso e' dado,
        # nao recurso. O que nao pode existir e' src=/href=/fetch( apontando
        # pra fora (file:// bloqueia fetch mesmo, mas nao custa garantir).
        sem_comentario = re.sub(r"<!--.*?-->", "", self._html(), flags=re.S)
        proibido = re.compile(
            r'(?:src|href)\s*=\s*["\']https?://|fetch\(\s*["\']https?://',
            re.IGNORECASE)
        achado = proibido.search(sem_comentario)
        self.assertIsNone(achado, achado.group(0) if achado else None)

    def test_emite_as_duas_rampas(self):
        html = self._html()
        self.assertIn("data-k-min=", html)
        self.assertIn("data-face-ate=", html)

    def test_caixa_navegavel_nao_carrega_data_k_min(self):
        # Senao o aplicarLod briga com o Zoom.acender e o fluxo pisca.
        for grupo in re.findall(r"<g [^>]*>", self._html()):
            if "data-navegavel" in grupo:
                self.assertNotIn("data-k-min", grupo, grupo)

    def test_o_arquivo_e_linha_chega_no_html(self):
        self.assertIn("app/followup_job.py:64", self._html())

    def test_escapa_o_que_viria_a_ser_markup(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "rota", "chave": "GET /a<b>&c", "simbolo": "x",
             "arquivo": "app/main.py", "linha": 1}]}}
        nos = {"chatbot-api": {"titulo": "C", "papel": "x"}}
        modelo = arq_modelo.carregar(raiz, frescor, nos)
        html = arq_render.render(arq_layout.dispor(modelo), modelo, "")
        self.assertNotIn("<b>", html)

    def test_o_js_entra_inteiro(self):
        self.assertIn("/* js */", self._html())

    def test_aresta_assincrona_sai_tracejada_e_marca_falta_de_retry(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [], "estoque-api": []}}
        nos = {"chatbot-api": {"titulo": "A", "papel": "x"},
               "estoque-api": {"titulo": "B", "papel": "y"}}
        arestas = [{"de": "chatbot-api", "para": "estoque-api",
                    "protocolo": "http", "sincrono": False, "retry": False}]
        modelo = arq_modelo.carregar(raiz, frescor, nos, arestas)
        html = arq_render.render(arq_layout.dispor(modelo), modelo, "")
        self.assertIn("stroke-dasharray", html)
        self.assertIn("sem retry", html)


class TestCli(unittest.TestCase):
    def test_gerar_escreve_arquivo_nao_vazio(self):
        raiz = varredura.raiz_repo()
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "arquitetura.html"
            gerar_arquitetura.gerar(raiz, destino)
            self.assertGreater(len(destino.read_text(encoding="utf-8")), 5000)

    def test_gerar_duas_vezes_da_bytes_identicos(self):
        raiz = varredura.raiz_repo()
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.html", Path(tmp) / "b.html"
            gerar_arquitetura.gerar(raiz, a)
            gerar_arquitetura.gerar(raiz, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_verificar_passa_com_o_html_commitado(self):
        # Se falhar: rode `python3 gerar_arquitetura.py` e commite o resultado.
        self.assertEqual(gerar_arquitetura.main(["--verificar"]), 0)


if __name__ == "__main__":
    unittest.main()
