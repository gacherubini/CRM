"""Contagem cacheada de não-vistos (F4/Task 1): notificacoes.py + template_extras.

Isolamento de ``cache_nao_vistos`` (TTL de relógio real, por processo):
fixture autouse em ``tests/conftest.py``, vale para todo teste do repositório —
não só os desta rota.

F4/Task 2 acrescenta a UI: o sino e o painel em ``.topbar-actions``
(``base.html``). Esses testes batem em ``/app/loja/perfil`` — tela do shell
sem gate de módulo (qualquer papel autenticado acessa) — porque o sino
precisa aparecer em QUALQUER tela do shell, não só na do Copiloto.
"""
import itertools
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import criar_usuario, csrf_da_resposta, login, seed_loja_operacional

import app.main as app_main
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
            ents,
            usuario,
            shell_enabled=True,
            copiloto_enabled=True,
            entitlements_enabled=True,
        )
        is True
    )


def test_copiloto_secao_liberada_false_com_shell_desligado():
    ents = fail_open("loja-teste", {"dono"})
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents,
            usuario,
            shell_enabled=False,
            copiloto_enabled=True,
            entitlements_enabled=True,
        )
        is False
    )


def test_copiloto_secao_liberada_false_com_flag_global_desligada():
    ents = fail_open("loja-teste", {"dono"})
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents,
            usuario,
            shell_enabled=True,
            copiloto_enabled=False,
            entitlements_enabled=True,
        )
        is False
    )


def test_copiloto_secao_liberada_false_sem_modulo_no_entitlement():
    ents = fail_open("loja-teste", set())  # sem cargo -> copiloto_enabled=False
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents,
            usuario,
            shell_enabled=True,
            copiloto_enabled=True,
            entitlements_enabled=True,
        )
        is False
    )


def test_copiloto_secao_liberada_false_com_papel_fora_da_gestao():
    ents = fail_open("loja-teste", {"vendedor"})
    usuario = SimpleNamespace(papel="vendedor")
    assert (
        copiloto_secao_liberada(
            ents,
            usuario,
            shell_enabled=True,
            copiloto_enabled=True,
            entitlements_enabled=True,
        )
        is False
    )


def test_copiloto_secao_liberada_bypassa_modulo_com_entitlements_desligada():
    """Mesmo bypass de ``check_module_access()``: com entitlements OFF, a
    rota nunca olha módulo — mesmo um ``ents`` com módulo desligado não pode
    barrar o sino aqui, senão diverge da rota (Important #2 da revisão)."""
    ents = fail_open("loja-teste", set())  # copiloto_enabled=False (sem cargo)
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents,
            usuario,
            shell_enabled=True,
            copiloto_enabled=True,
            entitlements_enabled=False,
        )
        is True
    )


