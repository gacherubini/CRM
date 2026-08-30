"""Intencao da arquitetura: o que o codigo nao diz de si mesmo. Stdlib apenas.

Escrito a MAO. Muda quando a TOPOLOGIA muda, nao quando nasce uma rota.
Mesmo padrao do TESTES em gerar_mapa.py:39 — dict literal, comentado.

Nao ha YAML aqui de proposito: o Python do dono e 3.9.6, sem pyyaml, e
tomllib so existe no 3.11+.

Fatos verificados em deploy/fly/3vm/ (supervisord.conf, nginx-edge.conf,
fly.*.toml) e nos READMEs dos produtos — ver task-3-brief.md para os
comandos usados. Papeis (`conversa`, `banco`, `veiculos`, `venda`,
`estrutura`, `vitrine`) sao os mesmos substantivos da AGENTS.md secao 5.

`dentro` e RECURSIVO (arq_modelo.carregar desce sem profundidade fixa). Todo
sub-no abaixo veio de `ls <produto>/app/` de verdade — nao ha diretorio nem
arquivo inventado. `modulo`, quando presente, e o prefixo de caminho que
arq_modelo usa pra puxar as entradas do `_frescor.json` pra dentro daquela
caixa; varios sub-nos ficam sem `modulo` (grupo de dominio, nao arquivo) ou
com um `modulo` que hoje nao casa nenhuma entrada do frescor (o extrator so
pega rota/worker/modelo/flag/migration — um helper puro fica sem entrada, e
isso e esperado, nao bug).
"""
from __future__ import annotations

# Task 9: o inventario passa a ter duas vistas. `rota`/`worker`/`flag` sao
# comportamento em producao; `template` fica aqui por decisao do dono, mesmo
# sendo apresentacao — nao e dado persistido, e ele nao quis mais uma vista
# so pra isso. `modelo`/`migration` sao o outro angulo: o que persiste, e
# onde. As duas vistas juntas tem que cobrir toda secao que o extrator emite
# (arq_modelo.filtrar avisa no stdout se aparecer uma secao nova que nao
# caia em nenhuma das duas — nunca falha calado).
SECOES_ARQUITETURA: frozenset[str] = frozenset({"rota", "worker", "flag", "template"})
SECOES_SCHEMA: frozenset[str] = frozenset({"modelo", "migration"})

