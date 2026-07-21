"""Contexto autenticado por token de serviço (loja derivada da credencial)."""
import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.hardening import aplicar_rate_limit
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


def verificar_webhook_token(
    request: Request, x_webhook_token: str = Header(default="")
) -> None:
    """Autentica o webhook por segredo compartilhado (opt-in via CHATBOT_WEBHOOK_TOKEN).

    Vazio => webhook aberto (não quebra o fluxo n8n vivo). Definido => exige header
    X-Webhook-Token igual, comparado em tempo constante.
    """
    # Executa antes da comparação do token: tentativas ausentes/inválidas também
    # consomem a janela e não contornam a proteção. O limite de tamanho do body é
    # aplicado separadamente pelo middleware antes do parse.
    aplicar_rate_limit(request)
    esperado = config.WEBHOOK_TOKEN
    if not esperado:
        return
    if not secrets.compare_digest(x_webhook_token, esperado):
        raise HTTPException(status_code=401, detail="webhook token inválido")
