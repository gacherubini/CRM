from conftest import csrf_da_resposta, login, seed_loja_operacional

import app.copiloto_turnos_job as copiloto_turnos_job
from app.config import settings
from app.copiloto_turnos_job import CopilotoTurnosWorker, _historico, processar_turno
from app.db import SessionLocal
from app.loja.copiloto.conversas import (
    cancelar_turno,
    concluir_turno,
    criar_turno,
    obter_turno,
    reivindicar_turno,
)
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


def test_turno_cancelado_durante_execucao_nao_vira_pronto(db):
    """I3: Cancelar roda numa sessão HTTP separada da do worker. Sem reler o
    estado do banco antes de gravar o resultado, o worker ressuscitaria um
    turno cancelado como `pronto` — a tela já parou de fazer polling em
    `cancelado`, então o dono só veria a resposta se recarregasse a página."""
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    turno_id = turno.id

    class LLMCancelaDuranteAChamada:
        def completar(self, *a, **k):
            outra_sessao = SessionLocal()
            try:
                assert cancelar_turno(outra_sessao, "loja-teste", turno_id) is True
            finally:
                outra_sessao.close()
            return RespostaLLM(
                texto="Você vendeu 2 motos.",
                tool_calls=(),
                tokens_entrada=100,
                tokens_saida=10,
                finish_reason="stop",
            )

    processar_turno(
        db, turno, llm=LLMCancelaDuranteAChamada(), estoque=EstoqueStub(),
        chatbot=ChatbotStub(),
    )
    db.refresh(turno)
    assert turno.estado == "cancelado"
    assert turno.resposta is None


def test_turno_ja_cancelado_no_pickup_nao_chama_o_provedor(db):
    """I3: turno cancelado ANTES do worker pegá-lo não pode gerar custo de
    LLM — nem `atualizar_progresso(estado='executando')` pode rodar por cima
    do cancelamento."""
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    assert cancelar_turno(db, "loja-teste", turno.id) is True

    class LLMEspiao:
        def completar(self, *a, **k):
            raise AssertionError("o provedor não deveria ser chamado")

    processar_turno(
        db, turno, llm=LLMEspiao(), estoque=EstoqueStub(), chatbot=ChatbotStub()
    )
    db.refresh(turno)
    assert turno.estado == "cancelado"


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


def _seedar_conversa_com_turnos_prontos(db, quantidade: int) -> tuple[list[CopilotoTurno], CopilotoTurno]:
    """Cria `quantidade` turnos `pronto` na mesma conversa e devolve
    (turnos_prontos, turno_atual_pendente). Pergunta/resposta são longas de
    propósito (bem acima do custo de sobrecarga por mensagem), para que o
    corte por orçamento de tokens tenha efeito real nos testes."""
    conversa_id = None
    prontos: list[CopilotoTurno] = []
    for i in range(quantidade):
        t = criar_turno(
            db,
            loja_slug="loja-teste",
            usuario_id="u1",
            pergunta=f"pergunta {i} " + "x" * 50,
            conversa_id=conversa_id,
        )
        conversa_id = t.conversa_id
        concluir_turno(
            db,
            t,
            resposta=f"resposta {i} " + "y" * 50,
            passos=[],
            tokens_entrada=10,
            tokens_saida=10,
            custo_estimado=None,
        )
        prontos.append(t)
    atual = criar_turno(
        db,
        loja_slug="loja-teste",
        usuario_id="u1",
        pergunta="pergunta atual",
        conversa_id=conversa_id,
    )
    return prontos, atual


