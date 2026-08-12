"""Contagem cacheada de não-vistos (F4/Task 1): notificacoes.py + template_extras.

Isolamento de ``cache_nao_vistos`` (TTL de relógio real, por processo):
fixture autouse em ``tests/conftest.py``, vale para todo teste do repositório —
não só os desta rota.
"""
from types import SimpleNamespace

from conftest import criar_usuario, seed_loja_operacional

from app.loja.copiloto import notificacoes
from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import contar_sinais_novos, sincronizar_sinais
from app.loja.entitlements import fail_open
from app.models import LojaOperacionalProjecao, Usuario
from app.web.loja_shell import copiloto_secao_liberada, template_extras


class _FakeRequest:
    """``template_extras`` só usa ``request.session`` (mapping) — não precisa
    de um Request FastAPI de verdade para este teste."""

    def __init__(self):
        self.session: dict = {}


def _ligar_shell_e_entitlements(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")
    # Gate quádruplo (F4/Task 1, correção pós-review): a flag global do
    # Copiloto entra no gate do sino também — default é "1" aqui para não
    # quebrar os testes que não são sobre ela; test_flag_global_do_copiloto_*
    # sobrescreve para "0" depois de chamar este helper.
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _seedar_modulo_copiloto(db, loja_slug="loja-teste", ligado=True):
    seed_loja_operacional(db, loja_slug=loja_slug, state="ativa")
    if ligado:
        db.add(
            LojaOperacionalProjecao(
                loja_slug=loja_slug,
                aggregate="copiloto",
                version=1,
                state="ativo",
                event_id="seed-copiloto",
            )
        )
    db.commit()


def _usuario(db, email):
    return db.query(Usuario).filter(Usuario.email == email).one()


def _cand(entidade="v1", regra="estoque_parado"):
    return SinalCandidato(
        regra=regra,
        severidade="atencao",
        titulo="Parada há 70 dias",
        detalhe="R$ 25.000,00 de capital preso.",
        entidade_ref=entidade,
        dados={"veiculo_id": entidade},
    )


# --- (a)-(c): gate de papel/entitlement em template_extras ------------------


def test_gestor_com_entitlement_ve_a_contagem_real(db, monkeypatch):
    _ligar_shell_e_entitlements(monkeypatch)
    criar_usuario(papel="dono", email="dono@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db)
    sincronizar_sinais(db, "loja-teste", [_cand()])
    usuario = _usuario(db, "dono@loja.test")

    extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] == 1


def test_vendedor_recebe_none(db, monkeypatch):
    _ligar_shell_e_entitlements(monkeypatch)
    criar_usuario(papel="vendedor", email="v@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db)
    sincronizar_sinais(db, "loja-teste", [_cand()])
    usuario = _usuario(db, "v@loja.test")

    extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] is None


def test_loja_sem_modulo_recebe_none_mesmo_com_papel_certo(db, monkeypatch):
    _ligar_shell_e_entitlements(monkeypatch)
    criar_usuario(papel="dono", email="dono2@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db, ligado=False)  # loja ativa, mas sem o módulo
    usuario = _usuario(db, "dono2@loja.test")

    extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] is None


def test_flag_global_do_copiloto_desligada_recebe_none(db, monkeypatch):
    """A seção Copiloto 404 com REVY_LOJA_COPILOTO_ENABLED=0 mesmo com shell
    ligado, entitlement do módulo ok e papel de gestão — o sino tem que
    concordar, senão mostra contagem para uma seção que não existe."""
    _ligar_shell_e_entitlements(monkeypatch)
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    criar_usuario(papel="dono", email="dono3@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db)
    usuario = _usuario(db, "dono3@loja.test")

    extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] is None


# --- copiloto_secao_liberada: fonte única dos 4 gates (sino + seção) -------


def test_copiloto_secao_liberada_true_quando_as_quatro_condicoes_batem():
    ents = fail_open("loja-teste", {"dono"})  # copiloto_enabled=True p/ dono
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents, usuario, shell_enabled=True, copiloto_enabled=True
        )
        is True
    )


def test_copiloto_secao_liberada_false_com_shell_desligado():
    ents = fail_open("loja-teste", {"dono"})
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents, usuario, shell_enabled=False, copiloto_enabled=True
        )
        is False
    )


