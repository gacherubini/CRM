"""Registro e agregação backend-only dos eventos de funil.

O módulo não conhece HTTP nem o Chatbot. Emissores locais/remotos podem usá-lo
sem acoplar a persistência de eventos às telas do Portal.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean, median
from typing import Iterable, Mapping

from sqlalchemy.orm import Session

from app.models import FUNIL_EVENTO_TIPOS, FunilEvento, agora, novo_id


MAX_PAYLOAD_BYTES = 4000
PAYLOAD_CHAVES_PERMITIDAS = frozenset(
    {
        "automacao",
        "campanha_id",
        "canal",
        "etapa",
        "etapa_anterior",
        "etapa_nova",
        "motivo_codigo",
        "origem",
        "simulacao_id",
        "status",
        "status_anterior",
        "status_novo",
        "venda_id",
        "versao",
    }
)
PAYLOAD_CHAVES_PII = frozenset(
    {
        "cpf",
        "data_nascimento",
        "email",
        "endereco",
        "nascimento",
        "nome",
        "placa",
        "senha",
        "telefone",
        "token",
    }
)
_VALORES_PAYLOAD = (str, int, bool, type(None))


class EventoFunilInvalido(ValueError):
    """O evento não atende ao contrato seguro do funil."""


class EventoFunilIdempotenciaConflitante(EventoFunilInvalido):
    """A chave já representa outro evento dentro da mesma loja."""


TIPOS_MATERIALIZADOS_CHATBOT = frozenset({"lead_criado", "primeira_resposta"})


def _texto_obrigatorio(valor: str, campo: str, maximo: int) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise EventoFunilInvalido(f"{campo} é obrigatório")
    if len(texto) > maximo:
        raise EventoFunilInvalido(f"{campo} excede {maximo} caracteres")
    return texto


def _momento_utc(momento: datetime) -> datetime:
    if momento.tzinfo is None:
        return momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(timezone.utc)


def _payload_seguro(payload: Mapping[str, object] | None) -> str | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise EventoFunilInvalido("payload deve ser um objeto JSON")

    seguro: dict[str, object] = {}
    for chave_original, valor in payload.items():
        chave = str(chave_original).strip().casefold()
        if chave in PAYLOAD_CHAVES_PII:
            raise EventoFunilInvalido(f"payload não pode conter PII: {chave}")
        if chave not in PAYLOAD_CHAVES_PERMITIDAS:
            raise EventoFunilInvalido(f"campo de payload não permitido: {chave}")
        if not isinstance(valor, _VALORES_PAYLOAD):
            raise EventoFunilInvalido(f"payload.{chave} deve ser um valor escalar")
        if isinstance(valor, str) and len(valor) > 240:
            raise EventoFunilInvalido(f"payload.{chave} excede 240 caracteres")
        seguro[chave] = valor

    serializado = json.dumps(seguro, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if len(serializado.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise EventoFunilInvalido(f"payload excede {MAX_PAYLOAD_BYTES} bytes")
    return serializado


def _validar_repeticao(
    existente: FunilEvento,
    *,
    lead_ref: str,
    tipo: str,
    payload_json: str | None,
    ocorrido_em: datetime | None,
) -> None:
    divergente = existente.lead_ref != lead_ref or existente.tipo != tipo
    if payload_json is not None and existente.payload_json != payload_json:
        divergente = True
    if ocorrido_em is not None and _momento_utc(existente.ocorrido_em) != _momento_utc(ocorrido_em):
        divergente = True
    if divergente:
        raise EventoFunilIdempotenciaConflitante(
            "idempotency_key já usada por outro evento nesta loja"
        )


def registrar_evento(
    db: Session,
    *,
    loja_slug: str,
    lead_ref: str,
    tipo: str,
    idempotency_key: str,
    ocorrido_em: datetime | None = None,
    ator_email: str | None = None,
    payload: Mapping[str, object] | None = None,
) -> tuple[FunilEvento, bool]:
    """Registra uma vez e retorna ``(evento, criado)``.

    A idempotência é composta por loja + chave. Reutilizar a mesma chave em
    lojas diferentes é válido; reutilizá-la para outro evento na mesma loja é
    erro. A função apenas faz ``flush``: o dono da transação decide o commit.
    """

    loja = _texto_obrigatorio(loja_slug, "loja_slug", 120)
    lead = _texto_obrigatorio(lead_ref, "lead_ref", 120)
    chave = _texto_obrigatorio(idempotency_key, "idempotency_key", 160)
    tipo_normalizado = _texto_obrigatorio(tipo, "tipo", 40).casefold()
    if tipo_normalizado not in FUNIL_EVENTO_TIPOS:
        raise EventoFunilInvalido(f"tipo de evento desconhecido: {tipo_normalizado}")

    ator = str(ator_email or "").strip() or None
    if ator and len(ator) > 320:
        raise EventoFunilInvalido("ator_email excede 320 caracteres")
    payload_json = _payload_seguro(payload)

    with db.no_autoflush:
        existente = (
            db.query(FunilEvento)
            .filter(
                FunilEvento.loja_slug == loja,
                FunilEvento.idempotency_key == chave,
            )
            .one_or_none()
        )
    if existente is not None:
        _validar_repeticao(
            existente,
            lead_ref=lead,
            tipo=tipo_normalizado,
            payload_json=payload_json,
            ocorrido_em=ocorrido_em,
        )
        return existente, False

    momento = _momento_utc(ocorrido_em or agora())
    evento_id = novo_id()
    valores = {
        "id": evento_id,
        "loja_slug": loja,
        "lead_ref": lead,
        "tipo": tipo_normalizado,
        "ocorrido_em": momento,
        "ator_email": ator,
        "payload_json": payload_json,
        "idempotency_key": chave,
        "criado_em": agora(),
    }
    dialeto = db.get_bind().dialect.name
    if dialeto == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    elif dialeto == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:  # pragma: no cover - produção e testes usam os dois dialetos acima
        raise RuntimeError(f"dialeto não suportado para idempotência do funil: {dialeto}")

    comando = insert(FunilEvento).values(**valores).on_conflict_do_nothing(
        index_elements=["loja_slug", "idempotency_key"]
    )
    db.execute(comando)
    # INSERT .. ON CONFLICT evita envenenar/rollbackar a transação do chamador
    # em uma corrida e, diferente de SAVEPOINT no pysqlite, não faz commit
    # implícito quando ainda não houve outra escrita.
    with db.no_autoflush:
        existente = (
            db.query(FunilEvento)
            .filter(
                FunilEvento.loja_slug == loja,
                FunilEvento.idempotency_key == chave,
            )
            .one()
        )
    if existente.id != evento_id:
        _validar_repeticao(
            existente,
            lead_ref=lead,
            tipo=tipo_normalizado,
            payload_json=payload_json,
            ocorrido_em=ocorrido_em,
        )
        return existente, False
    return existente, True


def materializar_eventos_chatbot(
    db: Session,
    *,
    loja_slug: str,
    eventos: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    """Materializa a projeção HTTP do Chatbot usando as chaves idempotentes de origem."""
    criados = 0
    repetidos = 0
    for item in eventos:
        if not isinstance(item, Mapping):
            raise EventoFunilInvalido("evento do Chatbot deve ser um objeto")
        tipo = str(item.get("tipo") or "").strip().casefold()
        if tipo not in TIPOS_MATERIALIZADOS_CHATBOT:
            raise EventoFunilInvalido("tipo não materializável a partir do Chatbot")
        raw_ocorrido = str(item.get("ocorrido_em") or "").strip()
        try:
            ocorrido_em = datetime.fromisoformat(raw_ocorrido.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EventoFunilInvalido("ocorrido_em inválido no evento do Chatbot") from exc
        _, criado = registrar_evento(
            db,
            loja_slug=loja_slug,
            lead_ref=str(item.get("lead_ref") or ""),
            tipo=tipo,
            idempotency_key=str(item.get("idempotency_key") or ""),
            ocorrido_em=ocorrido_em,
            payload=item.get("payload"),
        )
        criados += int(criado)
        repetidos += int(not criado)
    return {"criados": criados, "repetidos": repetidos}


def _segundos(inicio: datetime, fim: datetime) -> float | None:
    valor = (_momento_utc(fim) - _momento_utc(inicio)).total_seconds()
    return valor if valor >= 0 else None


def _segundos_arredondados(valores: list[float], calculo) -> int | None:
    if not valores:
        return None
    valor = Decimal(str(calculo(valores))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(valor)


def _percentual(parte: int, total: int) -> Decimal | None:
    if total <= 0:
        return None
    return (Decimal(parte) * Decimal("100") / Decimal(total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def agregar_funil_eventos(
    eventos: Iterable[FunilEvento],
    *,
    inicio: datetime,
    fim: datetime,
) -> dict:
    """Agrega a coorte cuja primeira criação de lead ocorreu no período.

    Respostas e conversões posteriores ao fim continuam atribuídas à coorte.
    Eventos anteriores à criação do lead são ignorados. Quando não há base,
    percentuais e tempos retornam ``None`` em vez de inventar zero.
    """

    inicio_utc = _momento_utc(inicio)
    fim_utc = _momento_utc(fim)
    if fim_utc < inicio_utc:
        raise EventoFunilInvalido("fim deve ser igual ou posterior a inicio")

    todos = list(eventos)
    criacoes: dict[str, datetime] = {}
    for evento in todos:
        if evento.tipo != "lead_criado":
            continue
        momento = _momento_utc(evento.ocorrido_em)
        atual = criacoes.get(evento.lead_ref)
        if atual is None or momento < atual:
            criacoes[evento.lead_ref] = momento

    coorte = {
        lead_ref: criado_em
        for lead_ref, criado_em in criacoes.items()
        if inicio_utc <= criado_em <= fim_utc
    }
    tipos_por_lead: dict[str, dict[str, datetime]] = {lead_ref: {} for lead_ref in coorte}
    eventos_por_tipo = {tipo: 0 for tipo in FUNIL_EVENTO_TIPOS}

    for evento in todos:
        criado_em = coorte.get(evento.lead_ref)
        if criado_em is None:
            continue
        momento = _momento_utc(evento.ocorrido_em)
        if momento < criado_em:
            continue
        eventos_por_tipo[evento.tipo] = eventos_por_tipo.get(evento.tipo, 0) + 1
        primeiro = tipos_por_lead[evento.lead_ref].get(evento.tipo)
        if primeiro is None or momento < primeiro:
            tipos_por_lead[evento.lead_ref][evento.tipo] = momento

    etapas = {
        tipo: sum(1 for tipos in tipos_por_lead.values() if tipo in tipos)
        for tipo in FUNIL_EVENTO_TIPOS
    }
    tempos_resposta = [
        segundos
        for lead_ref, tipos in tipos_por_lead.items()
        if (resposta := tipos.get("primeira_resposta")) is not None
        and (segundos := _segundos(coorte[lead_ref], resposta)) is not None
    ]
    tempos_conversao = [
        segundos
        for lead_ref, tipos in tipos_por_lead.items()
        if (venda := tipos.get("venda_confirmada")) is not None
        and (segundos := _segundos(coorte[lead_ref], venda)) is not None
    ]

    total = len(coorte)
    respondidos = etapas["primeira_resposta"]
    convertidos = etapas["venda_confirmada"]
    return {
        "total_leads": total,
        "etapas": etapas,
        "eventos_por_tipo": eventos_por_tipo,
        "taxa_resposta_pct": _percentual(respondidos, total),
        "taxa_conversao_pct": _percentual(convertidos, total),
        "tempo_medio_primeira_resposta_segundos": _segundos_arredondados(
            tempos_resposta, mean
        ),
        "tempo_mediano_primeira_resposta_segundos": _segundos_arredondados(
            tempos_resposta, median
        ),
        "tempo_medio_conversao_segundos": _segundos_arredondados(tempos_conversao, mean),
        "tempo_mediano_conversao_segundos": _segundos_arredondados(
            tempos_conversao, median
        ),
    }


def resumo_funil(
    db: Session,
    *,
    loja_slug: str,
    inicio: datetime,
    fim: datetime,
) -> dict:
    """Resumo da loja sem consultar ou misturar eventos de outros tenants."""

    loja = _texto_obrigatorio(loja_slug, "loja_slug", 120)
    eventos = db.query(FunilEvento).filter(FunilEvento.loja_slug == loja).all()
    return agregar_funil_eventos(eventos, inicio=inicio, fim=fim)
