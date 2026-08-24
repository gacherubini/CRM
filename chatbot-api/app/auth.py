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
    # ``None`` = credencial de integração: o token é da plataforma, não de uma
    # loja, e a loja de cada pedido vem da instância (spec §6.2).
    loja_id: str | None
    papel: str


def resolver_loja_id(db: Session, ctx: Contexto, instance: str | None) -> str:
    """Loja deste pedido. Credencial de loja manda; integração resolve pela instância.

    O ``n8n-cloud`` é **um** workflow para N lojas: se a loja viesse do token, ele
    procuraria a conversa na loja errada e o bot calaria sem erro nenhum — só
    ``200`` e silêncio. Era esse o sintoma no smoke do piloto.

    Fail-closed de propósito: integração sem instância é ``400``, nunca um
    fallback para "alguma" loja — isso mandaria a mensagem de uma loja pela
    outra. Instância desconhecida é ``404``, decidido por
    ``resolve_canal_for_instance``.
    """
    if ctx.loja_id:
        return ctx.loja_id
    if not (instance or "").strip():
        raise HTTPException(
            status_code=400,
            detail="instance é obrigatório para credencial de integração",
        )
    # Import tardio: servico importa auth (hash_token), então o topo daria ciclo.
    from app.servico import resolver_loja_e_canal_por_instancia

    loja, _canal = resolver_loja_e_canal_por_instancia(db, instance)
    return loja.id


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
