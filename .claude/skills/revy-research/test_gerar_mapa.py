import tempfile
import unittest
from pathlib import Path

import extratores
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


if __name__ == "__main__":
    unittest.main()
