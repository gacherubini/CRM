"""Diagnóstico read-only e sanitizado do destino de alertas de simulação.

Uso dentro do container app2037, que já possui CHATBOT_DATABASE_URL e dependências.
Não imprime números de telefone, credenciais nem o JID completo do grupo.
"""
from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, "/srv/chatbot")
from app.db import normalizar_database_url  # noqa: E402


QUERY = text(
    """
    SELECT l.id AS loja_id,
           g.grupo_jid,
           g.grupo_nome,
           COUNT(n.id) FILTER (WHERE n.ativo IS TRUE) AS ativos,
           COUNT(n.id) FILTER (
             WHERE n.ativo IS TRUE AND lower(n.papel) = 'vendedor'
           ) AS vendedores,
           COUNT(n.id) FILTER (
             WHERE n.ativo IS TRUE AND lower(n.papel) = 'dono'
           ) AS donos
    FROM lojas l
    LEFT JOIN grupos_estoque g ON g.loja_id = l.id
    LEFT JOIN numeros_autorizados n ON n.loja_id = l.id
    GROUP BY l.id, g.grupo_jid, g.grupo_nome
    ORDER BY l.id
    """
)


def main() -> None:
    engine = create_engine(
        normalizar_database_url(os.environ["CHATBOT_DATABASE_URL"])
    )
    with engine.connect() as connection:
        output = []
        for row in connection.execute(QUERY).mappings():
            jid = row["grupo_jid"] or ""
            output.append(
                {
                    "loja_final": str(row["loja_id"])[-6:],
                    "grupo_configurado": bool(jid),
                    "grupo_jid_final": jid[-12:] if jid else None,
                    "grupo_nome": row["grupo_nome"],
                    "numeros_ativos": row["ativos"],
                    "vendedores_ativos": row["vendedores"],
                    "donos_ativos": row["donos"],
                }
            )
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