NOS: dict[str, dict] = {
    "chatbot-api": {
        "titulo": "Chatbot API",
        "papel": "conversa",
        "vm": "app2037",
        # Task 13 — a camada de COMPONENTE (C4 nivel 3), escrita a mao.
        #
        # Antes daqui os sub-nos eram rotulo de agrupamento ("Workers
        # assincronos") e entrar no produto mostrava `config.py`, `main.py` e
        # uma pasta: arvore de arquivo, nao desenho. Cada caixa abaixo e uma
        # UNIDADE DE RESPONSABILIDADE que foi lida no codigo; o `termo` traz o
        # `arquivo:linha` que prova a existencia dela.
        #
        # Dez componentes de propósito: abaixo de seis nao conta a historia do
        # produto, acima de dez volta a ser a lista de arquivos com outro nome.
        # Tres coisas reais ficaram DE FORA por esse teto, e nao por nao
        # existirem: `app/operacao.py` (cadastro de veiculo por WhatsApp, E5 —
        # citado no termo de `integracoes.estoque`), `app/audio.py` +
        # `app/vehicle_photo.py` (midia efemera do inbound) e `app/hardening.py`
        # (protecoes de borda). Entram quando alguem precisar de seta pra elas.
        #
        # O que MUDOU de lugar em relacao ao no antigo, e por que:
        # - `workers.rodizio` virou o componente `atendimento`: o worker e' so
        #   o relogio de uma regra (fila, oferta, handoff) que mora em
        #   app/rodizio.py, app/oferta_*.py e app/handoff_gatilhos.py. Junto do
        #   dominio ele conta a historia; na sacola "workers" ele nao contava.
        # - `workers.notificacoes-outbox` foi pra `workers` ainda, mas quem
        #   ESCREVE na fila (`simulacao`) agora e uma caixa propria — sem isso
        #   nao havia entre o que desenhar a seta do outbox.
        # - `canais.cloud`/`canais.baileys` trocaram o `modulo` de prefixo
        #   generico (`app/meta_`, `app/whatsapp_`) pelo arquivo que de fato e'
        #   o canal; `app/whatsapp_` engolia o `whatsapp_outbound.py`, que e'
        #   saida, nao canal.
        "dentro": {
            "borda": {
                "titulo": "Borda HTTP",
                "papel": "conversa",
                # As 64 rotas do produto vivem todas em app/main.py — nao ha
                # router por dominio aqui — entao esta caixa e' a superficie
                # HTTP inteira. `_lifespan` (main.py:82) tambem e' daqui: e' o
                # que sobe os workers de fundo.
                "termo": "webhook Modo 1 e Modo 2, /v1 do n8n; lifespan em main.py:82",
                "modulo": "app/main.py",
            },
            "conversa": {
                "titulo": "Conversa e lead",
                "papel": "conversa",
                # servico.registrar_mensagem (servico.py) e' o unico caminho de
                # escrita de mensagem: n8n e LLM nunca escrevem no banco.
                "termo": "ingestão idempotente, bot_ativo por conversa, lead e CTWA",
                "modulo": "app/servico.py",
            },
            "canais": {
                "titulo": "Canais WhatsApp",
                "papel": "canal",
                "termo": "Cloud API (Meta) e Baileys (Evolution), credenciais por loja",
                "decisoes": ["2026-08-13-whatsapp-dois-modos-sem-coexistencia.md"],
                "dentro": {
                    "cloud": {"titulo": "Canal Cloud (Meta)", "papel": "canal",
                              # phone_number_id/waba_id/template por loja; o
                              # inbound e a assinatura ficam em meta_webhook.py
                              # e o embedded signup em onboarding_cloud.py.
                              "termo": "phone_number_id e waba_id por loja (cloud_canal.py:1)",
                              "modulo": "app/cloud_canal.py"},
                    "baileys": {"titulo": "Canal Baileys (Evolution)", "papel": "canal",
                                # channels.py e' o registro em `whatsapp_canais`;
                                # whatsapp_provider.py e' o port de instancia/QR.
                                "termo": "instância, QR e estado (whatsapp_provider.py:1)",
                                "modulo": "app/whatsapp_provider.py"},
                    "credenciais": {"titulo": "Segredo do canal", "papel": "canal",
                                    "termo": "cifra em repouso, fail-closed (segredo_canal.py:1)",
                                    "modulo": "app/segredo_canal.py"},
                    # app/config.py entra aqui porque as DUAS unicas flags do
                    # produto sao de canal: CHATBOT_WHATSAPP_MODO2_ENABLED
                    # (config.py:146) e MULTI_WHATSAPP_ENABLED (config.py:149).
                    # Sem dono, config.py voltava a ser uma caixa automatica de
                    # arquivo ao lado dos componentes.
                    "modo": {"titulo": "Modo do WhatsApp", "papel": "canal",
                             "termo": "MODO2 e MULTI_WHATSAPP (config.py:146,149)",
                             "modulo": "app/config.py"},
                },
            },
            "agente": {
                "titulo": "Agente por loja",
                "papel": "IA",
                # Nao ha IA neste produto: o agente roda no n8n. O que mora
                # aqui e' o prompt versionado que ele consome (README).
                "termo": "prompt versionado que o n8n consome; a IA não é daqui",
                "modulo": "app/agente_",
                "decisoes": ["2026-08-25-agente-por-loja-o-que-ficou-de-fora.md"],
            },
            "atendimento": {
                "titulo": "Rodízio, oferta e handoff",
                "papel": "operacao",
                # `app/rodizio` cobre rodizio.py (a regra pura) e rodizio_job.py
                # (o relogio). A oferta e o gatilho moram ao lado, em
                # oferta_envio.py:49, oferta_inbound.py:30 e
                # handoff_gatilhos.py:14 — mesmo componente, arquivos vizinhos.
                "termo": "fila do vendedor, prazo de 10 min, clique trava o lead",
                "modulo": "app/rodizio",
            },
            "simulacao": {
                "titulo": "Simulação humana",
                "papel": "operacao",
                # Os gates (maioridade, CNH, dedupe) e o alerta ao grupo de
                # estoque. Grava em `notificacoes_operacionais`
                # (solicitacoes_simulacao.py:712) — a fila que o worker drena.
                "termo": "gates e alerta ao grupo; grava o outbox (linha 712)",
                "modulo": "app/solicitacoes_simulacao.py",
            },
            "saida": {
                "titulo": "Saída WhatsApp",
                "papel": "canal",
                # Um port, dois adapters: Evolution (Modo 1, linha 76) e Graph
                # (Modo 2, linha 221). `outbound_para_loja` (linha 366) escolhe
                # POR LOJA — trocar o singleton derrubaria o Modo 1 das outras.
                "termo": "Evolution ou Graph, escolhido por loja (linha 366)",
                "modulo": "app/whatsapp_outbound.py",
            },
            "integracoes": {
                "titulo": "Clientes HTTP de outros produtos",
                "papel": "integracao",
                # Veiculo so o Estoque tem; banco so o Motor fala (AGENTS.md 2).
                "termo": "veículo no Estoque, parcela no Motor — nunca local",
                "dentro": {
                    "estoque": {"titulo": "Cliente da Estoque API", "papel": "veiculos",
                                # buscar: /public/v1 (inventory.py:210). Escrita:
                                # POST /v1/veiculos, usado pelo cadastro por
                                # WhatsApp em operacao.py:556 e vehicle_photo.py:254.
                                "termo": "GET /public/v1 e POST /v1/veiculos (inventory.py:210)",
                                "modulo": "app/inventory.py"},
                    "motor": {"titulo": "Cliente do Motor", "papel": "banco",
                              # Provider plugavel: none/mock/http. So o http bate
                              # no Motor de verdade (simulation.py:112).
                              "termo": "POST /v1/simulacoes, provider plugável (linha 112)",
                              "modulo": "app/simulation.py"},
                },
            },
            "provisionamento": {
                "titulo": "Projeção do Control",
                "papel": "estrutura",
                # O gate de suspensao de loja e' backend, nao item de menu
                # (AGENTS.md secao 5): allows_processing / is_store_operational /
                # allows_outbound_whatsapp sao consultados por servico.py:952,
                # rodizio.py:70, main.py:1701 e solicitacoes_simulacao.py:483.
                "termo": "gate de loja suspensa, projeção monotônica local",
                "modulo": "app/provisioning.py",
            },
            "workers": {
                "titulo": "Workers de fundo",
                "papel": "fundo",
                # O timer e' do produto, nao Wait do n8n (spec 5.3). As tres
                # threads sobem no lifespan (main.py:93 e main.py:106); o
                # ciclo de vida em si mora em modo2_workers.py:85.
                "termo": "thread daemon por worker, subida no lifespan (main.py:82)",
                "modulo": "app/modo2_workers.py",
                "dentro": {
                    "followup": {"titulo": "Follow-up do silêncio", "papel": "worker",
                                 "termo": "dois toques, 30 min e 1 h (followup_job.py:12)",
                                 "modulo": "app/followup_job.py"},
                    "notificacoes-outbox": {"titulo": "Drenador do outbox",
                                             "papel": "worker",
                                             "termo": "reprocessa alerta pending/failed "
                                                      "(notificacoes_outbox_job.py:71)",
                                             "modulo": "app/notificacoes_outbox_job.py"},
                    "cloud-retry": {"titulo": "Retomada do inbound Cloud",
                                    "papel": "worker",
                                    # A outra metade do "responde 200 e processa
                                    # depois": o corpo cru guardado pela rota
                                    # volta pra processar_evento_cloud.
                                    "termo": "reprocessa cloud_evento_falho, teto 5 "
                                             "(cloud_retry.py:28)",
                                    "modulo": "app/cloud_retry.py"},
                },
            },
        },
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
        "dentro": {
            "bancos": {
                "titulo": "Drivers bancários (Playwright)",
                "papel": "banco",
                "termo": "amortizacao, base, bradesco, fontecred, pan, santander, mock",
                "modulo": "app/motor/",
            },
            "worker": {
                "titulo": "Worker assíncrono",
                "papel": "fundo",
                "modulo": "app/worker.py",
            },
        },
    },
    "estoque-api": {
        "titulo": "Estoque API",
        "papel": "veiculos",
        "vm": "app2037",
        "termo": "fonte unica de verdade dos veiculos",
        "dentro": {
            "midia": {"titulo": "Mídia", "papel": "veiculos", "modulo": "app/media.py"},
            "outbox": {"titulo": "Outbox (vehicle.*)", "papel": "fundo",
                       "modulo": "app/outbox.py"},
            "worker": {"titulo": "Worker de entrega/limpeza", "papel": "fundo",
                       "modulo": "app/worker.py"},
            "provisioning": {"titulo": "Projeção do Control", "papel": "estrutura",
                              "modulo": "app/provisioning.py"},
            "admin": {"titulo": "Admin HTMX", "papel": "operacao",
                      "modulo": "app/admin"},
        },
    },
    "portal-gestao": {
        "titulo": "Revy Loja",
        "papel": "venda",
        "vm": "app2037",
        "decisoes": [
            "2026-08-07-vendedor-pode-confirmar-venda.md",
            "2026-08-16-financeiro-sem-rateio.md",
            "2026-08-07-treze-recusas-de-ux.md",
        ],
        "dentro": {
            "loja": {"titulo": "Revy Loja (tela)", "papel": "venda",
                     "modulo": "app/loja/"},
            "web": {"titulo": "Rotas HTTP", "papel": "venda", "modulo": "app/web/"},
            "clients": {"titulo": "Clientes HTTP de outros produtos",
                        "papel": "integracao", "modulo": "app/clients/"},
            "conversions": {"titulo": "Conversões Meta (CAPI)", "papel": "integracao",
                             "modulo": "app/conversions/"},
            "outbox-control": {"titulo": "Outbox → Control", "papel": "fundo",
                                "modulo": "app/revy_trafego_outbox"},
            "copiloto": {"titulo": "Copiloto de Vendas", "papel": "IA",
                         "modulo": "app/copiloto_",
                         "decisoes": ["2026-08-11-copiloto-nao-e-o-seller-ai.md"]},
        },
    },
    "revy-trafego": {
        "titulo": "Revy Control",
        "papel": "estrutura",
        "vm": "app2037",
        "decisoes": [
            "2026-08-07-treze-recusas-de-ux.md",
        ],
        "dentro": {
            "control": {
                "titulo": "Núcleo do Control",
                "papel": "estrutura",
                "modulo": "app/control/",
                "dentro": {
                    "google-ads": {"titulo": "Google Ads", "papel": "integracao",
                                   "modulo": "app/control/google_ads"},
                    "provisionamento": {"titulo": "Provisionamento → Estoque/Loja",
                                        "papel": "estrutura",
                                        "modulo": "app/control/provisioning"},
                },
            },
            "web": {"titulo": "Telas do Control", "papel": "estrutura",
                    "modulo": "app/web/"},
            "clients": {"titulo": "Clientes HTTP de outros produtos",
                        "papel": "integracao", "modulo": "app/clients/"},
            "email": {"titulo": "E-mail transacional", "papel": "estrutura",
                      "modulo": "app/email/"},
        },
    },
    "catalogo-publico": {
        "titulo": "Catálogo Público",
        "papel": "vitrine",
        "vm": "app2037",
        "dentro": {
            "outbox": {"titulo": "Outbox (interest_clicked)", "papel": "fundo",
                       "modulo": "app/outbox.py"},
            "pixel": {"titulo": "Pixel Meta (via Portal)", "papel": "integracao",
                      "modulo": "app/pixel.py"},
            "provider": {"titulo": "Cliente da Estoque API", "papel": "veiculos",
                         "modulo": "app/provider.py"},
        },
    },
}

