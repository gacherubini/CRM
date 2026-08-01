from app.db import SessionLocal
from app.models import RedefinicaoSenha, Usuario, agora
from app.auth import hash_senha


def test_persistir_redefinicao_senha():
    with SessionLocal() as db:
        user = Usuario(
            email="reset@x.com", nome="Reset", senha_hash=hash_senha("x" * 12),
            papel="dono", loja_slug="loja-a", ativo=True,
        )
        db.add(user)
        db.flush()
        reg = RedefinicaoSenha(
            usuario_id=user.id, token_hash="h" * 64, expira_em=agora(), criado_em=agora(),
        )
        db.add(reg)
        db.commit()
        assert reg.id is not None
        assert reg.usado_em is None and reg.revogado_em is None
