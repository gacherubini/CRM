import contextlib
import io
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

ZOOM_JS = Path(__file__).resolve().parent.joinpath("arq_zoom.js").read_text(encoding="utf-8")


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


def _todos_nos(no, acc=None):
    # Mesma ideia de _todas_entradas, so que devolvendo os NOS (pra checar
    # titulo/chave/auto de qualquer profundidade, nao so as entradas).
    acc = acc if acc is not None else []
    acc.append(no)
    for f in no.filhos:
        _todos_nos(f, acc)
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
            arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS,
            arquitetura.BANCOS)
        self.assertGreaterEqual(len(m.nos), 6)
        self.assertEqual(len(m.bancos), len(arquitetura.BANCOS))

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


class TestFiltrar(unittest.TestCase):
    # Task 9: as secoes viram duas vistas (Arquitetura x Schema). O teste
    # que importa e o catalogo-publico: zero `modelo`/`migration` (ver
    # contagem real na task), entao ele tem que sumir da vista Schema.
    def setUp(self):
        self.raiz = varredura.raiz_repo()
        frescor_path = Path(__file__).resolve().parent / "mapa" / "_frescor.json"
        self.frescor = json.loads(frescor_path.read_text(encoding="utf-8"))
        self.modelo = arq_modelo.carregar(
            self.raiz, self.frescor, arquitetura.NOS,
            arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS,
            arquitetura.BANCOS)

    def test_catalogo_publico_some_da_vista_schema(self):
        schema = arq_modelo.filtrar(self.modelo, arquitetura.SECOES_SCHEMA)
        self.assertNotIn("catalogo-publico", {n.chave for n in schema.nos})

    def test_suite_pg_mantem_portal_e_trafego_na_vista_schema(self):
        schema = arq_modelo.filtrar(self.modelo, arquitetura.SECOES_SCHEMA)
        chaves = {n.chave for n in schema.nos}
        self.assertIn("portal-gestao", chaves)
        self.assertIn("revy-trafego", chaves)
        suite_pg = next(b for b in schema.bancos if b.chave == "suite-pg")
        self.assertEqual(suite_pg.contem, ("portal-gestao", "revy-trafego"))

    def test_nenhuma_entrada_de_rota_sobrevive_na_vista_schema(self):
        schema = arq_modelo.filtrar(self.modelo, arquitetura.SECOES_SCHEMA)
        for no in schema.nos:
            for e in _todas_entradas(no):
                self.assertNotEqual(e.secao, "rota", f"{no.chave}: {e.chave}")

    def test_nenhuma_entrada_de_modelo_sobrevive_na_vista_arquitetura(self):
        arq = arq_modelo.filtrar(self.modelo, arquitetura.SECOES_ARQUITETURA)
        for no in arq.nos:
            for e in _todas_entradas(no):
                self.assertNotEqual(e.secao, "modelo", f"{no.chave}: {e.chave}")

    def test_no_auto_cujo_arquivo_so_tinha_rota_some_da_vista_schema(self):
        # Modelo pequeno a mao (nao depende do inventario real): um arquivo
        # so com `rota` e outro so com `modelo`, ambos sem `modulo` casado —
        # os dois viram no automatico (Task 8). Filtrar pra Schema tem que
        # refazer a arvore automatica, nao so podar a antiga, senao o
        # diretorio do arquivo-so-rota sobra vazio.
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "rota", "chave": "GET /x", "simbolo": "x",
             "arquivo": "app/so_rota.py", "linha": 1},
            {"secao": "modelo", "chave": "Pessoa", "simbolo": "Pessoa",
             "arquivo": "app/modelos.py", "linha": 1},
        ]}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"}}
        modelo = arq_modelo.carregar(self.raiz, frescor, nos)
        schema = arq_modelo.filtrar(modelo, arquitetura.SECOES_SCHEMA)
        titulos = {n.titulo for n in _todos_nos(schema.nos[0])}
        self.assertNotIn("so_rota.py", titulos)
        self.assertIn("modelos.py", titulos)

    def test_secao_desconhecida_avisa_e_nao_levanta(self):
        frescor = {"sha": "a", "inventario": {"chatbot-api": [
            {"secao": "trigger-fantasma", "chave": "X", "simbolo": "x",
             "arquivo": "app/x.py", "linha": 1}]}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gerar_arquitetura._avisar_secoes_desconhecidas(frescor)
        self.assertIn("trigger-fantasma", buf.getvalue())

    def test_referencia_morta_quando_banco_contem_no_inexistente(self):
        bancos = {"banco-fantasma": {"tipo": "postgres",
                                      "contem": ["produto-fantasma"]}}
        with self.assertRaises(arq_modelo.ReferenciaMorta) as ctx:
            arq_modelo.carregar(self.raiz, FRESCOR_FALSO, NOS_FALSOS,
                                 (), None, None, bancos)
        self.assertIn("produto-fantasma", str(ctx.exception))


class TestDisporSchema(unittest.TestCase):
    def test_vista_schema_produz_cena_valida_sem_caixa_orfa(self):
        raiz = varredura.raiz_repo()
        frescor_path = Path(__file__).resolve().parent / "mapa" / "_frescor.json"
        frescor = json.loads(frescor_path.read_text(encoding="utf-8"))
        modelo = arq_modelo.carregar(
            raiz, frescor, arquitetura.NOS, arquitetura.ARESTAS,
            arquitetura.VMS, arquitetura.FLUXOS, arquitetura.BANCOS)
        m = arq_modelo.filtrar(modelo, arquitetura.SECOES_SCHEMA)
        cena = arq_layout.dispor(m, m.bancos)
        self.assertGreater(cena.largura, 0)
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if c.pai is not None:
                self.assertIn(c.pai, por_chave, f"caixa orfa: {c.chave} (pai {c.pai})")


class TestLayout(unittest.TestCase):
    def _modelo(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {
            "chatbot-api": [
                {"secao": "worker", "chave": "FollowupWorker", "simbolo": "F",
                 "arquivo": "app/followup_job.py", "linha": 64}],
            "estoque-api": [
                {"secao": "rota", "chave": "GET /public/veiculos",
                 "simbolo": "listar_veiculos", "arquivo": "app/main.py",
                 "linha": 10}],
        }}
        nos = {
            "chatbot-api": {"titulo": "Chatbot", "papel": "conversa", "dentro": {
                "canais": {"titulo": "Canais", "papel": "entrada", "dentro": {
                    "loja-a": {"titulo": "WhatsApp loja A", "papel": "canal"}}}}},
            # Segundo produto solto, sem relacao com o chatbot-api alem de
            # dividir o nivel 1. Sem ele, chatbot-api e o UNICO no do
            # nivel 1 e cena.largura == chatbot-api.w sempre (razao 1.0
            # exata) — nenhum piso de k_min > 0 passaria no teste abaixo, e
            # nao por empacotamento ruim: uma cena de UM no nao tem como
            # ter um pai que nao seja "a tela inteira". O dado real sempre
            # tem produtos/VMs irmaos (arquitetura.py tem 6 produtos e 5
            # VMs); o mock precisa do mesmo formato pra nao testar uma
            # forma que nunca ocorre fora do teste.
            "estoque-api": {"titulo": "Estoque", "papel": "veiculos"},
        }
        return arq_modelo.carregar(raiz, frescor, nos)

    def test_e_deterministico_byte_a_byte(self):
        self.assertEqual(arq_layout.dispor(self._modelo(), self._modelo().vms),
                         arq_layout.dispor(self._modelo(), self._modelo().vms))

    def test_desce_ate_o_neto(self):
        niveis = {c.nivel for c in arq_layout.dispor(self._modelo(), self._modelo().vms).caixas}
        self.assertIn(3, niveis, "o neto (loja-a) nao virou caixa")

    def test_filho_cabe_dentro_do_pai_em_todo_nivel(self):
        cena = arq_layout.dispor(self._modelo(), self._modelo().vms)
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
        cena = arq_layout.dispor(self._modelo(), self._modelo().vms)
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if not c.pai or c.pai not in por_chave:
                continue
            k_do_pai_cheio = cena.largura / por_chave[c.pai].w
            self.assertLess(c.k_min, k_do_pai_cheio, f"{c.chave} nunca acende")

    def test_id_de_caixa_e_unico(self):
        chaves = [c.chave for c in arq_layout.dispor(self._modelo(), self._modelo().vms).caixas]
        self.assertEqual(len(chaves), len(set(chaves)))

    def _modelo_real(self):
        raiz = varredura.raiz_repo()
        frescor_path = Path(__file__).resolve().parent / "mapa" / "_frescor.json"
        frescor = json.loads(frescor_path.read_text(encoding="utf-8"))
        return arq_modelo.carregar(
            raiz, frescor, arquitetura.NOS,
            arquitetura.ARESTAS, arquitetura.VMS, arquitetura.FLUXOS)

    def test_limiar_nunca_abre_sozinho_no_zoom_inicial(self):
        # Defeito A: `k_min = 0.6 * (cena/pai)` supoe o pai bem menor que a
        # cena. app2037 e 97% da largura da cena original, entao a razao
        # dava ~1.03 e k_min saia 0.62 — abaixo do zoom inicial (k=1), e o
        # interior de todo produto ja abria no primeiro quadro. Piso: 1.6.
        cena = arq_layout.dispor(self._modelo_real(), self._modelo_real().vms)
        por_chave = {c.chave: c for c in cena.caixas}
        for c in cena.caixas:
            if c.pai and c.pai in por_chave:
                self.assertGreaterEqual(c.k_min, 1.6, c.chave)

    def test_a_cena_nao_e_uma_tira(self):
        # Defeito B: a grade `ceil(sqrt(n))` colunas nao levava em conta que
        # os filhos tem larguras muito diferentes, e a cena saia 19348x3739
        # (razao 5.2) — uma tira. Meta: entre 1.0 e 2.2 (~16:10 a ~2.2:1).
        cena = arq_layout.dispor(self._modelo_real(), self._modelo_real().vms)
        razao = cena.largura / cena.altura
        self.assertGreaterEqual(razao, 1.0, f"cena {cena.largura:.0f}x{cena.altura:.0f}")
        self.assertLessEqual(razao, 2.2, f"cena {cena.largura:.0f}x{cena.altura:.0f}")

    def test_vm_vazia_tem_tamanho_visivel(self):
        # Defeito C: motor2037, n8n2037, evolution2037 e suite-pg nao
        # contem produto, entao saiam do tamanho do titulo — um selo de
        # 238x82 ao lado de uma VM de 18824, ilegivel e mal clicavel no
        # nivel 1.
        cena = arq_layout.dispor(self._modelo_real(), self._modelo_real().vms)
        vms = [c for c in cena.caixas if c.tipo == "vm"]
        maior_w = max(c.w for c in vms)
        maior_h = max(c.h for c in vms)
        for c in vms:
            self.assertGreaterEqual(c.w, maior_w * 0.12, c.chave)
            self.assertGreaterEqual(c.h, maior_h * 0.12, c.chave)


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
        cena = arq_layout.dispor(modelo, modelo.vms)
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
        vista = arq_render.Vista("arquitetura", "Arquitetura",
                                 arq_layout.dispor(modelo, modelo.vms), modelo)
        return arq_render.render((vista,), "/* js */")

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
        vista = arq_render.Vista("arquitetura", "Arquitetura",
                                 arq_layout.dispor(modelo, modelo.vms), modelo)
        html = arq_render.render((vista,), "")
        self.assertNotIn("<b>", html)

    def test_subtitulo_truncado_nunca_fica_maior_que_o_original(self):
        # `sub[-0:]` devolve a string inteira, nao vazia: sem guarda, uma caixa
        # estreita produzia "…" + texto completo — pior que nao truncar.
        import arq_layout as _al
        estreita = _al.Caixa(chave="x", tipo="item", titulo="t",
                             subtitulo="app/um/caminho/bem/longo.py:1234",
                             x=0, y=0, w=6, h=13, pai="p", nivel=3,
                             k_min=2.0, k_face=2.0)
        saida = arq_render._item(estreita)
        self.assertNotIn("app/um/caminho/bem/longo.py:1234", saida)

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
        vista = arq_render.Vista("arquitetura", "Arquitetura",
                                 arq_layout.dispor(modelo, modelo.vms), modelo)
        html = arq_render.render((vista,), "")
        self.assertIn("stroke-dasharray", html)
        self.assertIn("sem retry", html)


class TestFluxos(unittest.TestCase):
    # Task 7: sem isto, FLUXOS e carregado, validado e ignorado — os itens
    # "fluxo de auth" e "fluxo critico do produto" do pedido original
    # ficam sem resposta. `_fluxos_html` e o seletor; `Zoom.acender`
    # (arq_zoom.js) e quem apaga o resto da cena sem faze-lo sumir.
    def test_o_fluxo_vira_seletor_com_os_passos_em_ordem(self):
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": [],
                                              "motor-simulacao": []}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"},
               "motor-simulacao": {"titulo": "Motor", "papel": "banco"}}
        fluxos = {"simular": {
            "titulo": "WhatsApp → simulação",
            "passos": [{"no": "chatbot-api", "faz": "interpreta"},
                       {"no": "motor-simulacao", "faz": "simula",
                        "sincrono": False}],
            "invariante": "a parcela nao volta ao cliente pelo bot"}}
        modelo = arq_modelo.carregar(raiz, frescor, nos, (), None, fluxos)
        vista = arq_render.Vista("arquitetura", "Arquitetura",
                                 arq_layout.dispor(modelo, modelo.vms), modelo)
        html = arq_render.render((vista,), "")
        self.assertIn("WhatsApp → simulação", html)
        self.assertIn("a parcela nao volta ao cliente pelo bot", html)
        # A ordem dos passos e conteudo do fluxo, nao pode sair alfabetica.
        # Conferida no JSON embutido, nao no <ol>: a lista passou a ser montada
        # no navegador, so para o fluxo escolhido — concatenar os quatro no HTML
        # fazia cada clique mostrar os passos de todos os fluxos somados.
        # `FLUXOS_arquitetura` (nao `FLUXOS`): Task 10 sufixa por vista, senao
        # duas vistas com fluxo colidiriam em nome de variavel.
        bruto = html.split("var FLUXOS_arquitetura = ", 1)[1].split(";</script>", 1)[0]
        passos = json.loads(bruto.replace("\\u003c", "<"))["simular"]["passos"]
        self.assertEqual([p["faz"] for p in passos], ["interpreta", "simula"])

    def test_passo_pode_citar_vm_que_nao_e_no(self):
        # evolution2037 e n8n2037 aparecem em fluxo sem serem produto.
        raiz = varredura.raiz_repo()
        frescor = {"sha": "a", "inventario": {"chatbot-api": []}}
        nos = {"chatbot-api": {"titulo": "Chatbot", "papel": "conversa"}}
        fluxos = {"f": {"titulo": "T", "passos": [
            {"no": "evolution2037", "faz": "recebe"},
            {"no": "chatbot-api", "faz": "responde"}]}}
        m = arq_modelo.carregar(raiz, frescor, nos, (), None, fluxos)
        self.assertEqual(m.fluxos[0].passos[0].no, "evolution2037")


