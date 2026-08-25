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
    .venv/bin/python -m scripts.semear_config_agente vitor-motos        # macOS
    .\\.venv\\Scripts\\python.exe -m scripts.semear_config_agente vitor-motos

Em produção, com o banco certo (senão o alembic/engine responde SQLite e mente):

    CHATBOT_DATABASE_URL=postgres://... .venv/bin/python -m scripts.semear_config_agente vitor-motos
"""
from __future__ import annotations

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

CAMPOS_POR_SLUG = {"vitor-motos": CAMPOS_VITOR_MOTOS}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in CAMPOS_POR_SLUG:
        print(f"uso: {argv[0]} <{'|'.join(CAMPOS_POR_SLUG)}>", file=sys.stderr)
        return 2
    slug = argv[1]

    from app import agente_config, models_db
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        loja = (
            db.query(models_db.Loja).filter(models_db.Loja.slug == slug).one_or_none()
        )
        if loja is None:
            print(f"loja {slug!r} não existe neste banco", file=sys.stderr)
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
