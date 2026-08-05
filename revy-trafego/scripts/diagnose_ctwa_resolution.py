"""Diagnóstico read-only de CTWA e resolução ad_id -> campaign_id.

Projetado para execução dentro do app2037. Não imprime tokens, IDs completos de
telefone/clique nem corpos brutos. ``--probe-graph`` faz um GET read-only para um
único ad pendente e devolve apenas status e códigos sanitizados da Meta.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import create_engine, text


def normalize_url(value: str) -> str:
    if value.startswith("postgresql+psycopg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://") :]
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://") :]
    return value


def scalar_map(connection, sql: str, params: dict | None = None) -> dict:
    row = connection.execute(text(sql), params or {}).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def graph_probe(revy_connection) -> dict:
    pending = revy_connection.execute(
        text(
            """
            SELECT c.loja_slug, c.ad_id, cfg.token_ciphertext
            FROM meta_ad_campanha c
            JOIN meta_ads_config cfg ON cfg.loja_slug = c.loja_slug
            WHERE c.meta_campaign_id IS NULL
              AND cfg.token_ciphertext IS NOT NULL
            ORDER BY c.ultima_tentativa_em DESC
            LIMIT 1
            """
        )
    ).mappings().first()
    if not pending:
        return {"executed": False, "reason": "no_pending_ad_with_token"}

    sys.path.insert(0, "/srv/revy-trafego")
    from app.cripto import decifrar  # noqa: E402

    token = decifrar(pending["token_ciphertext"])
    response = httpx.get(
        f"https://graph.facebook.com/v21.0/{pending['ad_id']}",
        params={"fields": "campaign{id,name}", "access_token": token},
        timeout=10.0,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else {}
    if not isinstance(error, dict):
        error = {}
    campaign = body.get("campaign") if isinstance(body, dict) else {}
    return {
        "executed": True,
        "ad_id_final": str(pending["ad_id"])[-6:],
        "http_status": response.status_code,
        "campaign_returned": bool(isinstance(campaign, dict) and campaign.get("id")),
        "error_type": error.get("type"),
        "error_code": error.get("code"),
        "error_subcode": error.get("error_subcode"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=36)
    parser.add_argument("--probe-graph", action="store_true")
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, args.hours))
    chatbot = create_engine(normalize_url(os.environ["CHATBOT_DATABASE_URL"]))
    revy = create_engine(os.environ["REVY_TRAFEGO_DATABASE_URL"])

    with chatbot.connect() as connection:
        events = scalar_map(
            connection,
            """
            SELECT COUNT(*) AS ctwa_events,
                   SUM(CASE WHEN meta_ad_id IS NOT NULL THEN 1 ELSE 0 END) AS events_with_ad_id,
                   SUM(CASE WHEN meta_campaign_id IS NOT NULL THEN 1 ELSE 0 END) AS events_with_campaign_id
            FROM ctwa_auditoria
            WHERE criada_em >= :cutoff
            """,
            {"cutoff": cutoff},
        )
        leads = scalar_map(
            connection,
            """
            SELECT COUNT(*) AS meta_ctwa_leads,
                   SUM(CASE WHEN meta_ad_id IS NOT NULL THEN 1 ELSE 0 END) AS leads_with_ad_id,
                   SUM(CASE WHEN meta_campaign_id IS NOT NULL THEN 1 ELSE 0 END) AS leads_with_campaign_id
            FROM leads
            WHERE origem = 'meta_ctwa' AND criada_em >= :cutoff
            """,
            {"cutoff": cutoff},
        )
        latest = [
            {
                "telefone_mascarado": row["telefone_mascarado"],
                "has_ad_id": bool(row["meta_ad_id"]),
                "has_campaign_id": bool(row["meta_campaign_id"]),
                "created_at": str(row["criada_em"]),
            }
            for row in connection.execute(
                text(
                    """
                    SELECT telefone_mascarado, meta_ad_id, meta_campaign_id, criada_em
                    FROM ctwa_auditoria
                    WHERE criada_em >= :cutoff
                    ORDER BY criada_em DESC
                    LIMIT 2
                    """
                ),
                {"cutoff": cutoff},
            ).mappings()
        ]

    with revy.connect() as connection:
        cache = scalar_map(
            connection,
            """
            SELECT COUNT(*) AS distinct_ads_cached,
                   SUM(CASE WHEN meta_campaign_id IS NOT NULL THEN 1 ELSE 0 END) AS resolved,
                   SUM(CASE WHEN erro = 'http_4xx' THEN 1 ELSE 0 END) AS http_4xx
            FROM meta_ad_campanha
            """,
        )
        errors = {
            str(row["erro"] or "none"): int(row["total"])
            for row in connection.execute(
                text(
                    """
                    SELECT erro, COUNT(*) AS total
                    FROM meta_ad_campanha
                    GROUP BY erro
                    ORDER BY erro
                    """
                )
            ).mappings()
        }
        probe = graph_probe(connection) if args.probe_graph else {"executed": False}

    print(
        json.dumps(
            {
                "cutoff_utc": cutoff.isoformat(),
                "events": events,
                "leads": leads,
                "latest_events": latest,
                "resolver_cache": cache,
                "resolver_errors": errors,
                "graph_probe": probe,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
