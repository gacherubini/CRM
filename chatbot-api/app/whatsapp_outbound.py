"""Port de envio de texto WhatsApp (atendimento humano → Evolution).

Adapter HTTP Evolution (sendText) e Fake para testes. A apikey nunca é logada.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app import config

logger = logging.getLogger("chatbot.whatsapp_outbound")

# Redige sequências longas de dígitos (CPF, telefone, nascimento, JID numérico)
# antes de logar o corpo de erro do Evolution: o texto do alerta contém PII e o
# provedor pode ecoá-lo no corpo da resposta.
_DIGITOS_SENSIVEIS = re.compile(r"\d{5,}")


def _sanitizar_corpo_erro(texto: str, api_key: str) -> str:
    """Trunca e remove PII/segredos do corpo de erro antes de ir para o log."""
    limpo = (texto or "")[:500]
    if api_key and api_key in limpo:
        limpo = limpo.replace(api_key, "[apikey]")
    return _DIGITOS_SENSIVEIS.sub("[num]", limpo)


def _classificar_falha_evolution(status: int, corpo: str) -> tuple[str, str]:
    """Mapeia o corpo de erro do Evolution para (code durável, motivo curto).

    O ``code`` cabe em ``last_error_code`` (<=80 chars) e é persistido; o corpo
    bruto NUNCA é persistido (só logado, já sanitizado).
    """
    baixo = corpo.lower()
    if any(
        termo in baixo
        for termo in ("not-authorized", "forbidden", "not a participant", "participant")
    ):
        return "evolution_group_forbidden", "instância não participa do grupo de destino"
    if any(
        termo in baixo
        for termo in ("item-not-found", "not found", "does not exist", '"exists":false')
    ):
        return "evolution_target_not_found", "grupo/número de destino não encontrado"
    return "evolution_send_failed", f"HTTP {status}"


class WhatsAppOutboundError(RuntimeError):
    """Falha ao enviar mensagem pelo provedor WhatsApp."""

    def __init__(self, message: str, *, code: str = "evolution_send_failed"):
        super().__init__(message)
        self.code = code


class WhatsAppOutboundPort(Protocol):
    """Port: envia texto por uma instância Evolution."""

    def send_text(
        self,
        *,
        instance: str,
        number: str,
        text: str,
    ) -> dict[str, Any]:
        """Envia texto. Retorna payload do provedor (opaco). Levanta WhatsAppOutboundError."""
        ...


class EvolutionWhatsAppOutbound:
    """POST /message/sendText/{instance} na Evolution API.

    Env (preferência):
      CHATBOT_EVOLUTION_URL / CHATBOT_EVOLUTION_API_KEY
    Fallback (mesmo host usado por imagem/áudio):
      CHATBOT_IMAGE_EVOLUTION_URL / CHATBOT_IMAGE_EVOLUTION_API_KEY
      (que por sua vez herdam AUDIO_*).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url if base_url is not None else config.EVOLUTION_URL).rstrip(
            "/"
        )
        self.api_key = (
            api_key if api_key is not None else config.EVOLUTION_API_KEY
        ) or ""
        self.timeout = (
            timeout if timeout is not None else config.EVOLUTION_SEND_TIMEOUT
        )
        self.transport = transport

    def send_text(
        self,
        *,
        instance: str,
        number: str,
        text: str,
    ) -> dict[str, Any]:
        instancia = (instance or "").strip()
        numero = (number or "").strip()
        corpo = text if text is not None else ""
        if not self.base_url or not self.api_key:
            raise WhatsAppOutboundError(
                "Evolution não configurada para envio de texto",
                code="evolution_not_configured",
            )
        if not instancia:
            raise WhatsAppOutboundError(
                "instância Evolution ausente",
                code="evolution_instance_missing",
            )
        if not numero:
            raise WhatsAppOutboundError(
                "número de destino ausente",
                code="evolution_number_missing",
            )
        path = f"/message/sendText/{quote(instancia, safe='')}"
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"apikey": self.api_key},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                resposta = client.post(
                    path,
                    json={"number": numero, "text": corpo},
                )
                if resposta.status_code >= 400:
                    corpo_erro = _sanitizar_corpo_erro(resposta.text, self.api_key)
                    code, motivo = _classificar_falha_evolution(
                        resposta.status_code, corpo_erro
                    )
                    logger.warning(
                        "Evolution sendText falhou status=%s instancia=%s code=%s corpo=%s",
                        resposta.status_code,
                        instancia,
                        code,
                        corpo_erro,
                    )
                    raise WhatsAppOutboundError(
                        f"Evolution recusou o envio (HTTP {resposta.status_code}): {motivo}",
                        code=code,
                    )
                if not resposta.content:
                    return {}
                try:
                    dados = resposta.json()
                except ValueError:
                    return {}
                return dados if isinstance(dados, dict) else {"data": dados}
        except WhatsAppOutboundError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(
                "Evolution sendText erro de rede instancia=%s err=%s",
                instancia,
                type(exc).__name__,
            )
            raise WhatsAppOutboundError(
                "não foi possível contatar a Evolution",
                code="evolution_unreachable",
            ) from exc


@dataclass
class FakeWhatsAppOutbound:
    """Adapter de teste: grava chamadas; pode simular falha."""

    calls: list[dict[str, str]] = field(default_factory=list)
    fail: bool = False
    fail_code: str = "evolution_send_failed"
    fail_message: str = "Evolution indisponível (fake)"
    response: dict[str, Any] = field(
        default_factory=lambda: {"key": {"id": "fake-provider-msg"}}
    )

    def send_text(
        self,
        *,
        instance: str,
        number: str,
        text: str,
    ) -> dict[str, Any]:
        self.calls.append(
            {"instance": instance, "number": number, "text": text}
        )
        if self.fail:
            raise WhatsAppOutboundError(self.fail_message, code=self.fail_code)
        return dict(self.response)


