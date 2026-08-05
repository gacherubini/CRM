"""Shell de navegação Revy Loja (F0/F1) — flags default off preservam legado."""
from conftest import csrf_da_resposta, login

from app.loja.navigation import build_nav, flatten_nav, nav_item_is_active
from app.loja.types import EntitlementState, NavItem, StoreContext


def _store(roles=("dono",), slug="loja-teste"):
    return StoreContext(loja_slug=slug, roles=frozenset(roles), loja_state="ativa")


def _ents(vendas=True, estoque=True, ativa=True, slug="loja-teste"):
    return EntitlementState(
        loja_slug=slug,
        loja_ativa=ativa,
        vendas_enabled=vendas,
        estoque_enabled=estoque,
        source="test",
    )


def test_nav_somente_vendas_e_estoque_com_acessos_bancarios():
    sections = build_nav(_store(), _ents(), shell_enabled=True)
    titles = [s.title for s in sections]
    assert titles == ["Vendas", "Estoque", "Ajustes", "Conta"]
    items = flatten_nav(sections)
    labels = [i.label for i in items]
    assert labels == [
        "Visão geral",
        "Atendimento",
        "Visão geral",
        "Veículos",
        "Acessos bancários",
        "Catálogo",
        "Grupo do estoque",
        "Integrações",
        "Equipe",
        "Perfil",
    ]
    hrefs = {i.href for i in items}
    assert "/app/loja/vendas" in hrefs
    assert "/app/loja/atendimento" in hrefs
    assert "/app/loja/estoque" in hrefs
    assert "/app/loja/estoque/veiculos" in hrefs
    assert "/app/financeiras" in hrefs
    assert "/app/loja/catalogo" in hrefs
    assert "/app/operacao/numeros" in hrefs
    assert "/app/loja/integracoes" in hrefs
    assert "/app/loja/equipe" in hrefs
    assert "/app/loja/perfil" in hrefs
    # Senha saiu de Ajustes (agora em Conta → Perfil)
    assert "/conta/senha" not in hrefs
    # Sem config técnica de tráfego/campanhas
    assert not any("trafego" in i.href or "campanhas" in i.href for i in items)
    assert not any(i.href.startswith("/app/configuracoes") for i in items)


def test_nav_oculta_estoque_sem_entitlement():
    sections = build_nav(_store(), _ents(estoque=False), shell_enabled=True)
    titles = [s.title for s in sections]
    assert "Estoque" not in titles
    assert "Vendas" in titles


def test_nav_vendedor_sem_acessos_bancarios():
    sections = build_nav(_store(roles=("vendedor",)), _ents(), shell_enabled=True)
    items = flatten_nav(sections)
    assert not any(i.href == "/app/financeiras" for i in items)
    # Vendedor também vê Perfil (Conta), mas não Ajustes
    assert any(i.href == "/app/loja/perfil" for i in items)
    assert "Ajustes" not in [s.title for s in sections]
    assert "Conta" in [s.title for s in sections]


def test_nav_shell_desligado_vazio():
    assert build_nav(_store(), _ents(), shell_enabled=False) == ()


def test_nav_item_active_prefix_estoque():
    visao = NavItem(
        label="Visão geral",
        href="/app/loja/estoque",
        section="Estoque",
        active_prefix="/app/loja/estoque",
    )
    veiculos = NavItem(
        label="Veículos",
        href="/app/loja/estoque/veiculos",
        section="Estoque",
        active_prefix="/app/loja/estoque/veiculos",
    )
    assert nav_item_is_active(visao, "/app/loja/estoque") is True
    assert nav_item_is_active(visao, "/app/loja/estoque/veiculos") is False
    assert nav_item_is_active(veiculos, "/app/loja/estoque/veiculos") is True
    # Lista/CRUD legado após redirect de /app/loja/estoque/veiculos
    assert nav_item_is_active(veiculos, "/app/estoque") is True
    assert nav_item_is_active(veiculos, "/app/estoque/novo") is True
    assert nav_item_is_active(visao, "/app/estoque") is False


def test_shell_off_mantem_nav_legado(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    login(client)
    r = client.get("/app/estoque")
    assert r.status_code == 200
    assert 'href="/app/simulacoes"' in r.text
    assert 'href="/app/equipe"' in r.text
    assert "Revy Loja" not in r.text or "Revy" in r.text
    assert 'href="/app/loja/vendas"' not in r.text


def test_shell_on_exibe_brand_e_nav_modulos(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    login(client)
    r = client.get("/app")
    assert r.status_code == 200
    assert "Revy Loja" in r.text
    assert 'href="/app/loja/vendas"' in r.text
    assert 'href="/app/loja/atendimento"' in r.text
    assert 'href="/app/loja/estoque"' in r.text
    assert 'href="/app/loja/estoque/veiculos"' in r.text
    # Menu técnico some do shell
    assert 'href="/app/simulacoes"' not in r.text
    assert 'href="/app/configuracoes"' not in r.text
    assert 'href="/app/equipe"' not in r.text


def test_shell_on_estoque_veiculos_redireciona_legado(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    login(client)
    r2 = client.get("/app/loja/estoque/veiculos", follow_redirects=False)
    assert r2.status_code == 303
    assert r2.headers["location"] == "/app/estoque"


def test_atendimento_sem_flag_retorna_404(client, monkeypatch):
    """Atendimento real exige REVY_LOJA_ATENDIMENTO_ENABLED (F4)."""
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ATENDIMENTO_ENABLED", "0")
    login(client)
    r = client.get("/app/loja/atendimento", follow_redirects=False)
    assert r.status_code == 404


def test_shell_off_vendas_retorna_404(client, monkeypatch):
    """Overview F3 não expõe path novo com shell off."""
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    login(client)
    r = client.get("/app/loja/vendas", follow_redirects=False)
    assert r.status_code == 404
