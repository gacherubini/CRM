"""A reoferta do rodízio precisa CHEGAR ao vendedor (spec §5.3 e §5.7).

Existe porque `test_rodizio_job.py` conferia só a linha do banco: passados os
10 min o `RodizioWorker` marcava a oferta como expirada, abria a próxima para o
vendedor seguinte e **parava aí** — `enviar_oferta` nunca era chamado nesse
caminho, e o `_ciclo_rodizio` do `modo2_workers` rodava sem outbound nenhum.
Em produção o celular do vendedor 2 nunca tocava e o lead morria num registro,
com a suíte inteira verde.

O segundo buraco do mesmo worker: quando a volta fecha sem ninguém pegar, o
cliente — que ouviu "Já estou chamando um vendedor para falar com você" — ficava
sem nenhum aviso.

Nenhum número real aqui: telefones sintéticos e rótulos `pnid-…`.
"""
import uuid

import pytest

from app import modo2_workers
from app.cloud_canal import phone_number_id_da_loja
from app.models_db import (
    FilaVendedor,
    LojaOperacionalProjecao,
    OfertaLead,
    WhatsAppCanal,
)
from app.rodizio import abrir_oferta
from app.rodizio_job import RodizioWorker
from app.whatsapp_outbound import (
    CloudWhatsAppOutbound,
    WhatsAppOutboundError,
    outbound_para_loja,
)
from app.whatsapp_provider import ESTADO_CLOUD_ATIVO

CLIENTE_A = "5511988887777"
CLIENTE_B = "5511966665555"


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _OutboundFake:
    """Mesmo dublê de `test_cloud_canal_por_loja.py`, com falha opcional.

    ``falhar_na`` é o índice (1-based) da chamada de oferta que levanta: serve
    para provar que uma falha de envio não derruba o ciclo inteiro.
    """

    def __init__(self, *, falhar_na: int | None = None):
        self.textos: list[dict] = []
        self.templates: list[dict] = []
        self.interativas: list[dict] = []
        self.falhar_na = falhar_na

    @property
    def ofertas(self) -> list[dict]:
        return self.templates + self.interativas

    def _talvez_falhar(self) -> None:
        if self.falhar_na is not None and len(self.ofertas) == self.falhar_na:
            raise WhatsAppOutboundError("provedor fora do ar (fake)")

    def send_text(self, **kwargs):
        self.textos.append(kwargs)
        return {"messages": [{"id": "wamid.X"}]}

    def send_template_button(self, **kwargs):
        self.templates.append(kwargs)
        self._talvez_falhar()
        return {"messages": [{"id": "wamid.T"}]}

    def send_interactive_button(self, **kwargs):
        self.interativas.append(kwargs)
        self._talvez_falhar()
        return {"messages": [{"id": "wamid.I"}]}


def _modo2(db, loja_id):
    db.add(
        LojaOperacionalProjecao(
            loja_id=loja_id,
            aggregate="whatsapp_modo",
            version=1,
            state="2",
            event_id=f"e-modo-{loja_id[:8]}",
        )
    )
    db.commit()


def _canal_cloud(db, loja_id, *, rotulo="pnid"):
    """Canal Cloud da loja. ``evolution_instance`` é UNIQUE: sufixo por teste."""
    sufixo = uuid.uuid4().hex[:8]
    phone_number_id = f"{rotulo}-{sufixo}"
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            e164_or_label="central",
            evolution_instance=phone_number_id,
            ativo=True,
            estado=ESTADO_CLOUD_ATIVO,
            waba_id=f"waba-{sufixo}",
            template_oferta="chama_vendedor",
        )
    )
    db.commit()
    return phone_number_id


def _fila(db, loja_id, quantos):
    ids = []
    for i in range(quantos):
        vid = f"{loja_id[:8]}-f{i}"
        db.add(
            FilaVendedor(
                id=vid,
                loja_id=loja_id,
                nome=f"V{i}",
                telefone=f"551199999000{i}",
                ordem=i,
                ativo=True,
            )
        )
        ids.append(vid)
    db.commit()
    return ids


def _vencer(db, oferta):
    from datetime import datetime, timedelta, timezone

    oferta.prazo_em = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()


def _abertas(db, loja_id):
    return (
        db.query(OfertaLead)
        .filter(OfertaLead.estado == "aberta", OfertaLead.loja_id == loja_id)
        .all()
    )


def _loja_pronta(db, loja, cliente, *, vendedores=2):
    """Loja Modo 2 com canal, fila e uma oferta já vencida."""
    loja_id = loja["loja_id"]
    _modo2(db, loja_id)
    pnid = _canal_cloud(db, loja_id, rotulo=f"pnid-{loja_id[:4]}")
    _fila(db, loja_id, vendedores)
    oferta = abrir_oferta(db, loja_id, cliente)
    _vencer(db, oferta)
    return loja_id, pnid, oferta