def test_copiloto_secao_liberada_aplica_modulo_com_entitlements_ligada():
    """Contraprova do teste acima: com entitlements ON, o módulo real do
    entitlement volta a valer (bypass é só para a flag desligada)."""
    ents = fail_open("loja-teste", set())  # copiloto_enabled=False
    usuario = SimpleNamespace(papel="dono")
    assert (
        copiloto_secao_liberada(
            ents,
            usuario,
            shell_enabled=True,
            copiloto_enabled=True,
            entitlements_enabled=True,
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


# --- Important #1 (revisão): sino precisa funcionar fora da tela do Copiloto -


def test_sessao_propria_nao_furou_o_cache(db, monkeypatch):
    """Duas chamadas seguidas sem ``db`` (como duas page views em telas
    diferentes do shell, dentro do TTL) abrem uma ``Session`` cada vez, mas
    só a primeira bate no banco de verdade — a segunda é o acerto de cache
    de ``contar_nao_vistos``. Prova que a sessão própria não reintroduz uma
    query por page view."""
    import app.web.loja_shell as loja_shell_mod

    sincronizar_sinais(db, "loja-teste", [_cand()])
    chamadas = _espiao_de_contar_sinais(monkeypatch)

    primeira = loja_shell_mod._contar_nao_vistos_com_sessao_propria(
        "loja-teste", "user-a", None
    )
    segunda = loja_shell_mod._contar_nao_vistos_com_sessao_propria(
        "loja-teste", "user-a", None
    )

    assert primeira == segunda == 1
    assert len(chamadas) == 1


def _capturar_contexto(monkeypatch):
    """Espiona ``templates.TemplateResponse`` (a mesma instância que TODAS as
    rotas do shell usam, importada de ``app.main``) para inspecionar o dict
    de contexto realmente passado pra rota, sem precisar de UI do sino
    (ainda não existe — é a próxima task) para provar que o valor chegou
    lá."""
    capturado = {}
    original = app_main.templates.TemplateResponse

    def _espiao(name, context=None, *args, **kwargs):
        capturado["context"] = context
        return original(name, context, *args, **kwargs)

    monkeypatch.setattr(app_main.templates, "TemplateResponse", _espiao)
    return capturado


def test_sessao_propria_e_sempre_fechada_mesmo_com_excecao(monkeypatch):
    """A sessão auto-provisionada precisa ser fechada sempre — inclusive
    quando ``contar_nao_vistos`` levanta. Testado direto na função
    (independente de HTTP) porque só assim dá pra observar ``close()`` sem
    depender do pool real de conexões."""
    import app.web.loja_shell as loja_shell_mod

    fechada = {"sucesso": False, "excecao": False}

    class _SessaoEspiao:
        def __init__(self, chave):
            self._chave = chave

        def close(self):
            fechada[self._chave] = True

    monkeypatch.setattr(loja_shell_mod, "SessionLocal", lambda: _SessaoEspiao("sucesso"))
    monkeypatch.setattr(
        loja_shell_mod.copiloto_notificacoes,
        "contar_nao_vistos",
        lambda db, loja_slug, usuario_id: 0,
    )
    resultado = loja_shell_mod._contar_nao_vistos_com_sessao_propria(
        "loja-teste", "user-a", None
    )
    assert resultado == 0
    assert fechada["sucesso"] is True

    monkeypatch.setattr(loja_shell_mod, "SessionLocal", lambda: _SessaoEspiao("excecao"))

    def _explode(db, loja_slug, usuario_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(loja_shell_mod.copiloto_notificacoes, "contar_nao_vistos", _explode)
    resultado = loja_shell_mod._contar_nao_vistos_com_sessao_propria(
        "loja-teste", "user-a", None
    )
    assert resultado is None
    assert fechada["excecao"] is True


def test_sessao_recebida_nao_e_fechada_pela_funcao(monkeypatch):
    """Sessão que já veio de fora (``db`` não-``None``) não é da função —
    ela não pode fechar uma sessão que não abriu."""
    import app.web.loja_shell as loja_shell_mod

    fechada = {"valor": False}

    class _SessaoEspiao:
        def close(self):
            fechada["valor"] = True

    monkeypatch.setattr(
        loja_shell_mod.copiloto_notificacoes,
        "contar_nao_vistos",
        lambda db, loja_slug, usuario_id: 3,
    )
    resultado = loja_shell_mod._contar_nao_vistos_com_sessao_propria(
        "loja-teste", "user-a", _SessaoEspiao()
    )
    assert resultado == 3
    assert fechada["valor"] is False


def test_badge_aparece_em_tela_que_nao_e_do_copiloto_com_entitlements_off(
    client, monkeypatch, db
):
    """Reproduz o achado da revisão pelo caminho real: ``/app/loja/vendas``
    (como ~90% das rotas do shell) chama ``contexto(request, usuario, ...)``
    SEM passar ``db=``. Com ``REVY_LOJA_ENTITLEMENTS_ENABLED`` no default do
    repo (desligada), ``contexto()`` não cria sessão de fallback, e sem
    sessão própria em ``_copiloto_nao_vistos`` o sino nunca aparecia fora da
    tela do Copiloto — que é a única rota que resolve ``db`` para outra
    coisa. Este teste bate na rota de verdade via HTTP, não chama
    ``template_extras`` diretamente."""
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    monkeypatch.delenv("REVY_LOJA_ENTITLEMENTS_ENABLED", raising=False)  # default off

    login(client)  # dono@loja.test / loja-teste (ver conftest.login)
    sincronizar_sinais(db, "loja-teste", [_cand()])

    capturado = _capturar_contexto(monkeypatch)

    r = client.get("/app/loja/vendas")

    assert r.status_code == 200
    assert capturado["context"]["copiloto_nao_vistos"] == 1


def test_badge_sobrevive_a_falha_de_contagem_em_tela_nao_copiloto(
    client, monkeypatch, db, caplog
):
    """Mesmo achado, mas garantindo que a degradação (Important I2 da F1)
    continua valendo quando a sessão é auto-provisionada: se a contagem
    falhar, a tela de Vendas não pode cair — vira ``None`` + warning."""
    import logging

    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    monkeypatch.delenv("REVY_LOJA_ENTITLEMENTS_ENABLED", raising=False)

    login(client)

    def _explode(db, loja_slug, usuario_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(notificacoes, "contar_nao_vistos", _explode)
    capturado = _capturar_contexto(monkeypatch)

    with caplog.at_level(logging.WARNING):
        r = client.get("/app/loja/vendas")

    assert r.status_code == 200
    assert capturado["context"]["copiloto_nao_vistos"] is None
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


# --- Important #2 (revisão): admin_plataforma sem membership de loja -------


def test_admin_plataforma_ve_a_contagem_com_entitlements_off(db, monkeypatch):
    """``admin_plataforma`` está em PAPEIS_GESTAO_COPILOTO mas fora de
    ROLES_OPERACIONAIS (identity.py) — não tem membership de loja, então
    ``resolve_store_and_entitlements`` sempre levanta ``SemAcessoLoja`` pra
    esse papel. A seção Copiloto (loja_copiloto.py) não depende de
    membership quando entitlements está OFF (bypass total); o sino precisa
    concordar."""
    _ligar_shell_e_entitlements(monkeypatch)
    monkeypatch.delenv("REVY_LOJA_ENTITLEMENTS_ENABLED", raising=False)  # off
    criar_usuario(papel="admin_plataforma", email="admin@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db)
    sincronizar_sinais(db, "loja-teste", [_cand()])
    usuario = _usuario(db, "admin@loja.test")

    extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] == 1


def test_admin_plataforma_recebe_none_com_entitlements_on(db, monkeypatch):
    """Contraprova: com entitlements ON, a rota TAMBÉM recebe SemAcessoLoja
    dentro de check_module_access() (LojaPermissionError) e devolve 403 —
    então o sino tem que continuar None aqui, sem usar o atalho de
    usuario.loja_slug."""
    _ligar_shell_e_entitlements(monkeypatch)
    criar_usuario(papel="admin_plataforma", email="admin2@loja.test", loja_slug="loja-teste")
    _seedar_modulo_copiloto(db)
    usuario = _usuario(db, "admin2@loja.test")

    extras = template_extras(_FakeRequest(), usuario, db)

    assert extras["copiloto_nao_vistos"] is None


# --- Paridade sino x seção: produto cartesiano das 5 variáveis -------------


def _preparar_combo(db, monkeypatch, *, shell_on, flag_on, modulo_on, papel, entitlements_on):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1" if shell_on else "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1" if flag_on else "0")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "1" if entitlements_on else "0")
    email = f"{papel}@paridade.test"
    criar_usuario(papel=papel, email=email, loja_slug="loja-teste")
    _seedar_modulo_copiloto(db, ligado=modulo_on)
    return email


@pytest.mark.parametrize(
    "shell_on,flag_on,modulo_on,papel,entitlements_on",
    list(
        itertools.product(
            [True, False],
            [True, False],
            [True, False],
            ["dono", "vendedor", "admin_plataforma"],
            [True, False],
        )
    ),
)
def test_paridade_sino_x_secao(
    client, db, monkeypatch, shell_on, flag_on, modulo_on, papel, entitlements_on
):
    """O sino (``template_extras``) e a seção Copiloto (``/app/loja/copiloto``,
    gate em ``loja_copiloto.py``) precisam concordar em toda combinação de
    shell x flag do Copiloto x módulo no entitlement x papel x entitlements
    ligado/desligado — 48 combinações, incluindo ``admin_plataforma``
    (achado da revisão: só ele expõe a divergência do bypass de
    entitlements). Isso transforma a paridade em propriedade verificada por
    teste, não em coincidência sustentada só por comentário cruzado."""
    email = _preparar_combo(
        db,
        monkeypatch,
        shell_on=shell_on,
        flag_on=flag_on,
        modulo_on=modulo_on,
        papel=papel,
        entitlements_on=entitlements_on,
    )

    pagina = client.get("/login")
    client.post(
        "/login",
        data={
            "email": email,
            "senha": "senha-segura",
            "csrf": csrf_da_resposta(pagina),
        },
        follow_redirects=False,
    )
    resposta = client.get("/app/loja/copiloto", follow_redirects=False)
    secao_permite = resposta.status_code == 200

    usuario = _usuario(db, email)
    extras = template_extras(_FakeRequest(), usuario, db)
    sino_aparece = extras.get("copiloto_nao_vistos") is not None

    assert secao_permite == sino_aparece, (
        f"divergência: shell={shell_on} flag={flag_on} modulo={modulo_on} "
        f"papel={papel} entitlements={entitlements_on} -> "
        f"secao(status={resposta.status_code})={secao_permite} "
        f"sino({extras.get('copiloto_nao_vistos')!r})={sino_aparece}"
    )


# =============================================================================
# F4/Task 2 — o sino e o painel em .topbar-actions (renderização)
# =============================================================================

_TELA_SEM_GATE_DE_MODULO = "/app/loja/perfil"


def _badge_texto(html: str) -> str | None:
    m = re.search(r'<span class="copiloto-notif-badge"[^>]*>([^<]*)</span>', html)
    return m.group(1) if m else None


def test_sino_presente_para_gestor_com_entitlement_e_mostra_contagem(
    client, db, monkeypatch
):
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    sincronizar_sinais(db, "loja-teste", [_cand("v1"), _cand("v2")])
    login(client, papel="dono", email="dono-sino@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert resposta.status_code == 200
    assert 'id="copiloto-notif-sino"' in resposta.text
    assert _badge_texto(resposta.text) == "2"
    assert "2 notificações não vistas" in resposta.text


def test_sino_ausente_para_vendedor(client, db, monkeypatch):
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    sincronizar_sinais(db, "loja-teste", [_cand("v1")])
    login(client, papel="vendedor", email="vendedor-sino@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert resposta.status_code == 200
    assert 'id="copiloto-notif-sino"' not in resposta.text


def test_sino_ausente_para_loja_sem_modulo(client, db, monkeypatch):
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db, ligado=False)  # loja ativa, módulo Copiloto off
    login(client, papel="dono", email="dono-semmodulo@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert resposta.status_code == 200
    assert 'id="copiloto-notif-sino"' not in resposta.text


def test_badge_numerico_ausente_quando_contagem_e_zero_mas_sino_permanece(
    client, db, monkeypatch
):
    """``None`` e ``0`` são coisas diferentes: sem sinal algum para este
    usuário, o sino continua aparecendo (sino!=None) — só o número some."""
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    login(client, papel="dono", email="dono-zero@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert resposta.status_code == 200
    assert 'id="copiloto-notif-sino"' in resposta.text
    assert _badge_texto(resposta.text) is None
    assert "0 notificações não vistas" in resposta.text


def test_frase_sobre_alcance_dos_alertas_esta_no_painel(client, db, monkeypatch):
    """A frase precisa descrever o comportamento REAL (Task 0 desta fase):
    visto é por pessoa; dispensar é da loja inteira."""
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    login(client, papel="dono", email="dono-frase@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert "class=\"copiloto-notif-escopo\"" in resposta.text
    assert "Estes alertas são da loja" in resposta.text
    assert "Marcar como visto vale só para você" in resposta.text
    assert "dispensar tira o alerta para todo mundo" in resposta.text


def test_estado_vazio_honesto_disponivel_para_o_painel_usar(client, db, monkeypatch):
    """O painel é populado por fetch (rota de listagem é a Task 3, ainda não
    existe) — por isso o texto honesto de "nada a tratar" vive num
    ``<template>`` que o JS usa quando a listagem real vier vazia, em vez de
    ser fabricado ad-hoc pelo JS ou assumido estaticamente pela contagem
    pessoal (que é um número DIFERENTE do conteúdo do painel: contagem 0 não
    prova painel vazio — só que ESTE usuário não tem sinal novo)."""
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    login(client, papel="dono", email="dono-vazio@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert (
        '<template data-copiloto-texto-vazio>Não há nada para tratar agora.'
        in resposta.text
    )


def test_painel_acessivel_fechado_por_padrao_com_aria_live(client, db, monkeypatch):
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    login(client, papel="dono", email="dono-acess@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    painel = re.search(r'<div class="copiloto-notif-painel"[\s\S]*?>', resposta.text)
    assert painel is not None
    assert 'aria-live="polite"' in painel.group(0)
    assert re.search(r"\bhidden\b", painel.group(0))
    assert 'aria-expanded="false"' in resposta.text


def test_lista_de_notificacoes_e_ul_para_leitor_de_tela(client, db, monkeypatch):
    """Important da revisão: ``montarItem()`` cria um ``<li>`` e o anexa em
    ``data-copiloto-lista``. Sem um ``<ul>``/``<ol>`` ancestral, esse ``<li>``
    é um ``listitem`` órfão — leitor de tela não anuncia "lista de N itens".
    Trava a estrutura no HTML servido, não só no JS (a rota que popula a
    lista é a Task 3; até lá isto é a única prova possível)."""
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    login(client, papel="dono", email="dono-estrutura@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    # O container que o JS usa para anexar <li> (data-copiloto-lista) tem que
    # ser um elemento de lista de verdade — nunca <div>/<span>.
    assert re.search(
        r'<ul class="copiloto-notif-lista" data-copiloto-lista\b', resposta.text
    )
    assert '<div class="copiloto-notif-lista"' not in resposta.text
    # E o status (carregando/vazio/erro) não pode ser filho do <ul>: um <p>
    # dentro de <ul> também é inválido/mal-anunciado. Tem que ser irmão.
    ul_aberto = resposta.text.index('<ul class="copiloto-notif-lista"')
    ul_fechado = resposta.text.index("</ul>", ul_aberto)
    assert "copiloto-notif-status" not in resposta.text[ul_aberto:ul_fechado]


def test_sem_innerhtml_no_script_do_sino(client, db, monkeypatch):
    """Regra dura do projeto (defeito de XSS já ocorreu numa fase anterior):
    qualquer JS que monte conteúdo a partir de dado do alerta usa
    createElement/textContent, nunca innerHTML/insertAdjacentHTML. Checa o uso
    real (``.innerHTML`` / ``insertAdjacentHTML(``), não o comentário do
    próprio script que documenta a regra em prosa."""
    _ligar_shell_e_entitlements(monkeypatch)
    _seedar_modulo_copiloto(db)
    login(client, papel="dono", email="dono-xss@loja.test")

    resposta = client.get(_TELA_SEM_GATE_DE_MODULO)

    assert ".innerHTML" not in resposta.text
    assert "insertAdjacentHTML(" not in resposta.text


def test_css_do_sino_nao_usa_cor_literal():
    """Only tokens: --danger/--warn/--ok e var(...) — nunca hex/rgba direto no
    bloco novo. Complementa (não substitui) o grep manual pedido no brief."""
    caminho = (
        Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "app.css"
    )
    texto = caminho.read_text(encoding="utf-8")
    inicio = texto.index("=== Copiloto: sino de notificacoes (F4/Task 2) ===")
    fim = texto.index("=== fim: sino de notificacoes (F4/Task 2) ===", inicio)
    bloco = texto[inicio:fim]
    achados = re.findall(r"#[0-9a-fA-F]{3,6}|rgba?\(", bloco)
    assert achados == []
