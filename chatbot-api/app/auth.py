"""Contexto autenticado por token de serviço (loja derivada da credencial)."""
import hashlib
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models_db import CredencialServico


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Contexto:
    loja_id: str
    papel: str


def get_contexto(
    authorization: str = Header(default=""), db: Session = Depends(get_db)
) -> Contexto:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="credencial ausente")
    token = authorization[len("Bearer ") :].strip()
    cred = db.get(CredencialServico, hash_token(token))
    if cred is None:
        raise HTTPException(status_code=401, detail="credencial inválida")
    return Contexto(loja_id=cred.loja_id, papel=cred.papel)
