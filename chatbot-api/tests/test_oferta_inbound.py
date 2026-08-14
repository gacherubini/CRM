import pytest

from app.models_db import FilaVendedor
from app.oferta_inbound import extrair_oferta_id, processar_clique
from app.rodizio import abrir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)


class _OutboundFake:
    def __init__(self):
        self.textos = []

    def send_text(self, *, instance, number, text):
        self.textos.append((number, text))
        return {"messages": [{"id": "wamid.X"}]}


def test_extrai_de_template():
    assert extrair_oferta_id({"button": {"payload": "pego:of-1"}}) == "of-1"


def test_extrai_de_interativa():
    payload = {"interactive": {"button_reply": {"id": "pego:of-2", "title": "Peguei"}}}
    assert extrair_oferta_id(payload) == "of-2"


def test_payload_desconhecido_devolve_none():
    assert extrair_oferta_id({"text": {"body": "peguei"}}) is None
    assert extrair_oferta_id({"button": {"payload": "outra_coisa"}}) is None


def _fila(db, loja_id, quantos=2):
    ids = []
    for i in range(quantos):
        vid = f"{loja_id[:8]}-f{i}"
        db.add(FilaVendedor(
            id=vid, loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
        ids.append(vid)
    db.commit()
    return ids


def test_clique_trava_e_manda_o_pacote(db, loja_a):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    assert processar_clique(
        db, loja_a["loja_id"], "5511999990000", oferta.id, outbound=fake
    ) == "travou"

    numero, texto = fake.textos[0]
    assert numero == "5511999990000"
    assert "wa.me/5511988887777" in texto


def test_clique_perdedor_recebe_ja_foi_pego_sem_contato(db, loja_a):
    _fila(db, loja_a["loja_id"])
    primeira = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    segunda = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    fake = _OutboundFake()
    processar_clique(db, loja_a["loja_id"], "5511999990000", primeira.id, outbound=fake)
    resultado = processar_clique(
        db, loja_a["loja_id"], "5511999990001", segunda.id, outbound=fake
    )

    assert resultado == "ja_foi_pego"
    _, texto_perdedor = fake.textos[-1]
    assert "wa.me" not in texto_perdedor
    assert "5511988887777" not in texto_perdedor
