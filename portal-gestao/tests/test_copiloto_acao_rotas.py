from datetime import datetime, timedelta, timezone

from conftest import csrf_da_resposta, login

from app.db import SessionLocal
from app.main import app, get_estoque_client
from app.models import CopilotoAcao, LojaOperacaoAuditoria


class EstoqueAcaoFake:
    def __init__(self, preco=28000.0, slug="loja-teste"):
        self.slug = slug
        self.veiculo = {
            "id": "v1", "marca": "Honda", "modelo": "CB 500F", "ano_modelo": 2020,
            "preco": preco, "status": "disponivel", "publicado": False,
        }
        self.patches = []
        self.acoes = []

    def obter_loja(self):
        return {"slug": self.slug}

    def obter(self, veiculo_id):
        return dict(self.veiculo)

    def listar(self, **f):
        return [dict(self.veiculo)]

    def atualizar(self, veiculo_id, dados):
        self.patches.append((veiculo_id, dados))
        self.veiculo.update(dados)
        return dict(self.veiculo)

    def acao(self, veiculo_id, acao):
        self.acoes.append((veiculo_id, acao))
        return {"ok": True}


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _com_estoque(fake):
    app.dependency_overrides[get_estoque_client] = lambda: fake
    return fake


def test_confirmar_ajuste_de_preco(client, monkeypatch):
    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake(preco=28000.0))
    login(client)
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        "/app/loja/copiloto/acao",
        data={
            "csrf": csrf_da_resposta(pagina),
            "acao": "ajustar_preco",
            "veiculo_id": "v1",
            "novo_preco": "25000",
            "preco_esperado": "28000.00",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert fake.patches == [("v1", {"preco": 25000.0})]


def test_agora_nunca_vem_da_requisicao(client, monkeypatch):
    """A trava real (rate-limit, carimbo, prazo de desfazer) só é testável
    aqui, na rota: ela nunca deriva `agora` de nada que vem da requisição
    (nem query, nem form, nem header). `executar_acao` aceita `agora` como
    ponto de injeção — mas só de teste, chamado direto em Python; a rota
    HTTP jamais repassa um valor vindo do cliente para esse parâmetro. Manda
    um campo com cara de timestamp no POST e confirma que foi ignorado: o
    prazo de desfazer devolvido é derivado do relógio real do servidor, não
    do ano 2000 que o cliente tentou injetar."""
    _ligar(monkeypatch)
    _com_estoque(EstoqueAcaoFake(preco=28000.0))
    login(client)
    pagina = client.get("/app/loja/copiloto")
    antes = datetime.now(timezone.utc)
    r = client.post(
        "/app/loja/copiloto/acao",
        data={
            "csrf": csrf_da_resposta(pagina),
            "acao": "ajustar_preco",
            "veiculo_id": "v1",
            "novo_preco": "25000",
            "preco_esperado": "28000.00",
            # Tentativa de injeção: se a rota repassasse isto como `agora`,
            # o rate-limit e o prazo de desfazer ficariam ancorados no ano
            # 2000 — inclusive furando o rate-limit de "1 hora" pra sempre.
            "agora": "2000-01-01T00:00:00+00:00",
        },
    )
    depois = datetime.now(timezone.utc)
    assert r.status_code == 200
    desfazer_ate = datetime.fromisoformat(r.json()["desfazer_ate"])
    assert desfazer_ate.year == depois.year
    # Janela generosa (o prazo real de desfazer soma alguns minutos ao
    # `agora` do servidor) — o que importa é que fica perto de "agora" de
    # verdade, longe de qualquer valor que o cliente tentou mandar.
    assert antes <= desfazer_ate <= depois + timedelta(hours=1)


def test_acao_sem_csrf_nao_escreve(client, monkeypatch):
    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake())
    login(client)
    r = client.post(
        "/app/loja/copiloto/acao",
        data={"csrf": "x", "acao": "ajustar_preco", "veiculo_id": "v1", "novo_preco": "25000"},
    )
    assert r.status_code == 403
    assert fake.patches == []


def test_vendedor_recebe_403_e_nao_escreve(client, monkeypatch):
    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake())
    login(client, papel="vendedor", email="v@loja.test")
    r = client.post(
        "/app/loja/copiloto/acao",
        data={"csrf": "x", "acao": "ajustar_preco", "veiculo_id": "v1", "novo_preco": "25000"},
    )
    assert r.status_code == 403
    assert fake.patches == []


def test_preco_fora_da_banda_e_recusado(client, monkeypatch):
    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake(preco=28000.0))
    login(client)
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        "/app/loja/copiloto/acao",
        data={
            "csrf": csrf_da_resposta(pagina), "acao": "ajustar_preco",
            "veiculo_id": "v1", "novo_preco": "1", "preco_esperado": "28000.00",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] in {"banda", "piso"}
    assert fake.patches == []


