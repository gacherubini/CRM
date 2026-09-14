"""Autenticação das APIs do Motor por credencial Bearer de cliente."""
import hashlib
import hmac

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.models_db import ClienteApiORM, CredencialApiORM


def hash_token(token: str) -> str:
    """Hash determinístico para tokens aleatórios de alta entropia."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _nao_autorizado() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
        content={"erro": {"code": "nao_autorizado", "message": "Credencial inválida"}},
    )


def autenticar_cliente(request: Request, db: Session = Depends(get_db)):
    recebido = request.headers.get("Authorization", "")
    esquema, separador, token = recebido.partition(" ")
    if not separador or esquema.lower() != "bearer" or not token.strip():
        return _nao_autorizado()

    credencial = (
        db.query(CredencialApiORM)
        .filter_by(token_hash=hash_token(token.strip()), ativo=True)
        .one_or_none()
    )
    if credencial is None:
        return _nao_autorizado()
    cliente = db.get(ClienteApiORM, credencial.cliente_id)
    if cliente is None or not cliente.ativo:
        return _nao_autorizado()
    return cliente


def autenticar_provisionamento(request: Request) -> JSONResponse | None:
    """Auth do endpoint interno de provisionamento (token de serviço dedicado).

    Retorna ``None`` quando autorizado; senão a resposta de erro já pronta:
    503 fail-closed sem ``MOTOR_PROVISIONING_TOKEN`` configurado, 401 quando o
    Bearer não confere. Nunca aceita Bearer de cliente aqui.
    """
    esperado = (config.PROVISIONING_TOKEN or "").strip()
    if not esperado:
        return JSONResponse(
            status_code=503,
            content={
                "erro": {
                    "code": "provisionamento_indisponivel",
                    "message": "provisionamento automático indisponível",
                }
            },
        )
    recebido = request.headers.get("Authorization", "")
    if not hmac.compare_digest(recebido, f"Bearer {esperado}"):
        return _nao_autorizado()
    return None
