"""Gate do módulo Financeiro da Revy Loja (leva de 2026-08-16).

Gate triplo, igual ao Copiloto: flag de rollout **e** entitlement do módulo
**e** papel de gestão. Com qualquer um faltando a seção não existe.

E a regra que não se negocia: custo e lucro nunca aparecem para vendedor.
"""
from __future__ import annotations

from conftest import login, seed_loja_operacional

from app.config import settings
from app.db import SessionLocal
from app.loja.entitlements import fail_open, from_allows_processing
from app.loja.navigation import build_nav, flatten_nav
from app.loja.permissions import module_enabled
from app.loja.types import EntitlementState, Module, StoreContext
from app.models import LojaOperacionalProjecao


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_FINANCEIRO_ENABLED", "1")
    object.__setattr__(settings, "revy_loja_shell_enabled", True)


def _store(roles=("dono",)):
    return StoreContext(
        loja_slug="loja-teste", roles=frozenset(roles), loja_state="ativa"
    )


def _ents(financeiro=True):
    return EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
        financeiro_enabled=financeiro,
    )


def _seedar_modulo(loja_slug="loja-teste", aggregate="financeiro", state="ativo"):
    db = SessionLocal()
    try:
        seed_loja_operacional(db, loja_slug=loja_slug, state="ativa")
        row = db.get(LojaOperacionalProjecao, (loja_slug, aggregate))
        if row is None:
            db.add(
                LojaOperacionalProjecao(
                    loja_slug=loja_slug,
                    aggregate=aggregate,
                    version=1,
                    state=state,
                    event_id=f"seed-{aggregate}",
                )
            )
        else:
            row.state = state
        db.commit()
    finally:
        db.close()


# --- Entitlement e navegação -------------------------------------------------


def test_module_enabled_reconhece_financeiro():
    assert module_enabled(_ents(financeiro=True), Module.FINANCEIRO) is True
    assert module_enabled(_ents(financeiro=False), Module.FINANCEIRO) is False


def test_fail_open_libera_financeiro_para_papel_operacional():
    """Com entitlements off o portal legado não pode perder função."""
    assert fail_open("loja-teste", {"dono"}).financeiro_enabled is True
    assert fail_open("loja-teste", {"externo"}).financeiro_enabled is False


def test_entitlement_por_projecao_consulta_o_modulo_financeiro():
    consultados = []

    def _allows(slug, module=None):
        consultados.append(module)
        return True

    estado = from_allows_processing("loja-teste", _allows)
    assert Module.FINANCEIRO.value in consultados
    assert estado.financeiro_enabled is True


def test_nav_mostra_financeiro_para_gestao():
    sections = build_nav(
        _store(), _ents(), shell_enabled=True, financeiro_enabled=True
    )
    assert "Financeiro" in [s.title for s in sections]
    hrefs = {i.href for i in flatten_nav(sections)}
    assert "/app/loja/financeiro" in hrefs
    assert "/app/loja/financeiro/despesas" in hrefs


def test_nav_sem_financeiro_quando_entitlement_falta():
    sections = build_nav(
        _store(),
        _ents(financeiro=False),
        shell_enabled=True,
        financeiro_enabled=True,
    )
    assert "Financeiro" not in [s.title for s in sections]


def test_nav_sem_financeiro_com_flag_desligada():
    sections = build_nav(
        _store(), _ents(), shell_enabled=True, financeiro_enabled=False
    )
    assert "Financeiro" not in [s.title for s in sections]


def test_nav_sem_financeiro_para_vendedor():
    sections = build_nav(
        _store(roles=("vendedor",)),
        _ents(),
        shell_enabled=True,
        financeiro_enabled=True,
    )
    assert "Financeiro" not in [s.title for s in sections]


# --- Rotas -------------------------------------------------------------------


def test_flag_off_retorna_404(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_FINANCEIRO_ENABLED", "0")
    login(client, papel="dono", email="dono@loja.test")
    assert client.get("/app/loja/financeiro", follow_redirects=False).status_code == 404
    assert (
        client.get("/app/loja/financeiro/despesas", follow_redirects=False).status_code
        == 404
    )


def test_shell_off_retorna_404(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    object.__setattr__(settings, "revy_loja_shell_enabled", False)
    login(client, papel="dono", email="dono@loja.test")
    assert client.get("/app/loja/financeiro", follow_redirects=False).status_code == 404


def test_vendedor_recebe_403_no_financeiro(client, monkeypatch):
    """Armadilha nº 1 do README: custo e lucro nunca para vendedor."""
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="vendedor@loja.test")
    assert client.get("/app/loja/financeiro").status_code == 403
    assert client.get("/app/loja/financeiro/despesas").status_code == 403


def test_dono_abre_o_financeiro(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="dono", email="dono@loja.test")
    r = client.get("/app/loja/financeiro")
    assert r.status_code == 200
    assert "Resultado financeiro" in r.text


def test_entitlement_ausente_bloqueia_mesmo_com_papel_certo(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client, papel="dono", email="dono@loja.test")
    assert client.get("/app/loja/financeiro", follow_redirects=False).status_code == 403


def test_entitlement_presente_libera(client, monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    login(client, papel="dono", email="dono@loja.test")
    _seedar_modulo()
    assert client.get("/app/loja/financeiro").status_code == 200


def _metricas_por_grade(html: str) -> list[int]:
    """Quantas `.metric` cada `.metric-grid` da página tem."""
    import re

    grades = []
    for bloco in re.split(r'<div class="metric-grid">', html)[1:]:
        # Até o fechamento da grade: a primeira `</div>` seguida de `</section>`
        # ou de outra grade. Contar `class="metric` já basta para o limite.
        corpo = bloco.split("</section>")[0]
        grades.append(len(re.findall(r'class="metric(?: accent)?"', corpo)))
    return grades


def test_nenhuma_grade_de_metricas_passa_de_quatro(client, monkeypatch):
    """`.metric-grid` é grid fixo de 4 colunas SEM separação entre linhas.

    Com 5+ métricas a quinta cai embaixo da primeira e, por causa do
    `border-right` de `.metric`, lê como continuação do mesmo card — foi o que
    aconteceu na primeira versão desta tela (verificado no navegador, não pelo
    pytest). Passar de 4 exige grade nova, não mais um item.
    """
    from decimal import Decimal

    from app.models import DespesaFixaLoja, Venda, agora

    _ligar(monkeypatch)
    # Sem venda a página cai no estado vazio e não renderiza grade nenhuma:
    # o teste só vale sobre a tela cheia.
    db = SessionLocal()
    try:
        db.add(
            Venda(
                loja_slug="loja-teste",
                vendedor_email="dono@loja.test",
                descricao="Honda CG 160",
                preco_venda=Decimal("14900"),
                custo_veiculo=Decimal("11200"),
                status="confirmada",
                confirmada_em=agora(),
            )
        )
        db.add(
            DespesaFixaLoja(
                loja_slug="loja-teste",
                categoria="aluguel",
                descricao="Aluguel",
                valor_mensal=Decimal("6000"),
                inicio_competencia="2020-01",
            )
        )
        db.commit()
    finally:
        db.close()

    login(client, papel="dono", email="dono@loja.test")
    r = client.get("/app/loja/financeiro")
    assert r.status_code == 200
    grades = _metricas_por_grade(r.text)
    assert grades, "a página não renderizou nenhuma grade de métricas"
    assert all(n <= 4 for n in grades), f"grade com mais de 4 métricas: {grades}"
