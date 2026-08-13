"""Diagnóstico read-only dos sinais CTWA que chegaram no webhook.

Responde: o `meta_ad_id` (chave que o Graph precisa para resolver ad -> campanha)
estava chegando? Desde quando? Em que proporção? Quantos leads CTWA ficaram cegos —
e, dos cegos, quantos eram anúncio de verdade e quantos nunca foram anúncio?

Uso dentro do container app2037, que já possui CHATBOT_DATABASE_URL e dependências:

    python /srv/chatbot/scripts/diagnose_ctwa_sinais.py

Não imprime telefone, ctwa_clid nem ids de lead — só contagens e ids de anúncio,
que não são PII.

Limites conhecidos da fonte:
- `ctwa_auditoria` só existe a partir de 2026-07-22 (migration 0011).
- Uma linha só é gravada quando houve ALGUM sinal, a menos que
  CHATBOT_CTWA_AUDIT_ALL=1. Sem essa flag, "sem linha" não distingue
  "mensagem comum" de "clique em anúncio que chegou vazio" — por isso o
  script imprime o estado da flag junto.
"""
from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, "/srv/chatbot")
from app.db import normalizar_database_url  # noqa: E402


POR_SEMANA = text(
    """
    SELECT date_trunc('week', criada_em)::date AS semana,
           count(*)                                        AS eventos,
           count(meta_ad_id)                               AS com_ad_id,
           count(meta_campaign_id)                         AS com_campaign_id,
           count(*) FILTER (WHERE tem_ctwa_clid)           AS com_clid,
           count(ctwa_codigo)                              AS com_codigo,
           count(*) FILTER (
             WHERE meta_ad_id IS NULL
               AND meta_campaign_id IS NULL
               AND ctwa_codigo IS NULL
               AND tem_ctwa_clid IS NOT TRUE
           )                                               AS sem_nada_util,
           count(*) FILTER (WHERE atribuido_lead)          AS atribuidos_na_hora
    FROM ctwa_auditoria
    GROUP BY 1
    ORDER BY 1
    """
)

ORFAS = text(
    """
    SELECT count(*)                                  AS orfas,
           count(meta_ad_id)                         AS orfas_com_ad_id,
           min(criada_em)::date                      AS primeira,
           max(criada_em)::date                      AS ultima
    FROM ctwa_auditoria
    WHERE lead_id IS NULL
    """
)

LEADS = text(
    """
    SELECT count(*)                    AS leads_ctwa,
           count(meta_ad_id)           AS com_ad_id,
           count(meta_campaign_id)     AS com_campaign_id,
           count(ctwa_clid)            AS com_clid,
           count(ctwa_codigo)          AS com_codigo,
           count(*) FILTER (
             WHERE meta_ad_id IS NULL
               AND meta_campaign_id IS NULL
               AND ctwa_clid IS NULL
               AND ctwa_codigo IS NULL
           )                           AS cegos
    FROM leads
    WHERE origem = 'meta_ctwa' OR ctwa_source_type IS NOT NULL
    """
)

POR_SOURCE_TYPE = text(
    """
    SELECT COALESCE(ctwa_source_type, '(sem source_type)') AS tipo,
           count(*)                                        AS leads,
           count(*) FILTER (
             WHERE meta_ad_id IS NULL
               AND meta_campaign_id IS NULL
               AND ctwa_clid IS NULL
               AND ctwa_codigo IS NULL
           )                                               AS cegos,
           count(meta_adset_id)                            AS com_adset
    FROM leads
    WHERE origem = 'meta_ctwa' OR ctwa_source_type IS NOT NULL
    GROUP BY 1
    ORDER BY 2 DESC
    """
)
"""Separa 'nunca foi anúncio' de 'anúncio sem identificador'.

Em 08/08/2026 os 17 leads sem identificador eram 8 de anúncio (`FB_Ads`, `ctwa_ad`)
mais 9 que nunca foram anúncio (`click_to_chat_link`, `message_short_link`,
`global_search_new_chat`) — link direto e busca dentro do WhatsApp. Contar os 17
como perda de atribuição superestima o buraco em mais do que o dobro.

Cuidado ao comparar em código: o valor real vem como `FB_Ads`, com maiúsculas.
"""


# NÃO adicionar aqui uma query que junte leads a auditorias por telefone
# mascarado. A máscara são só os 4 últimos dígitos e a colisão é real: em
# 08/08/2026 ela casou o lead de uma venda com a auditoria de outro cliente.
# Qualquer número saído desse join é ficção. Ver a retratação no plano
# docs/referencia-viva/planos/2026-08-08-ctwa-lead-ad-id-e-roi-venda.md.


def main() -> None:
    engine = create_engine(
        normalizar_database_url(os.environ["CHATBOT_DATABASE_URL"])
    )
    saida: dict[str, object] = {
        "audit_all_ligado": (os.getenv("CHATBOT_CTWA_AUDIT_ALL") or "").strip().lower()
        in {"1", "true", "yes", "on"},
    }
    with engine.connect() as connection:
        for nome, query in (
            ("por_semana", POR_SEMANA),
            ("por_source_type", POR_SOURCE_TYPE),
        ):
            saida[nome] = [
                {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}
                for row in connection.execute(query).mappings()
            ]
        for nome, query in (
            ("auditorias_orfas", ORFAS),
            ("leads", LEADS),
        ):
            linha = connection.execute(query).mappings().first()
            saida[nome] = {
                k: (str(v) if hasattr(v, "isoformat") else v)
                for k, v in (linha or {}).items()
            }
    print(json.dumps(saida, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
