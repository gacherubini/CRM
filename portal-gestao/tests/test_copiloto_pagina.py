from conftest import criar_usuario, csrf_da_resposta, login, seed_loja_operacional

from app.db import SessionLocal
from app.loja.copiloto import notificacoes
from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.models import CopilotoSinal, CopilotoSinalVisto, LojaOperacionalProjecao

# Isolamento de cache_overview (TTL global por processo): fixture autouse
# em tests/conftest.py, vale para todo teste do repositório — não só desta rota.


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _seedar_modulo_copiloto(loja_slug="loja-teste", state="ativo"):
    """Grava/atualiza a projeção do módulo Copiloto (aggregate='copiloto')."""
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


def _semear_sinal(loja="loja-teste"):
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
                    entidade_ref="v1",
                    dados={"veiculo_id": "v1"},
                )
            ],
        )
        return db.query(CopilotoSinal).one().id
    finally:
        db.close()


def test_flag_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404
    assert client.get("/app/loja/copiloto/hoje", follow_redirects=False).status_code == 404


def test_shell_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404
    assert client.get("/app/loja/copiloto/hoje", follow_redirects=False).status_code == 404


def test_vendedor_recebe_403(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    assert client.get("/app/loja/copiloto").status_code == 403
    assert client.get("/app/loja/copiloto/hoje").status_code == 403


def test_dono_abre_a_pagina_com_resumo(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    chat = client.get("/app/loja/copiloto")
    assert chat.status_code == 200
    assert "Copiloto de Vendas" in chat.text
    assert "Resumo de hoje" not in chat.text
    hoje = client.get("/app/loja/copiloto/hoje")
    assert hoje.status_code == 200
    assert "Resumo de hoje" in hoje.text


def test_pagina_lista_o_sinal_aberto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _semear_sinal()
    r = client.get("/app/loja/copiloto/hoje")
    assert "Honda CB 500F parada há 70 dias" in r.text
    chat = client.get("/app/loja/copiloto")
    assert "Honda CB 500F parada há 70 dias" not in chat.text


def test_nav_mostra_a_secao_copiloto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app")
    assert 'href="/app/loja/copiloto"' in r.text
    assert 'href="/app/loja/copiloto/hoje"' in r.text
    assert "Agente do WhatsApp" in r.text


def test_dispensar_sinal_exige_csrf(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": "invalido"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


def test_dispensar_sinal_com_csrf_valido(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/app/loja/copiloto/hoje")
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
    finally:
        db.close()


def test_sinal_de_outra_loja_nao_e_dispensavel(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal(loja="outra-loja")
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


# --- Entitlement por loja: menu oculto não é autorização (permissions.py:1) ---
# Com REVY_LOJA_ENTITLEMENTS_ENABLED=1 e o módulo Copiloto NÃO contratado
# (sem aggregate "copiloto" na projeção), a rota tem que bloquear sozinha —
# mesmo com shell/flag ligados e papel de gestão certo.


def test_entitlement_ausente_bloqueia_a_pagina_mesmo_com_papel_certo(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    r = client.get("/app/loja/copiloto", follow_redirects=False)
    assert r.status_code == 403
    assert client.get("/app/loja/copiloto/hoje", follow_redirects=False).status_code == 403


def test_entitlement_ausente_bloqueia_dispensar_e_nao_muta_sinal(client, monkeypatch):
    _ligar(monkeypatch)
    sinal_id = _semear_sinal()
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": "qualquer"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


def test_entitlement_ausente_bloqueia_marcar_visto(client, monkeypatch):
    _ligar(monkeypatch)
    sinal_id = _semear_sinal()
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/visto",
        data={"csrf": "qualquer"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    db = SessionLocal()
    try:
        # marcar_visto não mexe em CopilotoSinal.estado (fica sempre "novo",
        # visto ou não) — a prova real do bloqueio é que nenhuma linha foi
        # gravada em copiloto_sinal_visto.
        assert db.query(CopilotoSinal).one().estado == "novo"
        assert db.query(CopilotoSinalVisto).count() == 0
    finally:
        db.close()


def test_entitlement_presente_libera_a_pagina(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    _seedar_modulo_copiloto()
    r = client.get("/app/loja/copiloto")
    assert r.status_code == 200
    assert "Copiloto de Vendas" in r.text
    hoje = client.get("/app/loja/copiloto/hoje")
    assert hoje.status_code == 200
    assert "Resumo de hoje" in hoje.text


def test_entitlement_presente_libera_dispensar(client, monkeypatch):
    _ligar(monkeypatch)
    sinal_id = _semear_sinal()
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    _seedar_modulo_copiloto()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
    finally:
        db.close()


# --- Alcance da invalidação de cache das rotas ANTIGAS da página --------------
#
# Achado da revisão final da fase (I1): `_acao_sinal` (as rotas de página
# `/sinais/{id}/visto` e `/sinais/{id}/dispensar`, distintas das rotas JSON do
# painel do sino) não chamava `invalidar_contagem` — o corpo da página lê o
# banco direto, mas o sino do cabeçalho lê o cache de 45s, então os dois
# discordavam logo após o clique. Mesma técnica de dois gestores usada em
# `test_copiloto_notificacoes_rotas.py` (commit 7d21c1a): com um usuário só,
# "invalidar apenas quem clicou" e "invalidar a loja inteira" são
# indistinguíveis.


def _usuario_por_email(db, email):
    from app.models import Usuario

    return db.query(Usuario).filter(Usuario.email == email).one()


def test_pagina_visto_invalida_apenas_o_cache_de_quem_marcou(client, monkeypatch, db):
    _ligar(monkeypatch)
    login(client, papel="dono", email="gestor-a3@loja.test")
    criar_usuario(papel="gerente", email="gestor-b3@loja.test", loja_slug="loja-teste")
    usuario_a = _usuario_por_email(db, "gestor-a3@loja.test")
    usuario_b = _usuario_por_email(db, "gestor-b3@loja.test")
    sinal_id = _semear_sinal()

    # Aquece o cache dos dois ANTES da ação.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id) == 1
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id) == 1

    chamadas = []
    original = notificacoes.contar_sinais_novos

    def _espiao(db, loja_slug, usuario_id):
        chamadas.append((loja_slug, usuario_id))
        return original(db, loja_slug, usuario_id)

    monkeypatch.setattr(notificacoes, "contar_sinais_novos", _espiao)

    pagina = client.get("/app/loja/copiloto")
    client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/visto",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )

    # Cache de A caiu: a leitura seguinte tem que ir ao banco de novo.
    notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id)
    assert len(chamadas) == 1

    # Cache de B continua quente: a leitura seguinte NÃO pode bater no banco.
    notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id)
    assert len(chamadas) == 1


def test_pagina_dispensar_invalida_o_cache_de_toda_a_loja(client, monkeypatch, db):
    _ligar(monkeypatch)
    login(client, papel="dono", email="gestor-a4@loja.test")
    criar_usuario(papel="gerente", email="gestor-b4@loja.test", loja_slug="loja-teste")
    usuario_a = _usuario_por_email(db, "gestor-a4@loja.test")
    usuario_b = _usuario_por_email(db, "gestor-b4@loja.test")
    sinal_id = _semear_sinal()

    # Aquece o cache dos dois.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id) == 1
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id) == 1

    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # O sinal sumiu de verdade para os dois (estado é da loja) — o cache de
    # B (que não clicou em nada) tem que refletir isso, não a foto velha.
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_a.id) == 0
    assert notificacoes.contar_nao_vistos(db, "loja-teste", usuario_b.id) == 0
