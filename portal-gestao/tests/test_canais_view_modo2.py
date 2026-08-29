"""A tela de canais tem de falar do canal Cloud sem mentir.

Hoje ela mostra o nome tecnico cru como rotulo e oferece o botao Conectar do
Modo 1 — que pede QR na Evolution — para um numero que e da Cloud API.
"""
from app.loja.whatsapp_canais import montar_canais_view


def _bruto(estado, **extra):
    base = {
        "id": "c1",
        "e164_or_label": "linha-cloud",
        "evolution_instance": "1227059273831581",
        "estado": estado,
        "ativo": True,
        "principal_estoque": False,
    }
    base.update(extra)
    return base


def test_canal_cloud_nao_mostra_o_nome_tecnico():
    view = montar_canais_view([_bruto("cloud_pendente", waba_id="waba-1")])

    canal = view.canais[0]
    assert canal.rotulo != "cloud_pendente"
    assert "cloud_" not in canal.rotulo


def test_canal_cloud_nao_oferece_o_botao_do_modo_1():
    """O botao chama conectar_canal_whatsapp, que pede QR na Evolution."""
    view = montar_canais_view([_bruto("cloud_pendente", waba_id="waba-1")])

    canal = view.canais[0]
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is False
    assert canal.cloud is True


def test_canal_cloud_ativo_tambem_nao_oferece():
    view = montar_canais_view([_bruto("cloud_ativo", waba_id="waba-1")])

    assert view.canais[0].pode_desconectar is False


def test_os_quatro_estados_cloud_tem_rotulo_proprio():
    """Restrito e banido vem da Meta e nao se conserta clicando: o rotulo tem
    de dizer isso, senao o lojista fica tentando."""
    estados = ["cloud_pendente", "cloud_ativo", "cloud_restrito", "cloud_banido"]
    view = montar_canais_view(
        [_bruto(e, id=f"c{i}", evolution_instance=f"12270592738315{80 + i}",
                waba_id="waba-1")
         for i, e in enumerate(estados)]
    )

    rotulos = [c.rotulo for c in view.canais]
    assert len(set(rotulos)) == 4, f"estados diferentes com o mesmo rotulo: {rotulos}"
    for rotulo in rotulos:
        assert "cloud_" not in rotulo


def test_canal_do_modo_1_nao_muda():
    """Regressao: a loja piloto opera no Modo 1 e nada aqui pode mexer nela."""
    view = montar_canais_view([_bruto("conectado")])

    canal = view.canais[0]
    assert canal.rotulo == "Conectado"
    assert canal.pode_conectar is False
    assert canal.pode_desconectar is True
    assert canal.cloud is False


def test_dois_canais_cloud_continuam_cloud_depois_do_principal_estoque():
    """A loja com mais de um canal e o caso que ninguem testa a mao.

    Quando nenhum canal vem marcado como principal, ``montar_canais_view``
    reconstroi cada ``CanalView`` campo a campo para eleger o primeiro. Se
    ``cloud`` nao for repassado nessa reconstrucao, o canal volta ``cloud=False``
    e a tela oferece de novo o botao de QR — sem nenhum outro teste ficar
    vermelho.
    """
    view = montar_canais_view([
        _bruto("cloud_ativo", id="c1", evolution_instance="111", waba_id="waba-1"),
        _bruto("cloud_pendente", id="c2", evolution_instance="222", waba_id="waba-2"),
    ])

    assert [c.id for c in view.canais] == ["c1", "c2"]
    assert [c.principal_estoque for c in view.canais] == [True, False]
    for canal in view.canais:
        assert canal.cloud is True, f"canal {canal.id} perdeu o cloud na reconstrucao"
        assert canal.pode_conectar is False
        assert canal.pode_desconectar is False
