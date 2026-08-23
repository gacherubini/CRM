import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
    def test_armadilha_hoje_o_repo_nao_tem_nenhum_prefix(self):
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

if __name__ == "__main__":
    unittest.main()
