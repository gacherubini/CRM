"""Perfil: avatar preset (bichinhos) + foto própria + onde a foto aparece."""

from conftest import criar_usuario, csrf_da_resposta, login

from app.auth import hash_senha, verifica_senha
from app.db import SessionLocal
from app.models import Usuario

_PERFIL = "/app/loja/perfil"
_AVATAR = "/app/loja/perfil/avatar"
_FOTO = "/app/loja/perfil/foto"

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _csrf_perfil(client):
    return csrf_da_resposta(client.get(_PERFIL))


def _usuario_por_email(email):
    db = SessionLocal()
    try:
        return db.query(Usuario).filter(Usuario.email == email).one()
    finally:
        db.close()


def _foto_url(usuario_id):
    return f"/app/loja/perfil/foto/{usuario_id}"


def test_avatar_preset_persiste_e_aparece(client):
    login(client)
    dono = _usuario_por_email("dono@loja.test")

    resposta = client.post(
        _AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "gato"}
    )

    assert resposta.status_code == 200
    assert "Avatar atualizado" in resposta.text
    assert _usuario_por_email("dono@loja.test").avatar_key == "gato"
    assert _usuario_por_email("dono@loja.test").foto_perfil is None
    # Galeria marca o escolhido e a foto passa a servir o bichinho.
    assert 'value="gato" checked' in resposta.text
    servida = client.get(_foto_url(dono.id))
    assert servida.status_code == 200
    assert servida.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in servida.content


def test_usar_inicial_limpa_avatar_e_foto(client):
    login(client)
    dono = _usuario_por_email("dono@loja.test")
    client.post(_AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "sapo"})

    resposta = client.post(_AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": ""})

    assert resposta.status_code == 200
    assert "inicial" in resposta.text.lower()
    apos = _usuario_por_email("dono@loja.test")
    assert apos.avatar_key is None
    assert apos.foto_perfil is None
    assert client.get(_foto_url(dono.id)).status_code == 404


def test_avatar_invalido_recusado_sem_mudar_nada(client):
    login(client)

    resposta = client.post(
        _AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "dragao"}
    )

    assert resposta.status_code == 400
    assert "Avatar inválido" in resposta.text
    assert _usuario_por_email("dono@loja.test").avatar_key is None


def test_upload_foto_valida_persiste_e_serve(client):
    login(client)
    dono = _usuario_por_email("dono@loja.test")

    resposta = client.post(
        _FOTO,
        data={"csrf": _csrf_perfil(client)},
        files={"foto": ("eu.png", _PNG, "image/png")},
    )

    assert resposta.status_code == 200
    assert "Foto de perfil atualizada" in resposta.text
    apos = _usuario_por_email("dono@loja.test")
    assert bytes(apos.foto_perfil) == _PNG
    assert apos.avatar_key is None
    servida = client.get(_foto_url(dono.id))
    assert servida.status_code == 200
    assert servida.headers["content-type"] == "image/png"
    assert servida.content == _PNG
    assert _foto_url(dono.id) in resposta.text


def test_upload_recusa_txt_e_svg(client):
    login(client)
    csrf = _csrf_perfil(client)

    txt = client.post(
        _FOTO,
        data={"csrf": csrf},
        files={"foto": ("nota.txt", b"hello", "text/plain")},
    )
    svg = client.post(
        _FOTO,
        data={"csrf": _csrf_perfil(client)},
        files={"foto": ("x.svg", b"<svg></svg>", "image/svg+xml")},
    )

    assert txt.status_code == 400
    assert "Formato de foto inválido" in txt.text
    assert svg.status_code == 400
    assert "Formato de foto inválido" in svg.text
    assert _usuario_por_email("dono@loja.test").foto_perfil is None


def test_upload_maior_que_2mb_recusado_com_mensagem_amigavel(client):
    login(client)
    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * (2 * 1024 * 1024)

    resposta = client.post(
        _FOTO,
        data={"csrf": _csrf_perfil(client)},
        files={"foto": ("grande.png", grande, "image/png")},
    )

    assert resposta.status_code == 400
    assert "2 MB" in resposta.text
    assert _usuario_por_email("dono@loja.test").foto_perfil is None


def test_upload_sem_arquivo_recusado(client):
    login(client)

    resposta = client.post(_FOTO, data={"csrf": _csrf_perfil(client)})

    assert resposta.status_code == 400
    assert "Escolha um arquivo" in resposta.text


