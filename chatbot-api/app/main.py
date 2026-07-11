"""API do Chatbot (Plano #2A). n8n consome esta API; não escreve no banco direto."""
import os
from typing import Optional

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config, models_db, servico  # noqa: F401 (registra os modelos)
from app.auth import Contexto, get_contexto
from app.db import Base, engine, get_db

app = FastAPI(title="Chatbot API")

if os.getenv("CHATBOT_SKIP_INIT") != "1":
    Base.metadata.create_all(bind=engine)


class MensagemEntrada(BaseModel):
    instance: str
    telefone: str
    texto: Optional[str] = None
    provider_message_id: Optional[str] = None
    from_me: bool = False


class EstadoInput(BaseModel):
    bot_ativo: bool


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"versao": config.VERSAO, "schema": config.SCHEMA_VERSAO}


@app.post("/webhook/mensagem")
def webhook_mensagem(msg: MensagemEntrada, db: Session = Depends(get_db)):
    """Recebe uma mensagem (loja resolvida pela instância) e persiste idempotente."""
    return servico.registrar_mensagem(
        db, msg.instance, msg.telefone, msg.texto, msg.provider_message_id, msg.from_me
    )


@app.get("/v1/conversas/{telefone}/estado")
def obter_estado(
    telefone: str, ctx: Contexto = Depends(get_contexto), db: Session = Depends(get_db)
):
    return servico.obter_estado(db, ctx.loja_id, telefone)


@app.patch("/v1/conversas/{telefone}/estado")
def definir_estado(
    telefone: str,
    dados: EstadoInput,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
):
    return servico.definir_bot_ativo(db, ctx.loja_id, telefone, dados.bot_ativo)
