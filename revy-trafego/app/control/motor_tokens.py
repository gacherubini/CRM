"""Cofre de tokens do Motor por loja (Revy Control guarda, Portal consome).

O Control emite um cliente+credencial por loja via Motor
(``POST /v1/internal/provisioning/ensure-cliente``), guarda o token cifrado
(Fernet, chave só em env ``REVY_CONTROL_TOKENS_KEY``) e serve ao Portal por
endpoint interno. Loja criada ganha credencial sem CLI nem edição de secret.

Regras que não se afrouxam:

- Token em repouso só cifrado; sem a chave, leitura e emissão falham fechado
  (``CofreIndisponivel`` → 503). A chave dedicada nunca é a de CAPI/Ads e
  nunca há fallback para chave de desenvolvimento.
- Token em claro nunca em log, auditoria, erro, snapshot ou outbox: as
  exceções carregam só tipo/status, os logs só o slug.
- Concorrência: trava local (um ensure por vez neste processo) + idempotência
  do Motor (só a criação devolve o token 1x; repetição volta ``ja_existia``
  sem token) + escrita que nunca sobrescreve linha existente. A trava
  distribuída é o próprio Motor: só um 201 existe por slug, então dois
  processos nunca guardam tokens divergentes.
- Resolução para servir: cofre primeiro; se ausente, o mapa em env
  (``motor_token_para``); se ambos ausentes, sem token. O mapa em env nunca é
  copiado para o cofre (rotação do mapa não pode divergir do guardado).
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app import config as config_mod
from app.models import MotorTokenCofre, agora

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SLUG_MAX = 120

# Um ensure por vez neste processo: o check (cofre/mapa) e o emit+guardar
# acontecem atomicamente, então dois ensures simultâneos para o mesmo slug
# nunca disparam duas emissões utilizáveis divergentes.
_ENSURE_LOCK = threading.Lock()


class CofreIndisponivel(RuntimeError):
    """Chave do cofre ausente ou inválida: falhar fechado (503)."""


class SlugInvalido(ValueError):
    """Slug fora do canônico do Motor ([a-z0-9-], minúsculo, ≤120)."""


class MotorIndisponivel(RuntimeError):
    """Motor sem emissão (não configurado, fora ou resposta inesperada)."""


def slug_canonico(valor: object) -> str | None:
    """Slug canônico do Motor: strip + minúsculas, hífens internos, ≤120."""
    slug = (valor if isinstance(valor, str) else "").strip().lower()
    if not slug or len(slug) > _SLUG_MAX or not _SLUG_RE.fullmatch(slug):
        return None
    return slug


def _fernet() -> Fernet:
    chave = (config_mod.settings.control_tokens_key or "").strip()
    if not chave:
        raise CofreIndisponivel(
            "cofre de tokens do Motor sem chave (REVY_CONTROL_TOKENS_KEY)"
        )
    try:
        return Fernet(chave.encode())
    except Exception as exc:
        raise CofreIndisponivel("chave do cofre de tokens inválida") from exc


def guardar_token(db: Any, slug: str, token_claro: str) -> bool:
    """Cifra e guarda o token; nunca sobrescreve linha existente.

    Retorna True se guardou agora, False se o cofre já tinha este slug
    (first-write-wins: com a trava local + idempotência do Motor, a primeira
    escrita é a do token 1x emitido na criação).
    """
    canon = slug_canonico(slug)
    if canon is None:
        raise SlugInvalido("slug fora do canônico do Motor")
    if not token_claro or not isinstance(token_claro, str):
        raise ValueError("token vazio não entra no cofre")
    if db.get(MotorTokenCofre, canon) is not None:
        return False
    blob = _fernet().encrypt(token_claro.encode()).decode()
    momento = agora()
    db.add(
        MotorTokenCofre(
            loja_slug=canon,
            token_ciphertext=blob,
            criado_em=momento,
            atualizado_em=momento,
        )
    )
    db.flush()
    return True


def ler_token(db: Any, slug: str) -> str | None:
    """Lê o claro do cofre; None se ausente. Sem chave, falha fechado."""
    canon = slug_canonico(slug)
    if canon is None:
        raise SlugInvalido("slug fora do canônico do Motor")
    fernet = _fernet()
    linha = db.get(MotorTokenCofre, canon)
    if linha is None:
        return None
    try:
        return fernet.decrypt(linha.token_ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CofreIndisponivel("cofre ilegível com a chave atual") from exc


def token_para_portal(db: Any, slug: str) -> str | None:
    """Resolve o token a servir: cofre primeiro, mapa em env depois."""
    token = ler_token(db, slug)
    if token:
        return token
    canon = slug_canonico(slug)
    if canon is None:
        raise SlugInvalido("slug fora do canônico do Motor")
    return (config_mod.settings.motor_token_para(canon) or "").strip() or None


def _chamar_ensure_motor(
    slug: str,
    *,
    base_url: str,
    provisioning_token: str,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    """POST ensure-cliente no Motor. Ponto único de rede (monkeypatch em teste)."""
    headers = {"Authorization": f"Bearer {provisioning_token}"}
    with httpx.Client(
        base_url=base_url.rstrip("/"), headers=headers, timeout=timeout
    ) as client:
        resposta = client.post(
            "/v1/internal/provisioning/ensure-cliente",
            json={"loja_slug": slug},
        )
    try:
        corpo = resposta.json()
    except ValueError:
        corpo = {}
    return resposta.status_code, corpo if isinstance(corpo, dict) else {}


def _emitir_via_motor(slug: str) -> str | None:
    """Emite no Motor; 201 devolve o token 1x, 200 (ja_existia) devolve None."""
    base_url = (config_mod.settings.motor_url or "").strip()
    prov = (config_mod.settings.motor_provisioning_token or "").strip()
    if not base_url or not prov:
        raise MotorIndisponivel("emissão no Motor não configurada")
    try:
        status, corpo = _chamar_ensure_motor(
            slug,
            base_url=base_url,
            provisioning_token=prov,
            timeout=config_mod.settings.request_timeout,
        )
    except MotorIndisponivel:
        raise
    except Exception as exc:
        raise MotorIndisponivel("motor inacessível para emissão") from exc
    if status == 201:
        token = corpo.get("token")
        if not token or not isinstance(token, str):
            raise MotorIndisponivel("motor respondeu criação sem token")
        return token
    if status == 200 and corpo.get("ja_existia") is True:
        logger.info(
            "motor_tokens: cliente já existia no Motor loja=%s (sem token a guardar)",
            slug,
        )
        return None
    raise MotorIndisponivel(f"motor ensure respondeu status={status}")


def ensure_motor_token(db: Any, slug: str) -> str | None:
    """Retorna token utilizável para o slug; emite e guarda quando falta.

    Ordem: cofre → mapa em env → emissão no Motor (201 guarda e retorna; 200
    ``ja_existia`` sem token retorna None). Sem chave do cofre, falha fechado
    antes de qualquer IO. Chamar sob transação do dono: faz ``flush``, quem
    commita é o chamador. Nunca loga nem levanta o token em claro.
    """
    canon = slug_canonico(slug)
    if canon is None:
        raise SlugInvalido("slug fora do canônico do Motor")
    _fernet()
    with _ENSURE_LOCK:
        hit = ler_token(db, canon)
        if hit:
            return hit
        do_mapa = (config_mod.settings.motor_token_para(canon) or "").strip()
        if do_mapa:
            return do_mapa
        novo = _emitir_via_motor(canon)
        if novo is None:
            return None
        guardar_token(db, canon, novo)
        logger.info("motor_tokens: token emitido e guardado loja=%s", canon)
        return novo