def test_preco_divergente_do_cartao_aborta(client, monkeypatch):
    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake(preco=26000.0))
    login(client)
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        "/app/loja/copiloto/acao",
        data={
            "csrf": csrf_da_resposta(pagina), "acao": "ajustar_preco",
            "veiculo_id": "v1", "novo_preco": "25000", "preco_esperado": "28000.00",
        },
    )
    assert r.status_code == 409
    assert r.json()["error"] == "divergencia"
    assert fake.patches == []


def test_acao_grava_auditoria_com_ator(client, monkeypatch):
    _ligar(monkeypatch)
    _com_estoque(EstoqueAcaoFake())
    login(client)
    pagina = client.get("/app/loja/copiloto")
    client.post(
        "/app/loja/copiloto/acao",
        data={
            "csrf": csrf_da_resposta(pagina), "acao": "repostar_veiculo",
            "veiculo_id": "v1",
        },
    )
    db = SessionLocal()
    try:
        linha = db.query(LojaOperacaoAuditoria).one()
        assert linha.dominio == "copiloto"
        assert linha.ator_email == "dono@loja.test"
    finally:
        db.close()


def test_desfazer_restaura_pela_rota(client, monkeypatch):
    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake(preco=28000.0))
    login(client)
    pagina = client.get("/app/loja/copiloto")
    csrf = csrf_da_resposta(pagina)
    acao_id = client.post(
        "/app/loja/copiloto/acao",
        data={
            "csrf": csrf, "acao": "ajustar_preco", "veiculo_id": "v1",
            "novo_preco": "25000", "preco_esperado": "28000.00",
        },
    ).json()["acao_id"]
    r = client.post(f"/app/loja/copiloto/acao/{acao_id}/desfazer", data={"csrf": csrf})
    assert r.json()["desfeito"] is True
    assert fake.veiculo["preco"] == 28000.0


def test_desfazer_acao_de_outra_loja_falha(client, monkeypatch):
    _ligar(monkeypatch)
    _com_estoque(EstoqueAcaoFake())
    login(client)
    db = SessionLocal()
    try:
        alheia = CopilotoAcao(
            loja_slug="outra-loja", ator_email="x@o.test", acao="ajustar_preco",
            entidade_ref="v1", estado="executada",
        )
        db.add(alheia)
        db.commit()
        acao_id = alheia.id
    finally:
        db.close()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/acao/{acao_id}/desfazer",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.json()["desfeito"] is False


def test_acao_com_flag_off_e_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    login(client)
    r = client.post(
        "/app/loja/copiloto/acao",
        data={"csrf": "x", "acao": "ajustar_preco", "veiculo_id": "v1"},
    )
    assert r.status_code == 404


def test_polling_devolve_cartao_apos_propor_acao(client, monkeypatch):
    """O caminho real de uso: pergunta -> turno roda -> o modelo chama
    propor_acao -> o polling em /turno/{id}.json devolve `cartao` preenchido.
    Todos os outros testes deste arquivo exercitam POST /acao com um
    formulário montado à mão, nunca este caminho pergunta->proposta->cartão
    — e foi exatamente por isso que o cartão podia nunca chegar à tela sem
    que nenhum teste da suíte percebesse."""
    from app.copiloto_turnos_job import processar_turno
    from app.loja.copiloto.conversas import obter_turno
    from app.loja.copiloto.port import LLMFake, RespostaLLM, ToolCall

    class ChatbotStub:
        def listar_conversas(self, **k):
            return []

        def listar_leads(self, etapa=None):
            return []

    _ligar(monkeypatch)
    fake = _com_estoque(EstoqueAcaoFake(preco=28000.0))
    login(client)
    pagina = client.get("/app/loja/copiloto")
    turno_id = client.post(
        "/app/loja/copiloto/perguntar",
        data={
            "csrf": csrf_da_resposta(pagina),
            "pergunta": "baixa o preço da CB500 que está parada",
        },
    ).json()["turno_id"]

    llm = LLMFake(
        [
            RespostaLLM(
                texto=None,
                tool_calls=(
                    ToolCall(
                        id="c1", nome="propor_acao",
                        argumentos={
                            "acao": "ajustar_preco", "veiculo_id": "v1",
                            "novo_preco": "25000", "justificativa": "dias_parado",
                        },
                    ),
                ),
                tokens_entrada=900, tokens_saida=20, finish_reason="tool_calls",
            ),
            RespostaLLM(
                texto="Aqui está a proposta.", tool_calls=(),
                tokens_entrada=1200, tokens_saida=30, finish_reason="stop",
            ),
        ]
    )
    db = SessionLocal()
    try:
        turno = obter_turno(db, "loja-teste", turno_id)
        processar_turno(db, turno, llm=llm, estoque=fake, chatbot=ChatbotStub())
    finally:
        db.close()

    corpo = client.get(f"/app/loja/copiloto/turno/{turno_id}.json").json()
    assert corpo["cartao"] is not None
    assert corpo["cartao"]["acao"] == "ajustar_preco"
    assert "Alterar o preço" in corpo["cartao"]["titulo"]
