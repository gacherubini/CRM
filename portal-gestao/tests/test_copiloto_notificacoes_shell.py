"""Contagem cacheada de não-vistos (F4/Task 1): notificacoes.py + template_extras.

Isolamento de ``cache_nao_vistos`` (TTL de relógio real, por processo):
fixture autouse em ``tests/conftest.py``, vale para todo teste do repositório —
não só os desta rota.
"""
from conftest import criar_usuario, seed_loja_operacional

from app.loja.copiloto import notificacoes
from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import contar_sinais_novos, sincronizar_sinais
from app.models import LojaOperacionalProjecao, Usuario
from app.web.loja_shell import template_extras


class _FakeRequest:
    """``template_extras`` só usa ``request.session`` (mapping) — não precisa
    de um Request FastAPI de verdade para este teste."""

    def __init__(self):
        self.session: dict = {}


def _ligar_shell_e_entitlements(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1")


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