# --------------------------------------------------------------------------
# 1. a reoferta chega ao próximo vendedor
# --------------------------------------------------------------------------


def test_reoferta_e_enviada_ao_proximo_vendedor(db, loja_a):
    """O furo que foi para produção: passava no banco e não mandava nada."""
    loja_id, pnid, oferta = _loja_pronta(db, loja_a, CLIENTE_A)
    velha_id, primeiro = oferta.id, oferta.vendedor_id

    fake = _OutboundFake()
    resultado = RodizioWorker().run_once(db, outbound=fake)

    assert resultado["reofertadas"] == 1
    (nova,) = _abertas(db, loja_id)
    assert nova.vendedor_id != primeiro

    assert len(fake.ofertas) == 1, "o vendedor da vez não recebeu nada"
    envio = fake.ofertas[0]
    assert envio["oferta_id"] == nova.id
    assert envio["oferta_id"] != velha_id
    assert envio["instance"] == pnid
    assert envio["number"] == db.get(FilaVendedor, nova.vendedor_id).telefone


def test_reoferta_nao_leva_o_telefone_do_cliente(db, loja_a):
    """Spec §5.7: o contato do cliente só vai DEPOIS do clique."""
    _loja_pronta(db, loja_a, CLIENTE_A)

    fake = _OutboundFake()
    RodizioWorker().run_once(db, outbound=fake)

    enviado = str(fake.ofertas)
    assert CLIENTE_A not in enviado
    assert "wa.me" not in enviado


# --------------------------------------------------------------------------
# 2. a volta que morre não deixa o cliente no vácuo
# --------------------------------------------------------------------------


def test_volta_esgotada_avisa_o_cliente(db, loja_a):
    """Fila de 1: a volta fecha em 10 min e ninguém falava com o cliente."""
    loja_id, pnid, _ = _loja_pronta(db, loja_a, CLIENTE_A, vendedores=1)

    fake = _OutboundFake()
    resultado = RodizioWorker().run_once(db, outbound=fake)

    assert resultado["esgotadas"] == 1
    assert fake.ofertas == []
    assert len(fake.textos) == 1, "a volta esgotou e o cliente não foi avisado"
    aviso = fake.textos[0]
    assert aviso["instance"] == pnid
    assert aviso["number"] == CLIENTE_A
    assert aviso["text"].strip()


def test_aviso_da_volta_esgotada_sai_uma_vez_so(db, loja_a):
    """O worker roda a cada 300 s: o cliente não pode receber isto em laço."""
    _loja_pronta(db, loja_a, CLIENTE_A, vendedores=1)

    fake = _OutboundFake()
    RodizioWorker().run_once(db, outbound=fake)
    RodizioWorker().run_once(db, outbound=fake)

    assert len(fake.textos) == 1


# --------------------------------------------------------------------------
# 3. idempotência e isolamento de falha
# --------------------------------------------------------------------------


def test_segundo_ciclo_nao_reenvia_a_mesma_oferta(db, loja_a):
    """A oferta nova tem prazo próprio: o ciclo seguinte não a repete."""
    _loja_pronta(db, loja_a, CLIENTE_A)

    fake = _OutboundFake()
    RodizioWorker().run_once(db, outbound=fake)
    RodizioWorker().run_once(db, outbound=fake)

    assert len(fake.ofertas) == 1


def test_falha_de_envio_nao_impede_as_outras_ofertas(db, loja_a, loja_b):
    """Provedor fora do ar para UM vendedor não pode matar o ciclo."""
    loja_a_id, _, _ = _loja_pronta(db, loja_a, CLIENTE_A)
    loja_b_id, _, _ = _loja_pronta(db, loja_b, CLIENTE_B)

    fake = _OutboundFake(falhar_na=1)
    resultado = RodizioWorker().run_once(db, outbound=fake)

    assert resultado["expiradas"] == 2
    assert resultado["reofertadas"] == 2
    assert len(fake.ofertas) == 2, "a falha da 1ª oferta engoliu a 2ª"
    assert len(_abertas(db, loja_a_id)) == 1
    assert len(_abertas(db, loja_b_id)) == 1


# --------------------------------------------------------------------------
# 4. a fiação: o ciclo do worker tem que passar um outbound de verdade
# --------------------------------------------------------------------------


