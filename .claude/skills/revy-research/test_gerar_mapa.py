import contextlib
import copy
import io
import ast
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cruzamentos
import extratores
import gerar_mapa
import varredura


class TestVarredura(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_raiz_do_repo_tem_agents_md(self):
        self.assertTrue((self.raiz / "AGENTS.md").exists())

    def test_acha_arquivos_do_chatbot(self):
        arquivos = varredura.arquivos_py(self.raiz, "chatbot-api")
        self.assertGreater(len(arquivos), 10)

    def test_nunca_entra_em_venv_nem_pycache(self):
        for produto in varredura.PRODUTOS:
            for caminho in varredura.arquivos_py(self.raiz, produto):
                partes = caminho.parts
                self.assertNotIn(".venv", partes, f"venv vazou em {caminho}")
                self.assertNotIn("__pycache__", partes, f"pycache vazou em {caminho}")

    def test_projeto_e_muito_menor_que_a_arvore_toda(self):
        do_projeto = sum(
            len(varredura.arquivos_py(self.raiz, p)) for p in varredura.PRODUTOS
        )
        self.assertGreater(do_projeto, 300)
        self.assertLess(do_projeto, 2000)


FONTE_ROTAS = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/app/loja/agente", response_class=HTMLResponse)
def pagina_agente(request):
    return 1

@app.post("/webhook/cloud")
async def webhook_cloud(request):
    return 2

@app.exception_handler(RequestValidationError)
def nao_e_rota(request, exc):
    return 3
'''


class TestExtratorDeRotas(unittest.TestCase):
    def test_le_verbo_path_e_funcao(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        chaves = {e.chave for e in achadas}
        self.assertIn("GET /app/loja/agente", chaves)
        self.assertIn("POST /webhook/cloud", chaves)

    def test_exception_handler_nao_e_rota(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        self.assertEqual(len(achadas), 2)

    def test_simbolo_e_o_path_porque_e_isso_que_esta_na_linha(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        por_chave = {e.chave: e for e in achadas}
        self.assertEqual(por_chave["POST /webhook/cloud"].simbolo, "/webhook/cloud")

    def test_linha_aponta_para_o_decorator(self):
        achadas = extratores.rotas(FONTE_ROTAS, "app/exemplo.py")
        por_chave = {e.chave: e for e in achadas}
        linha = FONTE_ROTAS.splitlines()[por_chave["POST /webhook/cloud"].linha - 1]
        self.assertIn("/webhook/cloud", linha)

    def test_decorator_quebrado_em_varias_linhas_aponta_para_a_string(self):
        # control.py e control_ui.py escrevem assim. dec.lineno daria a linha
        # do `@router.post(`, onde o path nao esta, e o --verificar acusaria.
        fonte = (
            '@router.post(\n'
            '    "/lojas/{loja_id}/google-ads/oauth/start",\n'
            '    dependencies=[Depends(_flag)],\n'
            ')\n'
            'def inicia(request):\n'
            '    return 1\n'
        )
        achadas = extratores.rotas(fonte, 'app/web/control.py')
        self.assertEqual(len(achadas), 1)
        linha = fonte.splitlines()[achadas[0].linha - 1]
        self.assertIn(achadas[0].simbolo, linha)

    def test_no_repo_real_toda_rota_cai_numa_linha_que_contem_o_path(self):
        # a prova que o --verificar vai refazer: nenhuma rota do repo pode
        # apontar para uma linha onde o path nao esteja escrito.
        raiz = varredura.raiz_repo()
        fora = []
        for produto in varredura.PRODUTOS:
            base = raiz / produto
            for caminho in varredura.arquivos_py(raiz, produto):
                texto = caminho.read_text(encoding='utf-8', errors='replace')
                linhas = texto.splitlines()
                rel = caminho.relative_to(base).as_posix()
                for e in extratores.rotas(texto, rel):
                    if e.simbolo not in linhas[e.linha - 1]:
                        fora.append(f'{produto}/{e.arquivo}:{e.linha} {e.chave}')
        self.assertEqual(fora, [], f'{len(fora)} rotas com linha errada')

    def test_no_repo_real_o_webhook_cloud_existe(self):
        raiz = varredura.raiz_repo()
        alvo = raiz / "chatbot-api" / "app" / "main.py"
        achadas = extratores.rotas(alvo.read_text(encoding="utf-8"), "app/main.py")
        self.assertIn("POST /webhook/cloud", {e.chave for e in achadas})
        self.assertGreater(len(achadas), 30)


FONTE_PREFIXO = '''
from fastapi import FastAPI
from .rotas_oferta import router as router_oferta
from .rotas_misterio import router as router_misterio

app = FastAPI()
app.include_router(router_oferta, prefix="/v1")
app.include_router(router_misterio, prefix=PREFIXO_QUE_E_VARIAVEL)
app.include_router(router_oferta)
'''


class TestPrefixoDeRouter(unittest.TestCase):
    def test_repo_nao_tem_include_router_com_prefix(self):
        """Fica vermelho no dia em que o primeiro prefix= aparecer.

        Quando acontecer: confira no mapa que a rota saiu com o path composto
        (ou com `?`) e so entao apague este teste.
        """
        raiz = varredura.raiz_repo()
        achados = []
        for produto in varredura.PRODUTOS:
            base = raiz / produto
            for caminho in varredura.arquivos_py(raiz, produto):
                achados.extend(extratores.prefixos_de_router(
                    caminho.read_text(encoding="utf-8", errors="replace"),
                    caminho.relative_to(base).as_posix(),
                ))
        self.assertEqual(achados, [], f"apareceu prefix= no repo: {achados}")

    def test_prefixo_do_construtor_entra_na_chave_e_nao_no_simbolo(self):
        fonte = (
            "router = APIRouter(prefix=\'/v1\', tags=[\'v1\'])\n"
            "@router.get(\'/lojas/{slug}/resultados\')\n"
            "def r(request):\n"
            "    return 1\n"
        )
        achadas = extratores.rotas(fonte, "app/api_v1.py")
        self.assertEqual(len(achadas), 1)
        self.assertEqual(achadas[0].chave, "GET /v1/lojas/{slug}/resultados")
        # simbolo fica CRU: e o texto da linha, e o --verificar reabre a linha
        self.assertEqual(achadas[0].simbolo, "/lojas/{slug}/resultados")

    def test_no_repo_real_o_api_v1_do_control_sai_com_v1(self):
        raiz = varredura.raiz_repo()
        alvo = raiz / "revy-trafego" / "app" / "api_v1.py"
        achadas = extratores.rotas(alvo.read_text(encoding="utf-8"), "app/api_v1.py")
        self.assertTrue(achadas)
        for e in achadas:
            self.assertTrue(
                e.chave.split(" ", 1)[1].startswith("/v1/"),
                f"perdeu o prefixo do construtor: {e.chave}",
            )

    def test_armadilha_toda_forma_de_prefix_do_repo_e_uma_que_tratamos(self):
        """A armadilha anterior olhava so include_router e passou verde com um
        APIRouter(prefix=) no repo — o mesmo erro que ela existia para pegar.

        Esta varre QUALQUER chamada com `prefix=` e exige que o nome chamado
        esteja entre os que sabemos compor. Forma nova (uma fabrica de router,
        por exemplo) fica vermelha aqui antes de o mapa mentir.
        """
        TRATADAS = {"APIRouter", "include_router"}
        raiz = varredura.raiz_repo()
        fora = []
        for produto in varredura.PRODUTOS:
            base = raiz / produto
            for caminho in varredura.arquivos_py(raiz, produto):
                try:
                    arvore = ast.parse(
                        caminho.read_text(encoding="utf-8", errors="replace")
                    )
                except SyntaxError:
                    continue
                for no in ast.walk(arvore):
                    if not isinstance(no, ast.Call):
                        continue
                    if not any(k.arg == "prefix" for k in no.keywords):
                        continue
                    f = no.func
                    nome = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    # so interessa quem monta rota: engine_from_config(prefix=)
                    # do Alembic tambem tem prefix= e nao tem nada com path.
                    if "router" not in nome.lower():
                        continue
                    if nome not in TRATADAS:
                        rel = caminho.relative_to(base).as_posix()
                        fora.append(f"{produto}/{rel}:{no.lineno} {nome}(prefix=...)")
        self.assertEqual(fora, [], f"forma de prefix nao tratada: {fora}")

    def test_le_o_literal_e_marca_o_que_nao_e_literal(self):
        achados = extratores.prefixos_de_router(FONTE_PREFIXO, "app/main.py")
        self.assertEqual(len(achados), 2)  # o include_router sem prefix= nao conta
        por_stem = {s: p for s, p, _ in achados}
        self.assertEqual(por_stem["rotas_oferta"], "/v1")
        self.assertIsNone(por_stem["rotas_misterio"])

    def test_compoe_o_resolvido_sem_tocar_no_simbolo(self):
        rota = varredura.Entrada(
            secao="rota", chave="POST /oferta", simbolo="/oferta",
            arquivo="app/rotas_oferta.py", linha=10,
        )
        saida = extratores.aplicar_prefixos(
            [rota], [("rotas_oferta", "/v1", "app/main.py:7")]
        )
        self.assertEqual(saida[0].chave, "POST /v1/oferta")
        self.assertEqual(saida[0].simbolo, "/oferta")  # o --verificar continua achando

    def test_marca_interrogacao_quando_nao_resolve(self):
        rota = varredura.Entrada(
            secao="rota", chave="POST /x", simbolo="/x",
            arquivo="app/rotas_misterio.py", linha=3,
        )
        saida = extratores.aplicar_prefixos(
            [rota], [("rotas_misterio", None, "app/main.py:8")]
        )
        self.assertEqual(saida[0].chave, "POST /x ?")
        self.assertEqual(saida[0].simbolo, "/x")

    def test_include_sem_alias_rastreavel_vira_aviso(self):
        saida = extratores.aplicar_prefixos([], [(None, "/v1", "app/main.py:9")])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0].secao, "aviso")
        self.assertEqual(saida[0].linha, 0)


FONTE_MODELOS = '''
class Loja(Base):
    __tablename__ = "lojas"
    id = Column(Integer)

class FilaVendedor(Base):
    __tablename__ = "fila_vendedor"
'''


class TestExtratorDeModelos(unittest.TestCase):
    def test_acha_tabela_e_classe(self):
        achados = extratores.modelos(FONTE_MODELOS, "app/models_db.py")
        chaves = {e.chave for e in achados}
        self.assertEqual(chaves, {"lojas", "fila_vendedor"})

    def test_linha_aponta_para_o_tablename(self):
        achados = extratores.modelos(FONTE_MODELOS, "app/models_db.py")
        por_chave = {e.chave: e for e in achados}
        linha = FONTE_MODELOS.splitlines()[por_chave["fila_vendedor"].linha - 1]
        self.assertIn("fila_vendedor", linha)

    def test_no_repo_real_fila_vendedor_esta_em_models_db(self):
        raiz = varredura.raiz_repo()
        alvo = raiz / "chatbot-api" / "app" / "models_db.py"
        achados = extratores.modelos(alvo.read_text(encoding="utf-8"), "app/models_db.py")
        self.assertIn("fila_vendedor", {e.chave for e in achados})


class TestExtratorDeMigrations(unittest.TestCase):
    def test_conta_e_acha_o_head_do_chatbot(self):
        raiz = varredura.raiz_repo()
        entradas, head = extratores.migrations(raiz / "chatbot-api" / "alembic" / "versions")
        self.assertEqual(len(entradas), 25)
        self.assertTrue(head, "head nao pode ser vazio")

    def test_pasta_inexistente_nao_quebra(self):
        entradas, head = extratores.migrations(Path("nao/existe"))
        self.assertEqual(entradas, [])
        self.assertEqual(head, "")

    def test_le_os_dois_estilos_de_revision_do_repo(self):
        """O repo mistura `revision = "x"` e `revision: str = "x"`.

        Ler so o Assign perde metade das migrations do chatbot e quebra a
        cadeia do head (cada anotada vira uma head solta).
        """
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "0001_base.py").write_text(
                'revision: str = "0001"\n'
                'down_revision: Union[str, None] = None\n',
                encoding="utf-8",
            )
            (pasta / "0002_topo.py").write_text(
                'revision = "0002"\n'
                'down_revision = "0001"\n',
                encoding="utf-8",
            )
            entradas, head = extratores.migrations(pasta)
        self.assertEqual({e.chave for e in entradas}, {"0001", "0002"})
        self.assertEqual(head, "0002")
        self.assertEqual([e.linha for e in entradas], [0, 0])


FONTE_WORKERS = '''
class FollowupWorker:
    def rodar(self):
        pass

def iniciar_rodizio_job():
    pass
'''

FONTE_FLAGS = '''
import os
ATIVO = os.getenv("REVY_LOJA_COPILOTO_ENABLED", "0") == "1"
MODO = os.environ.get("MULTI_WHATSAPP_ENABLED", "0")
QUALQUER = os.getenv("DATABASE_URL")
'''


class TestExtratorDeWorkers(unittest.TestCase):
    def test_acha_classe_worker(self):
        achados = extratores.workers(FONTE_WORKERS, "app/modo2_workers.py")
        self.assertIn("FollowupWorker", {e.chave for e in achados})

    def test_acha_funcao_job(self):
        achados = extratores.workers(FONTE_WORKERS, "app/rodizio_job.py")
        self.assertIn("iniciar_rodizio_job", {e.chave for e in achados})

    def test_arquivo_comum_so_da_a_classe_worker(self):
        achados = extratores.workers(FONTE_WORKERS, "app/servicos.py")
        self.assertEqual({e.chave for e in achados}, {"FollowupWorker"})

    def test_arquivo_de_teste_nao_tem_worker(self):
        """`tests/test_rodizio_job.py` casa com `_job.py` e nao e worker.

        Sao 7 arquivos assim no repo; sem a guarda, cada `def test_...` deles
        entraria no mapa como job de producao.
        """
        fonte = "def test_rodizio_gira(db):\n    pass\n"
        self.assertEqual(extratores.workers(fonte, "tests/test_rodizio_job.py"), [])

    def test_worker_py_sem_underscore_tambem_conta(self):
        """O motor e o estoque chamam o worker deles de `app/worker.py`.

        So com os sufixos `_job.py`/`_workers.py` do plano, esses dois produtos
        ficariam com ZERO worker no mapa.
        """
        raiz = varredura.raiz_repo()
        for produto in ("motor-simulacao", "estoque-api"):
            alvo = raiz / produto / "app" / "worker.py"
            achados = extratores.workers(
                alvo.read_text(encoding="utf-8"), "app/worker.py"
            )
            self.assertIn("main", {e.chave for e in achados}, produto)

    def test_no_repo_real_o_followup_worker_esta_no_chatbot(self):
        raiz = varredura.raiz_repo()
        alvo = raiz / "chatbot-api" / "app" / "followup_job.py"
        texto = alvo.read_text(encoding="utf-8")
        achados = extratores.workers(texto, "app/followup_job.py")
        por_chave = {e.chave: e for e in achados}
        self.assertIn("FollowupWorker", por_chave)
        linha = texto.splitlines()[por_chave["FollowupWorker"].linha - 1]
        self.assertIn("FollowupWorker", linha)


class TestExtratorDeFlags(unittest.TestCase):
    def test_pega_revy_e_multi_com_default(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        simbolos = {e.simbolo for e in achados}
        self.assertEqual(
            simbolos, {"REVY_LOJA_COPILOTO_ENABLED", "MULTI_WHATSAPP_ENABLED"}
        )

    def test_ignora_env_que_nao_e_flag(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        self.assertNotIn("DATABASE_URL", {e.simbolo for e in achados})

    def test_registra_o_default_do_codigo(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        por_simbolo = {e.simbolo: e for e in achados}
        self.assertIn("0", por_simbolo["REVY_LOJA_COPILOTO_ENABLED"].chave)

    def test_escrever_no_environ_nao_e_declarar_flag(self):
        """`os.environ["REVY_X"] = "1"` e teste ESCREVENDO no ambiente.

        Sao 11 linhas assim no repo (quase todas no conftest do revy-trafego).
        Se entrassem, o mapa diria que a flag nasce ligada.
        """
        fonte = 'import os\nos.environ["REVY_TRAFEGO_SKIP_INIT"] = "1"\n'
        self.assertEqual(extratores.flags(fonte, "tests/conftest.py"), [])

    def test_linha_aponta_para_a_string_da_flag(self):
        achados = extratores.flags(FONTE_FLAGS, "app/config.py")
        for entrada in achados:
            linha = FONTE_FLAGS.splitlines()[entrada.linha - 1]
            self.assertIn(entrada.simbolo, linha)

    def test_flag_lida_por_helper_tambem_entra(self):
        """As flags que mais importam NAO passam por `os.getenv`.

        O portal le por `_env_bool(nome, "0")` e o control por `_env_flag(nome)`.
        Casar so `getenv` deixaria de fora REVY_LOJA_COPILOTO_ENABLED,
        REVY_LOJA_SHELL_ENABLED, REVY_CONTROL_DASHBOARD_ENABLED e companhia -
        17 flags de rollout, justo as que alguem procura no mapa.
        """
        fonte = (
            'ATIVO = _env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")\n'
            'DASH = _env_flag("REVY_CONTROL_DASHBOARD_ENABLED")\n'
            'TENT = _numero("REVY_TRAFEGO_RETRY", 60)\n'
        )
        por_simbolo = {e.simbolo: e for e in extratores.flags(fonte, "app/config.py")}
        self.assertEqual(
            set(por_simbolo),
            {
                "REVY_LOJA_COPILOTO_ENABLED",
                "REVY_CONTROL_DASHBOARD_ENABLED",
                "REVY_TRAFEGO_RETRY",
            },
        )
        self.assertIn("0", por_simbolo["REVY_LOJA_COPILOTO_ENABLED"].chave)
        # sem default literal na chamada nao se inventa default nenhum
        self.assertEqual(
            por_simbolo["REVY_CONTROL_DASHBOARD_ENABLED"].chave,
            "REVY_CONTROL_DASHBOARD_ENABLED",
        )

    def test_monkeypatch_setenv_nao_e_leitura(self):
        fonte = 'def test_x(monkeypatch):\n    monkeypatch.setenv("REVY_X", "1")\n'
        self.assertEqual(extratores.flags(fonte, "tests/test_x.py"), [])

    def test_frase_que_so_comeca_com_o_nome_da_flag_nao_entra(self):
        fonte = 'log.warning("REVY_LOJA_COPILOTO_ENABLED ligada sem chave")\n'
        self.assertEqual(extratores.flags(fonte, "app/main.py"), [])

    def test_o_gate_do_modo2_aparece_no_mapa(self):
        """Achado do ensaio cego de 23/08.

        A pergunta do ensaio era sobre o Modo 2, e a flag que liga o Modo 2
        (`CHATBOT_WHATSAPP_MODO2_ENABLED`) nao estava no mapa: o filtro so
        aceitava prefixo REVY_/MULTI_. Mapa que nao tem a flag que mais se
        procura e mapa que manda abrir o codigo — o que ele existe para evitar.
        """
        raiz = varredura.raiz_repo()
        alvo = raiz / "chatbot-api" / "app" / "config.py"
        nomes = {
            e.simbolo
            for e in extratores.flags(alvo.read_text(encoding="utf-8"), "app/config.py")
        }
        self.assertIn("CHATBOT_WHATSAPP_MODO2_ENABLED", nomes)

    def test_no_repo_real_passa_de_sessenta_flags(self):
        """Medido em 23/08: 80 leituras, 67 nomes distintos.

        O plano dizia 74; 74 e o `grep -o REVY_|MULTI_ | sort -u` cru, que conta
        pedaco de nome (`REVY_TRAFEGO_`) e nome que so aparece em comentario.
        """
        raiz = varredura.raiz_repo()
        nomes = set()
        for produto in varredura.PRODUTOS:
            base = raiz / produto
            for caminho in varredura.arquivos_py(raiz, produto):
                nomes.update(
                    e.simbolo for e in extratores.flags(
                        caminho.read_text(encoding="utf-8", errors="replace"),
                        caminho.relative_to(base).as_posix(),
                    )
                )
        self.assertGreater(len(nomes), 60)
        self.assertIn("REVY_LOJA_COPILOTO_ENABLED", nomes)
        self.assertIn("MULTI_WHATSAPP_ENABLED", nomes)


class TestExtratorDeTemplates(unittest.TestCase):
    def test_portal_tem_dezenas_de_templates(self):
        raiz = varredura.raiz_repo()
        achados = extratores.templates(raiz / "portal-gestao")
        self.assertGreater(len(achados), 40)

    def test_html_de_fixture_de_teste_nao_e_template(self):
        # o motor so tem .html sob tests/fixtures (paginas de banco salvas para
        # o Playwright). Se entrassem, o mapa diria que o motor renderiza HTML.
        raiz = varredura.raiz_repo()
        achados = extratores.templates(raiz / "motor-simulacao")
        self.assertEqual(achados, [])

    def test_chatbot_nao_tem_template(self):
        raiz = varredura.raiz_repo()
        self.assertEqual(extratores.templates(raiz / "chatbot-api"), [])

    def test_produto_inexistente_nao_quebra(self):
        self.assertEqual(extratores.templates(Path("nao/existe")), [])

    def test_le_as_tres_sintaxes_de_template_response(self):
        """O repo escreve TemplateResponse de tres jeitos.

        Nome primeiro (assinatura antiga), request primeiro (assinatura nova do
        Starlette) e tudo por keyword. Ler so um jeito perderia a maioria dos
        templates do portal e do control.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "app").mkdir()
            (base / "app" / "templates").mkdir()
            for nome in ("antiga.html", "nova.html", "keyword.html", "solta.html"):
                (base / "app" / "templates" / nome).write_text("x", encoding="utf-8")
            (base / "app" / "main.py").write_text(
                "def a(request):\n"
                '    return t.TemplateResponse("antiga.html", {"request": request})\n'
                "def b(request):\n"
                '    return t.TemplateResponse(request, "nova.html", {})\n'
                "def c(request):\n"
                "    return t.TemplateResponse(\n"
                "        request=request,\n"
                '        name="keyword.html",\n'
                "    )\n",
                encoding="utf-8",
            )
            achados = extratores.templates(base)
            por_chave = {e.chave: e for e in achados}
            linhas = (base / "app" / "main.py").read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(achados), 4)
        for nome in ("antiga.html", "nova.html", "keyword.html"):
            entrada = por_chave["app/templates/" + nome]
            self.assertEqual(entrada.arquivo, "app/main.py", nome)
            self.assertGreater(entrada.linha, 0, nome)
            self.assertIn(entrada.simbolo, linhas[entrada.linha - 1], nome)

    def test_template_solto_fica_com_linha_zero(self):
        """linha=0 no contrato do --verificar = basta o arquivo existir.

        Nao se inventa linha para template que nenhuma rota renderiza.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "orfao.html").write_text("x", encoding="utf-8")
            achados = extratores.templates(base)
        self.assertEqual(len(achados), 1)
        self.assertEqual(achados[0].linha, 0)
        self.assertEqual(achados[0].arquivo, "orfao.html")
        self.assertEqual(achados[0].simbolo, "orfao.html")

    def test_no_repo_real_a_linha_do_template_contem_o_nome(self):
        """O contrato do --verificar, checado contra o repo de verdade.

        Como quase toda chamada do repo quebra em varias linhas, a linha tem de
        ser a da STRING, nao a do `TemplateResponse(`.
        """
        raiz = varredura.raiz_repo()
        for produto in ("portal-gestao", "revy-trafego", "catalogo-publico"):
            base = raiz / produto
            renderizados = 0
            for entrada in extratores.templates(base):
                if entrada.linha == 0:
                    continue
                renderizados += 1
                texto = (base / entrada.arquivo).read_text(
                    encoding="utf-8", errors="replace"
                )
                linha = texto.splitlines()[entrada.linha - 1]
                self.assertIn(
                    entrada.simbolo, linha,
                    f"{produto} {entrada.arquivo}:{entrada.linha}",
                )
            self.assertGreater(renderizados, 0, produto)

    def test_nenhum_template_vem_de_venv_ou_node_modules(self):
        raiz = varredura.raiz_repo()
        for produto in varredura.PRODUTOS:
            for entrada in extratores.templates(raiz / produto):
                partes = entrada.chave.split("/")
                self.assertNotIn(".venv", partes, entrada.chave)
                self.assertNotIn("node_modules", partes, entrada.chave)

# Coletar o repo inteiro custa ~6s. Os testes abaixo pedem a mesma coleta
# varias vezes; sem cache a suite triplicaria de tamanho por nada.
_CACHE_DE_COLETA: dict[str, list] = {}


def coleta(produto: str) -> list:
    if produto not in _CACHE_DE_COLETA:
        _CACHE_DE_COLETA[produto] = gerar_mapa.coletar(varredura.raiz_repo(), produto)
    return _CACHE_DE_COLETA[produto]


FONTE_FAKE_MAIN = """
from fastapi import APIRouter
router = APIRouter()


class Loja(Base):
    __tablename__ = "lojas"


@router.post("/webhook/cloud")
async def webhook_cloud(request):
    return {}
"""

FONTE_FAKE_MIGRATION = """
revision = "0001"
down_revision = None
"""


def repo_de_mentira(pasta: Path) -> Path:
    """Um repo minimo: um produto com rota, modelo e migration."""
    app = pasta / "chatbot-api" / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text(FONTE_FAKE_MAIN, encoding="utf-8")
    versions = pasta / "chatbot-api" / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_schema_inicial.py").write_text(
        FONTE_FAKE_MIGRATION, encoding="utf-8"
    )
    return pasta


class TestGeracaoDoMapa(unittest.TestCase):
    def test_coleta_do_chatbot_traz_rota_e_modelo(self):
        secoes = {e.secao for e in coleta("chatbot-api")}
        self.assertIn("rota", secoes)
        self.assertIn("modelo", secoes)

    def test_todo_produto_tem_comando_de_teste_nos_dois_sos(self):
        for produto in varredura.PRODUTOS:
            self.assertIn(produto, gerar_mapa.TESTES)
            self.assertIn("macos", gerar_mapa.TESTES[produto])
            self.assertIn("windows", gerar_mapa.TESTES[produto])

    def test_revy_trafego_avisa_que_usa_o_venv_do_portal(self):
        self.assertIn("portal-gestao", gerar_mapa.TESTES["revy-trafego"]["macos"])
        self.assertIn("portal-gestao", gerar_mapa.TESTES["revy-trafego"]["windows"])

    def test_portal_no_windows_desliga_o_cache_do_pytest(self):
        # o .pytest_cache do Portal quebra com WinError 183 no Windows do dono.
        # E conhecimento de "como rodar teste", entao mora no mapa, nao num learning.
        self.assertIn("no:cacheprovider", gerar_mapa.TESTES["portal-gestao"]["windows"])

    def test_render_traz_o_sha_e_as_secoes(self):
        texto = gerar_mapa.render(
            "chatbot-api", coleta("chatbot-api"), head="0025_x", sha="abc1234"
        )
        self.assertIn("abc1234", texto)
        self.assertIn("/webhook/cloud", texto)
        self.assertIn("fila_vendedor", texto)

    def test_render_traz_a_secao_de_testes_dos_dois_sos(self):
        texto = gerar_mapa.render("revy-trafego", coleta("revy-trafego"), "0020", "a1")
        self.assertIn("## Testes", texto)
        self.assertIn(gerar_mapa.TESTES["revy-trafego"]["macos"], texto)
        self.assertIn(gerar_mapa.TESTES["revy-trafego"]["windows"], texto)
        self.assertIn(gerar_mapa.TESTES["revy-trafego"]["nota"], texto)

    def test_todo_arquivo_do_mapa_existe_no_disco(self):
        # a armadilha: a Entrada de migration guarda so o NOME do arquivo.
        # Se `coletar` nao recompoe a pasta, o mapa aponta para nada.
        raiz = varredura.raiz_repo()
        for produto in varredura.PRODUTOS:
            for e in coleta(produto):
                if e.secao == "aviso":
                    continue
                self.assertTrue(
                    (raiz / produto / e.arquivo).exists(),
                    f"{produto}/{e.arquivo} ({e.secao} {e.chave}) nao existe",
                )

    def test_migration_aponta_para_o_arquivo_e_nao_para_a_revision(self):
        # No motor a revision e "0014" mas o arquivo e
        # "0014_cliente_operacional_projecao.py": montar o caminho a partir da
        # chave daria um path que nao existe.
        migs = [e for e in coleta("motor-simulacao") if e.secao == "migration"]
        self.assertEqual(len(migs), 14)
        for e in migs:
            self.assertTrue(e.arquivo.startswith("alembic/versions/"), e.arquivo)
            self.assertTrue(e.arquivo.endswith(".py"), e.arquivo)
        self.assertIn("0014", {e.chave for e in migs})
        self.assertNotIn("alembic/versions/0014.py", {e.arquivo for e in migs})

    def test_render_escreve_o_caminho_da_migration(self):
        texto = gerar_mapa.render(
            "chatbot-api",
            coleta("chatbot-api"),
            head="0025_canal_cloud_por_loja",
            sha="abc1234",
        )
        self.assertIn("alembic/versions/0025_canal_cloud_por_loja.py", texto)
        self.assertIn("Migration head: `0025_canal_cloud_por_loja`", texto)

    def test_linha_zero_nao_vira_dois_pontos_zero(self):
        # linha == 0 quer dizer "basta o arquivo existir" (contrato do
        # --verificar). Escrever "arquivo:0" viraria um alvo impossivel.
        texto = gerar_mapa.render("portal-gestao", coleta("portal-gestao"), "x", "y")
        self.assertNotIn(":0`", texto)

    def test_produto_sem_migration_nao_quebra(self):
        texto = gerar_mapa.render(
            "catalogo-publico", coleta("catalogo-publico"), "", "s"
        )
        self.assertIn("Migration head: `n/a`", texto)
        self.assertNotIn("## Migrations", texto)

    def test_cabecalho_conta_o_que_a_secao_lista(self):
        entradas = coleta("estoque-api")
        texto = gerar_mapa.render("estoque-api", entradas, "0010", "s")
        rotas = len([e for e in entradas if e.secao == "rota"])
        self.assertIn(f"{rotas} rotas", texto.splitlines()[0])
        self.assertIn("NAO editar a mao", texto)

    def test_escrever_tudo_gera_um_md_por_produto_e_o_selo(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            raiz = repo_de_mentira(pasta / "repo")
            destino = pasta / "mapa"
            saida = io.StringIO()
            with mock.patch.object(gerar_mapa, "PASTA_MAPA", destino):
                with contextlib.redirect_stdout(saida):
                    gerar_mapa.escrever_tudo(raiz)
            for produto in varredura.PRODUTOS:
                self.assertTrue((destino / f"{produto}.md").exists(), produto)
            selo = json.loads((destino / "_frescor.json").read_text(encoding="utf-8"))
            self.assertIn("sha", selo)
            self.assertEqual(sorted(selo["inventario"]), sorted(varredura.PRODUTOS))
            self.assertIn("chatbot-api:", saida.getvalue())

    def test_selo_guarda_os_cinco_campos_da_entrada(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            raiz = repo_de_mentira(pasta / "repo")
            destino = pasta / "mapa"
            with mock.patch.object(gerar_mapa, "PASTA_MAPA", destino):
                with contextlib.redirect_stdout(io.StringIO()):
                    gerar_mapa.escrever_tudo(raiz)
            selo = json.loads((destino / "_frescor.json").read_text(encoding="utf-8"))
            itens = selo["inventario"]["chatbot-api"]
            self.assertTrue(itens)
            for item in itens:
                self.assertEqual(
                    sorted(item), ["arquivo", "chave", "linha", "secao", "simbolo"]
                )
            migs = [i for i in itens if i["secao"] == "migration"]
            self.assertEqual(
                [i["arquivo"] for i in migs],
                ["alembic/versions/0001_schema_inicial.py"],
            )

    def test_gerador_nao_escreve_segredo_no_mapa(self):
        # invariante do AGENTS.md: nada de token/cookie/.env no que vai pro git.
        texto = gerar_mapa.render("portal-gestao", coleta("portal-gestao"), "x", "y")
        for proibido in ("Bearer ", "sk-", "-----BEGIN"):
            self.assertNotIn(proibido, texto)

class TestMapaVersionadoConfere(unittest.TestCase):
    """O mapa COMO ESTA NO DISCO (o que vai pro git) tem que conferir.

    E o unico teste que le a PASTA_MAPA de verdade, sem regenerar antes. Se
    regenerasse, passaria sempre e nao provaria nada: o valor esta em pegar o
    mapa que alguem commitou envelhecendo em relacao ao codigo.
    """

    def test_o_mapa_que_esta_no_git_confere_com_o_codigo(self):
        problemas = gerar_mapa.verificar(varredura.raiz_repo())
        self.assertEqual(problemas, [], "\n".join(problemas[:20]))

    def test_o_mapa_do_disco_tem_as_seis_secoes_e_muita_entrada(self):
        selo = json.loads(
            (gerar_mapa.PASTA_MAPA / "_frescor.json").read_text(encoding="utf-8")
        )
        entradas = [e for lista in selo["inventario"].values() for e in lista]
        self.assertGreater(len(entradas), 500)
        self.assertEqual(
            {e["secao"] for e in entradas},
            {"rota", "modelo", "migration", "worker", "flag", "template"},
        )


class TestVerificacao(unittest.TestCase):
    """Contrato: linha > 0 -> a linha contem o simbolo; linha == 0 -> o arquivo existe.

    Cada teste trabalha sobre uma COPIA do selo num tempdir, com a PASTA_MAPA
    trocada. Nada aqui reescreve o mapa versionado.
    """

    @classmethod
    def setUpClass(cls):
        cls.raiz = varredura.raiz_repo()
        cls._tmp_classe = tempfile.TemporaryDirectory()
        destino = Path(cls._tmp_classe.name) / "mapa"
        with mock.patch.object(gerar_mapa, "PASTA_MAPA", destino):
            with contextlib.redirect_stdout(io.StringIO()):
                gerar_mapa.escrever_tudo(cls.raiz)
        cls.selo_fresco = json.loads(
            (destino / "_frescor.json").read_text(encoding="utf-8")
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp_classe.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.destino = Path(tmp.name) / "mapa"
        self.destino.mkdir(parents=True)
        patch = mock.patch.object(gerar_mapa, "PASTA_MAPA", self.destino)
        patch.start()
        self.addCleanup(patch.stop)
        self.selo_json = self.destino / "_frescor.json"

    def selo(self) -> dict:
        return copy.deepcopy(self.selo_fresco)

    def gravar(self, selo: dict) -> None:
        self.selo_json.write_text(
            json.dumps(selo, ensure_ascii=False), encoding="utf-8"
        )

    def test_mapa_recem_gerado_nao_tem_divergencia(self):
        self.gravar(self.selo())
        self.assertEqual(gerar_mapa.verificar(self.raiz), [])

    def test_entrada_mentirosa_e_pega(self):
        selo = self.selo()
        selo["inventario"]["chatbot-api"].append({
            "secao": "rota", "chave": "GET /inventado",
            "simbolo": "/rota-que-nao-existe-em-lugar-nenhum",
            "arquivo": "app/main.py", "linha": 1,
        })
        self.gravar(selo)
        problemas = gerar_mapa.verificar(self.raiz)
        self.assertTrue(problemas)
        self.assertIn("/rota-que-nao-existe-em-lugar-nenhum", " ".join(problemas))
        self.assertIn("app/main.py:1", " ".join(problemas))

    def test_arquivo_que_sumiu_e_pego(self):
        selo = self.selo()
        selo["inventario"]["portal-gestao"].append({
            "secao": "modelo", "chave": "Fantasma",
            "simbolo": "class Fantasma", "arquivo": "app/models_fantasma.py",
            "linha": 3,
        })
        self.gravar(selo)
        problemas = gerar_mapa.verificar(self.raiz)
        self.assertTrue(any("models_fantasma.py" in p for p in problemas))

    def test_linha_zero_so_exige_que_o_arquivo_exista(self):
        # template solto: nenhuma rota o renderiza, entao nao ha linha a apontar.
        selo = self.selo()
        selo["inventario"]["portal-gestao"].append({
            "secao": "template", "chave": "base.html",
            "simbolo": "isto nao esta escrito em lugar nenhum do arquivo",
            "arquivo": "app/templates/base.html", "linha": 0,
        })
        self.gravar(selo)
        self.assertEqual(gerar_mapa.verificar(self.raiz), [])

    def test_linha_zero_ainda_cobra_o_arquivo(self):
        selo = self.selo()
        selo["inventario"]["portal-gestao"].append({
            "secao": "template", "chave": "nao_existe.html",
            "simbolo": "nao_existe.html",
            "arquivo": "app/templates/nao_existe.html", "linha": 0,
        })
        self.gravar(selo)
        self.assertTrue(
            any("nao_existe.html" in p for p in gerar_mapa.verificar(self.raiz))
        )

    def test_linha_alem_do_fim_do_arquivo_e_pega(self):
        selo = self.selo()
        selo["inventario"]["chatbot-api"].append({
            "secao": "rota", "chave": "GET /fim", "simbolo": "/fim",
            "arquivo": "app/main.py", "linha": 999999,
        })
        self.gravar(selo)
        problemas = gerar_mapa.verificar(self.raiz)
        self.assertTrue(any("999999" in p for p in problemas))

    def test_verifica_todos_os_produtos_do_inventario(self):
        # uma mentira por produto: se o loop parasse no primeiro, viria 1 e nao 6.
        selo = self.selo()
        for produto in varredura.PRODUTOS:
            selo["inventario"][produto].append({
                "secao": "rota", "chave": f"GET /{produto}",
                "simbolo": f"/mentira-do-{produto}",
                "arquivo": "nem-este-arquivo-existe.py", "linha": 1,
            })
        self.gravar(selo)
        problemas = gerar_mapa.verificar(self.raiz)
        self.assertEqual(len(problemas), len(varredura.PRODUTOS))
        for produto in varredura.PRODUTOS:
            self.assertTrue(any(p.startswith(produto) for p in problemas), produto)

    def test_migration_do_selo_abre_a_partir_da_pasta_do_produto(self):
        # a Task 6 ja gravou "alembic/versions/<arquivo>" no selo. Se o
        # --verificar recompusesse a pasta de novo, toda migration divergiria.
        selo = self.selo()
        migs = [
            e for e in selo["inventario"]["chatbot-api"] if e["secao"] == "migration"
        ]
        self.assertTrue(migs)
        for mig in migs:
            self.assertTrue(mig["arquivo"].startswith("alembic/versions/"), mig)
            self.assertEqual(mig["arquivo"].count("alembic/versions/"), 1, mig)
        self.gravar(selo)
        self.assertEqual(gerar_mapa.verificar(self.raiz), [])

    def test_selo_ausente_avisa_em_vez_de_estourar(self):
        problemas = gerar_mapa.verificar(self.raiz)  # setUp nao gravou nada
        self.assertEqual(len(problemas), 1)
        self.assertIn("_frescor.json", problemas[0])

    def test_verificar_nao_regenera_o_mapa(self):
        # se regenerasse antes de conferir, passaria sempre e nao provaria nada.
        selo = self.selo()
        selo["inventario"]["chatbot-api"].append({
            "secao": "rota", "chave": "GET /inventado", "simbolo": "/mentira-teimosa",
            "arquivo": "app/main.py", "linha": 1,
        })
        self.gravar(selo)
        antes = self.selo_json.read_text(encoding="utf-8")
        self.assertTrue(gerar_mapa.verificar(self.raiz))
        self.assertEqual(self.selo_json.read_text(encoding="utf-8"), antes)
        self.assertEqual(list(self.destino.glob("*.md")), [])

    def test_cli_verificar_sai_zero_quando_confere(self):
        self.gravar(self.selo())
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = gerar_mapa.main(["--verificar"])
        self.assertEqual(codigo, 0)
        self.assertIn("mapa confere com o codigo", saida.getvalue())

    def test_cli_verificar_sai_um_quando_mente(self):
        selo = self.selo()
        selo["inventario"]["chatbot-api"].append({
            "secao": "rota", "chave": "GET /inventado", "simbolo": "/mentira-do-cli",
            "arquivo": "app/main.py", "linha": 1,
        })
        self.gravar(selo)
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = gerar_mapa.main(["--verificar"])
        self.assertEqual(codigo, 1)
        self.assertIn("DIVERGENCIA", saida.getvalue())
        self.assertIn("/mentira-do-cli", saida.getvalue())

    def test_cli_sem_flag_continua_gerando(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = gerar_mapa.main([])
        self.assertEqual(codigo, 0)
        self.assertTrue(self.selo_json.exists())
        self.assertTrue((self.destino / "chatbot-api.md").exists())


# ---------------------------------------------------------------- Task 8
# Cruzamentos: rota orfa, funcao sem chamador, n8n x chatbot, fly.toml.

FONTE_CLIENTE = '''
class MotorClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def listar(self):
        return self._request("GET", "/v1/provedores")

    def obter(self, nome):
        return self._request("GET", f"/v1/provedores/{nome}/credenciais")

    def criar(self, payload):
        url = f"{self.base_url}/v1/simulacoes"
        return httpx.post(url, json=payload)
'''


class TestCruzamentos(unittest.TestCase):
    def test_acha_path_literal(self):
        self.assertIn("/v1/provedores", cruzamentos.paths_chamados(FONTE_CLIENTE))

    def test_acha_path_de_fstring_normalizado(self):
        achados = cruzamentos.paths_chamados(FONTE_CLIENTE)
        self.assertIn("/v1/provedores/{}/credenciais", achados)

    def test_acha_path_montado_sobre_base_url(self):
        # chatbot-api/app/simulation.py e inventory.py so tem esta forma:
        # f"{self.base_url}/v1/..." — a versao que so olhava argumento de
        # chamada com barra inicial devolvia ZERO path para esses dois.
        self.assertIn("/v1/simulacoes", cruzamentos.paths_chamados(FONTE_CLIENTE))

    def test_a_barra_do_rstrip_nao_e_um_path(self):
        # `base_url.rstrip("/")` e um ast.Call com argumento "/". Sem este
        # filtro, TODO cliente HTTP do repo aparecia com uma rota orfa "/".
        self.assertNotIn("/", cruzamentos.paths_chamados(FONTE_CLIENTE))

    def test_normalizar_iguala_nomes_de_parametro(self):
        self.assertEqual(
            cruzamentos.normalizar("/v1/lojas/{id}"),
            cruzamentos.normalizar("/v1/lojas/{loja_id}"),
        )

    def test_todo_cliente_mapeado_aponta_para_produto_real(self):
        for arquivo, alvo in cruzamentos.ALVO_POR_CLIENTE.items():
            self.assertIn(alvo, varredura.PRODUTOS, f"{arquivo} aponta para {alvo}")

    def test_todo_cliente_mapeado_existe_no_repo(self):
        raiz = varredura.raiz_repo()
        for arquivo in cruzamentos.ALVO_POR_CLIENTE:
            self.assertTrue((raiz / arquivo).exists(), arquivo)

    def test_cada_cliente_real_rende_pelo_menos_um_path(self):
        # mede contra o repo, nao contra fonte de exemplo: se um cliente
        # passar a montar a URL de um jeito que o extrator nao le, a checagem
        # daquele cliente vira no-op em silencio.
        raiz = varredura.raiz_repo()
        for arquivo in cruzamentos.ALVO_POR_CLIENTE:
            texto = (raiz / arquivo).read_text(encoding="utf-8", errors="replace")
            self.assertTrue(cruzamentos.paths_chamados(texto), arquivo)


class TestFuncoesSemChamador(unittest.TestCase):
    def setUp(self):
        self.raiz = varredura.raiz_repo()

    def test_handler_de_rota_nao_conta_como_orfao(self):
        # handler tem decorator: quem chama e o framework, nunca o nome.
        # Sem esta regra a secao vinha com 336 linhas e ninguem leria.
        publicas = cruzamentos.funcoes_publicas(self.raiz, "chatbot-api")
        # @app.post("/v1/operacao/handoff-humano") em app/main.py:1865
        self.assertNotIn("acionar_handoff_humano", publicas)
        # @app.exception_handler(RequestValidationError) em app/main.py:112
        self.assertNotIn("erro_validacao_request", publicas)

    def test_funcao_sem_decorator_continua_entrando(self):
        publicas = cruzamentos.funcoes_publicas(self.raiz, "estoque-api")
        self.assertIn("atualizar_whatsapp_loja", publicas)

    def test_nao_olha_dentro_de_tests_nem_de_alembic(self):
        for produto in varredura.PRODUTOS:
            for _, (arquivo, _) in cruzamentos.funcoes_publicas(
                self.raiz, produto
            ).items():
                self.assertFalse(arquivo.startswith("tests/"), arquivo)
                self.assertFalse(arquivo.startswith("alembic/"), arquivo)

    def test_nome_so_importado_conta_como_usado(self):
        # payload_form entra so por `from app.campanhas import payload_form as
        # campanha_payload_form` — ast.alias, nem Name nem Attribute.
        usados = cruzamentos.nomes_usados(self.raiz)
        self.assertIn("payload_form", usados)

    def test_a_secao_nao_grita_lobo(self):
        usados = cruzamentos.nomes_usados(self.raiz)
        total = sum(
            len(cruzamentos.sem_chamador(self.raiz, p, usados))
            for p in varredura.PRODUTOS
        )
        self.assertGreater(total, 0, "detector cego nao serve para nada")
        self.assertLess(total, 40, f"{total} linhas: heuristica frouxa demais")


class TestCosturaN8n(unittest.TestCase):
    def test_acha_os_tres_arquivos_e_seus_webhooks(self):
        raiz = varredura.raiz_repo()
        workflows, _ = cruzamentos.n8n_costura(raiz)
        self.assertEqual(len(workflows), 3)
        paths = {w["webhook"] for w in workflows}
        self.assertIn("whatsapp-ai", paths)     # o canonico
        self.assertIn("whatsapp-cloud", paths)

    def test_so_dois_estao_no_ar(self):
        raiz = varredura.raiz_repo()
        workflows, _ = cruzamentos.n8n_costura(raiz)
        no_ar = {w["arquivo"] for w in workflows if w["publicado"]}
        self.assertEqual(no_ar, {"workflow-ai-nao-salvos.json", "workflow-cloud.json"})

    def test_nome_declarado_vem_do_proprio_json(self):
        raiz = varredura.raiz_repo()
        workflows, _ = cruzamentos.n8n_costura(raiz)
        por_arquivo = {w["arquivo"]: w["nome"] for w in workflows}
        self.assertEqual(por_arquivo["workflow-cloud.json"], "whatsapp-cloud")

    def test_so_conta_rota_de_workflow_no_ar(self):
        raiz = varredura.raiz_repo()
        _, chamadas = cruzamentos.n8n_costura(raiz)
        self.assertIn("/webhook/cloud", chamadas)
        self.assertIn("/v1/operacao/roteamento", chamadas)
        self.assertGreaterEqual(len(chamadas), 5)

    def test_url_de_expressao_do_n8n_vira_o_path_inteiro(self):
        # a URL do n8n e 'http://chatbot-api:8000/v1/conversas/' + expr +
        # '/pode-responder'. Cortar no primeiro apostrofo devolvia
        # "/v1/conversas/" e acusava rota faltando que nunca faltou.
        raiz = varredura.raiz_repo()
        _, chamadas = cruzamentos.n8n_costura(raiz)
        self.assertIn("/v1/conversas/{}/pode-responder", chamadas)
        self.assertNotIn("/v1/conversas", chamadas)
        self.assertNotIn("/v1/conversas/", chamadas)

    def test_nao_puxa_rota_de_workflow_fora_do_ar(self):
        # /webhook/mensagem esta nos dois: no publicado e no de teste.
        # /v1/operacao/responder so no cloud (publicado). Nada exclusivo do
        # workflow de teste pode entrar — e ele nao tem rota exclusiva hoje,
        # entao o que se prova e o tamanho do conjunto.
        raiz = varredura.raiz_repo()
        workflows, chamadas = cruzamentos.n8n_costura(raiz)
        fora = [w for w in workflows if not w["publicado"]]
        self.assertTrue(fora, "sem workflow fora do ar o teste nao prova nada")
        so_dos_publicados = set()
        for arquivo in cruzamentos.PUBLICADOS:
            so_dos_publicados |= cruzamentos.paths_do_workflow(
                raiz / "n8n" / arquivo
            )
        self.assertEqual(chamadas, so_dos_publicados)

    def test_todas_as_rotas_no_ar_estao_declaradas_no_chatbot(self):
        # a costura de maior severidade do repo: quando ela abre, o bot emudece.
        raiz = varredura.raiz_repo()
        _, chamadas = cruzamentos.n8n_costura(raiz)
        declaradas = {
            cruzamentos.normalizar(e.simbolo)
            for e in gerar_mapa.coletar(raiz, "chatbot-api")
            if e.secao == "rota"
        }
        self.assertEqual(sorted(chamadas - declaradas), [])

    def test_nao_casa_por_substring(self):
        # /v1/conversas/{}/pode-responder NAO pode casar com
        # /v1/conversas/{}/mensagens so porque compartilham prefixo
        self.assertNotEqual(
            cruzamentos.normalizar("/v1/conversas/{telefone}/pode-responder"),
            cruzamentos.normalizar("/v1/conversas/{telefone}/mensagens"),
        )


class TestFlyTomls(unittest.TestCase):
    def test_acha_os_sete_tomls_e_os_apps(self):
        raiz = varredura.raiz_repo()
        achados = dict(cruzamentos.fly_tomls(raiz))
        apps = set(achados.values())
        self.assertIn("n8n2037", apps)
        self.assertIn("portal2037", apps)
        self.assertGreaterEqual(len(achados), 6)

    def test_sao_exatamente_sete_e_nenhum_sem_app(self):
        raiz = varredura.raiz_repo()
        achados = cruzamentos.fly_tomls(raiz)
        self.assertEqual(len(achados), 7)
        for caminho, app in achados:
            self.assertNotEqual(app, "?", caminho)

    def test_nao_entra_em_venv_nem_em_pasta_de_teste(self):
        raiz = varredura.raiz_repo()
        for caminho, _ in cruzamentos.fly_tomls(raiz):
            partes = caminho.split("/")
            self.assertNotIn(".venv", partes, caminho)
            self.assertNotIn("node_modules", partes, caminho)
            for parte in partes:
                self.assertFalse(parte.startswith("test-tmp"), caminho)


class TestRenderDosCruzamentos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # render() faz uma varredura cara (nomes_usados); uma vez por classe.
        cls.raiz = varredura.raiz_repo()
        rotas = {
            produto: {
                cruzamentos.normalizar(e.simbolo)
                for e in gerar_mapa.coletar(cls.raiz, produto)
                if e.secao == "rota"
            }
            for produto in varredura.PRODUTOS
        }
        cls.texto = cruzamentos.render(cls.raiz, rotas)

    def test_traz_as_quatro_secoes(self):
        for titulo in (
            "## Rotas chamadas por cliente HTTP sem servidor declarado",
            "## Funcoes publicas sem nenhum chamador",
            "## n8n x chatbot",
            "## fly.toml no repo",
        ):
            self.assertIn(titulo, self.texto)

    def test_diz_que_e_suspeita_e_nao_erro(self):
        self.assertIn("SUSPEITA", self.texto)

    def test_tabela_do_n8n_tem_tres_linhas_e_duas_no_ar(self):
        linhas = [
            ln for ln in self.texto.splitlines()
            if ln.startswith("| `workflow-")
        ]
        self.assertEqual(len(linhas), 3)
        self.assertEqual(sum(1 for ln in linhas if ln.rstrip().endswith("SIM |")), 2)

    def test_denuncia_workflow_fora_da_tabela_publicados(self):
        self.assertIn("workflow-teste-numero-autorizado.json", self.texto)
        self.assertIn("PUBLICADOS", self.texto)

    def test_nenhuma_rota_do_n8n_aparece_sem_servidor(self):
        self.assertNotIn("SEM SERVIDOR", self.texto)

    def test_lista_os_sete_fly_tomls(self):
        linhas = [ln for ln in self.texto.splitlines() if "fly.toml` ->" in ln]
        self.assertEqual(len(linhas), 7)

    def test_nao_tem_secao_gritando(self):
        self.assertLess(len(self.texto.splitlines()), 120)


class TestCruzamentosNoGerador(unittest.TestCase):
    def test_escrever_tudo_gera_o_arquivo_de_cruzamentos(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "mapa"
            with mock.patch.object(gerar_mapa, "PASTA_MAPA", destino):
                saida = io.StringIO()
                with contextlib.redirect_stdout(saida):
                    gerar_mapa.escrever_tudo(varredura.raiz_repo())
            gerado = (destino / "_cruzamentos.md").read_text(encoding="utf-8")
            self.assertIn("## n8n x chatbot", gerado)
            self.assertIn("cruzamentos:", saida.getvalue())

    def test_cruzamentos_nao_entra_no_selo_de_frescor(self):
        # o selo so guarda Entrada; suspeita nao vira contrato de --verificar.
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "mapa"
            with mock.patch.object(gerar_mapa, "PASTA_MAPA", destino):
                with contextlib.redirect_stdout(io.StringIO()):
                    gerar_mapa.escrever_tudo(varredura.raiz_repo())
                selo = json.loads(
                    (destino / "_frescor.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    set(selo["inventario"]), set(varredura.PRODUTOS)
                )
                problemas = gerar_mapa.verificar(varredura.raiz_repo())
            self.assertEqual(problemas, [])


class TestCruzamentosVersionado(unittest.TestCase):
    def test_o_arquivo_commitado_existe_e_confere_com_o_codigo(self):
        atual = (gerar_mapa.PASTA_MAPA / "_cruzamentos.md").read_text(
            encoding="utf-8"
        )
        raiz = varredura.raiz_repo()
        # usa a MESMA funcao do gerador, nunca uma copia da regra
        rotas = {
            produto: gerar_mapa.paths_declarados(gerar_mapa.coletar(raiz, produto))
            for produto in varredura.PRODUTOS
        }
        self.assertEqual(atual, cruzamentos.render(raiz, rotas))

class TestFrescor(unittest.TestCase):
    """O frescor sai do commit que atualizou `mapa/`, nunca do sha do selo."""

    def _git(self, *args):
        subprocess.run(
            ["git", *args], cwd=self.repo,
            capture_output=True, text=True, check=True,
        )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.mapa = self.repo / gerar_mapa.CAMINHO_DO_MAPA_NO_GIT
        self.mapa.mkdir(parents=True)
        (self.repo / "chatbot-api").mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")

    def tearDown(self):
        self.tmp.cleanup()

    def _commit(self, msg):
        self._git("add", "-A")
        self._git("commit", "-q", "-m", msg)
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo,
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip()

    def test_o_bug_que_esta_proposta_consertou(self):
        """Codigo e mapa no MESMO commit nao pode acusar desatualizado.

        E o cenario que o `AGENTS.md` §6 manda produzir: mexeu em rota, regerou
        o mapa, commitou os dois juntos. Com o sha do selo (lido ANTES do
        commit) o diff lista as mudancas do proprio commit certo, e o aviso
        dispara justamente quando o agente acertou.
        """
        (self.repo / "chatbot-api" / "main.py").write_text("v1", encoding="utf-8")
        (self.mapa / "chatbot-api.md").write_text("mapa v1", encoding="utf-8")
        selo = self._commit("estado inicial")

        # agora o passo certo: muda o produto E regera o mapa, no mesmo commit
        (self.repo / "chatbot-api" / "main.py").write_text("v2", encoding="utf-8")
        (self.mapa / "chatbot-api.md").write_text("mapa v2", encoding="utf-8")
        self._commit("feat: rota nova + mapa regerado")

        # o jeito antigo (sha do selo) acusaria o proprio commit certo
        antigo = subprocess.run(
            ["git", "diff", "--name-only", f"{selo}..HEAD", "--", "chatbot-api/"],
            cwd=self.repo, capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(antigo, ["chatbot-api/main.py"], "o bug tem que existir")

        # o jeito novo fica calado, que e a resposta certa
        self.assertEqual(gerar_mapa.frescor(self.repo, ["chatbot-api"]), {})

    def test_produto_mexido_depois_do_mapa_aparece(self):
        (self.mapa / "chatbot-api.md").write_text("mapa", encoding="utf-8")
        self._commit("mapa")
        (self.repo / "chatbot-api" / "novo.py").write_text("x", encoding="utf-8")
        self._commit("feat: mexe no produto sem regerar")
        atrasados = gerar_mapa.frescor(self.repo, ["chatbot-api"])
        self.assertEqual(list(atrasados), ["chatbot-api"])
        self.assertEqual(atrasados["chatbot-api"], ["chatbot-api/novo.py"])

    def test_mexer_num_produto_nao_avisa_sobre_outro(self):
        """Aviso que dispara a toa e aviso que se aprende a ignorar."""
        (self.repo / "motor-simulacao").mkdir()
        (self.mapa / "x.md").write_text("mapa", encoding="utf-8")
        self._commit("mapa")
        (self.repo / "chatbot-api" / "novo.py").write_text("x", encoding="utf-8")
        self._commit("feat: so o chatbot")
        atrasados = gerar_mapa.frescor(self.repo, ["chatbot-api", "motor-simulacao"])
        self.assertEqual(list(atrasados), ["chatbot-api"])

    def test_sem_mapa_no_historico_nao_estoura(self):
        (self.repo / "chatbot-api" / "a.py").write_text("x", encoding="utf-8")
        self._commit("sem mapa nenhum")
        self.assertEqual(gerar_mapa.commit_do_mapa(self.repo), "")
        self.assertEqual(gerar_mapa.frescor(self.repo, ["chatbot-api"]), {})

    def test_no_repo_real_o_commit_do_mapa_tocou_o_mapa(self):
        raiz = varredura.raiz_repo()
        sha = gerar_mapa.commit_do_mapa(raiz)
        self.assertTrue(sha)
        tocados = subprocess.run(
            ["git", "show", "--name-only", "--format=", sha],
            cwd=raiz, capture_output=True, text=True, check=True,
        ).stdout
        self.assertIn(gerar_mapa.CAMINHO_DO_MAPA_NO_GIT.replace("\\", "/"), tocados)


class TestRotaComPathEmVariavel(unittest.TestCase):
    """Achado do ensaio cego de 23/08: 25 rotas fora do mapa, caladas."""

    FONTE = """
_PAGINA = "/app/loja/financeiro"
_DESPESAS = _PAGINA + "/despesas"

@router.get(_PAGINA, response_class=HTMLResponse)
async def financeiro_resultado():
    pass

@router.get(_PAGINA + "/dados")
async def financeiro_dados():
    pass

@router.post(_DESPESAS + "/{despesa_id}/ajuste")
async def despesa_ajuste():
    pass
"""

    def test_constante_simples_encadeada_e_concatenada(self):
        achadas = extratores.rotas(self.FONTE, "app/web/loja_financeiro.py")
        chaves = {e.chave for e in achadas if e.secao == "rota"}
        self.assertEqual(chaves, {
            "GET /app/loja/financeiro",
            "GET /app/loja/financeiro/dados",
            "POST /app/loja/financeiro/despesas/{despesa_id}/ajuste",
        })

    def test_a_ancora_esta_escrita_na_linha_que_o_mapa_aponta(self):
        """O --verificar reabre a linha e exige o simbolo nela.

        Com path em variavel o simbolo NAO pode ser o path (ele nao esta
        escrito ali) e sim o nome da constante, que esta.
        """
        linhas = self.FONTE.splitlines()
        for e in extratores.rotas(self.FONTE, "x.py"):
            self.assertIn(e.simbolo, linhas[e.linha - 1], e.chave)

    def test_path_que_o_gerador_nao_le_vira_aviso_e_nao_silencio(self):
        """Sumir calado e o modo de falha que este projeto repete.

        Quem le um mapa que nao avisa conclui que a rota nao existe — foi assim
        que o ensaio quase escreveu um plano para reconstruir um modulo pronto.
        """
        fonte = """
@router.get(f"/app/{tenant}/x")
async def handler_exotico():
    pass
"""
        achadas = extratores.rotas(fonte, "app/web/x.py")
        self.assertEqual([e.secao for e in achadas], ["aviso"])
        self.assertIn("nao leu", achadas[0].chave)
        # o aviso tambem precisa ser verificavel, senao e so barulho
        self.assertIn(achadas[0].simbolo, fonte.splitlines()[achadas[0].linha - 1])

    def test_no_repo_real_nenhuma_rota_some_calada(self):
        """Antirregressao da classe inteira, nao de um caso.

        Todo decorator de rota do repo tem que virar OU uma entrada de rota OU
        um aviso. O que nao pode e o gerador dar de ombros: o --verificar so
        reabre o que esta no mapa, entao ausencia ele nao ve, e o mapa seguia
        dizendo "confere com o codigo" com 25 rotas faltando.
        """
        raiz = varredura.raiz_repo()
        decorators = extraidas = 0
        for produto in varredura.PRODUTOS:
            for arq in varredura.arquivos_py(raiz, produto):
                texto = arq.read_text(encoding="utf-8", errors="replace")
                try:
                    arvore = ast.parse(texto)
                except SyntaxError:
                    continue
                for no in ast.walk(arvore):
                    if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    for dec in no.decorator_list:
                        if not isinstance(dec, ast.Call):
                            continue
                        f = dec.func
                        if isinstance(f, ast.Attribute) and f.attr in extratores.VERBOS \
                                and dec.args:
                            decorators += 1
                rel = arq.relative_to(raiz / produto).as_posix()
                extraidas += len(extratores.rotas(texto, rel))
        self.assertGreater(decorators, 380)
        self.assertEqual(decorators, extraidas)

    def test_o_financeiro_da_loja_esta_no_mapa(self):
        """O modulo concreto que o ensaio procurou e nao achou."""
        mapa = (gerar_mapa.PASTA_MAPA / "portal-gestao.md").read_text(encoding="utf-8")
        self.assertIn("GET /app/loja/financeiro", mapa)
        self.assertIn("POST /app/loja/financeiro/despesas", mapa)


class TestFrescorValidaOAlvo(unittest.TestCase):
    def _rodar(self, *args):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            code = gerar_mapa.main(["--frescor", *args])
        return code, saida.getvalue()

    def test_nome_da_tabela_do_agents_md_nao_passa_por_produto(self):
        """`Motor` e `Revy Loja` respondiam "mapa em dia".

        Sao os nomes da coluna Produto da tabela do AGENTS.md secao 2 — o unico
        lugar onde o agente aprende como os produtos se chamam. O documento que
        manda rodar o comando ensinava os argumentos que o comando engolia, e o
        passo 2 do protocolo manda seguir calado ao ouvir "mapa em dia".
        """
        for nome in ("Motor", "Estoque", "Revy Loja", "Revy Control", "chatbot"):
            code, texto = self._rodar(nome)
            self.assertEqual(code, 2, nome)
            self.assertIn("nao conheco", texto)
            self.assertNotIn("mapa em dia", texto)

    def test_produto_de_verdade_passa(self):
        code, texto = self._rodar("portal-gestao")
        self.assertEqual(code, 0)
        self.assertNotIn("nao conheco", texto)

    def test_n8n_e_deploy_alimentam_o_mapa_entao_tem_frescor(self):
        """`cruzamentos` le n8n/workflow-*.json e os fly.toml do repo.

        Enquanto o frescor olhava so PRODUTOS, mexer no workflow nunca acendia
        luz — e e a secao que o proprio cruzamentos.py chama de "junta de maior
        severidade do repo: quando abre, o bot emudece".
        """
        self.assertIn("n8n", varredura.FONTES_DO_MAPA)
        self.assertIn("deploy", varredura.FONTES_DO_MAPA)
        for alvo in ("n8n", "deploy"):
            self.assertEqual(self._rodar(alvo)[0], 0, alvo)


if __name__ == "__main__":
    unittest.main()