_outbound: WhatsAppOutboundPort | None = None


def get_whatsapp_outbound() -> WhatsAppOutboundPort:
    global _outbound
    if _outbound is None:
        _outbound = EvolutionWhatsAppOutbound()
    return _outbound


def set_whatsapp_outbound(port: WhatsAppOutboundPort | None) -> None:
    """Sobrescreve o port (testes). None restaura o adapter Evolution padrão."""
    global _outbound
    _outbound = port


class CloudWhatsAppOutbound:
    """POST /{phone_number_id}/messages na Graph API (spec §6).

    ``instance`` aqui é o ``phone_number_id`` — o mesmo slot que no Modo 1
    carrega a instância Evolution. Assim ``send_text`` continua satisfazendo
    ``WhatsAppOutboundPort`` sem mudar a assinatura do port.

    O ``oferta_id`` vai no ``payload``/``id`` do botão porque o clique volta
    como inbound e precisa dizer QUAL lead (spec §5.7): o mesmo vendedor pode
    ter uma oferta viva e outra velha que ainda vale.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 15,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or config.GRAPH_BASE_URL).rstrip("/")
        self.token = token or config.GRAPH_TOKEN
        self.timeout = timeout
        self._transport = transport

    def _post(self, instance: str, corpo: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise WhatsAppOutboundError("Cloud API não configurada")
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self.token}"},
            ) as cliente:
                resposta = cliente.post(f"{self.base_url}/{instance}/messages", json=corpo)
                resposta.raise_for_status()
                return resposta.json()
        except httpx.HTTPError as exc:
            raise WhatsAppOutboundError(f"falha no envio Cloud: {exc}") from exc

    def send_text(self, *, instance: str, number: str, text: str) -> dict[str, Any]:
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"body": text},
        })

    def marcar_lido_e_digitando(self, *, instance: str, wamid: str) -> dict[str, Any]:
        """Acende o "digitando…" para o cliente — e marca a entrada como lida.

        Na Cloud API o indicador **não** é parâmetro de envio, como o ``delay``
        da Evolution é no Modo 1: é esta chamada à parte, que precisa do
        ``wamid`` da mensagem **do cliente** e vai no mesmo endpoint de
        ``/messages``. Os dois efeitos vêm juntos e não se separam — ligar o
        indicador liga o tique azul.

        A Meta dispensa o indicador quando a resposta sai, ou sozinha em 25 s,
        o que vier primeiro. Por isso quem chama é o juiz do debounce, no
        instante em que o agente começa a pensar: a espera real do turno vira
        a janela do "digitando…", sem nenhum atraso simulado.
        """
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wamid,
            "typing_indicator": {"type": "text"},
        })

    def send_template_button(
        self, *, instance: str, number: str, template: str,
        variaveis: list[str], oferta_id: str, idioma: str = "pt_BR",
    ) -> dict[str, Any]:
        """Janela de 24 h FECHADA com aquele vendedor: template pago (~R$0,04)."""
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": idioma},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": v} for v in variaveis],
                    },
                    {
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": "0",
                        "parameters": [{"type": "payload", "payload": f"pego:{oferta_id}"}],
                    },
                ],
            },
        })

    def send_interactive_button(
        self, *, instance: str, number: str, texto: str, oferta_id: str,
        rotulo: str = "Peguei",
    ) -> dict[str, Any]:
        """Janela ABERTA: interativa, de graça. Mesmo significado do template."""
        return self._post(instance, {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": f"pego:{oferta_id}", "title": rotulo},
                        }
                    ]
                },
            },
        })


def acender_digitando(
    db: Session, loja_id: str, *, instance: str, wamid: str
) -> bool:
    """Liga o "digitando…" quando a loja fala pela central Cloud.

    Devolve ``True`` só quando o indicador foi mesmo aceso, para o teste poder
    distinguir "não era Modo 2" de "a Meta recusou".

    **Enfeite nunca derruba resposta.** Qualquer falha aqui é engolida e vira
    log: o cliente prefere receber a mensagem sem o "digitando…" a não receber
    mensagem nenhuma. No Modo 1 não há o que fazer — quem mostra o indicador é
    a Evolution, pelo ``delay`` que já viaja no envio.
    """
    port = outbound_para_loja(db, loja_id)
    if not isinstance(port, CloudWhatsAppOutbound):
        return False
    if not wamid:
        return False
    try:
        port.marcar_lido_e_digitando(instance=instance, wamid=wamid)
        return True
    except Exception:
        logger.warning("digitando nao acendeu")
        return False


def outbound_para_loja(db: Session, loja_id: str) -> WhatsAppOutboundPort:
    """Modo 1 e Modo 2 convivem no processo, em lojas diferentes.

    Por isso a escolha é por loja e não pelo singleton de
    ``get_whatsapp_outbound`` — trocar o singleton derrubaria o Modo 1 das
    outras lojas. O singleton continua sendo o default (Modo 1) e o
    ``set_whatsapp_outbound`` continua servindo aos testes.
    """
    from app.rodizio import loja_opera_modo2

    if loja_opera_modo2(db, loja_id):
        return CloudWhatsAppOutbound()
    return get_whatsapp_outbound()
