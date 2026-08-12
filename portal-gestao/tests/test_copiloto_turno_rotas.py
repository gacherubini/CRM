from conftest import csrf_da_resposta, login, seed_loja_operacional

from app.copiloto_turnos_job import CopilotoTurnosWorker, processar_turno
from app.db import SessionLocal
from app.loja.copiloto.conversas import criar_turno, obter_turno
from app.loja.copiloto.port import LLMFake, RespostaLLM, ToolCall
from app.models import CopilotoTurno, LojaOperacionalProjecao


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _llm_ok():
    return LLMFake(
        [
            RespostaLLM(
                texto=None,
                tool_calls=(ToolCall(id="c1", nome="vendas_resumo", argumentos={}),),
                tokens_entrada=1000, tokens_saida=20, finish_reason="tool_calls",
            ),
            RespostaLLM(
                texto="Você não vendeu nada em agosto de 2026.",
                tool_calls=(), tokens_entrada=1200, tokens_saida=40,
                finish_reason="stop",
            ),
        ]
    )


class EstoqueStub:
    def obter_loja(self):
        return {"slug": "loja-teste"}

    def listar(self, **f):
        return []


class ChatbotStub:
    def listar_conversas(self, **k):
        return []

    def listar_leads(self, etapa=None):
        return []


def _seedar_modulo_copiloto(loja_slug="loja-teste", state="ativo"):
    """Grava/atualiza a projeção do módulo Copiloto (aggregate='copiloto').

    Mesmo helper de tests/test_copiloto_pagina.py: prova que as rotas novas
    obedecem ao MESMO entitlement por loja que a página do Fase 1 já usa —
    não basta a flag global + papel certo.
    """
    db = SessionLocal()
    try:
        seed_loja_operacional(db, loja_slug=loja_slug, state="ativa")
        row = db.get(LojaOperacionalProjecao, (loja_slug, "copiloto"))
        if row is None:
            db.add(
                LojaOperacionalProjecao(
                    loja_slug=loja_slug,
                    aggregate="copiloto",
                    version=1,
                    state=state,
                    event_id="seed-copiloto",
                )
            )
        else:
            row.state = state
        db.commit()
    finally:
        db.close()


def test_entitlement_ausente_bloqueia_perguntar_mesmo_com_papel_certo(client, monkeypatch):
    """Gate-duplo (§ criticals da Fase 1): flag global + papel certo NÃO bastam
    sem o entitlement do módulo por loja — a rota precisa checar sozinha.

    CSRF válido de propósito (vem de /app, não da própria página do Copiloto,
    que com o módulo não contratado já barra a página): se o CSRF estivesse
    errado, o 403 provaria só a checagem de sessão, não a de entitlement.
    """
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    csrf = csrf_da_resposta(client.get("/app"))
    r = client.post(
        "/app/loja/copiloto/perguntar", data={"csrf": csrf, "pergunta": "a?"}
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoTurno).count() == 0
    finally:
        db.close()


