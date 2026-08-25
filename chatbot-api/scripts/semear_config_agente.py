#!/usr/bin/env python3
"""Semeia a config do agente de uma loja que já atendia antes da feature.

Existe por causa do teste de aceite do spec §11: *"a vitor motos entra com uma
config que reproduz o prompt de hoje. Se o bot mudar de jeito de falar no dia do
deploy, é bug, não feature."*

O card 2 tira `vitor motos` e `limeira-sp` do `systemMessage` do n8n e passa a
buscar esse texto em `GET /v1/agente/config`. Loja sem config publicada cai no
`CAMPOS_PADRAO_REVY`, que diz *"você atende os clientes da a loja"* — correto
como rede de segurança, péssimo como estreia. Então a config da loja que já
estava no ar entra **antes** de o workflow subir.

Idempotente: rodar de novo republica o mesmo texto e cria mais uma versão no
histórico; não apaga nada.

    cd chatbot-api
    .venv/bin/python -m scripts.semear_config_agente moto-center        # macOS
    .\\.venv\\Scripts\\python.exe -m scripts.semear_config_agente moto-center

Em produção, dentro do `app2037`. **A variável é `DATABASE_URL`, não
`CHATBOT_DATABASE_URL`**: `app/db.py` lê a primeira, e quem traduz uma na outra é
o entrypoint, para os processos do bundle. Num shell avulso de `fly ssh console`
essa tradução não aconteceu, e passar só a segunda faz o engine resolver
`sqlite:///./chatbot.db` — o mesmo "o alembic mente" que este script alerta.
Conferido em 25/08: com só `CHATBOT_DATABASE_URL` definido, `alembic current`
respondeu `SQLiteImpl`.

    fly ssh console -a app2037 -C "sh -lc 'cd /srv/chatbot && \\
      DATABASE_URL=\\$CHATBOT_DATABASE_URL python -m scripts.semear_config_agente moto-center'"
"""
from __future__ import annotations

import os
import sys

from app.agente_prompt import CamposAgente

# Os campos que reproduzem o prompt que a vitor motos tem hoje no n8n. Cada
# valor aqui corresponde a uma frase que saiu do `systemMessage` — é isso que
# `tests/test_agente_prompt_migrado_do_n8n.py` guarda, frase por frase.
CAMPOS_VITOR_MOTOS = CamposAgente(
    nome_loja="vitor motos",
    cidade="Limeira",
    uf="SP",
    endereco_completo=False,
    entrega="cortesia para todo o estado de são paulo",
    # Sem grade: o prompt de hoje não fala em horário, e inventar um calaria o
    # bot fora dele.
    horario={},
    nome_agente="",
    assume_ia="nunca",
    tom="direto",
    tratamento="primeiro_nome",
    escrita="minusculas",
    emoji="nunca",
    tamanho_resposta="curto",
    expressoes=["certinho", "beleza"],
    nunca_diga=[],
    faq=[],
    # Confirmado pelo dono em 25/08: financiamento, a vista e troca; consignacao
    # NAO. O gerador diz ao cliente o que a loja nao faz, entao esta linha vira
    # afirmacao no WhatsApp — nao e palpite a partir do prompt antigo.
    oferece=["financiamento", "a_vista", "troca"],
    fotos="so_quando_pedir",
    sem_moto_anuncio="segura",
    handoff=["quando_pedir"],
    cita_vendedor=False,
    followup_ativo=True,
    agente_ativo=True,
    so_horario_comercial=False,
    instrucoes="",
)

# A loja do piloto está gravada como `moto-center` — slug de exemplo herdado do
# plano de deploy de julho — enquanto o nome que o cliente ouve, e que o
# `systemMessage` de hoje diz, é "vitor motos". Conferido no Postgres de produção
# em 25/08: `moto-center` é a única loja com conversa (1.235) e instância
# Evolution, e é para ela que o `CHATBOT_API_TOKEN` do workflow do Modo 1 aponta.
# Semear por `vitor-motos` parava o passo 2 do rollout com "loja não existe".
CAMPOS_POR_SLUG = {
    "moto-center": CAMPOS_VITOR_MOTOS,
    # Continua aceito para o dia em que a linha for renomeada.
    "vitor-motos": CAMPOS_VITOR_MOTOS,
}


def _banco_errado() -> str | None:
    """Motivo para parar antes de escrever, ou ``None`` quando o banco confere.

    `app/db.py` lê `DATABASE_URL`. Quem passa só `CHATBOT_DATABASE_URL` — que é o
    nome do secret, e por isso o palpite natural — escreve num SQLite de mentira
    sem perceber. Recusar aqui é barato; descobrir depois é a loja estreando com
    o prompt padrão.
    """
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
    if len(argv) != 2 or argv[1] not in CAMPOS_POR_SLUG:
        print(f"uso: {argv[0]} <{'|'.join(CAMPOS_POR_SLUG)}>", file=sys.stderr)
        return 2
    slug = argv[1]

    motivo = _banco_errado()
    if motivo is not None:
        print(f"erro: {motivo}", file=sys.stderr)
        return 2

    from app import agente_config, models_db
    from app import db as db_module

    db = db_module.SessionLocal()
    try:
        loja = (
            db.query(models_db.Loja).filter(models_db.Loja.slug == slug).one_or_none()
        )
        if loja is None:
            existentes = sorted(s for (s,) in db.query(models_db.Loja.slug).all())
            print(
                f"loja {slug!r} não existe neste banco. "
                f"lojas presentes: {', '.join(existentes) or '(nenhuma)'}",
                file=sys.stderr,
            )
            return 1
        agente_config.salvar_rascunho(
            db, loja.id, CAMPOS_POR_SLUG[slug], autor="semear_config_agente"
        )
        versao = agente_config.publicar(db, loja.id, autor="semear_config_agente")
    finally:
        db.close()

    print(f"publicado para {slug}: versão {versao.id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
