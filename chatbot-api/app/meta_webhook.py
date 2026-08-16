"""Entrada do webhook da Cloud API (spec §6.1)."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

_PREFIXO = "sha256="


@dataclass(frozen=True)
class EventoCloud:
    phone_number_id: str
    tipo: str  # texto | audio | imagem | clique | status | ignorado
    remetente: str = ""
    wamid: str = ""
    texto: str | None = None
    media_id: str | None = None
    mime: str | None = None
    oferta_id: str | None = None
    referral_ad_id: str | None = None
    status: str | None = None


def assinatura_valida(corpo_cru: bytes, header: str, *, app_secret: str) -> bool:
    """Confere ``X-Hub-Signature-256`` sobre o corpo **cru**.

    Recebe ``bytes`` de propósito: calcular o HMAC sobre o JSON re-serializado
    é o erro clássico dessa integração — ordem de chave e escape de unicode
    mudam os bytes e a assinatura nunca bate. O tipo impede o erro.

    Fail-closed: sem ``app_secret`` configurado, nada passa.
    """
    if not app_secret or not header.startswith(_PREFIXO):
        return False
    recebida = header[len(_PREFIXO):].strip()
    esperada = hmac.new(app_secret.encode("utf-8"), corpo_cru, hashlib.sha256).hexdigest()
    return hmac.compare_digest(recebida, esperada)


def _oferta_do_clique(mensagem: dict) -> str | None:
    bruto = str(
        (mensagem.get("button") or {}).get("payload")
        or ((mensagem.get("interactive") or {}).get("button_reply") or {}).get("id")
        or ""
    )
    return bruto[len("pego:"):] or None if bruto.startswith("pego:") else None


def parse_inbound(payload: dict) -> list[EventoCloud]:
    """Traduz o envelope da Cloud API para eventos.

    Um POST pode trazer vários eventos, e ``statuses`` (entregue/lido/falhou)
    vem no mesmo lugar que ``messages`` — tratar status como mensagem criaria
    lead fantasma a cada confirmação de entrega.
    """
    eventos: list[EventoCloud] = []
    for entrada in payload.get("entry") or []:
        for mudanca in entrada.get("changes") or []:
            valor = mudanca.get("value") or {}
            phone_number_id = str((valor.get("metadata") or {}).get("phone_number_id") or "")

            for status in valor.get("statuses") or []:
                eventos.append(EventoCloud(
                    phone_number_id=phone_number_id,
                    tipo="status",
                    remetente=str(status.get("recipient_id") or ""),
                    wamid=str(status.get("id") or ""),
                    status=str(status.get("status") or ""),
                ))

            for mensagem in valor.get("messages") or []:
                tipo_meta = str(mensagem.get("type") or "")
                comum = {
                    "phone_number_id": phone_number_id,
                    "remetente": str(mensagem.get("from") or ""),
                    "wamid": str(mensagem.get("id") or ""),
                    "referral_ad_id": (
                        str((mensagem.get("referral") or {}).get("source_id"))
                        if (mensagem.get("referral") or {}).get("source_id")
                        else None
                    ),
                }
                if tipo_meta == "text":
                    eventos.append(EventoCloud(
                        tipo="texto", texto=(mensagem.get("text") or {}).get("body"), **comum
                    ))
                elif tipo_meta in ("audio", "voice"):
                    midia = mensagem.get(tipo_meta) or {}
                    eventos.append(EventoCloud(
                        tipo="audio",
                        media_id=str(midia.get("id") or "") or None,
                        mime=str(midia.get("mime_type") or "").split(";", 1)[0].strip() or None,
                        **comum,
                    ))
                elif tipo_meta == "image":
                    midia = mensagem.get("image") or {}
                    eventos.append(EventoCloud(
                        tipo="imagem",
                        media_id=str(midia.get("id") or "") or None,
                        mime=str(midia.get("mime_type") or "").split(";", 1)[0].strip() or None,
                        **comum,
                    ))
                elif tipo_meta in ("button", "interactive"):
                    eventos.append(EventoCloud(
                        tipo="clique", oferta_id=_oferta_do_clique(mensagem), **comum
                    ))
                else:
                    eventos.append(EventoCloud(tipo="ignorado", **comum))
    return eventos