def test_entitlement_presente_libera_perguntar(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    _seedar_modulo_copiloto()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        "/app/loja/copiloto/perguntar",
        data={"csrf": csrf_da_resposta(pagina), "pergunta": "quanto vendi?"},
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "pendente"


def test_perguntar_devolve_turno_id_sem_bloquear(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        "/app/loja/copiloto/perguntar",
        data={"csrf": csrf_da_resposta(pagina), "pergunta": "quanto vendi?"},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["turno_id"]
    assert corpo["estado"] == "pendente"


def test_perguntar_sem_csrf_e_recusado(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.post(
        "/app/loja/copiloto/perguntar",
        data={"csrf": "x", "pergunta": "quanto vendi?"},
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoTurno).count() == 0
    finally:
        db.close()


def test_perguntar_com_flag_off_e_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    login(client)
    r = client.post(
        "/app/loja/copiloto/perguntar", data={"csrf": "x", "pergunta": "a?"}
    )
    assert r.status_code == 404


def test_vendedor_nao_pergunta(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    r = client.post(
        "/app/loja/copiloto/perguntar", data={"csrf": "x", "pergunta": "a?"}
    )
    assert r.status_code == 403


def test_polling_reflete_pendente_e_depois_pronto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    pagina = client.get("/app/loja/copiloto")
    turno_id = client.post(
        "/app/loja/copiloto/perguntar",
        data={"csrf": csrf_da_resposta(pagina), "pergunta": "quanto vendi?"},
    ).json()["turno_id"]

    assert client.get(f"/app/loja/copiloto/turno/{turno_id}.json").json()["estado"] == "pendente"

    db = SessionLocal()
    try:
        turno = obter_turno(db, "loja-teste", turno_id)
        processar_turno(
            db, turno, llm=_llm_ok(), estoque=EstoqueStub(), chatbot=ChatbotStub()
        )
    finally:
        db.close()

    corpo = client.get(f"/app/loja/copiloto/turno/{turno_id}.json").json()
    assert corpo["estado"] == "pronto"
    assert "agosto de 2026" in corpo["texto"]
    assert corpo["passos"][0]["ferramenta"] == "vendas_resumo"


def test_turno_de_outra_loja_nao_e_lido(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    db = SessionLocal()
    try:
        alheio = criar_turno(
            db, loja_slug="outra-loja", usuario_id="u9", pergunta="segredo?"
        )
        turno_id = alheio.id
    finally:
        db.close()
    assert client.get(f"/app/loja/copiloto/turno/{turno_id}.json").status_code == 404


def test_cancelar_turno_em_andamento(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    pagina = client.get("/app/loja/copiloto")
    csrf = csrf_da_resposta(pagina)
    turno_id = client.post(
        "/app/loja/copiloto/perguntar", data={"csrf": csrf, "pergunta": "a?"}
    ).json()["turno_id"]
    r = client.post(
        f"/app/loja/copiloto/turno/{turno_id}/cancelar", data={"csrf": csrf}
    )
    assert r.json()["cancelado"] is True


def test_cancelar_sem_csrf_e_recusado(client, monkeypatch):
    """Fix round 1 / Finding 1: mesma checagem de CSRF de /perguntar, agora
    provada em /cancelar — o brief exigia o par para as duas rotas POST."""
    _ligar(monkeypatch)
    login(client)
    pagina = client.get("/app/loja/copiloto")
    turno_id = client.post(
        "/app/loja/copiloto/perguntar",
        data={"csrf": csrf_da_resposta(pagina), "pergunta": "a?"},
    ).json()["turno_id"]

    r = client.post(
        f"/app/loja/copiloto/turno/{turno_id}/cancelar", data={"csrf": "x"}
    )
    assert r.status_code == 403

    db = SessionLocal()
    try:
        # Estado inalterado — não só o HTTP status, o efeito colateral também.
        assert obter_turno(db, "loja-teste", turno_id).estado == "pendente"
    finally:
        db.close()


def test_limite_de_turnos_abertos_por_usuario(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("PORTAL_COPILOTO_MAX_TURNOS_ABERTOS", "1")
    login(client)
    pagina = client.get("/app/loja/copiloto")
    csrf = csrf_da_resposta(pagina)
    client.post("/app/loja/copiloto/perguntar", data={"csrf": csrf, "pergunta": "a?"})
    r = client.post(
        "/app/loja/copiloto/perguntar", data={"csrf": csrf, "pergunta": "b?"}
    )
    assert r.status_code == 429


def test_provedor_fora_grava_erro_e_nao_texto(db):
    from app.loja.copiloto.port import LLMIndisponivel

    class LLMQuebrado:
        def completar(self, *a, **k):
            raise LLMIndisponivel("fora")

    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    processar_turno(
        db, turno, llm=LLMQuebrado(), estoque=EstoqueStub(), chatbot=ChatbotStub()
    )
    db.refresh(turno)
    assert turno.estado == "erro"
    assert turno.erro_code == "provedor"


def test_worker_pega_turno_pendente(db):
    seed_loja_operacional(db)
    criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?")
    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=_llm_ok,
        estoque_factory=lambda: EstoqueStub(),
        chatbot_factory=lambda: ChatbotStub(),
    )
    resultado = worker.run_once()
    assert resultado["processados"] == 1
    assert db.query(CopilotoTurno).one().estado == "pronto"


def test_worker_desligado_nao_processa(db):
    criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal, enabled=False, llm_factory=_llm_ok,
        estoque_factory=lambda: EstoqueStub(), chatbot_factory=lambda: ChatbotStub(),
    )
    assert worker.run_once()["processados"] == 0
    assert db.query(CopilotoTurno).one().estado == "pendente"


def test_worker_nao_processa_turno_de_loja_sem_entitlement(db, monkeypatch):
    """Fix round 1 / Finding 2: um turno pode esperar na fila (lote, intervalo
    do worker) tempo suficiente para a loja perder o entitlement do Copiloto
    (ou ser desativada) entre a pergunta e o processamento. Sem recheck aqui,
    o worker chamaria o provedor — e cobraria custo real — por uma loja que
    já não tem mais acesso. O turno também não pode ficar `pendente` para
    sempre: isso recriaria o mesmo problema de órfão/429 permanente que
    `expirar_orfaos()` existe para evitar.
    """
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    seed_loja_operacional(db, loja_slug="loja-teste", state="ativa")
    # loja ativa, mas SEM aggregate "copiloto" contratado — entitlement ausente.
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )

    chamadas = []

    class LLMEspiao:
        def completar(self, *a, **k):
            chamadas.append((a, k))
            raise AssertionError("o provedor não deveria ser chamado")

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=lambda: LLMEspiao(),
        estoque_factory=lambda: EstoqueStub(),
        chatbot_factory=lambda: ChatbotStub(),
    )
    resultado = worker.run_once()
    assert resultado["processados"] == 0
    assert chamadas == []  # LLM nunca chamado

    db.refresh(turno)
    assert turno.estado == "erro"  # terminal — não fica pendente para sempre
    assert turno.erro_code == "sem_acesso"


def test_worker_processa_turno_quando_entitlement_presente(db, monkeypatch):
    """Contraprova da Finding 2: com o módulo contratado e ativo, o worker
    processa normalmente — a checagem não é fail-closed a ponto de travar
    quem tem acesso de verdade."""
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    seed_loja_operacional(db, loja_slug="loja-teste", state="ativa")
    db.add(
        LojaOperacionalProjecao(
            loja_slug="loja-teste",
            aggregate="copiloto",
            version=1,
            state="ativo",
            event_id="seed-copiloto",
        )
    )
    db.commit()
    criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?")

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=_llm_ok,
        estoque_factory=lambda: EstoqueStub(),
        chatbot_factory=lambda: ChatbotStub(),
    )
    resultado = worker.run_once()
    assert resultado["processados"] == 1
    assert db.query(CopilotoTurno).one().estado == "pronto"


def test_worker_le_a_flag_de_produto_a_cada_ciclo(db, monkeypatch):
    """Rota lê a flag em runtime; o worker também, senão um abre e o outro dorme."""
    monkeypatch.setenv("PORTAL_COPILOTO_TURNOS_ENABLED", "1")
    monkeypatch.delenv("REVY_LOJA_COPILOTO_ENABLED", raising=False)
    seed_loja_operacional(db)
    criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")

    worker = CopilotoTurnosWorker(  # sem `enabled=`: o gate da flag fica ativo
        db_factory=SessionLocal, llm_factory=_llm_ok,
        estoque_factory=lambda: EstoqueStub(), chatbot_factory=lambda: ChatbotStub(),
    )
    assert worker.run_once()["processados"] == 0

    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    assert worker.run_once()["processados"] == 1  # sem reiniciar o worker


def test_worker_expira_turno_orfao_de_processo_morto(db):
    """`fly deploy` no meio da pergunta deixa `executando` sem ninguém tocando."""
    from datetime import datetime, timedelta, timezone

    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    turno.estado = "executando"
    turno.iniciado_em = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.commit()

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal, enabled=True, llm_factory=_llm_ok,
        estoque_factory=lambda: EstoqueStub(), chatbot_factory=lambda: ChatbotStub(),
    )
    worker.run_once()
    db.refresh(turno)
    assert turno.estado == "erro"
    assert turno.erro_code == "interrompido"


def test_worker_nao_expira_turno_em_andamento(db):
    """Turno vivo dentro do TTL não pode ser morto pelo reaper."""
    from datetime import datetime, timezone

    turno = criar_turno(db, loja_slug="loja-teste", usuario_id="u1", pergunta="a?")
    turno.estado = "executando"
    turno.iniciado_em = datetime.now(timezone.utc)
    db.commit()

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal, enabled=True, llm_factory=_llm_ok,
        estoque_factory=lambda: EstoqueStub(), chatbot_factory=lambda: ChatbotStub(),
    )
    worker.run_once()
    db.refresh(turno)
    assert turno.estado == "executando"


def test_turno_orfao_nao_tranca_o_usuario_no_429(client, db, monkeypatch):
    """A guarda de runaway conta só turno recente — senão o 429 vira permanente."""
    from datetime import datetime, timedelta, timezone

    _ligar(monkeypatch)
    for _ in range(3):
        t = criar_turno(
            db, loja_slug="loja-teste", usuario_id="u1", pergunta="antiga?"
        )
        t.estado = "executando"
        t.criado_em = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()

    login(client)
    # Não usar a resposta de /login (redirect 303 sem corpo): o token de CSRF
    # vem da página, como em todo outro teste desta suíte.
    pagina = client.get("/app/loja/copiloto")
    csrf = csrf_da_resposta(pagina)
    r = client.post(
        "/app/loja/copiloto/perguntar",
        data={"csrf": csrf, "pergunta": "quanto vendi?"},
    )
    assert r.status_code == 200, r.text
