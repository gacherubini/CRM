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


def _ents_com_copiloto(slug="loja-teste"):
    return EntitlementState(
        loja_slug=slug,
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
        copiloto_enabled=True,
    )


def test_nav_somente_vendas_e_estoque_com_acessos_bancarios():
    sections = build_nav(_store(), _ents(), shell_enabled=True)
    titles = [s.title for s in sections]
    assert titles == ["Vendas", "Estoque", "Ajustes", "Conta"]
    items = flatten_nav(sections)
    labels = [i.label for i in items]
    # WhatsApp no menu depende da flag (default off nos unit tests sem flag).
    assert labels == [
        "Resultado",
        "Atendimento",
        "Vendas da loja",
        "Agente do WhatsApp",
        "Simulações",
        "Situação do estoque",
        "Veículos",
        "Vitrine",
        "Acessos bancários",
        "Grupo do estoque",
        "Integrações",
        "Equipe",
        "Perfil",
    ]
    hrefs = {i.href for i in items}
    assert "/app/loja/vendas" in hrefs
    assert "/app/loja/atendimento" in hrefs
    assert "/app/loja/agente" in hrefs
    assert "/app/simulacoes" in hrefs
    assert "/app/loja/estoque" in hrefs
    assert "/app/loja/estoque/veiculos" in hrefs
    assert "/app/financeiras" in hrefs
    assert "/app/loja/catalogo" not in hrefs
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
    # Vendedor simula (pode_simular inclui vendedor) → link no menu Vendas
    assert any(i.href == "/app/simulacoes" for i in items)
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


def test_nav_rotula_a_lista_de_vendas_por_papel():
    """"Vendas da loja" mente para o vendedor, que só enxerga as próprias."""
    gestao = flatten_nav(build_nav(_store(roles=("dono",)), _ents(), shell_enabled=True))
    vendedor = flatten_nav(
        build_nav(_store(roles=("vendedor",)), _ents(), shell_enabled=True)
    )

    def _label(items):
        return next(i.label for i in items if i.href == "/app/loja/vendas/lista")

    assert _label(gestao) == "Vendas da loja"
    assert _label(vendedor) == "Minhas vendas"


def test_nav_item_active_prefix_vendas():
    """Resultado nao pode acender junto com a lista de vendas."""
    resultado = NavItem(
        label="Resultado",
        href="/app/loja/vendas",
        section="Vendas",
        active_prefix="/app/loja/vendas",
    )
    lista = NavItem(
        label="Minhas vendas",
        href="/app/loja/vendas/lista",
        section="Vendas",
        active_prefix="/app/loja/vendas/lista",
    )
    assert nav_item_is_active(resultado, "/app/loja/vendas") is True
    assert nav_item_is_active(resultado, "/app/loja/vendas/lista") is False
    assert nav_item_is_active(lista, "/app/loja/vendas/lista") is True


def test_nav_copiloto_tem_um_item_so():
    """A página Hoje foi removida em 2026-08-16; o sino cobre os sinais."""
    sections = build_nav(
        _store(),
        _ents_com_copiloto(),
        shell_enabled=True,
        copiloto_enabled=True,
    )
    copiloto = next(s for s in sections if s.title == "Copiloto")
    assert [i.href for i in copiloto.items] == ["/app/loja/copiloto"]

    chat = copiloto.items[0]
    assert nav_item_is_active(chat, "/app/loja/copiloto") is True
    assert nav_item_is_active(chat, "/app/loja/vendas") is False


def _itens_acesos(html: str) -> list[str]:
    """hrefs do menu marcados como página atual no HTML renderizado."""
    import re

    return re.findall(r'<a class="nav-link[^"]*" href="([^"]+)"[^>]*aria-current="page"', html)


def test_shell_render_acende_apenas_a_pagina_atual(client, monkeypatch):
    """O template não pode reimplementar (e divergir de) nav_item_is_active.

    A regra existia em navigation.py e o base.html tinha uma cópia sem a
    exceção de Vendas: "Resultado" acendia junto com a lista de vendas.
    """
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    login(client)

    r = client.get("/app/loja/vendas/lista")
    assert r.status_code == 200
    assert _itens_acesos(r.text) == ["/app/loja/vendas/lista"]

    r = client.get("/app/loja/vendas")
    assert r.status_code == 200
    assert _itens_acesos(r.text) == ["/app/loja/vendas"]


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
    # Simulações é ferramenta de Vendas: presente no shell (sob a seção Vendas)
    assert 'href="/app/simulacoes"' in r.text
    # Config técnica continua fora do shell
    assert 'href="/app/configuracoes"' not in r.text
    assert 'href="/app/equipe"' not in r.text


def test_shell_nav_todos_os_itens_tem_icone(client, monkeypatch):
    """Item novo em navigation.py sem entrada em loja_icons vira link sem ícone."""
    import re

    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    login(client)
    r = client.get("/app")
    assert r.status_code == 200
    links = re.findall(r'<a class="nav-link[^"]*" href="([^"]+)"[^>]*>(.{0,10})', r.text)
    assert links, "shell não renderizou nenhum item de navegação"
    hrefs = {href for href, _ in links}
    assert "/app/loja/agente" in hrefs
    assert "/app/loja/copiloto" in hrefs
    sem_icone = [href for href, inicio in links if not inicio.startswith("<svg")]
    assert sem_icone == []


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


def test_nav_sem_copiloto_quando_entitlement_falta():
    """Copiloto é módulo contratável: sem entitlement, não aparece."""
    sections = build_nav(_store(), _ents(), shell_enabled=True, copiloto_enabled=True)
    assert "Copiloto" not in [s.title for s in sections]


def test_nav_copiloto_e_a_primeira_secao_quando_liberado():
    ents = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
        copiloto_enabled=True,
    )
    sections = build_nav(_store(), ents, shell_enabled=True, copiloto_enabled=True)
    assert [s.title for s in sections][0] == "Copiloto"
    labels = [i.label for i in flatten_nav(sections)]
    assert labels[0] == "Copiloto de Vendas"
    assert labels[1] == "Resultado"


def test_nav_copiloto_nao_aparece_para_vendedor():
    ents = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
        copiloto_enabled=True,
    )
    sections = build_nav(
        _store(roles=("vendedor",)), ents, shell_enabled=True, copiloto_enabled=True
    )
    assert "Copiloto" not in [s.title for s in sections]
