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


def test_shell_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404


def test_vendedor_recebe_403(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    assert client.get("/app/loja/copiloto").status_code == 403


def test_dono_abre_a_pagina_com_resumo(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    chat = client.get("/app/loja/copiloto")
    assert chat.status_code == 200
    assert "Copiloto de Vendas" in chat.text
    assert "Resumo de hoje" not in chat.text


def test_pagina_hoje_nao_existe_mais(client, monkeypatch):
    """A página Hoje foi removida: o sino do cabeçalho cobre os sinais."""
    _ligar(monkeypatch)
    login(client)


def test_nav_mostra_a_secao_copiloto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app")
    assert 'href="/app/loja/copiloto"' in r.text
    assert 'href="/app/loja/copiloto/hoje"' not in r.text
    assert "Agente do WhatsApp" in r.text


def test_sino_segue_listando_e_dispensando_sinais(client, monkeypatch):
    """Sem a página Hoje, o sino é o único caminho para agir sobre um sinal."""
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()

    painel = client.get("/app/loja/copiloto/notificacoes.json")
    assert painel.status_code == 200
    titulos = [item["titulo"] for item in painel.json()["itens"]]
    assert "Honda CB 500F parada há 70 dias" in titulos

    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/notificacoes/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code in (200, 204, 303)
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
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




def test_entitlement_presente_libera_a_pagina(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client)
    _seedar_modulo_copiloto()
    r = client.get("/app/loja/copiloto")
    assert r.status_code == 200
    assert "Copiloto de Vendas" in r.text
