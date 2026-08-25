"""Preview do agente: o rascunho conversando, sem WhatsApp no meio (spec §6.1).

Quem roda o agente é o n8n — não existe IA dentro deste produto. O papel daqui é
o de porteiro: monta o pedido com o prompt do **rascunho**, troca o telefone do
lojista por um sintético e chama o webhook `whatsapp-ai-preview`.

O telefone sintético é a peça que mais parece detalhe e menos é. `consultar_estoque`
não é só leitura: com resultado único ela guarda a moto escolhida chaveada por
telefone. O lojista vai testar com o próprio número — que é um número real, com
conversa real — e sem freio ele sobrescreveria o estado de uma conversa de
verdade. Por isso o telefone nunca vem da tela: é derivado da loja, aqui.
"""
from __future__ import annotations

import hashlib

import httpx

from app import config


class PreviewIndisponivel(RuntimeError):
    """O n8n não respondeu, ou respondeu o que não dá para mostrar."""


def telefone_sintetico(loja_id: str) -> str:
    """Estável por loja e fora da faixa de número real.

    Começa em ``0``: nenhum MSISDN começa com zero, então ele não colide com
    telefone de cliente nenhum nem depois do ``replace(/\\D/g, '')`` que as
    ferramentas fazem. Estável para o preview ter memória entre uma mensagem e a
    seguinte — sem isso cada turno seria uma conversa nova e o teste não mostraria
    a jornada, que é justamente o que o lojista quer ver.
    """
    digest = hashlib.sha256(f"preview:{loja_id}".encode()).hexdigest()
    return "0" + str(int(digest[:12], 16)).zfill(12)[:12]


def conversar(
    *,
    instance: str,
    loja_id: str,
    texto: str,
    prompt: str,
    historico: str = "",
    minusculas: bool = True,
    sem_emoji: bool = True,
    turno: int = 1,
    primeira_mensagem: bool = False,
) -> str:
    """Manda um turno ao workflow de preview e devolve a resposta do agente."""
    if not config.AGENTE_PREVIEW_URL:
        raise PreviewIndisponivel("preview do agente não configurado")
    corpo = {
        "instance": instance,
        # NUNCA o telefone de quem está logado: ver o docstring do módulo.
        "telefone": telefone_sintetico(loja_id),
        "texto": texto,
        "prompt": prompt,
        "historico": historico,
        "saida_minusculas": minusculas,
        "saida_sem_emoji": sem_emoji,
        "turno": turno,
        "primeira_mensagem": primeira_mensagem,
    }
    try:
        resposta = httpx.post(
            config.AGENTE_PREVIEW_URL,
            json=corpo,
            timeout=config.AGENTE_PREVIEW_TIMEOUT,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError) as e:
        raise PreviewIndisponivel("o preview não respondeu agora") from e
    texto_resposta = str((dados or {}).get("texto") or "").strip()
    if not texto_resposta:
        raise PreviewIndisponivel("o preview respondeu vazio")
    return texto_resposta