def test_escolher_preset_limpa_foto_e_upload_limpa_preset(client):
    login(client)
    dono = _usuario_por_email("dono@loja.test")
    client.post(
        _FOTO,
        data={"csrf": _csrf_perfil(client)},
        files={"foto": ("eu.jpg", _JPG, "image/jpeg")},
    )

    client.post(_AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "raposa"})
    apos_preset = _usuario_por_email("dono@loja.test")
    assert apos_preset.avatar_key == "raposa"
    assert apos_preset.foto_perfil is None

    client.post(
        _FOTO,
        data={"csrf": _csrf_perfil(client)},
        files={"foto": ("eu.png", _PNG, "image/png")},
    )
    apos_foto = _usuario_por_email("dono@loja.test")
    assert apos_foto.avatar_key is None
    assert bytes(apos_foto.foto_perfil) == _PNG


def test_foto_de_outra_loja_nao_servida(client):
    db = SessionLocal()
    outra = Usuario(
        email="outra@outra.test",
        nome="Outra Loja",
        senha_hash=hash_senha("senha-segura"),
        papel="vendedor",
        loja_slug="outra-loja",
        foto_perfil=_PNG,
    )
    db.add(outra)
    db.commit()
    outra_id = outra.id
    db.close()
    login(client)
    dono = _usuario_por_email("dono@loja.test")

    assert client.get(_foto_url(outra_id)).status_code == 404
    assert client.get(_foto_url(outra_id)).content == b""
    assert client.get("/app/loja/perfil/foto/id-inexistente").status_code == 404
    # A própria foto continua servindo para quem é da loja.
    assert client.get(_foto_url(dono.id)).status_code == 404  # dono sem avatar
    client.post(_AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "panda"})
    assert client.get(_foto_url(dono.id)).status_code == 200


def test_foto_deslogado_redireciona_login(client):
    resposta = client.get(_foto_url("qualquer-id"), follow_redirects=False)
    assert resposta.status_code == 303
    assert resposta.headers["location"] == "/login"


def test_avatar_e_foto_nao_mudam_senha_nem_dados(client):
    login(client)
    antes = _usuario_por_email("dono@loja.test")
    hash_antes = antes.senha_hash
    client.post(_AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "urso"})
    client.post(
        _FOTO,
        data={"csrf": _csrf_perfil(client)},
        files={"foto": ("eu.png", _PNG, "image/png")},
    )

    depois = _usuario_por_email("dono@loja.test")
    assert depois.nome == antes.nome
    assert depois.email == antes.email
    assert depois.papel == antes.papel
    assert depois.loja_slug == antes.loja_slug
    assert depois.senha_hash == hash_antes
    assert verifica_senha(depois.senha_hash, "senha-segura")


def test_csrf_invalido_nao_troca_avatar_nem_foto(client):
    login(client)

    avatar = client.post(_AVATAR, data={"csrf": "invalido", "avatar_key": "gato"})
    foto = client.post(
        _FOTO,
        data={"csrf": "invalido"},
        files={"foto": ("eu.png", _PNG, "image/png")},
    )

    assert avatar.status_code == 400
    assert "Sessão expirada" in avatar.text
    assert foto.status_code == 400
    assert "Sessão expirada" in foto.text
    apos = _usuario_por_email("dono@loja.test")
    assert apos.avatar_key is None
    assert apos.foto_perfil is None


def test_topbar_mostra_foto_de_quem_tem_avatar(client):
    login(client)
    dono = _usuario_por_email("dono@loja.test")
    client.post(_AVATAR, data={"csrf": _csrf_perfil(client), "avatar_key": "coelho"})

    pagina = client.get(_PERFIL)

    assert pagina.status_code == 200
    assert f'src="{_foto_url(dono.id)}"' in pagina.text


def test_equipe_lista_mostra_miniatura_do_membro(client):
    criar_usuario(papel="vendedor", email="vera@loja.test")
    db = SessionLocal()
    vera = db.query(Usuario).filter(Usuario.email == "vera@loja.test").one()
    vera.avatar_key = "pinguim"
    db.commit()
    vera_id = vera.id
    db.close()
    login(client)

    pagina = client.get("/app/equipe")

    assert pagina.status_code == 200
    assert f'src="{_foto_url(vera_id)}"' in pagina.text
    servida = client.get(_foto_url(vera_id))
    assert servida.status_code == 200
    assert servida.headers["content-type"] == "image/svg+xml"