def test_historico_corta_por_orcamento_de_tokens_preservando_o_mais_recente(db):
    """Substitui a antiga cobertura de corte por contagem fixa (6 pares):
    agora o corte é por orçamento de tokens (§ app/loja/copiloto/historico.py),
    não por número de turnos. Cada par pronto=(pergunta, resposta) custa ~40
    tokens estimados nesta fixture — orçamento pequeno só cabe o mais recente."""
    prontos, atual = _seedar_conversa_com_turnos_prontos(db, quantidade=3)

    curto = _historico(db, atual, orcamento_tokens=40)
    assert curto == [(prontos[-1].pergunta, prontos[-1].resposta)]

    completo = _historico(db, atual, orcamento_tokens=10_000)
    assert completo == [(t.pergunta, t.resposta) for t in prontos]  # ordem cronológica


def test_historico_sem_orcamento_explicito_usa_o_da_config(db):
    """`orcamento_tokens=None` (chamada real do worker) cai em
    `settings.copiloto_historico_tokens` — o teste controla isso sem mexer em
    variável de ambiente. `Settings` é dataclass frozen (mesmo padrão de
    `object.__setattr__` usado nos demais testes deste repo para ligar/
    desligar flags durante o teste)."""
    original = settings.copiloto_historico_tokens
    object.__setattr__(settings, "copiloto_historico_tokens", 40)
    try:
        prontos, atual = _seedar_conversa_com_turnos_prontos(db, quantidade=3)
        resultado = _historico(db, atual)
    finally:
        object.__setattr__(settings, "copiloto_historico_tokens", original)

    assert resultado == [(prontos[-1].pergunta, prontos[-1].resposta)]


def test_reivindicar_turno_so_o_primeiro_vence(db):
    """Dois processos disputando o mesmo turno: o banco escolhe um."""
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    assert reivindicar_turno(db, turno.id) is True
    assert reivindicar_turno(db, turno.id) is False
    db.refresh(turno)
    assert turno.estado == "executando"
    assert turno.iniciado_em is not None


def test_reivindicar_turno_cancelado_devolve_false(db):
    """Cancelar tira o turno de `pendente` — a reivindicação não pode ressuscitar."""
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    assert cancelar_turno(db, "loja-teste", turno.id) is True
    assert reivindicar_turno(db, turno.id) is False
    db.refresh(turno)
    assert turno.estado == "cancelado"


def test_reivindicar_turno_inexistente_devolve_false(db):
    assert reivindicar_turno(db, "nao-existe") is False


def test_worker_solta_o_turno_quando_perde_a_reivindicacao(db, monkeypatch):
    """Outro processo reivindicou entre o SELECT e o pickup: não pode chamar o
    provedor, e não pode contar como processado."""
    seed_loja_operacional(db)
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )

    class LLMProibido:
        def completar(self, *a, **k):
            raise AssertionError("provedor não pode ser chamado")

    monkeypatch.setattr(
        copiloto_turnos_job, "reivindicar_turno", lambda db, turno_id: False
    )
    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=lambda: LLMProibido(),
        estoque_factory=lambda: EstoqueStub(),
        chatbot_factory=lambda: ChatbotStub(),
    )
    assert worker.run_once()["processados"] == 0
    db.refresh(turno)
    assert turno.estado == "pendente"