def test_ciclo_do_rodizio_passa_um_outbound(monkeypatch, db):
    """`_ciclo_rodizio` chamava `run_once(db)` — sem outbound, sem envio."""
    monkeypatch.setattr("app.modo2_workers.config.MODO2_ENABLED", True)
    for var in (
        "CHATBOT_MODO2_RODIZIO_INTERVAL_SECONDS",
        "CHATBOT_MODO2_FOLLOWUP_INTERVAL_SECONDS",
        "CHATBOT_MODO2_RETRY_INTERVAL_SECONDS",
    ):
        monkeypatch.setenv(var, "0")  # intervalo 0 = nenhuma thread nasce

    capturado: dict = {}

    def _espiao(self, sessao, **kwargs):
        capturado.update(kwargs)
        return {}

    monkeypatch.setattr("app.rodizio_job.RodizioWorker.run_once", _espiao)

    modo2_workers.stop_workers()
    workers = modo2_workers.start_workers(lambda: db, enabled=True)
    try:
        workers["rodizio"].alvo(db)
    finally:
        modo2_workers.stop_workers()

    outbound = capturado.get("outbound")
    assert outbound is not None, "o ciclo do rodízio roda sem outbound"
    for metodo in ("send_text", "send_interactive_button", "send_template_button"):
        assert callable(getattr(outbound, metodo, None)), f"falta {metodo}"


def test_adaptador_por_loja_delega_os_tres_envios(db):
    """`enviar_oferta` usa os dois botões; o adaptador só expunha `send_text`."""

    class _Recorder:
        def __init__(self):
            self.chamadas = []

        def send_text(self, **kwargs):
            self.chamadas.append(("text", kwargs))

        def send_template_button(self, **kwargs):
            self.chamadas.append(("template", kwargs))

        def send_interactive_button(self, **kwargs):
            self.chamadas.append(("interativa", kwargs))

    recorder = _Recorder()
    adaptador = modo2_workers._OutboundPorLoja(db, lambda _db, _chave: recorder)

    adaptador.send_text(instance="pnid-x", number="5511900000000", text="oi")
    adaptador.send_template_button(
        instance="pnid-x",
        number="5511900000000",
        template="chama_vendedor",
        variaveis=["Ana"],
        oferta_id="of-1",
    )
    adaptador.send_interactive_button(
        instance="pnid-x", number="5511900000000", texto="oi", oferta_id="of-1"
    )

    assert [nome for nome, _ in recorder.chamadas] == [
        "text",
        "template",
        "interativa",
    ]
    assert recorder.chamadas[1][1]["oferta_id"] == "of-1"


def test_adaptador_resolve_a_loja_pelo_phone_number_id(db, loja_a):
    """O `instance` do envio é o phone_number_id, não a loja.

    Sem traduzir, o resolvedor pergunta "a loja <pnid> é Modo 2?", ouve não, e
    devolve o adapter do Modo 1 — que não tem `send_template_button`. A oferta
    morria num `AttributeError` mesmo com o worker consertado.
    """
    loja_id = loja_a["loja_id"]
    _modo2(db, loja_id)
    pnid = _canal_cloud(db, loja_id)
    assert phone_number_id_da_loja(db, loja_id) == pnid

    adaptador = modo2_workers._OutboundPorLoja(db, outbound_para_loja)

    assert isinstance(adaptador._para(pnid), CloudWhatsAppOutbound)


def test_ciclo_real_manda_a_reoferta_pela_cloud(monkeypatch, db, loja_a):
    """Ponta a ponta da fiação, sem dublê injetado no worker.

    Só a Cloud API é substituída: o ciclo, o resolvedor por loja e o adaptador
    são os de produção. É o teste que pega os dois furos de uma vez — o ciclo
    sem outbound e o adaptador caindo no transporte do Modo 1.
    """
    _, pnid, _ = _loja_pronta(db, loja_a, CLIENTE_A)
    monkeypatch.setattr("app.modo2_workers.config.MODO2_ENABLED", True)
    for var in (
        "CHATBOT_MODO2_RODIZIO_INTERVAL_SECONDS",
        "CHATBOT_MODO2_FOLLOWUP_INTERVAL_SECONDS",
        "CHATBOT_MODO2_RETRY_INTERVAL_SECONDS",
    ):
        monkeypatch.setenv(var, "0")

    enviados: list[tuple[str, dict]] = []

    class _CloudEspiao:
        def __init__(self, *args, **kwargs):
            pass

        def send_text(self, **kwargs):
            enviados.append(("text", kwargs))

        def send_template_button(self, **kwargs):
            enviados.append(("template", kwargs))

        def send_interactive_button(self, **kwargs):
            enviados.append(("interativa", kwargs))

    monkeypatch.setattr("app.whatsapp_outbound.CloudWhatsAppOutbound", _CloudEspiao)

    modo2_workers.stop_workers()
    workers = modo2_workers.start_workers(lambda: db, enabled=True)
    try:
        workers["rodizio"].alvo(db)
    finally:
        modo2_workers.stop_workers()

    assert [nome for nome, _ in enviados] == ["template"], (
        "a reoferta não saiu pela Cloud no caminho de produção"
    )
    assert enviados[0][1]["instance"] == pnid