class TestDuasVistasNoHtml(unittest.TestCase):
    # Task 10: as duas vistas (Arquitetura x Schema) no MESMO html, com
    # alternador. `montar()` e o caminho real (o que gerar_arquitetura.py
    # escreve em arquitetura.html) — sem mock, porque o que importa aqui e
    # o HTML final que o navegador abre.
    def setUp(self):
        self.raiz = varredura.raiz_repo()
        self.html = gerar_arquitetura.montar(self.raiz)

    def _svg(self, chave):
        # Recorta o <svg id="mapa-{chave}" ...>...</svg> inteiro, sem pegar
        # o svg da outra vista (os dois tem os mesmos filhos superficiais).
        inicio = self.html.index(f'<svg id="mapa-{chave}"')
        fim = self.html.index("</svg>", inicio) + len("</svg>")
        return self.html[inicio:fim]

    def test_as_duas_vistas_tem_svg_proprio(self):
        self.assertIn('id="mapa-arquitetura"', self.html)
        self.assertIn('id="mapa-schema"', self.html)

    def test_svg_da_schema_nao_tem_aresta(self):
        self.assertNotIn("data-aresta", self._svg("schema"))

    def test_catalogo_publico_so_aparece_na_arquitetura(self):
        self.assertIn("catalogo-publico", self._svg("arquitetura"))
        self.assertNotIn("catalogo-publico", self._svg("schema"))

    def test_um_botao_data_vista_por_vista_e_so_um_ativo(self):
        botoes = re.findall(r'<button data-vista="[^"]*"[^>]*>', self.html)
        self.assertEqual(len(botoes), 2, botoes)
        chaves = {re.search(r'data-vista="([^"]*)"', b).group(1) for b in botoes}
        self.assertEqual(chaves, {"arquitetura", "schema"})
        ativos = [b for b in botoes if 'class="ativo"' in b]
        self.assertEqual(len(ativos), 1, botoes)

    def test_so_o_primeiro_svg_sai_visivel(self):
        primeiro = self.html.index('<svg id="mapa-')
        tag_primeiro = self.html[primeiro:self.html.index(">", primeiro) + 1]
        self.assertNotIn("hidden", tag_primeiro, tag_primeiro)

        segundo = self.html.index('<svg id="mapa-', primeiro + 1)
        tag_segundo = self.html[segundo:self.html.index(">", segundo) + 1]
        self.assertIn("hidden", tag_segundo, tag_segundo)

    def test_zoom_criar_uma_vez_por_vista_sem_depender_de_init(self):
        self.assertIn("criar:", ZOOM_JS)
        # window.Zoom nao expoe mais `init` — a fabrica e a UNICA porta de
        # entrada, e o render chama `criar` uma vez por svg.
        self.assertNotIn("init:", ZOOM_JS)
        self.assertEqual(self.html.count("Zoom.criar("), 2)

    def test_regra_svg_hidden_display_none_existe(self):
        # Achado no navegador (nao aparecia so lendo o codigo): `svg{
        # display:block }` (regra que ja existia antes de haver mais de um
        # <svg>) e CSS de autor, que pisa a regra padrao do navegador pra
        # `[hidden]` (CSS do user-agent, sempre perde de CSS de autor,
        # independente de especificidade). Sem uma regra `svg[hidden]{
        # display:none }` propria, o atributo `hidden` no segundo <svg> nao
        # esconde nada e as duas vistas ficam sobrepostas na tela, mesmo com
        # o atributo presente no HTML.
        estilo = self.html[self.html.index("<style>"):self.html.index("</style>")]
        self.assertIn("svg[hidden]", estilo)
        self.assertIn("display:none", estilo[estilo.index("svg[hidden]"):])

    def test_troca_de_vista_usa_atributo_hidden_nao_a_propriedade(self):
        # Achado no navegador: neste Chrome o <svg> RAIZ (SVGSVGElement) nao
        # implementa a propriedade IDL `hidden` — le `undefined`, e
        # atribuir `svgEl.hidden = true/false` nao muda o atributo nem o
        # `display` computado. `mostrarVista` (arq_render.py) tem que
        # esconder/mostrar o svg com `setAttribute`/`removeAttribute`, nunca
        # com `svgEl.hidden = ...`.
        script = self.html[self.html.rindex("<script>"):self.html.rindex("</script>")]
        self.assertIn('svgEl.setAttribute("hidden"', script)
        self.assertIn("svgEl.removeAttribute(\"hidden\")", script)
        self.assertNotIn("svgEl.hidden", script)


class TestZoomJs(unittest.TestCase):
    def test_esc_guard_usa_hasattribute_nao_a_propriedade_hidden(self):
        # Mesmo achado do teste acima, do lado do arq_zoom.js: o guard do
        # Esc (`Zoom.criar`) tem que testar `svg.hasAttribute("hidden")`,
        # nao `svg.hidden` — a propriedade le `undefined` no <svg> raiz
        # neste Chrome, entao `!svg.hidden` seria sempre true e o guard
        # nunca guardaria nada (Esc na vista escondida subiria a arvore da
        # vista visivel, invisivelmente — exatamente o defeito que o guard
        # existe para evitar).
        self.assertIn('svg.hasAttribute("hidden")', ZOOM_JS)
        self.assertNotIn("!svg.hidden", ZOOM_JS)


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
