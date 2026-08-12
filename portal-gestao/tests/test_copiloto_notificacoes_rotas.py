"""Rotas do painel de notificações do Copiloto (F4/Task 3):
GET /app/loja/copiloto/notificacoes.json,
POST /app/loja/copiloto/notificacoes/{sinal_id}/visto e
POST /app/loja/copiloto/notificacoes/{sinal_id}/dispensar.

Reusa `listar_sinais_abertos`, `marcar_visto` (que agora exige `usuario_id` —
Task 0 desta fase) e `dispensar`, todas de `sinais_store.py`. Nenhuma
função nova de domínio aqui — só o gate HTTP e a serialização.

Mesmo gate quádruplo das outras rotas do Copiloto (shell + flag + entitlement
+ papel de gestão), CSRF nos dois POST e invalidação do cache de contagem
depois de qualquer mutação — ver `app/web/loja_copiloto.py`.
"""
from conftest import csrf_da_resposta, login, seed_loja_operacional

from app.db import SessionLocal
from app.loja.copiloto import notificacoes
from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.models import CopilotoSinal, CopilotoSinalVisto, LojaOperacionalProjecao


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _seedar_modulo_copiloto(loja_slug="loja-teste", state="ativo"):
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


def _semear_sinal(loja="loja-teste", entidade="v1", **extra):
    db = SessionLocal()
    try:
        sincronizar_sinais(
            db,
            loja,
            [
                SinalCandidato(
                    regra="estoque_parado",
                    severidade="atencao",
                    titulo="Honda CB 500F parada há 70 dias",
                    detalhe="R$ 25.000,00 de capital preso.",
                    entidade_ref=entidade,
                    dados={"veiculo_id": entidade},
                    acao_sugerida={"acao": "abrir", "href": "/app/loja/estoque"},
                    **extra,
                )
            ],
        )
        return db.query(CopilotoSinal).filter(CopilotoSinal.loja_slug == loja).one().id
    finally:
        db.close()


# --- GET /notificacoes.json --------------------------------------------------


def test_listar_devolve_itens_e_contagem(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _semear_sinal()
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["nao_vistos"] == 1
    assert len(corpo["itens"]) == 1
    item = corpo["itens"][0]
    assert item["titulo"] == "Honda CB 500F parada há 70 dias"
    assert item["detalhe"] == "R$ 25.000,00 de capital preso."
    assert item["severidade"] == "atencao"
    assert item["acao_sugerida"] == {"acao": "abrir", "href": "/app/loja/estoque"}
    assert item["quando"]


def test_listar_nao_mostra_sinal_de_outra_loja(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _semear_sinal(loja="outra-loja")
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 200
    assert r.json()["itens"] == []
    assert r.json()["nao_vistos"] == 0


def test_listar_com_flag_off_e_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    login(client)
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 404


def test_listar_vendedor_recebe_403(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 403


def test_listar_entitlement_ausente_bloqueia_mesmo_com_papel_certo(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 403


# --- POST .../visto -----------------------------------------------------------


def test_visto_com_csrf_valido_marca_para_o_usuario(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/visto",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    db = SessionLocal()
    try:
        linha = db.query(CopilotoSinalVisto).one()
        assert linha.sinal_id == sinal_id
        assert linha.usuario_id == _usuario_id(db)
    finally:
        db.close()


def test_visto_sem_csrf_e_recusado_e_nao_grava(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/visto",
        data={"csrf": "invalido"},
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinalVisto).count() == 0
    finally:
        db.close()


def test_visto_de_sinal_de_outra_loja_e_nao_encontrado(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal(loja="outra-loja")
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/visto",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 404
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinalVisto).count() == 0
    finally:
        db.close()


def test_visto_invalida_cache_de_nao_vistos(client, monkeypatch, db):
    """Sem invalidar_contagem, o badge (contagem cacheada) continuaria
    contando o sinal já visto até o TTL vencer sozinho."""
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    # Aquece o cache: uma leitura antes de marcar visto.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", _usuario_id(db)) == 1

    pagina = client.get("/app/loja/copiloto")
    client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/visto",
        data={"csrf": csrf_da_resposta(pagina)},
    )

    assert notificacoes.contar_nao_vistos(db, "loja-teste", _usuario_id(db)) == 0


def test_visto_entitlement_ausente_bloqueia_e_nao_grava(client, monkeypatch):
    """CSRF válido de propósito (não "qualquer"): ``check_module_access`` roda
    ANTES do CSRF no gate (``_guard_json``), mas as duas falhas devolvem 403
    nestas rotas JSON — com um token inválido, o teste passaria mesmo se o
    gate de entitlement fosse removido, porque o CSRF sozinho já barraria com
    o mesmo status code. Um token de sessão real (tirado de uma tela do shell
    sem gate de módulo) isola a garantia que este teste diz cobrir."""
    _ligar(monkeypatch)
    sinal_id = _semear_sinal()
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    pagina = client.get("/app/loja/perfil")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/visto",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinalVisto).count() == 0
    finally:
        db.close()


# --- POST .../dispensar --------------------------------------------------------


def test_dispensar_com_csrf_valido_muda_estado(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
    finally:
        db.close()


def test_dispensar_sem_csrf_e_recusado_e_nao_muda_estado(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": "invalido"},
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


def test_dispensar_de_sinal_de_outra_loja_e_nao_encontrado(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal(loja="outra-loja")
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 404
    db = SessionLocal()
    try:
        assert (
            db.query(CopilotoSinal)
            .filter(CopilotoSinal.loja_slug == "outra-loja")
            .one()
            .estado
            == "novo"
        )
    finally:
        db.close()


def test_dispensar_zera_o_badge_apos_limpar_tudo(client, monkeypatch, db):
    """O caso concreto do brief: sem invalidar_contagem, o dono clica em
    dispensar, mas o sino continua mostrando 1 até o TTL vencer — e ele
    clica de novo achando que não funcionou."""
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    # Aquece o cache com a contagem "suja" (1 sinal novo).
    assert notificacoes.contar_nao_vistos(db, "loja-teste", _usuario_id(db)) == 1

    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 200

    assert notificacoes.contar_nao_vistos(db, "loja-teste", _usuario_id(db)) == 0


def test_dispensar_entitlement_ausente_bloqueia_e_nao_muda_estado(client, monkeypatch):
    """CSRF válido pelo mesmo motivo de ``test_visto_entitlement_ausente_...``
    acima — token inválido esconderia a remoção do gate de entitlement atrás
    do 403 de CSRF."""
    _ligar(monkeypatch)
    sinal_id = _semear_sinal()
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    pagina = client.get("/app/loja/perfil")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


def test_dispensar_com_entitlement_presente_libera(client, monkeypatch):
    _ligar(monkeypatch)
    sinal_id = _semear_sinal()
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    _seedar_modulo_copiloto()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 200
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
    finally:
        db.close()


def _usuario_id(db):
    from app.models import Usuario

    return db.query(Usuario).filter(Usuario.email == "dono@loja.test").one().id