# O que cruzamentos.py NAO infere: ALVO_POR_CLIENTE (cruzamentos.py) so cobre
# clientes HTTP sincronos de portal-gestao e chatbot-api. Estas arestas sao
# outbox assincrona ou clientes que o AST-scan nao cobre (catalogo-publico e
# revy-trafego nao tem entrada em ALVO_POR_CLIENTE).
ARESTAS: list[dict] = [
    # As duas que substituem a contencao errada em suite-pg. Desde o corte de
    # 16/08/2026 os dois vivem no banco `revy`, com schema por produto.
    {"de": "portal-gestao", "para": "suite-pg",
     "protocolo": "tcp", "sincrono": True, "retry": False},
    {"de": "revy-trafego", "para": "suite-pg",
     "protocolo": "tcp", "sincrono": True, "retry": False},
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

# Task 13 — as arestas ENTRE OS COMPONENTES do Chatbot API (C4 nivel 3).
#
# ATENCAO, ler antes de mexer: esta lista NAO esta ligada em `ARESTAS` de
# proposito. Hoje ela nao pode estar: `arq_modelo.carregar` so aceita ponta de
# aresta que seja chave de NOS de RAIZ ou de VMS (a checagem em torno de
# `conhecidos_e_vms`), entao qualquer chave de sub-no levanta `ReferenciaMorta`
# e derruba o gerador inteiro. `arq_render._resolver_produto` JA resolveria
# todas elas — o casamento por sufixo alcanca sub-no em qualquer profundidade
# (verificado: "chatbot-api.workers.cloud-retry" acha
# "app2037.chatbot-api.workers.cloud-retry"). O que falta e' so a validacao de
# carga aceitar o mesmo enderecamento, e `arq_modelo.py` e' de outro dono.
#
# Segundo bloqueio, do mesmo tamanho: `arq_modelo.filtrar`/`_podar` remove todo
# no escrito a mao que nao tenha `entradas` proprias. Como o inventario do
# Chatbot so tem rota (todas em app/main.py), worker (4 arquivos) e flag
# (config.py, main.py), SEIS dos dez componentes acima nao chegam a virar caixa
# na vista Arquitetura — e por isso, e nao por falta de intencao escrita, que
# entrar no produto ainda mostra pouca coisa. Foi essa regra que apagou
# "Canal Cloud (Meta)" e "Agente por loja", que ja estavam escritos aqui desde
# a Task 3 e nunca apareceram no HTML.
#
# Toda linha abaixo saiu de codigo LIDO, com o arquivo:linha no comentario.
# Nada aqui e' suposicao: relacao que nao foi encontrada no codigo ficou de
# fora (ver o relatorio da Task 13).
#
# Vocabulario de `protocolo`, de proposito curto: "chamada" (import + chamada
# no mesmo processo), "outbox" (uma grava numa tabela, a outra consome depois)
# e "timer" (thread periodica que aciona a outra).
ARESTAS_INTERNAS: list[dict] = [
    # --- a borda HTTP e' o unico ponto de entrada, entao ela fala com quase tudo
    # main.py:809 (/webhook/mensagem, Modo 1) e main.py:726 (inbound Cloud):
    # servico.registrar_mensagem e' o unico caminho de escrita de mensagem.
    {"de": "chatbot-api.borda", "para": "chatbot-api.conversa",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:42 importa loja_id_do_phone_number_id/phone_number_id_da_loja de
    # app/cloud_canal.py; usado em main.py:692 pra achar a loja do inbound.
    {"de": "chatbot-api.borda", "para": "chatbot-api.canais.cloud",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:1397 campos_publicados, :1399 prompt_publicado, :1464 publicar.
    {"de": "chatbot-api.borda", "para": "chatbot-api.agente",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:787 processar_clique (oferta_inbound.py:30) e main.py:2265
    # disparar_handoff (handoff_gatilhos.py:14).
    {"de": "chatbot-api.borda", "para": "chatbot-api.atendimento",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:2155 solicitacoes_simulacao.solicitar_simulacao_humana (:460).
    {"de": "chatbot-api.borda", "para": "chatbot-api.simulacao",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:44 importa acender_digitando/outbound_para_loja; usados em
    # main.py:747, :789, :1025 e :2205.
    {"de": "chatbot-api.borda", "para": "chatbot-api.saida",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:1592 provider.buscar -> inventory.py:210 GET /public/v1/....
    {"de": "chatbot-api.borda", "para": "chatbot-api.integracoes.estoque",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # main.py:1735 e :1773 Depends(get_simulation_provider) -> simulation.py:112
    # POST {MOTOR_URL}/v1/simulacoes.
    {"de": "chatbot-api.borda", "para": "chatbot-api.integracoes.motor",
     "protocolo": "chamada", "sincrono": True, "retry": False},

    # --- a fila que o brief pedia: a rota grava, o worker consome
    # main.py:615 registrar_evento_falho grava a linha `cloud_evento_falho`
    # (cloud_retry.py:31) porque a Meta ja recebeu 200 e nao reentrega.
    {"de": "chatbot-api.borda", "para": "chatbot-api.workers.cloud-retry",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    # e a volta: cloud_retry.py:75 importa app.main.processar_evento_cloud e
    # chama em :113 — o reprocesso reentra pela mesma funcao da rota.
    {"de": "chatbot-api.workers.cloud-retry", "para": "chatbot-api.borda",
     "protocolo": "chamada", "sincrono": True, "retry": False},

    # --- os workers acionam o dominio
    # modo2_workers.py:101 importa RodizioWorker e :111 chama run_once — o
    # prazo de 10 min do rodizio tem relogio proprio, nao Wait do n8n.
    {"de": "chatbot-api.workers", "para": "chatbot-api.atendimento",
     "protocolo": "timer", "sincrono": False, "retry": False},
    # followup_job.py:69 e :112 leem agente_config.campos_publicados(...)
    # .followup_ativo: o cutucao so sai se a loja ligou no formulario.
    {"de": "chatbot-api.workers.followup", "para": "chatbot-api.agente",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # followup_job.py:126 outbound.send_text; o outbound vem de
    # modo2_workers.py:119 (_OutboundPorLoja sobre outbound_para_loja).
    {"de": "chatbot-api.workers.followup", "para": "chatbot-api.saida",
     "protocolo": "chamada", "sincrono": True, "retry": False},

    # --- atendimento
    # rodizio_job.py:102 enviar_oferta(..., outbound) e :127 send_text;
    # oferta_envio.py:49 e handoff_gatilhos.py:55,:62,:64 idem.
    {"de": "chatbot-api.atendimento", "para": "chatbot-api.saida",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # rodizio.py:16 importa allows_processing e :70 recusa abrir oferta pra
    # loja nao operacional — a suspensao e' gate de backend (AGENTS.md 5).
    {"de": "chatbot-api.atendimento", "para": "chatbot-api.provisionamento",
     "protocolo": "chamada", "sincrono": True, "retry": False},

    # --- simulacao humana
    # solicitacoes_simulacao.py:712 cria a linha NotificacaoOperacional; o
    # drenador (notificacoes_outbox_job.py:16 e :73) chama processar_pendentes
    # (solicitacoes_simulacao.py:826) e reprocessa pending/failed.
    {"de": "chatbot-api.simulacao", "para": "chatbot-api.workers.notificacoes-outbox",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    # solicitacoes_simulacao.py:754 e :759 disparar_handoff quando a loja e'
    # Modo 2 — sem isso a simulacao ficava pronta e ninguem chamava vendedor.
    {"de": "chatbot-api.simulacao", "para": "chatbot-api.atendimento",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # solicitacoes_simulacao.py:38 importa get_whatsapp_outbound e :123 manda o
    # alerta ao grupo de estoque.
    {"de": "chatbot-api.simulacao", "para": "chatbot-api.saida",
     "protocolo": "chamada", "sincrono": True, "retry": False},

    # --- conversa
    # servico.py:947/:952 is_store_operational e :1253/:1255,:1443/:1445,
    # :1761/:1764 allows_outbound_whatsapp.
    {"de": "chatbot-api.conversa", "para": "chatbot-api.provisionamento",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # servico.py:1719 importa outbound_para_loja e :1721 envia o texto do
    # atendimento humano vindo da Loja.
    {"de": "chatbot-api.conversa", "para": "chatbot-api.saida",
     "protocolo": "chamada", "sincrono": True, "retry": False},
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
        # Task 11: o rotulo da forma interna (retangulo — nao e terceiro,
        # e' codigo do proprio Motor) sai literal da nota acima.
        "roda": "worker Playwright · RPA",
        "terceiro": False,
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
        "roda": "n8n · orquestração",
        "terceiro": True,
    },
    "evolution2037": {
        "tipo": "fly-machine",
        "contem": [],
        "nota": (
            "imagem evoapicloud/evolution-api, sessao WhatsApp (Baileys). "
            "Sempre ligado pela mesma decisao 2026-07-14-evolution-e-n8n-nao-dormem.md "
            "— a sessao cai se a maquina suspender."
        ),
        "roda": "evolution-api · sessão WhatsApp",
        "terceiro": True,
    },
    "suite-pg": {
        "tipo": "postgres",
        # Vazio de proposito: Loja e Control NAO rodam dentro do Postgres, eles
        # FALAM com ele. Modelar isso como contencao fazia a arvore inteira dos
        # dois ser desenhada duas vezes. Virou aresta tcp em ARESTAS.
        "contem": [],
        "nota": (
            "banco `revy`, schema por produto, desde o corte de 16/08/2026 "
            "(PORTAL_DATABASE_URL e REVY_TRAFEGO_DATABASE_URL viraram secrets "
            "em fly.app.toml). Os demais produtos mantem banco e migrations "
            "proprios fora do suite-pg."
        ),
    },
}

# Grupos de topo da vista Schema (Task 9): reusa o dataclass Vm de
# arq_modelo.py:52 porque a forma e identica a VMS (chave, tipo, contem,
# nota) — so troca "maquina Fly" por "banco". `catalogo-publico` NAO aparece
# aqui de proposito: ele nao tem `modelo` nem `migration`, entao some da
# vista Schema (arq_modelo.filtrar poda o no de raiz sem conteudo).
BANCOS: dict[str, dict] = {
    "suite-pg": {
        "tipo": "postgres",
        "contem": ["portal-gestao", "revy-trafego"],
        "nota": (
            "banco `revy`, um schema por produto. PORTAL_DATABASE_URL "
            "(portal-gestao/app/config.py:116) e REVY_TRAFEGO_DATABASE_URL "
            "(revy-trafego/app/config.py:17) apontam para o mesmo Postgres "
            "desde o corte de 16/08/2026. Dividir banco e o que faz um OOM "
            "derrubar Loja e Control juntos."
        ),
    },
    "chatbot-db": {
        "tipo": "banco-proprio",
        "contem": ["chatbot-api"],
        "nota": "DATABASE_URL propria (chatbot-api/app/db.py:14), default sqlite:///./chatbot.db",
    },
    "estoque-db": {
        "tipo": "banco-proprio",
        "contem": ["estoque-api"],
        "nota": "DATABASE_URL propria (estoque-api/app/db.py:14), default sqlite:///./estoque.db",
    },
    "motor-db": {
        "tipo": "banco-proprio",
        "contem": ["motor-simulacao"],
        "nota": "DATABASE_URL propria (motor-simulacao/app/db.py:18), default sqlite:///./motor.db",
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
