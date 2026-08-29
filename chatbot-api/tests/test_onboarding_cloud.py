"""A cadeia do embedded signup, sem HTTP (spec §7).

O cliente da Meta e um duplo em memoria: aqui se testa ORDEM, RETOMADA e TETO,
nao formato de corpo — isso e do test_meta_onboarding.py.
"""
import pytest

from app import onboarding_cloud, segredo_canal
from app.meta_onboarding import OnboardingErro
from app.models_db import WhatsAppCanal

CHAVE = "LvALLRsc3ZykD4ZrrFrm25elgLGhYThKQ7Z2ili9KYw="


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)


class _MetaFalsa:
    """Registra a ordem das chamadas. `falhar_em` para no elo pedido."""

    def __init__(self, falhar_em: int | None = None):
        self.chamadas: list[str] = []
        self.falhar_em = falhar_em
        self.pins: list[str] = []

    def _talvez_falhar(self, elo: int):
        if self.falhar_em == elo:
            raise OnboardingErro(f"falhou no elo {elo}", elo=elo)

    def trocar_code_por_token(self, code):
        self.chamadas.append("elo1")
        self._talvez_falhar(1)
        return "EAAG-token-da-loja"

    def inscrever_app(self, *, waba_id, token):
        self.chamadas.append("elo2")
        self._talvez_falhar(2)

    def registrar_numero(self, *, phone_number_id, pin, token):
        self.chamadas.append("elo3")
        self.pins.append(pin)
        self._talvez_falhar(3)

    def criar_template(self, *, waba_id, token, nome="chama_vendedor"):
        self.chamadas.append("elo4")
        self._talvez_falhar(4)


# Cada teste usa um `phone_number_id` PROPRIO. O conftest cria UM banco em
# memoria para a sessao inteira e nunca limpa: numero repetido faz o teste 2 em
# diante bater na guarda "ja e de outra loja" do canal deixado pelo teste 1.
def _conectar(db, loja_id, meta, **troca):
    dados = dict(
        code="code-do-popup",
        waba_id="waba-1",
        phone_number_id="1227059273831590",
        business_id="biz-1",
    )
    dados.update(troca)
    return onboarding_cloud.conectar(db, loja_id, meta=meta, **dados)


def test_cadeia_completa_deixa_o_canal_pendente(db, loja_a):
    meta = _MetaFalsa()

    canal = _conectar(db, loja_a["loja_id"], meta)

    assert meta.chamadas == ["elo1", "elo2", "elo3", "elo4"]
    # `evolution_instance` guarda o phone_number_id no Modo 2 (spec §16.3).
    assert canal.evolution_instance == "1227059273831590"
    assert canal.waba_id == "waba-1"
    assert canal.business_id == "biz-1"
    assert canal.onboarding_elo == 5
    assert canal.onboarding_erro is None
    # Pendente, nao ativo: quem ativa e a projecao do Control (Card 2, spec §9).
    assert canal.estado == "cloud_pendente"


def test_o_token_fica_cifrado_e_abre():
    """Sanidade do contrato com o Card 2: nao adianta cifrar e nao conseguir ler."""
    assert segredo_canal.decifrar(segredo_canal.cifrar("EAAG-x")) == "EAAG-x"


def test_token_nao_fica_em_claro_no_banco(db, loja_a):
    canal = _conectar(db, loja_a["loja_id"], _MetaFalsa(),
                      phone_number_id="1227059273831591")

    assert canal.token_cifrado
    assert "EAAG-token-da-loja" not in canal.token_cifrado
    assert segredo_canal.decifrar(canal.token_cifrado) == "EAAG-token-da-loja"


def test_falha_no_elo_2_guarda_onde_parou_e_o_token(db, loja_a):
    """O ponto da divergencia do §7: o elo 1 nao e retomavel, entao o canal tem
    de existir com o token ANTES do elo 2."""
    canal = None
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], _MetaFalsa(falhar_em=2),
                  phone_number_id="1227059273831592")

    canal = db.query(WhatsAppCanal).filter_by(loja_id=loja_a["loja_id"],
                                              waba_id="waba-1").one()
    assert canal.onboarding_elo == 1
    assert canal.onboarding_erro
    assert canal.token_cifrado, "sem isto a retomada exigiria o popup de novo"
    assert canal.estado == "cloud_pendente"