def test_copiloto_secao_liberada_false_com_flag_global_desligada():
    ents = fail_open("loja-teste", {"dono"})
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents, usuario, shell_enabled=True, copiloto_enabled=False
        )
        is False
    )


def test_copiloto_secao_liberada_false_sem_modulo_no_entitlement():
    ents = fail_open("loja-teste", set())  # sem cargo -> copiloto_enabled=False
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents, usuario, shell_enabled=True, copiloto_enabled=True
        )
        is False
    )


def test_copiloto_secao_liberada_false_com_papel_fora_da_gestao():
    ents = fail_open("loja-teste", {"vendedor"})
    usuario = SimpleNamespace(papel="vendedor")
    assert (
        copiloto_secao_liberada(
            ents, usuario, shell_enabled=True, copiloto_enabled=True
        )
        is False
    )


# --- (d): degradação sem propagar --------------------------------------------


def test_excecao_na_contagem_vira_none_e_nao_propaga(db, monkeypatch, caplog):
    _ligar_shell_e_entitlements(monkeypatch)
    criar_usuario(papel="gerente", email="gerente@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db)
    usuario = _usuario(db, "gerente@loja.test")

    def _explode(db, loja_slug, usuario_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(notificacoes, "contar_nao_vistos", _explode)
    import logging

    with caplog.at_level(logging.WARNING):
        extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# --- (e)/(f): cache TTL e invalidação ----------------------------------------


def _espiao_de_contar_sinais(monkeypatch):
    chamadas = []
    original = contar_sinais_novos

    def _espiao(db, loja_slug, usuario_id):
        chamadas.append((loja_slug, usuario_id))
        return original(db, loja_slug, usuario_id)

    monkeypatch.setattr(notificacoes, "contar_sinais_novos", _espiao)
    return chamadas


def test_segunda_chamada_dentro_do_ttl_nao_vai_ao_banco(db, monkeypatch):
    sincronizar_sinais(db, "loja-teste", [_cand()])
    chamadas = _espiao_de_contar_sinais(monkeypatch)

    primeira = notificacoes.contar_nao_vistos(db, "loja-teste", "user-a")
    segunda = notificacoes.contar_nao_vistos(db, "loja-teste", "user-a")

    assert primeira == segunda == 1
    assert len(chamadas) == 1


def test_invalidar_contagem_com_usuario_forca_releitura(db, monkeypatch):
    sincronizar_sinais(db, "loja-teste", [_cand()])
    chamadas = _espiao_de_contar_sinais(monkeypatch)

    notificacoes.contar_nao_vistos(db, "loja-teste", "user-a")
    notificacoes.invalidar_contagem("loja-teste", "user-a")
    notificacoes.contar_nao_vistos(db, "loja-teste", "user-a")

    assert len(chamadas) == 2


def test_chave_do_cache_inclui_usuario(db):
    """Cachear só por loja devolveria a contagem de uma pessoa (o sócio) para
    outra — aqui, user-a marcou visto e user-b não; as contagens cacheadas
    não podem se misturar."""
    from app.loja.copiloto.sinais_store import marcar_visto
    from app.models import CopilotoSinal

    sincronizar_sinais(db, "loja-teste", [_cand()])
    sinal = db.query(CopilotoSinal).one()
    marcar_visto(db, "loja-teste", sinal.id, "user-a")

    assert notificacoes.contar_nao_vistos(db, "loja-teste", "user-a") == 0
    assert notificacoes.contar_nao_vistos(db, "loja-teste", "user-b") == 1


def test_invalidar_sem_usuario_limpa_a_loja_inteira(db, monkeypatch):
    """``invalidar_contagem(loja_slug)`` sem usuário precisa limpar TODAS as
    entradas da loja: o worker que cria um sinal novo não sabe de quem é o
    cache quente — se limpasse só uma pessoa, o resto ficaria com o número
    velho até o TTL vencer sozinho."""
    sincronizar_sinais(db, "loja-teste", [_cand()])
    chamadas = _espiao_de_contar_sinais(monkeypatch)

    notificacoes.contar_nao_vistos(db, "loja-teste", "user-a")
    notificacoes.contar_nao_vistos(db, "loja-teste", "user-b")
    assert len(chamadas) == 2

    notificacoes.invalidar_contagem("loja-teste")

    notificacoes.contar_nao_vistos(db, "loja-teste", "user-a")
    notificacoes.contar_nao_vistos(db, "loja-teste", "user-b")
    assert len(chamadas) == 4
