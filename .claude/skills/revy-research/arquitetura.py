"""Intencao da arquitetura: o que o codigo nao diz de si mesmo. Stdlib apenas.

Escrito a MAO. Muda quando a TOPOLOGIA muda, nao quando nasce uma rota.
Mesmo padrao do TESTES em gerar_mapa.py:39 — dict literal, comentado.

Nao ha YAML aqui de proposito: o Python do dono e 3.9.6, sem pyyaml, e
tomllib so existe no 3.11+.

Fatos verificados em deploy/fly/3vm/ (supervisord.conf, nginx-edge.conf,
fly.*.toml) e nos READMEs dos produtos — ver task-3-brief.md para os
comandos usados. Papeis (`conversa`, `banco`, `veiculos`, `venda`,
`estrutura`, `vitrine`) sao os mesmos substantivos da AGENTS.md secao 5.
"""
from __future__ import annotations

NOS: dict[str, dict] = {
    "chatbot-api": {
        "titulo": "Chatbot API",
        "papel": "conversa",
        "vm": "app2037",
        "decisoes": [
            "2026-08-13-whatsapp-dois-modos-sem-coexistencia.md",
            "2026-08-25-agente-por-loja-o-que-ficou-de-fora.md",
        ],
    },
    "motor-simulacao": {
        "titulo": "Motor de Simulação",
        "papel": "banco",
        "vm": "app2037",          # a API; o worker Playwright vive na motor2037
        "spof": True,
        "spof_porque": (
            "Playwright single-flight e o driver engole o clique que falha — ver "
            "learnings/2026-08-23-driver-playwright-engole-o-clique-que-falha.md"
        ),
    },
    "estoque-api": {
        "titulo": "Estoque API",
        "papel": "veiculos",
        "vm": "app2037",
        "termo": "fonte unica de verdade dos veiculos",
    },
    "portal-gestao": {
        "titulo": "Revy Loja",
        "papel": "venda",
        "vm": "app2037",
        "decisoes": [
            "2026-08-07-vendedor-pode-confirmar-venda.md",
            "2026-08-16-financeiro-sem-rateio.md",
            "2026-08-11-copiloto-nao-e-o-seller-ai.md",
            "2026-08-07-treze-recusas-de-ux.md",
        ],
    },
    "revy-trafego": {
        "titulo": "Revy Control",
        "papel": "estrutura",
        "vm": "app2037",
        "decisoes": [
            "2026-08-07-treze-recusas-de-ux.md",
        ],
    },
    "catalogo-publico": {
        "titulo": "Catálogo Público",
        "papel": "vitrine",
        "vm": "app2037",
    },
}