def test_run_once_nao_reivindica_o_lote_inteiro_antes_de_processar(db):
    """`expirar_orfaos` filtra por `iniciado_em < agora - ttl_executando`; se
    `run_once` reivindicasse o lote inteiro ANTES de processar qualquer um, o
    relógio de órfão do 2º/3º turno começaria a contar antes de o 1º sequer
    rodar, e a morte do processo no meio do lote deixaria os turnos que
    nunca chegaram a iniciar presos como `interrompido` em vez de voltarem
    para a fila como `pendente`. A propriedade que protege isso: enquanto o
    turno N-1 está sendo processado, o turno N ainda está `pendente` — a
    reivindicação não corre na frente do processamento. Pina isso inspecionando
    o banco, de dentro do LLM fake, no instante em que o 1º turno é processado."""
    seed_loja_operacional(db)
    primeiro = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="primeira?"
    )
    segundo = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="segunda?"
    )

    estados_do_segundo_visto_de_dentro_do_primeiro: list[str] = []

    class LLMQueEspiaOProximoTurnoDoLote:
        def __init__(self):
            self.chamadas = 0

        def completar(self, *a, **k):
            self.chamadas += 1
            if self.chamadas == 1:
                # Sessão separada, mesmo padrão de LLMCancelaDuranteAChamada
                # acima: quer ler o estado comitado por `run_once`, não o
                # cache da sessão do próprio worker.
                outra_sessao = SessionLocal()
                try:
                    turno_segundo = outra_sessao.get(CopilotoTurno, segundo.id)
                    estados_do_segundo_visto_de_dentro_do_primeiro.append(
                        turno_segundo.estado
                    )
                finally:
                    outra_sessao.close()
            return RespostaLLM(
                texto="ok",
                tool_calls=(),
                tokens_entrada=10,
                tokens_saida=10,
                finish_reason="stop",
            )

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        lote=2,  # os dois turnos precisam caber no mesmo run_once
        llm_factory=LLMQueEspiaOProximoTurnoDoLote,
        estoque_factory=lambda: EstoqueStub(),
        chatbot_factory=lambda: ChatbotStub(),
    )
    resultado = worker.run_once()

    assert resultado["processados"] == 2
    # Se o laço reivindicasse o lote inteiro antes de processar (o bug que
    # este teste existe para travar), o segundo turno já estaria
    # `executando` neste ponto — e não `pendente`.
    assert estados_do_segundo_visto_de_dentro_do_primeiro == ["pendente"]

    db.refresh(primeiro)
    db.refresh(segundo)
    assert primeiro.estado == "pronto"
    assert segundo.estado == "pronto"


def test_run_once_sem_turnos_pendentes_nao_constroi_provedores(db):
    """Construir LLM/estoque/chatbot virou preguiçoso de propósito (§
    `_provedores` em `run_once`): montar o client HTTP do estoque/chatbot ou
    instanciar o cliente LLM tem custo real mesmo quando não há nenhum
    turno para processar. Um ciclo do worker roda a cada
    `PORTAL_COPILOTO_TURNOS_INTERVAL_SECONDS` — pagar esse custo à toa em
    todo ciclo ocioso é desperdício constante, não só de um turno. As
    factories aqui levantam se forem chamadas: a fila vazia não pode
    tocá-las."""

    def _nao_deveria_ser_chamada():
        raise AssertionError("provedor não deveria ser construído sem trabalho")

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=_nao_deveria_ser_chamada,
        estoque_factory=_nao_deveria_ser_chamada,
        chatbot_factory=_nao_deveria_ser_chamada,
    )
    resultado = worker.run_once()
    assert resultado["processados"] == 0


def test_run_once_com_todos_sem_entitlement_nao_constroi_provedores(db, monkeypatch):
    """Mesma preguiça de `_provedores`, agora com trabalho na fila mas sem
    acesso: a checagem de entitlement (`_copiloto_permitido`) roda ANTES de
    `_provedores()` ser chamada, então uma loja sem contrato do módulo não
    paga o custo de montar LLM/estoque/chatbot para, no fim, só gravar
    `falhar_turno(erro_code="sem_acesso")`."""
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    seed_loja_operacional(db, loja_slug="loja-teste", state="ativa")
    # loja ativa, mas SEM aggregate "copiloto" contratado — entitlement ausente.
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )

    def _nao_deveria_ser_chamada():
        raise AssertionError("provedor não deveria ser construído sem entitlement")

    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=_nao_deveria_ser_chamada,
        estoque_factory=_nao_deveria_ser_chamada,
        chatbot_factory=_nao_deveria_ser_chamada,
    )
    resultado = worker.run_once()
    assert resultado["processados"] == 0

    db.refresh(turno)
    assert turno.estado == "erro"
    assert turno.erro_code == "sem_acesso"