def test_retomada_nao_repete_o_elo_1(db, loja_a):
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], _MetaFalsa(falhar_em=2),
                  phone_number_id="1227059273831593")

    segunda = _MetaFalsa()
    canal = _conectar(db, loja_a["loja_id"], segunda, code="code-ja-morto",
                      phone_number_id="1227059273831593")

    assert segunda.chamadas == ["elo2", "elo3", "elo4"]
    assert canal.onboarding_elo == 5
    assert canal.onboarding_erro is None


def test_retomada_reusa_o_mesmo_pin(db, loja_a):
    """PIN novo a cada tentativa e PIN perdido, e PIN perdido trava o
    re-registro do numero para sempre."""
    primeira = _MetaFalsa(falhar_em=3)
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], primeira,
                  phone_number_id="1227059273831594")

    segunda = _MetaFalsa()
    _conectar(db, loja_a["loja_id"], segunda, code="code-ja-morto",
              phone_number_id="1227059273831594")

    assert primeira.pins == segunda.pins
    assert len(primeira.pins[0]) == 6 and primeira.pins[0].isdigit()


def test_o_teto_do_elo_3_para_antes_de_chamar_a_meta(db, loja_a):
    """133016 trava o numero por 72 h. O teto e do NOSSO lado, bem abaixo de 10."""
    for _ in range(onboarding_cloud.TETO_REGISTRO):
        with pytest.raises(OnboardingErro):
            _conectar(db, loja_a["loja_id"], _MetaFalsa(falhar_em=3),
                      phone_number_id="1227059273831595")

    ultima = _MetaFalsa()
    with pytest.raises(OnboardingErro) as erro:
        _conectar(db, loja_a["loja_id"], ultima, code="code-ja-morto",
                  phone_number_id="1227059273831595")

    assert "elo3" not in ultima.chamadas, "estourou o teto e chamou a Meta assim mesmo"
    assert erro.value.elo == 3

    canal = db.query(WhatsAppCanal).filter_by(loja_id=loja_a["loja_id"],
                                              waba_id="waba-1").one()
    assert canal.registro_tentativas == onboarding_cloud.TETO_REGISTRO


def test_numero_de_outra_loja_nao_e_sequestrado(db, loja_a, loja_b):
    """`evolution_instance` e UNIQUE de proposito: um numero, uma loja."""
    _conectar(db, loja_a["loja_id"], _MetaFalsa(), phone_number_id="1227059273831596")

    with pytest.raises(OnboardingErro):
        _conectar(db, loja_b["loja_id"], _MetaFalsa(), phone_number_id="1227059273831596")


def test_retomada_depois_do_elo_2_nao_reinscreve_o_app(db, loja_a):
    """A guarda `< 2` do elo 2, que os outros oito testes nao alcancam.

    Todos eles param NO elo 2 ou antes, entao o canal nunca chega a retomada com
    `onboarding_elo >= 2` e a guarda ficava sem rede — a mesma armadilha do
    learning `2026-08-29-o-conftest-do-chatbot-nao-semeia-todo-aggregate.md`.

    Reinscrever nao quebraria nada (o elo 2 e idempotente), mas seria uma
    chamada a Meta por retomada, de graca.
    """
    primeira = _MetaFalsa(falhar_em=3)
    with pytest.raises(OnboardingErro):
        _conectar(db, loja_a["loja_id"], primeira,
                  phone_number_id="1227059273831597")
    assert primeira.chamadas == ["elo1", "elo2", "elo3"]

    segunda = _MetaFalsa()
    _conectar(db, loja_a["loja_id"], segunda, code="code-ja-morto",
              phone_number_id="1227059273831597")

    assert segunda.chamadas == ["elo3", "elo4"], "reinscreveu o app sem precisar"