# O que cruzamentos.py NAO infere: ALVO_POR_CLIENTE (cruzamentos.py) so cobre
# clientes HTTP sincronos de portal-gestao e chatbot-api. Estas arestas sao
# outbox assincrona ou clientes que o AST-scan nao cobre (catalogo-publico e
# revy-trafego nao tem entrada em ALVO_POR_CLIENTE).
ARESTAS: list[dict] = [
    {"de": "portal-gestao", "para": "revy-trafego",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    {"de": "estoque-api", "para": "chatbot-api",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    {"de": "revy-trafego", "para": "estoque-api",
     "protocolo": "http", "sincrono": True},
    {"de": "catalogo-publico", "para": "estoque-api",
     "protocolo": "http", "sincrono": True},
    {"de": "catalogo-publico", "para": "chatbot-api",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    {"de": "catalogo-publico", "para": "portal-gestao",
     "protocolo": "http", "sincrono": True},
]

VMS: dict[str, dict] = {
    "app2037": {
        "tipo": "fly-machine",
        "contem": ["catalogo-publico", "chatbot-api", "estoque-api",
                   "motor-simulacao", "portal-gestao", "revy-trafego"],
        "nota": (
            "nginx-edge:8080 na frente, supervisord por tras. Roteia "
            "/webhook /v1 /health -> chatbot:8001, /public/ -> estoque:8002, "
            "/catalogo/ -> catalogo:8003, / (default) -> portal:9000, "
            "/trafego/ -> revy-trafego:9010, /healthz -> healthz:8099. "
            "Motor:8004 nao tem rota no edge, so MOTOR_URL interno."
        ),
    },
    "motor2037": {
        "tipo": "fly-machine",
        "contem": [],
        "nota": (
            "worker Playwright/RPA do Motor de Simulacao — a API do Motor "
            "mora em app2037, esta VM so roda o navegador headless que "
            "acessa banco. Nao contem produto porque nao serve HTTP de produto."
        ),
    },
    "n8n2037": {
        "tipo": "fly-machine",
        "contem": [],
        "nota": (
            "imagem n8nio/n8n oficial, orquestra n8n/workflow-ai-nao-salvos.json. "
            "Sempre ligado (auto_stop_machines=false) — decisao "
            "2026-07-14-evolution-e-n8n-nao-dormem.md. Nao e produto Revy, "
            "por isso nao vira No."
        ),
    },
    "evolution2037": {
        "tipo": "fly-machine",
        "contem": [],
        "nota": (
            "imagem evoapicloud/evolution-api, sessao WhatsApp (Baileys). "
            "Sempre ligado pela mesma decisao 2026-07-14-evolution-e-n8n-nao-dormem.md "
            "— a sessao cai se a maquina suspender."
        ),
    },
    "suite-pg": {
        "tipo": "postgres",
        "contem": ["portal-gestao", "revy-trafego"],
        "nota": (
            "banco `revy`, schema por produto, desde o corte de 16/08/2026 "
            "(PORTAL_DATABASE_URL e REVY_TRAFEGO_DATABASE_URL viraram secrets "
            "em fly.app.toml). Os demais produtos mantem banco e migrations "
            "proprios fora do suite-pg."
        ),
    },
}

FLUXOS: dict[str, dict] = {
    "whatsapp-simulacao": {
        "titulo": "WhatsApp → simulação",
        "passos": [
            {"no": "evolution2037", "faz": "recebe a mensagem"},
            {"no": "n8n2037", "faz": "roteia", "protocolo": "webhook"},
            {"no": "chatbot-api", "faz": "interpreta e decide"},
            {"no": "motor-simulacao", "faz": "simula no banco", "sincrono": False},
        ],
        "invariante": "a parcela nao volta ao cliente pelo bot",
    },
    "venda-outbox": {
        "titulo": "Venda confirmada → Control",
        "passos": [
            {"no": "portal-gestao", "faz": "vendedor confirma a venda em Revy Loja"},
            {"no": "portal-gestao", "faz": "grava o evento na outbox "
             "(revy_trafego_outbox.py)", "protocolo": "outbox", "sincrono": False},
            {"no": "revy-trafego", "faz": "recebe e projeta a venda no Control",
             "protocolo": "outbox", "sincrono": False},
        ],
        "invariante": (
            "o vendedor lanca a venda sozinho — dono/gerente/vendedor podem "
            "confirmar, sem revisao extra — decisao "
            "2026-08-07-vendedor-pode-confirmar-venda.md"
        ),
    },
    "publicacao-veiculo": {
        "titulo": "Publicação de veículo → vitrine",
        "passos": [
            {"no": "estoque-api", "faz": "dono/gerente publica o veiculo "
             "(disponivel + publicado)"},
            {"no": "estoque-api", "faz": "emite vehicle.* na outbox HMAC",
             "protocolo": "outbox", "sincrono": False},
            {"no": "catalogo-publico", "faz": "consome GET /public/v1/... "
             "e mostra na vitrine", "protocolo": "http"},
        ],
        "invariante": (
            "custo e dado interno nunca saem na API publica — GET /public/v1 "
            "so devolve disponivel + publicado, sem custo (nem para operador)"
        ),
    },
    "login": {
        "titulo": "Login — Pessoa Revy",
        "passos": [
            {"no": "portal-gestao", "faz": "autentica local (SessionMiddleware) "
             "contra o schema proprio no banco revy"},
            {"no": "revy-trafego", "faz": "autentica local (SessionMiddleware), "
             "schema proprio no mesmo banco revy"},
        ],
        "invariante": (
            "nao ha SSO entre Loja e Control — Pessoa Revy e uma identidade "
            "canonica so no conceito (CONTEXT.md), mas cada produto autentica "
            "contra o seu proprio schema no banco revy compartilhado (suite-pg), "
            "sem misturar as permissoes das duas superficies"
        ),
    },
}
