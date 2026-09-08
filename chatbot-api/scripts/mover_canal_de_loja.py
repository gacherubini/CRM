#!/usr/bin/env python3
"""Move um canal Cloud de uma loja para outra (spec §5.1).

Um chip só atende as duas fases do rollout do Modo 2: o número entra pelo
embedded signup na loja `teste`, é exercitado ali, e depois vira para a loja
real. O popup está fechado para a segunda vez — `evolution_instance` é UNIQUE
global e o elo 1 recusa número já cadastrado —, então esta é a única porta.

Não é rota HTTP de propósito: expor isso na API daria a qualquer loja um caminho
para roubar o número de outra, que é exatamente o que a UNIQUE global impede.

    cd chatbot-api
    .venv/bin/python -m scripts.mover_canal_de_loja \\
      --phone-number-id 123 --para-slug loja-do-amigo --dry-run
"""
from __future__ import annotations

import argparse
import sys


def _montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mover_canal_de_loja")
    parser.add_argument("--phone-number-id", required=True)
    parser.add_argument("--para-slug", required=True)
    parser.add_argument("--apagar-dados-da-origem", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _apagar_trafego_da_origem(db, models_db, loja_id: str) -> dict[str, int]:
    """Apaga o tráfego do período de teste, na ordem que as FKs permitem.

    Sem isto a troca de ``loja_id`` não basta: ``Conversa`` é única por
    ``(canal_id, telefone)`` e ``_get_or_create_conversa`` devolve a conversa
    achada sem conferir ``loja_id``. Como o ``canal_id`` não muda na virada, os
    telefones que participaram do teste — o do dono, o do lojista, os dos
    vendedores — voltariam a cair na conversa da loja de origem.

    ``fila_vendedor`` fica: é cadastro, não tráfego, e serve o próximo teste.
    """
    apagados: dict[str, int] = {}
    for modelo in (
        models_db.Mensagem,
        models_db.Conversa,
        models_db.Consentimento,
        models_db.CtwaAuditoria,
        models_db.CatalogAttribution,
        models_db.OfertaLead,
        models_db.Lead,
        models_db.RodizioPonteiro,
    ):
        apagados[modelo.__tablename__] = (
            db.query(modelo)
            .filter(modelo.loja_id == loja_id)
            .delete(synchronize_session=False)
        )
    return apagados


def _banco_errado() -> str | None:
    """Motivo para parar antes de ler, ou ``None`` quando o banco confere.

    `app/db.py` lê `DATABASE_URL`. Quem passa só `CHATBOT_DATABASE_URL` — que é o
    nome do secret, e por isso o palpite natural — fala com o SQLite do
    container. Aqui isso apareceria como "canal não encontrado", com o canal
    intacto em produção e o operador procurando defeito no lugar errado.

    Cópia deliberada do mesmo guarda em ``scripts/semear_config_agente.py``:
    são dois scripts de operação avulsa e a armadilha é a mesma.
    """
    import os

    from app import db as db_module

    if db_module.DATABASE_URL.startswith("sqlite") and os.getenv(
        "CHATBOT_DATABASE_URL"
    ):
        return (
            "CHATBOT_DATABASE_URL está definido, mas o engine resolveu "
            f"{db_module.DATABASE_URL!r} — app/db.py lê DATABASE_URL. "
            "Rode com DATABASE_URL=$CHATBOT_DATABASE_URL."
        )
    return None


def main(argv: list[str]) -> int:
    args = _montar_parser().parse_args(argv[1:])

    motivo = _banco_errado()
    if motivo is not None:
        print(f"erro: {motivo}", file=sys.stderr)
        return 2

    from app import db as db_module
    from app import models_db
    from app.provisioning import allows_processing

    db = db_module.SessionLocal()
    try:
        canal = (
            db.query(models_db.WhatsAppCanal)
            .filter(models_db.WhatsAppCanal.evolution_instance == args.phone_number_id)
            .first()
        )
        if canal is None:
            print(
                f"nenhum canal com phone_number_id {args.phone_number_id!r}",
                file=sys.stderr,
            )
            return 1

        destino = (
            db.query(models_db.Loja)
            .filter(models_db.Loja.slug == args.para_slug)
            .first()
        )
        if destino is None:
            existentes = sorted(s for (s,) in db.query(models_db.Loja.slug).all())
            print(
                f"loja {args.para_slug!r} não existe neste banco. "
                f"lojas presentes: {', '.join(existentes) or '(nenhuma)'}",
                file=sys.stderr,
            )
            return 1

        # Modo 2 é fail-closed: sem projeção `ativa` o canal chega mudo à loja
        # nova, e o sintoma (número que não responde) não aponta para cá.
        if not allows_processing(db, destino.id):
            print(
                f"loja {args.para_slug!r} não está projetada como ativa; "
                "libere no Control antes de mover",
                file=sys.stderr,
            )
            return 1

        # Oferta viva aponta para `fila_vendedor` da origem. Mover agora deixa o
        # rodízio da loja nova despachando lead para vendedor que não é dela.
        abertas = (
            db.query(models_db.OfertaLead)
            .filter(
                models_db.OfertaLead.loja_id == canal.loja_id,
                models_db.OfertaLead.estado == "aberta",
            )
            .count()
        )
        if abertas:
            print(
                f"a loja de origem tem {abertas} oferta(s) aberta(s); "
                "espere o rodízio fechar antes de mover",
                file=sys.stderr,
            )
            return 1

        origem_id = canal.loja_id
        if args.apagar_dados_da_origem:
            for tabela, quantas in _apagar_trafego_da_origem(
                db, models_db, origem_id
            ).items():
                if quantas:
                    print(f"apagadas {quantas} linha(s) de {tabela}")

        canal.loja_id = destino.id
        db.flush()

        print(
            f"canal {canal.id} ({args.phone_number_id}): "
            f"{origem_id} -> {destino.id} [{args.para_slug}]"
        )
        if args.dry_run:
            db.rollback()
            print("--dry-run: nada foi gravado")
            return 0
        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
