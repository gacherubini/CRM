"""Tela de cadastro da fila de rodízio (spec §5.8).

A pessoa vem da **equipe da loja**, não de nome digitado: é assim que o
`Usuario.id` entra no cadastro e o sino 1:1 ganha destinatário real. Sem
vínculo, o vendedor recebe a oferta pelo WhatsApp e o sino não toca.
"""
from conftest import criar_usuario, csrf_da_resposta, login

from app.db import SessionLocal
from app.models import Usuario

TELA = "/app/loja/whatsapp/fila"


def _membro(papel="vendedor", email="ana@loja.test", loja_slug="loja-teste"):
    """Cria e devolve o usuário — `criar_usuario` do conftest devolve None."""
    criar_usuario(papel=papel, email=email, loja_slug=loja_slug)
    with SessionLocal() as db:
        return db.query(Usuario).filter(Usuario.email == email).one()


def _ligar(monkeypatch, whatsapp="1", shell="1"):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", shell)
    monkeypatch.setenv("REVY_LOJA_WHATSAPP_ENABLED", whatsapp)
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")


def _csrf(client):
    return csrf_da_resposta(client.get(TELA))


def test_gestao_ve_a_tela(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    resposta = client.get(TELA)
    assert resposta.status_code == 200
    assert "Fila de atendimento" in resposta.text


def test_vendedor_nao_acessa(client, chatbot_fake, monkeypatch):
    """Cadastrar a fila é do lojista, não de quem está nela."""
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="vend@loja.test")
    resposta = client.get(TELA, follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/app"


def test_flag_off_esconde_a_tela(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch, whatsapp="0")
    login(client)
    resposta = client.get(TELA, follow_redirects=False)
    assert resposta.status_code == 303


def test_lista_avisa_quem_nao_tem_vinculo(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    chatbot_fake.fila_vendedores = [
        {"id": "f0", "nome": "Ana", "telefone": "5511999990000", "ordem": 0,
         "ativo": True, "usuario_id": "u-ana"},
        {"id": "f1", "nome": "Bruno", "telefone": "5511988887777", "ordem": 1,
         "ativo": True, "usuario_id": None},
    ]
    corpo = client.get(TELA).text
    assert "Ana" in corpo and "Bruno" in corpo
    # Sem vínculo o sino não toca para ele — a tela precisa dizer isso.
    assert "sem acesso à Loja" in corpo


def test_cadastrar_manda_o_usuario_escolhido(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    membro = _membro(email="ana@loja.test")
    client.post(
        TELA,
        data={"csrf": _csrf(client), "usuario_id": membro.id,
              "telefone": "(11) 99999-0000", "ordem": "0"},
        follow_redirects=False,
    )
    assert chatbot_fake.fila_criados[0]["usuario_id"] == membro.id
    assert chatbot_fake.fila_criados[0]["nome"] == membro.nome


def test_pessoa_de_outra_loja_nao_entra_na_fila(client, chatbot_fake, monkeypatch):
    """O id vem do form: sem checar a equipe, daria para injetar qualquer um."""
    _ligar(monkeypatch)
    login(client)
    de_fora = _membro(email="x@outra.test", loja_slug="outra-loja")
    client.post(
        TELA,
        data={"csrf": _csrf(client), "usuario_id": de_fora.id,
              "telefone": "11999990000", "ordem": "0"},
        follow_redirects=False,
    )
    assert chatbot_fake.fila_criados == []


def test_sem_telefone_nao_chama_o_chatbot(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    membro = _membro(email="ana2@loja.test")
    client.post(
        TELA,
        data={"csrf": _csrf(client), "usuario_id": membro.id, "telefone": "", "ordem": "0"},
        follow_redirects=False,
    )
    assert chatbot_fake.fila_criados == []


def test_csrf_invalido_nao_cadastra(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    membro = _membro(email="ana3@loja.test")
    client.post(
        TELA,
        data={"csrf": "errado", "usuario_id": membro.id, "telefone": "11999990000",
              "ordem": "0"},
        follow_redirects=False,
    )
    assert chatbot_fake.fila_criados == []


def test_remover_tira_da_fila(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    chatbot_fake.fila_vendedores = [
        {"id": "f0", "nome": "Ana", "telefone": "5511999990000", "ordem": 0,
         "ativo": True, "usuario_id": "u-ana"},
    ]
    client.post(
        f"{TELA}/f0/remover", data={"csrf": _csrf(client)}, follow_redirects=False
    )
    assert chatbot_fake.fila_removidos == ["f0"]


def test_chatbot_fora_do_ar_nao_derruba_a_tela(client, chatbot_fake, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    chatbot_fake.fila_indisponivel = True
    resposta = client.get(TELA)
    assert resposta.status_code == 200
    assert "Fila de atendimento" in resposta.text
