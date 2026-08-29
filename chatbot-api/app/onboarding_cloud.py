"""A cadeia do embedded signup, do lado do banco (spec §7).

Não monta URL e não conhece httpx: quem fala com a Graph é
``app/meta_onboarding.py``. Aqui moram a ordem dos elos, a retomada e o teto.

**O canal nasce depois do elo 1, não no fim.** O ``code`` do popup tem TTL de
30 s e não é retomável; se o canal só aparecesse no fim, uma falha no elo 2
perderia o token e mandaria o lojista de volta ao popup — o oposto do que o
spec §7 promete ("depois do elo 1 o popup nunca mais é necessário").
"""
from __future__ import annotations

import secrets
import uuid

from sqlalchemy.orm import Session

from app import segredo_canal
from app.meta_onboarding import MetaOnboarding, OnboardingErro
from app.models_db import WhatsAppCanal

# A Meta aceita 10 registros por número em 72 h móveis e trava o número por três
# dias ao estourar (133016). Paramos em 5: o custo do erro é do lojista, em dias
# sem WhatsApp, e nenhuma tentativa nossa vale isso.
TETO_REGISTRO = 5


def _pin_novo() -> str:
    """Seis dígitos. ``secrets``, não ``random``: é credencial."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _canal_da_waba(db: Session, loja_id: str, waba_id: str) -> WhatsAppCanal | None:
    return (
        db.query(WhatsAppCanal)
        .filter(WhatsAppCanal.loja_id == loja_id, WhatsAppCanal.waba_id == waba_id)
        .first()
    )


def _parar(db: Session, canal: WhatsAppCanal, erro: OnboardingErro) -> None:
    """Grava onde parou. A mensagem é NOSSA — corpo de erro da Meta ecoa os
    parâmetros enviados, e um deles é o App Secret."""
    canal.onboarding_erro = str(erro)[:200]
    db.commit()
    raise erro


def conectar(
    db: Session,
    loja_id: str,
    *,
    code: str,
    waba_id: str,
    phone_number_id: str,
    business_id: str,
    meta: MetaOnboarding | None = None,
) -> WhatsAppCanal:
    meta = meta or MetaOnboarding()
    canal = _canal_da_waba(db, loja_id, waba_id)

    # --- elo 1: só na primeira vez. Depois dele o popup não é mais necessário.
    if canal is None:
        dono = (
            db.query(WhatsAppCanal)
            .filter(WhatsAppCanal.evolution_instance == phone_number_id)
            .first()
        )
        if dono is not None:
            raise OnboardingErro(
                "este número já está conectado a outra loja", elo=1
            )
        token = meta.trocar_code_por_token(code)
        canal = WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_id,
            e164_or_label=phone_number_id,
            evolution_instance=phone_number_id,
            waba_id=waba_id,
            business_id=business_id,
            estado="cloud_pendente",
            onboarding_elo=1,
            token_cifrado=segredo_canal.cifrar(token),
            pin_cifrado=segredo_canal.cifrar(_pin_novo()),
        )
        db.add(canal)
        db.commit()

    token = segredo_canal.decifrar(canal.token_cifrado)
    pin = segredo_canal.decifrar(canal.pin_cifrado)
    canal.onboarding_erro = None

    # --- elo 2: idempotente, repetir não dói.
    if (canal.onboarding_elo or 0) < 2:
        try:
            meta.inscrever_app(waba_id=waba_id, token=token)
        except OnboardingErro as erro:
            _parar(db, canal, erro)
        canal.onboarding_elo = 2
        db.commit()

    # --- elo 3: teto nosso, bem abaixo do da Meta. Sem retry automático.
    if (canal.onboarding_elo or 0) < 3:
        if canal.registro_tentativas >= TETO_REGISTRO:
            _parar(
                db,
                canal,
                OnboardingErro(
                    "já tentamos registrar este número vezes demais; fale com a "
                    "Revy antes de tentar de novo",
                    elo=3,
                ),
            )
        canal.registro_tentativas += 1
        db.commit()
        try:
            meta.registrar_numero(
                phone_number_id=phone_number_id, pin=pin, token=token
            )
        except OnboardingErro as erro:
            _parar(db, canal, erro)
        canal.onboarding_elo = 3
        db.commit()

    # --- elo 4: template já existente é sucesso, não erro.
    if (canal.onboarding_elo or 0) < 4:
        try:
            meta.criar_template(waba_id=waba_id, token=token)
        except OnboardingErro as erro:
            _parar(db, canal, erro)
        canal.onboarding_elo = 4
        canal.template_oferta = "chama_vendedor"
        db.commit()

    canal.onboarding_elo = 5
    db.commit()
    return canal
