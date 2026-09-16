"""O agora do rodízio: quem está com lead, há quanto tempo, e para quem passa.

View-model puro da seção ao vivo de `/app/loja/whatsapp/fila`. Sem I/O: recebe
a fila ordenada e as ofertas do Chatbot e devolve cartões prontos para o
template. Cada caso vira um teste de duas linhas.

O Chatbot é dono da decisão (ponteiro, prazos); aqui só se lê o estado:
- oferta ``aberta`` com ``vendedor_id`` = vendedor com o lead agora;
- ``prazo_em - agora`` = quanto falta para passar ao próximo;
- próximo = primeiro vendedor livre na ordem depois de quem está com o lead
  (o motor pula quem já tem oferta aberta — ``escolher_proximo``).
"""
from __future__ import annotations

from datetime import datetime, timezone


def _instante(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def _fim_telefone(telefone: str | None) -> str:
    digitos = "".join(ch for ch in (telefone or "") if ch.isdigit())
    return digitos[-4:] if len(digitos) >= 4 else digitos


def proximo_livre(
    fila: list[dict], *, depois_de: str, ocupados: set[str]
) -> dict | None:
    """Primeiro vendedor livre na ordem circular depois de ``depois_de``.

    ``None`` = todo mundo ocupado agora; o lead espera uma vaga, não é fim.
    """
    if not fila:
        return None
    inicio = next(
        (i for i, v in enumerate(fila) if v.get("id") == depois_de), -1
    )
    for salto in range(1, len(fila) + 1):
        candidato = fila[(inicio + salto) % len(fila)]
        if candidato.get("id") not in ocupados:
            return candidato
    return None


def formatar_decorrido(segundos: int) -> str:
    segundos = max(int(segundos), 0)
    if segundos < 60:
        return f"há {segundos} s"
    minutos = segundos // 60
    if minutos < 60:
        return f"há {minutos} min"
    return f"há {minutos // 60} h {minutos % 60:02d} min"


def formatar_restante(segundos: int) -> str:
    segundos = max(int(segundos), 0)
    return f"{segundos // 60}:{segundos % 60:02d}"


def montar_agora(
    fila: list[dict], ofertas: list[dict], *, agora: datetime
) -> dict:
    """Monta os cartões do carrossel na ordem da fila.

    Devolve ``{"cartoes": [...], "orfas": [...], "abertas": n}``. Oferta cuja
    ``vendedor_id`` saiu da fila cai em ``orfas``: ela continua viva no motor
    (a remoção é lógica), então some da ordem mas não some da tela.
    """
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    abertas = [o for o in ofertas if o.get("estado") == "aberta"]
    por_vendedor: dict[str, list[dict]] = {}
    for oferta in abertas:
        por_vendedor.setdefault(oferta.get("vendedor_id"), []).append(oferta)
    ocupados = set(por_vendedor)

    cartoes = []
    for posicao, vendedor in enumerate(fila, start=1):
        minhas = por_vendedor.get(vendedor.get("id"), [])
        linhas = []
        for oferta in minhas:
            criado = _instante(oferta.get("criado_em"))
            prazo = _instante(oferta.get("prazo_em"))
            decorrido = int((agora - criado).total_seconds()) if criado else 0
            restante = int((prazo - agora).total_seconds()) if prazo else None
            total = (
                int((prazo - criado).total_seconds())
                if prazo and criado and prazo > criado
                else None
            )
            proximo = proximo_livre(
                fila, depois_de=vendedor.get("id"), ocupados=ocupados
            )
            linhas.append(
                {
                    "id": oferta.get("id"),
                    "telefone_cliente": oferta.get("telefone_cliente") or "",
                    "cliente_curto": _fim_telefone(oferta.get("telefone_cliente")),
                    "criado_em": oferta.get("criado_em"),
                    "prazo_em": oferta.get("prazo_em"),
                    "decorrido_s": max(decorrido, 0),
                    "decorrido": formatar_decorrido(decorrido),
                    "restante_s": restante,
                    "restante": (
                        formatar_restante(restante) if restante is not None else None
                    ),
                    "progresso_pct": (
                        min(max(decorrido / total, 0.0), 1.0) * 100
                        if total
                        else None
                    ),
                    "proximo_nome": proximo.get("nome") if proximo else None,
                }
            )
        if minhas:
            estado = "com_lead"
        elif not abertas and posicao == 1:
            estado = "primeiro"
        else:
            estado = "aguardando"
        cartoes.append(
            {
                "vendedor": vendedor,
                "posicao": posicao,
                "estado": estado,
                "ofertas": linhas,
                "total": len(linhas),
            }
        )

    ids_na_fila = {v.get("id") for v in fila}
    orfas = []
    for oferta in abertas:
        if oferta.get("vendedor_id") in ids_na_fila:
            continue
        criado = _instante(oferta.get("criado_em"))
        prazo = _instante(oferta.get("prazo_em"))
        decorrido = int((agora - criado).total_seconds()) if criado else 0
        restante = int((prazo - agora).total_seconds()) if prazo else None
        orfas.append(
            {
                "id": oferta.get("id"),
                "vendedor_nome": oferta.get("vendedor_nome") or "fora da fila",
                "telefone_cliente": oferta.get("telefone_cliente") or "",
                "cliente_curto": _fim_telefone(oferta.get("telefone_cliente")),
                "criado_em": oferta.get("criado_em"),
                "prazo_em": oferta.get("prazo_em"),
                "decorrido": formatar_decorrido(decorrido),
                "restante": (
                    formatar_restante(restante) if restante is not None else None
                ),
            }
        )
    return {"cartoes": cartoes, "orfas": orfas, "abertas": len(abertas)}
