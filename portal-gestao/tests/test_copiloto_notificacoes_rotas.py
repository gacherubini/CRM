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
from conftest import criar_usuario, csrf_da_resposta, login, seed_loja_operacional

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


def _semear_sinal(loja="loja-teste", entidade="v1", regra="estoque_parado", **extra):
    db = SessionLocal()
    try:
        sincronizar_sinais(
            db,
            loja,
            [
                SinalCandidato(
                    regra=regra,
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


def test_listar_traz_rotulo_icone_e_severidade_padrao_do_catalogo(client, monkeypatch):
    """A rota nasceu (F4/Task 3) sem conhecer o catálogo (F4/Task 5) — as
    duas tasks rodaram em paralelo, em branches diferentes. Este teste prende
    a ligação: o item de um sinal com regra CONHECIDA carrega o rótulo, o
    ícone e a severidade padrão de ``catalogo_regra``, não só os campos que
    já existiam antes desta correção."""
    _ligar(monkeypatch)
    login(client)
    _semear_sinal()  # regra="estoque_parado" — ver _semear_sinal acima
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 200
    item = r.json()["itens"][0]

    esperado = notificacoes.catalogo_regra("estoque_parado")
    assert item["rotulo"] == esperado.rotulo == "Estoque parado"
    assert item["icone"] == esperado.icone == "estoque"
    assert item["severidade_padrao"] == esperado.severidade_padrao == "atencao"
    # Nome cru da regra nunca vaza para o payload — só o rótulo do catálogo.
    assert "regra" not in item
    assert "estoque_parado" not in item.values()


def test_listar_com_regra_desconhecida_traz_rotulo_generico_nunca_o_nome_cru(
    client, monkeypatch
):
    """Regra sem entrada no catálogo (dado inesperado, ou regra nova ainda
    não catalogada) cai em ``ENTRADA_GENERICA`` — nunca no nome cru da
    função/regra. Vazar ``regra_preco_fora_da_faixa`` (ou qualquer nome de
    função) no painel do sino é vazamento de implementação para o lojista."""
    _ligar(monkeypatch)
    login(client)
    _semear_sinal(regra="regra_fantasma_desconhecida")
    r = client.get("/app/loja/copiloto/notificacoes.json")
    assert r.status_code == 200
    item = r.json()["itens"][0]

    assert item["rotulo"] == notificacoes.ENTRADA_GENERICA.rotulo
    assert item["icone"] == notificacoes.ENTRADA_GENERICA.icone
    assert item["severidade_padrao"] == notificacoes.ENTRADA_GENERICA.severidade_padrao
    assert item["rotulo"] != "regra_fantasma_desconhecida"
    assert "regra_fantasma_desconhecida" not in item.values()


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


# --- Alcance da invalidação com DUAS pessoas na mesma loja --------------------
#
# Achado da revisão (Important pós-aprovação): todo teste de cache acima
# aquece e confere o cache de um único usuário logado — "invalidar só o meu"
# e "invalidar o de todos" são indistinguíveis com uma pessoa só. Os dois
# testes abaixo precisam de um segundo gestor (mesma loja) para separar as
# duas garantias de verdade: visto é por pessoa (só o cache de quem marcou
# cai); dispensar é da loja inteira (o cache de todo mundo tem que cair,
# porque o estado que mudou é compartilhado).


def _usuario_por_email(db, email):
    from app.models import Usuario

    return db.query(Usuario).filter(Usuario.email == email).one()


def _espiar_contar_sinais_novos(monkeypatch):
    """Mesma técnica de ``test_copiloto_notificacoes_shell.py``: espiona a
    função NÃO cacheada para contar consultas reais ao banco. Necessário
    porque, para ``visto``, o valor recalculado do outro usuário seria igual
    de qualquer jeito (visto de A não muda o que B viu) — só o NÚMERO de
    chamadas distingue "cache de B intacto" de "cache de B invalidado e
    recalculado por acaso com o mesmo resultado"."""
    chamadas = []
    original = notificacoes.contar_sinais_novos

    def _espiao(db, loja_slug, usuario_id):
        chamadas.append((loja_slug, usuario_id))
        return original(db, loja_slug, usuario_id)

    monkeypatch.setattr(notificacoes, "contar_sinais_novos", _espiao)
    return chamadas


def test_visto_invalida_apenas_o_cache_de_quem_marcou(client, monkeypatch, db):
    _ligar(monkeypatch)
    login(client, papel="dono", email="gestor-a@loja.test")
    criar_usuario(papel="gerente", email="gestor-b@loja.test", loja_slug="loja-teste")
    usuario_a = _usuario_por_email(db, "gestor-a@loja.test")
    usuario_b = _usuario_por_email(db, "gestor-b@loja.test")
    sinal_id = _semear_sinal()

    # Aquece o cache dos dois ANTES de ligar o espião — o aquecimento não
    # conta como chamada "durante" a ação que estamos medindo.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id) == 1
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id) == 1

    chamadas = _espiar_contar_sinais_novos(monkeypatch)

    pagina = client.get("/app/loja/copiloto")
    client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/visto",
        data={"csrf": csrf_da_resposta(pagina)},
    )

    # Cache de A caiu: a leitura seguinte tem que ir ao banco de novo.
    notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id)
    assert len(chamadas) == 1

    # Cache de B continua quente: a leitura seguinte NÃO pode bater no banco.
    notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id)
    assert len(chamadas) == 1


def test_dispensar_invalida_o_cache_de_toda_a_loja_nao_so_de_quem_clicou(
    client, monkeypatch, db
):
    _ligar(monkeypatch)
    login(client, papel="dono", email="gestor-a2@loja.test")
    criar_usuario(papel="gerente", email="gestor-b2@loja.test", loja_slug="loja-teste")
    usuario_a = _usuario_por_email(db, "gestor-a2@loja.test")
    usuario_b = _usuario_por_email(db, "gestor-b2@loja.test")
    sinal_id = _semear_sinal()

    # Aquece o cache dos dois.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id) == 1
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id) == 1

    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
    )
    assert r.status_code == 200

    # O sinal sumiu de verdade para os dois (estado é da loja) — o cache de
    # B (que não clicou em nada) tem que refletir isso, não a foto velha.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id) == 0
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id) == 0


def _usuario_id(db):
    return _usuario_por_email(db, "dono@loja.test").id
