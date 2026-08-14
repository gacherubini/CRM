"""Persistência dos sinais: dedupe, cooldown, resolução automática.

Anti-spam em três regras:
1. mesma (regra, entidade_ref) já aberta → atualiza, não duplica;
2. dispensado NUNCA volta — o dono já disse que não quer;
3. resolvido fecha sozinho e respeita cooldown antes de poder reabrir.

Todo acesso filtra por ``loja_slug``: id de sinal sozinho nunca basta.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.loja.copiloto.sinais import SinalCandidato
from app.models import CopilotoSinal, CopilotoSinalVisto

# "visto" saiu daqui na Fase 4/Task 0: virou copiloto_sinal_visto (por
# pessoa), não mais um estado do sinal. Nenhum código escreve mais
# estado="visto" — a migration 0023 faz backfill das linhas antigas.
ESTADOS_ABERTOS = ("novo",)
COOLDOWN_PADRAO_HORAS = 24


@dataclass
class ResultadoSincronizacao:
    criados: int = 0
    atualizados: int = 0
    resolvidos: int = 0
    em_cooldown: int = 0
    dispensados_ignorados: int = 0

    def resumo(self) -> str:
        return (
            f"criados={self.criados} atualizados={self.atualizados} "
            f"resolvidos={self.resolvidos} cooldown={self.em_cooldown} "
            f"dispensados={self.dispensados_ignorados}"
        )


def invalidar_contagem(loja_slug: str, usuario_id: str | None = None) -> None:
    # notificacoes.py importa contar_sinais_novos daqui: import direto no
    # topo (ou no fim) cicla. O nome precisa existir neste módulo para o
    # monkeypatch dos testes; a implementação real é resolvida na chamada.
    from app.loja.copiloto.notificacoes import invalidar_contagem as _fn

    _fn(loja_slug, usuario_id)


def _chave(regra: str, entidade_ref: str | None) -> tuple[str, str]:
    return (regra, entidade_ref or "")


def _aware(momento: datetime | None) -> datetime | None:
    if momento is None:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def sincronizar_sinais(
    db: Session,
    loja_slug: str,
    candidatos: Iterable[SinalCandidato],
    *,
    agora: datetime | None = None,
    cooldown_horas: int = COOLDOWN_PADRAO_HORAS,
) -> ResultadoSincronizacao:
    """Reconcilia os candidatos desta passada com o que já está gravado."""
    ref = agora or datetime.now(timezone.utc)
    resultado = ResultadoSincronizacao()

    candidatos = list(candidatos)
    por_chave = {_chave(c.regra, c.entidade_ref): c for c in candidatos}

    existentes = (
        db.query(CopilotoSinal).filter(CopilotoSinal.loja_slug == loja_slug).all()
    )
    indice: dict[tuple[str, str], list[CopilotoSinal]] = {}
    for linha in existentes:
        indice.setdefault(_chave(linha.regra, linha.entidade_ref), []).append(linha)

    # 1) Candidatos → cria, atualiza ou ignora.
    for chave, candidato in por_chave.items():
        linhas = indice.get(chave, [])
        aberto = next((l for l in linhas if l.estado in ESTADOS_ABERTOS), None)
        if aberto is not None:
            aberto.severidade = candidato.severidade
            aberto.titulo = candidato.titulo
            aberto.detalhe = candidato.detalhe
            aberto.dados_json = json.dumps(candidato.dados, ensure_ascii=False)
            aberto.acao_sugerida_json = (
                json.dumps(candidato.acao_sugerida, ensure_ascii=False)
                if candidato.acao_sugerida
                else None
            )
            aberto.atualizado_em = ref
            resultado.atualizados += 1
            continue

        if any(l.estado == "dispensado" for l in linhas):
            resultado.dispensados_ignorados += 1
            continue

        resolvidos = [l for l in linhas if l.estado == "resolvido"]
        if resolvidos:
            ultimo = max(
                resolvidos,
                key=lambda l: _aware(l.resolvido_em) or _aware(l.criado_em) or ref,
            )
            marco = _aware(ultimo.resolvido_em) or _aware(ultimo.criado_em)
            if marco is not None and ref - marco < timedelta(hours=cooldown_horas):
                resultado.em_cooldown += 1
                continue

        db.add(
            CopilotoSinal(
                loja_slug=loja_slug,
                regra=candidato.regra,
                entidade_ref=candidato.entidade_ref,
                severidade=candidato.severidade,
                titulo=candidato.titulo,
                detalhe=candidato.detalhe,
                dados_json=json.dumps(candidato.dados, ensure_ascii=False),
                acao_sugerida_json=(
                    json.dumps(candidato.acao_sugerida, ensure_ascii=False)
                    if candidato.acao_sugerida
                    else None
                ),
                estado="novo",
                criado_em=ref,
                atualizado_em=ref,
            )
        )
        resultado.criados += 1

    # 2) Abertos sem candidato correspondente → a condição saiu.
    for chave, linhas in indice.items():
        if chave in por_chave:
            continue
        for linha in linhas:
            if linha.estado not in ESTADOS_ABERTOS:
                continue
            linha.estado = "resolvido"
            linha.resolvido_em = ref
            linha.atualizado_em = ref
            resultado.resolvidos += 1

    db.commit()
    return resultado


def listar_sinais_abertos(
    db: Session,
    loja_slug: str,
    *,
    limite: int = 20,
    usuario_id: str | None = None,
) -> list[CopilotoSinal]:
    """Sinais abertos da loja.

    ``usuario_id`` filtra o endereçamento 1:1 (spec §5.7): com ele, sinal de
    outra pessoa não aparece. Sem ele, devolve tudo — é o comportamento
    legado, mantido para não mudar chamador que ainda não conhece
    destinatário.
    """
    ordem = {"critico": 0, "atencao": 1, "info": 2}
    consulta = db.query(CopilotoSinal).filter(
        CopilotoSinal.loja_slug == loja_slug,
        CopilotoSinal.estado.in_(ESTADOS_ABERTOS),
    )
    if usuario_id is not None:
        consulta = consulta.filter(
            or_(
                CopilotoSinal.destinatario_usuario_id.is_(None),
                CopilotoSinal.destinatario_usuario_id == usuario_id,
            )
        )
    linhas = consulta.all()
    linhas.sort(
        key=lambda s: (
            ordem.get(s.severidade, 9),
            -(_aware(s.criado_em) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        )
    )
    return linhas[: max(1, limite)]


def contar_sinais_novos(db: Session, loja_slug: str, usuario_id: str) -> int:
    """Sinais novos que ESTA pessoa ainda não marcou como visto.

    "Visto" é por pessoa (Fase 4, Task 0): o gestor A marcar visto não pode
    fazer o contador do gestor B cair — por isso o filtro é contra
    ``copiloto_sinal_visto`` de ``usuario_id``, não contra ``estado`` do
    sinal (que é compartilhado pela loja inteira).

    Destinatário: ``NULL`` continua da loja inteira (as 7 regras do
    Copiloto); preenchido só conta para essa pessoa.
    """
    vistos_pelo_usuario = db.query(CopilotoSinalVisto.sinal_id).filter(
        CopilotoSinalVisto.usuario_id == usuario_id
    )
    return (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == loja_slug,
            CopilotoSinal.estado == "novo",
            CopilotoSinal.id.notin_(vistos_pelo_usuario),
            # Sinal endereçado só conta para o destinatário. NULL continua
            # sendo da loja inteira — é o caso das 7 regras do Copiloto.
            or_(
                CopilotoSinal.destinatario_usuario_id.is_(None),
                CopilotoSinal.destinatario_usuario_id == usuario_id,
            ),
        )
        .count()
    )


def _transicionar(
    db: Session, loja_slug: str, sinal_id: str, estado: str
) -> bool:
    sinal = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.id == sinal_id,
            CopilotoSinal.loja_slug == loja_slug,
        )
        .first()
    )
    if sinal is None or sinal.estado not in ESTADOS_ABERTOS:
        return False
    agora_utc = datetime.now(timezone.utc)
    sinal.estado = estado
    sinal.atualizado_em = agora_utc
    if estado == "dispensado":
        sinal.dispensado_em = agora_utc
    db.commit()
    return True


def marcar_visto(db: Session, loja_slug: str, sinal_id: str, usuario_id: str) -> bool:
    """Registra que ESTA pessoa viu o sinal — não muda ``estado`` do sinal.

    Sem `usuario_id` opcional: um default aqui silenciosamente contaria
    "visto" para a pessoa errada e ninguém notaria (é exatamente o bug que
    esta task existe para fechar). ``loja_slug`` é conferido no servidor —
    sinal de outra loja nunca é aceito, mesmo que o chamador erre o escopo.
    """
    sinal = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.id == sinal_id,
            CopilotoSinal.loja_slug == loja_slug,
        )
        .first()
    )
    if sinal is None:
        return False

    ja_visto = (
        db.query(CopilotoSinalVisto)
        .filter(
            CopilotoSinalVisto.sinal_id == sinal_id,
            CopilotoSinalVisto.usuario_id == usuario_id,
        )
        .first()
    )
    if ja_visto is None:
        db.add(CopilotoSinalVisto(sinal_id=sinal_id, usuario_id=usuario_id))
        db.commit()
    return True


def dispensar(db: Session, loja_slug: str, sinal_id: str) -> bool:
    return _transicionar(db, loja_slug, sinal_id, "dispensado")


def criar_sinal_direcionado(
    db: Session,
    loja_slug: str,
    *,
    regra: str,
    destinatario_usuario_id: str,
    entidade_ref: str,
    titulo: str,
    detalhe: str,
    severidade: str = "atencao",
    dados_json: str | None = None,
) -> CopilotoSinal:
    """Cria sinal de UMA pessoa (oferta 1:1 do rodízio, spec §5.7).

    Não passa por ``sincronizar_sinais``: aquilo é para regra determinística
    que roda em lote sobre a loja. Aqui o produtor é um evento único, e o
    destinatário é obrigatório — um sinal de oferta sem dono seria
    exatamente o "sino da loja inteira" que o dono recusou.

    ``entidade_ref`` guarda o id da oferta, nunca o telefone do cliente.
    """
    sinal = CopilotoSinal(
        loja_slug=loja_slug,
        regra=regra,
        entidade_ref=entidade_ref,
        severidade=severidade,
        titulo=titulo,
        detalhe=detalhe,
        dados_json=dados_json,
        estado="novo",
        destinatario_usuario_id=destinatario_usuario_id,
    )
    db.add(sinal)
    db.commit()
    invalidar_contagem(loja_slug, destinatario_usuario_id)
    return sinal


def transferir_sinal(
    db: Session,
    loja_slug: str,
    *,
    entidade_ref: str,
    de_usuario_id: str,
    para_usuario_id: str,
) -> bool:
    """Passa a oferta ao próximo do rodízio: resolve a do anterior, cria a nova.

    Não é um UPDATE do destinatário: o sinal antigo precisa sair do contador
    do vendedor que perdeu a vez, e ``CopilotoSinalVisto`` é por sinal — reusar
    a linha carregaria o "visto" do anterior para o próximo.
    """
    anterior = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == loja_slug,
            CopilotoSinal.entidade_ref == entidade_ref,
            CopilotoSinal.destinatario_usuario_id == de_usuario_id,
            CopilotoSinal.estado.in_(ESTADOS_ABERTOS),
        )
        .first()
    )
    if anterior is None:
        return False

    agora_utc = datetime.now(timezone.utc)
    anterior.estado = "resolvido"
    anterior.resolvido_em = agora_utc
    anterior.atualizado_em = agora_utc

    db.add(
        CopilotoSinal(
            loja_slug=loja_slug,
            regra=anterior.regra,
            entidade_ref=entidade_ref,
            severidade=anterior.severidade,
            titulo=anterior.titulo,
            detalhe=anterior.detalhe,
            dados_json=anterior.dados_json,
            estado="novo",
            destinatario_usuario_id=para_usuario_id,
        )
    )
    db.commit()
    # Os dois: quem perdeu a vez precisa parar de ver agora, não em 45s.
    invalidar_contagem(loja_slug, de_usuario_id)
    invalidar_contagem(loja_slug, para_usuario_id)
    return True
