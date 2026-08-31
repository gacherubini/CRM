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
SECOES_ARQUITETURA: frozenset[str] = frozenset({"worker", "flag", "template"})

# Deliberadamente fora das duas vistas — nao e' secao desconhecida, e' secao
# DISPENSADA, e a diferenca importa: desconhecida avisa no stdout, dispensada
# nao.
#
# `rota` saiu por decisao do dono em 30/08: 407 das 816 entradas do inventario
# sao rota, e so o Chatbot tem 64. Elas viravam uma parede de fichas em tres
# colunas dentro de "Borda HTTP", que sozinha ocupava quase metade do produto
# e espremia todos os outros componentes ate o titulo nao caber. E o que a
# parede respondia — QUAIS sao as rotas — nao e' o que esta pagina existe pra
# responder: aqui a pergunta e' como as partes se falam.
#
# O dado nao se perde: `mapa/<produto>.md` continua listando toda rota com
# `arquivo:linha`, e o `_frescor.json` continua sendo a fonte dos dois.
SECOES_DISPENSADAS: frozenset[str] = frozenset({"rota"})
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
        # ---------------------------------------------------------------
        # DECISAO DO DONO, 30/08 — NAO RE-PROPOR "entra / decide / sai".
        #
        # O agrupamento por estagio do fluxo foi implementado, visto no
        # navegador e RECUSADO. Ele nao estava errado no dado (19 das 20
        # arestas internas andam no mesmo sentido, o produto e' mesmo um
        # pipeline) — o dono simplesmente nao le a arquitetura dele por
        # estagio abstrato. Gaveta boa aqui e' a que nomeia uma coisa
        # concreta; "Configuracao do canal" ficou justamente por isso.
        #
        # O que SOBROU daquela rodada, e vale manter:
        # - `config` saiu de dentro de `canais`. O grupo antigo misturava os
        #   adapters (Cloud, Baileys) com o que e' so configuracao (segredo,
        #   modo) — duas coisas diferentes na mesma caixa.
        #
        # Grupo aqui existe quando ele diz algo que a caixa sozinha nao diz:
        # `workers` = as tres threads que sobem no MESMO lifespan;
        # `integracoes` = produto de fora, nunca dado local; `canais` = os
        # dois adapters de WhatsApp; `config` = o que o canal precisa saber.
        # Componente que nao se encaixa em nenhuma dessas frases fica solto,
        # no nivel do produto — e' a maioria deles, de proposito.
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
        # - quem ESCREVE na fila do outbox (`simulacao`) virou caixa propria —
        #   sem isso nao havia entre o que desenhar a seta do outbox.
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
            "canais": {
                "titulo": "Canais WhatsApp",
                "papel": "canal",
                # So os ADAPTERS. O que e' configuracao (segredo, modo) mudou
                # para `config` em 30/08 — ficar tudo junto aqui fazia a caixa
                # responder duas perguntas diferentes.
                "termo": "Cloud API (Meta) e Baileys (Evolution)",
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
                },
            },
            "config": {
                "titulo": "Configuração do canal",
                "papel": "canal",
                # Nao e' caminho de mensagem: nada PASSA por aqui. E' o que o
                # canal precisa saber pra funcionar. Era a metade de baixo de
                # "Canais WhatsApp" ate 30/08.
                "termo": "fora do caminho da mensagem",
                "dentro": {
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
            "workers": {
                "titulo": "Workers de fundo",
                "papel": "fundo",
                # O timer e' do produto, nao Wait do n8n (spec 5.3). As tres
                # threads sobem no lifespan (main.py:93 e main.py:106); o
                # ciclo de vida em si mora em modo2_workers.py:85. E' isso que
                # o grupo diz e a caixa sozinha nao diria — por isso ele fica.
                "termo": "thread daemon por worker, subida no lifespan (main.py:82)",
                "modulo": "app/modo2_workers.py",
                "dentro": {
                    "followup": {"titulo": "Follow-up do silêncio", "papel": "worker",
                                 "termo": "dois toques, 30 min e 1 h (followup_job.py:12)",
                                 "modulo": "app/followup_job.py"},
                    "notificacoes-outbox": {"titulo": "Drenador do outbox",
                                             "papel": "worker",
                                             "termo": "reprocessa alerta pending/failed (linha 71)",
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
        # Camada de componente escrita a mao (30/08), do mesmo molde do Estoque.
        # Antes daqui eram duas caixas, e uma delas (`bancos`) era a LISTA DE
        # BANCOS: o produto inteiro — idempotencia, fila, lease, teto de
        # browser, credencial cifrada — nao aparecia.
        #
        # Cada caixa saiu da tabela "Onde editar" do README e foi conferida no
        # codigo. As arestas sairam de import real.
        #
        # SEGREDO BANCARIO SO VIVE AQUI (AGENTS.md secao 5). Por isso
        # `credenciais` e' caixa propria e recebe seta de quatro lugares: e' a
        # unica porta pro segredo em claro, e nenhum termo aqui carrega valor
        # de env.
        #
        # Ficaram de fora por serem infraestrutura, e nao responsabilidade:
        # `app/models_db.py` + `app/db.py` (ORM), `app/config.py`,
        # `app/auth.py`, `app/validadores.py`, `app/observabilidade.py`,
        # `app/provisioning.py` e `app/cli.py`. Entram quando alguem precisar
        # de seta pra elas.
        "dentro": {
            "borda": {
                "titulo": "Borda HTTP",
                "papel": "banco",
                # O contrato publico inteiro em 359 linhas: criar (:181),
                # consultar, cancelar (:345), e o CRUD de credencial por
                # provedor (:112). A criacao responde 202 com `recebida` — a
                # execucao e' de outro processo, possivelmente de outra VM.
                "termo": "/v1/simulacoes e credenciais (main.py:181,112)",
                "modulo": "app/main.py",
            },
            "simulacao": {
                "titulo": "Domínio da simulação",
                "papel": "banco",
                # Idempotencia real, nao "ignora repetido": mesma chave com o
                # MESMO hash de payload devolve o mesmo id; com payload
                # diferente levanta ErroIdempotencia (:106) e a borda responde
                # 409. O ciclo e' recebida -> processando -> concluida |
                # parcial | falhou | aguardando_intervencao.
                "termo": "idempotência por hash de payload (servico.py:103,106)",
                "modulo": "app/servico.py",
            },
            "fila": {
                "titulo": "Fan-out por provedor",
                "papel": "banco",
                # Uma tarefa por provedor pedido (:47), cada uma ja marcada com
                # `tipo_driver` (:26) — e' esse campo que decide se a tarefa
                # precisa de um slot de browser na motor2037 ou roda no
                # app2037 mesmo. Parcial e' status normal: um banco responde,
                # outro falha.
                "termo": "uma tarefa por provedor (fanout.py:26,47)",
                "modulo": "app/fanout.py",
            },
            "orquestrador": {
                "titulo": "Slots e wake das Machines",
                "papel": "fundo",
                # O teto de 2 browsers simultaneos (:116) e' decisao B+D de
                # captcha/IP, e conta o que ja esta EM VOO, nao so o wake deste
                # tick — subir esse teto piora o scoring de IP e derruba os
                # logins. Quem fala com a Machines API e' `WorkerLifecycle`
                # (lifecycle.py); sem FLY_AUTOSCALE_ENABLED isto e' no-op.
                "termo": "teto de 2 browsers, wake Fly (orquestrador.py:77,116)",
                "modulo": "app/orquestrador.py",
            },
            "worker": {
                "titulo": "Worker e execução do job",
                "papel": "fundo",
                # Reserva com lease (processamento.py:162) e devolve a fila o
                # que expirou depois de uma queda (:118) — por isso o worker
                # pode morrer no meio sem perder o job.
                # ARMADILHA: com MOTOR_WORKER_PROVEDOR definido o modo
                # on-demand liga sozinho e o processo sai `exit 0` no idle
                # (worker.py:96). No Fly isso e' certo (a Machine para e o
                # orquestrador reacorda); FORA do Fly e' o processo morrendo
                # sem ninguem pra reiniciar — use IDLE_STOP_SECONDS=0.
                "termo": "lease (processamento.py:162), exit 0 (worker.py:96)",
                "modulo": "app/worker.py",
            },
            "registro": {
                "titulo": "Contrato e seleção de driver",
                "papel": "banco",
                # E' aqui que mora a armadilha numero um do README: o contrato
                # NAO muda entre mock e real. `resolver_drivers` (:185) escolhe
                # pela credencial existir, e sem credencial NAO cai no mock
                # silencioso. A taxonomia de erro (ErroTransitorio :25,
                # RejeicaoNegocio :31, IntervencaoNecessaria :37) e' o que
                # todo driver promete devolver — e' o que faz o cliente ver so
                # `codigo_erro`, nunca mensagem tecnica ou pagina bancaria.
                # `providers.py:66` e' o catalogo; `mock.py` e a amortizacao
                # Price fecham o lado ficticio.
                "termo": "resolve driver, sem mock mudo (drivers.py:185,25)",
                "modulo": "app/motor/drivers.py",
            },
            "api-parceiro": {
                "titulo": "Driver de API (Pan)",
                "papel": "banco",
                # Pan e BV tem API de parceiro; Santander, Bradesco e Fontecred
                # nao — por isso o RPA daqueles tres e' permanente, e nao
                # remendo. Este caminho NAO consome slot do teto de browser
                # (api_base.py:28), entao e' o unico banco que escala sem
                # esbarrar no captcha de IP. `_pan_dispatch` (drivers.py:162)
                # e' quem decide entre este e o `pan_portal` do RPA.
                "termo": "API de parceiro, sem slot (pan.py:11; api_base.py:28)",
                "modulo": "app/motor/pan.py",
            },
            "credenciais": {
                "titulo": "Credenciais cifradas",
                "papel": "banco",
                # A chave e' MOTOR_ENCRYPTION_KEY e ela tem que ser a MESMA no
                # app2037 e no motor2037 — divergiu, credencial nao abre. O
                # Portal e' so BFF: cifra e envia; decifrar so acontece aqui.
                # `indice_cego` (cripto.py:37) permite buscar por CPF sem
                # guardar o CPF em claro. Toda escrita passa por auditoria
                # (credenciais.py:101).
                "termo": "cifra e índice cego (cripto.py:29,37)",
                "modulo": "app/credenciais.py",
            },
            "rpa": {
                "titulo": "RPA Playwright (motor2037)",
                "papel": "banco",
                # O grupo diz o que a caixa sozinha nao diz: estes sobem
                # Chromium DE VERDADE, num slot da motor2037, sob o teto de 2
                # simultaneos — e e' so aqui que o captcha e o scoring de IP
                # existem. `pan` ficou de fora de proposito: e' API de
                # parceiro, nao consome slot, e meter ele aqui faria a gaveta
                # mentir.
                "termo": "Chromium real, sob o teto de 2 slots",
                "dentro": {
                    "bancos": {
                        "titulo": "Drivers por banco",
                        "papel": "banco",
                        # Quatro drivers de browser. Cada um busca o proprio
                        # segredo direto em `credenciais` na hora de logar
                        # (santander.py:424, bradesco.py:376, fontecred.py:403,
                        # pan_portal.py:378) — nao ha segredo viajando no
                        # payload da tarefa.
                        "termo": "santander, bradesco, fontecred, pan_portal",
                        "modulo": "app/motor/",
                    },
                    "base": {
                        "titulo": "Base RPA e sessão quente",
                        "papel": "banco",
                        # `storage_state` por (cliente, provedor) e' o que
                        # mantem a sessao quente entre jobs; hoje ela renasce
                        # em IP de datacenter, que e' justamente a hipotese do
                        # card do worker em IP residencial.
                        "termo": "storage_state por loja (sessao_browser.py:26,57)",
                        "modulo": "app/motor/playwright_base.py",
                    },
                },
            },
        },
    },
    "estoque-api": {
        "titulo": "Estoque API",
        "papel": "veiculos",
        "vm": "app2037",
        "termo": "fonte única de verdade dos veículos",
        # Camada de componente escrita a mao (30/08), no mesmo molde do
        # Chatbot. Antes daqui as caixas eram PASTA (`app/admin`), nao
        # responsabilidade, e nao havia aresta interna nenhuma: entrar no
        # produto mostrava arvore de arquivo.
        #
        # Cada caixa saiu da tabela "Onde editar" do README do produto e foi
        # conferida no codigo — o `termo` traz o `arquivo:linha` que prova.
        # As arestas sairam de IMPORT REAL (quem importa quem, e quantas
        # vezes usa), nao de intuicao.
        #
        # Sem grupo, de proposito: nenhum conjunto destes nove diz algo que a
        # caixa sozinha nao diga. `outbox` + `worker` chegou a ser candidato,
        # mas o worker faz duas coisas (entrega o outbox E roda a limpeza de
        # midia), entao a gaveta mentiria.
        "dentro": {
            "borda": {
                "titulo": "Borda HTTP",
                "papel": "veiculos",
                # O corte publico e' de borda, nao de dominio: `/public/v1`
                # escapa do rate limit privado (main.py:48) e `_pode_ver_custo`
                # (main.py:139) decide se o custo sai. Custo fora da API
                # publica e' armadilha declarada no README.
                "termo": "/v1 privada, /public/v1 sem custo, health (main.py:48,139)",
                "modulo": "app/main.py",
            },
            "veiculos": {
                "titulo": "Veículos, publicação e CSV",
                "papel": "veiculos",
                # O dominio inteiro num modulo so. Reservar (535) e vender
                # (558) sao transicoes de estado que geram evento; a
                # importacao CSV adivinha o delimitador (773).
                "termo": "cadastro, publicação, venda, CSV (servico.py:535,558,773)",
                "modulo": "app/servico.py",
            },
            "midia": {
                "titulo": "Mídia",
                "papel": "veiculos",
                # O banco guarda so URL e metadado — nunca base64 nem path
                # local (README). A limpeza de orfas falha FECHADO: sem
                # ESTOQUE_MEDIA_PUBLIC_BASE_URL nao remove arquivo nenhum.
                "termo": "assinatura, escrita atômica, órfãs (media.py:35,87,180)",
                "modulo": "app/media.py",
            },
            "outbox": {
                "titulo": "Outbox (vehicle.*)",
                "papel": "fundo",
                # Entrega NAO e' garantida para sempre: descarta apos 5
                # tentativas (outbox.py:19). O receptor precisa validar o HMAC
                # e deduplicar por X-Evento-Id.
                "termo": "HMAC, backoff, desiste em 5 (outbox.py:19,27,83)",
                "modulo": "app/outbox.py",
            },
            "worker": {
                "titulo": "Worker de entrega e limpeza",
                "papel": "fundo",
                # Duas tarefas no mesmo laco. A limpeza periodica nunca
                # propaga a propria falha (worker.py:37) — derrubar a entrega
                # do outbox por causa de uma varredura de arquivo seria pior.
                "termo": "entrega o outbox e limpa mídia (worker.py:21,37)",
                "modulo": "app/worker.py",
            },
            "credenciais": {
                "titulo": "Credenciais e papéis",
                "papel": "estrutura",
                # auth.py e cripto.py nao tem prefixo comum, entao `modulo`
                # aponta so o primeiro e o termo carrega o outro. Quem cifra o
                # segredo do webhook e' `cripto.cifrar` (cripto.py:20); quem
                # decifra na hora de assinar e' o outbox.
                "termo": "token e papel (auth.py:16); cifra (cripto.py:20)",
                "modulo": "app/auth.py",
            },
            "admin": {
                "titulo": "Admin HTMX",
                "papel": "operacao",
                "termo": "painel de operação, sessão própria (admin.py:37,73)",
                "modulo": "app/admin",
            },
            "provisionamento": {
                "titulo": "Projeção do Control",
                "papel": "estrutura",
                # Mesmo padrao do Chatbot: gate de backend, fail-closed quando
                # a projecao da loja nao existe (provisioning.py:30).
                "termo": "gate de loja e módulo, fail-closed (provisioning.py:30)",
                "modulo": "app/provisioning.py",
            },
            "cli": {
                "titulo": "Comandos de operação",
                "papel": "operacao",
                "termo": "criar-loja, credencial, webhook, limpar-mídias (cli.py:11)",
                "modulo": "app/cli.py",
            },
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
        # A vitrine e' o produto mais fechado do monorepo, e isso e' desenho:
        # ela consome SOMENTE o contrato HTTP publico da Estoque
        # (`/public/v1`, provider.py:58) e guarda so os proprios eventos de
        # interesse, em SQLite dela (events.py:39). Nao ha banco compartilhado,
        # nao ha import de `app` alheio, e o dado do veiculo nao persiste aqui.
        #
        # Camada de componente escrita a mao (30/08). Antes daqui eram tres
        # caixas-arquivo (`outbox`, `pixel`, `provider`) e nenhuma aresta: os
        # 625 linhas do `main.py`, o SQLite de interesse e o gate do Control
        # simplesmente nao apareciam.
        #
        # Sem grupo: nenhum conjunto destes sete diz algo que a caixa sozinha
        # nao diga. `contratos` chegou a ser candidato a virar campo do
        # `provider`, mas ele e' o formato que a Estoque PROMETE — quando o
        # contrato muda, muda ali, e nao no cliente.
        #
        # Ficaram de fora por serem infraestrutura, nao responsabilidade:
        # `app/config.py` (leitura de env) e `app/templates/` (Jinja, inclusive
        # `templates/marca/`). Entram se alguem precisar de seta pra elas.
        "dentro": {
            "borda": {
                "titulo": "Vitrine HTTP",
                "papel": "vitrine",
                # A superficie inteira sao 3 telas publicas (:348 lista,
                # :460 ficha, :525 interesse) mais health/version. O middleware
                # de :105 poe CSP/nosniff/DENY em toda resposta, e o cookie
                # anonimo `catalog_visitor` nasce aqui (visitor_id, :232) —
                # nao ha login nesta vitrine.
                "termo": "lista, ficha e CSP (main.py:105,348,460)",
                "modulo": "app/main.py",
            },
            "interesse": {
                "titulo": "Clique de interesse",
                "papel": "vitrine",
                # O clique e a linha da outbox entram na MESMA transacao
                # (events.py:163 abre, :166 e :194 inserem): ou o interesse e'
                # gravado com o evento pendente, ou nada foi gravado. O payload
                # nao leva telefone nem o id anonimo do visitante — o que sai
                # daqui pro cliente e' o `public_ref`, no texto do wa.me.
                "termo": "clique e evento na mesma transação (events.py:163,194)",
                "modulo": "app/events.py",
            },
            "outbox": {
                "titulo": "Outbox (catalog.interest_clicked)",
                "papel": "fundo",
                # Mesma promessa da outbox da Estoque, e a mesma armadilha:
                # entrega NAO e' pra sempre, descarta em 5 tentativas
                # (outbox.py:31,60). O `event_id` e' estavel entre tentativas,
                # entao o Chatbot deduplica por Idempotency-Key.
                "termo": "backoff, desiste em 5 (outbox.py:31,60,73)",
                "modulo": "app/outbox.py",
            },
            "provider": {
                "titulo": "Cliente da Estoque",
                "papel": "veiculos",
                # A unica porta pra dado de veiculo. `/public/v1` nao devolve
                # custo (decisao de borda da Estoque), entao a vitrine nao tem
                # como vazar preco de compra nem que queira.
                "termo": "só o /public/v1 da Estoque (provider.py:32,58)",
                "modulo": "app/provider.py",
            },
            "contratos": {
                "titulo": "Contrato da vitrine",
                "papel": "veiculos",
                # O formato que a Estoque promete, escrito deste lado. Quando
                # o contrato HTTP muda, o erro aparece aqui na validacao — nao
                # no meio de um template.
                "termo": "Store, Vehicle, VehiclePage (contracts.py:6,14,47)",
                "modulo": "app/contracts.py",
            },
            "pixel": {
                "titulo": "Pixel Meta (via Portal)",
                "papel": "integracao",
                # O Pixel ID vem do Portal, nao do env: quem salvou foi o dono,
                # em Trafego. O env so e' fallback. Cache com TTL curto quando
                # a consulta FALHA (pixel.py:83), pra nao congelar o erro.
                # O token CAPI nunca passa por aqui — isso e' do Portal.
                "termo": "Pixel por loja, do Portal (pixel.py:66,97)",
                "modulo": "app/pixel.py",
            },
            "provisionamento": {
                "titulo": "Projeção do Control",
                "papel": "estrutura",
                # ATENCAO: aqui o gate e' fail-OPEN (provisioning.py:107), ao
                # contrario do da Estoque e do Chatbot, que sao fail-closed.
                # Sem projecao de loja a vitrine continua abrindo — foi escolha
                # do cutover, pra loja nao sumir da internet se o Control
                # estiver mudo. Com projecao, `state != ativa` esconde a loja.
                "termo": "gate de loja, fail-open (provisioning.py:99,107)",
                "modulo": "app/provisioning.py",
            },
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

# Posicoes ajustadas a mao, em DESLOCAMENTO (dx, dy) a partir de onde o
# empacotamento pos a caixa — nunca coordenada absoluta. Ver
# `arq_layout._aplicar_posicoes`.
#
# Como preencher: abra `arquitetura.html`, arraste as caixas ate ficar do
# jeito que voce quer, clique em "exportar" no canto e cole o bloco aqui.
# O botao "automatico" na mesma barra joga fora o que voce moveu.
#
# Por que deslocamento e nao coordenada: acrescentar um componente novo
# reempacota tudo. Com coordenada absoluta, todo ajuste feito a mao viraria
# lixo no dia seguinte; com deslocamento, a vizinhanca anda junto e o ajuste
# continua valendo em cima dela.
POSICOES: dict[str, tuple[float, float]] = {}

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
# --- Estoque API (30/08) -----------------------------------------------
# Derivadas de IMPORT REAL, nao de intuicao: `main` importa e usa `servico`
# 40 vezes, `media` 7, `provisioning` 3; `servico` usa `media` 4; `admin` usa
# `servico` 11; `cli`, 5. Onde o import nao conta a historia toda, o
# comentario diz por que.
ARESTAS_ESTOQUE = [
    {"de": "estoque-api.borda", "para": "estoque-api.veiculos",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "estoque-api.borda", "para": "estoque-api.midia",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "estoque-api.borda", "para": "estoque-api.credenciais",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "estoque-api.borda", "para": "estoque-api.provisionamento",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "estoque-api.veiculos", "para": "estoque-api.midia",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # A UNICA assincrona daqui: o dominio nao chama o outbox, ele GRAVA na
    # fila (`EventoSaida`, servico.py:61) e vai embora. Quem entrega e' o
    # worker, depois, com backoff — e desiste em 5.
    {"de": "estoque-api.veiculos", "para": "estoque-api.outbox",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    {"de": "estoque-api.worker", "para": "estoque-api.outbox",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # A limpeza de midia passa pelo dominio (`servico.limpar_midias_orfas`,
    # servico.py:639), nao direto no modulo de midia — por isso a seta vai
    # para `veiculos` e nao para `midia`.
    {"de": "estoque-api.worker", "para": "estoque-api.veiculos",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # O outbox precisa do segredo do webhook em claro pra assinar; quem
    # decifra e' `cripto.decifrar` (outbox.py:16).
    {"de": "estoque-api.outbox", "para": "estoque-api.credenciais",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "estoque-api.admin", "para": "estoque-api.veiculos",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "estoque-api.cli", "para": "estoque-api.veiculos",
     "protocolo": "chamada", "sincrono": True, "retry": True},
]

ARESTAS_INTERNAS = ARESTAS_INTERNAS + ARESTAS_ESTOQUE

# --- Catalogo Publico (30/08) -------------------------------------------
# Derivadas de IMPORT REAL: `main` importa events, pixel, provider, outbox e
# provisioning (main.py:17-21) e nada mais; `outbox` importa InterestStore
# (outbox.py:7); `provider` importa os contratos (provider.py:6). Nao ha
# import de `app` de outro produto — o que sai daqui sai por HTTP.
ARESTAS_CATALOGO = [
    {"de": "catalogo-publico.borda", "para": "catalogo-publico.provider",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "catalogo-publico.borda", "para": "catalogo-publico.interesse",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "catalogo-publico.borda", "para": "catalogo-publico.pixel",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # O gate roda ANTES de qualquer uma das tres telas (storefront_hidden,
    # main.py:165) — loja escondida nem chega a consultar a Estoque.
    {"de": "catalogo-publico.borda", "para": "catalogo-publico.provisionamento",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # A thread da outbox sobe no lifespan da propria API (main.py:20,58):
    # nao ha processo separado neste produto.
    {"de": "catalogo-publico.borda", "para": "catalogo-publico.outbox",
     "protocolo": "timer", "sincrono": False, "retry": False},
    {"de": "catalogo-publico.provider", "para": "catalogo-publico.contratos",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # A UNICA assincrona daqui, e o espelho da do Estoque: a rota nao chama a
    # entrega, ela GRAVA a linha `event_outbox` na mesma transacao do clique
    # (events.py:194) e redireciona o visitante pro wa.me. Quem entrega e' a
    # thread, depois.
    {"de": "catalogo-publico.interesse", "para": "catalogo-publico.outbox",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    # E a volta: `process_pending` le a fila e marca entregue/falho pelo mesmo
    # InterestStore (outbox.py:7,25) — o SQLite de interesse e' um so.
    {"de": "catalogo-publico.outbox", "para": "catalogo-publico.interesse",
     "protocolo": "chamada", "sincrono": True, "retry": True},
]

ARESTAS_INTERNAS = ARESTAS_INTERNAS + ARESTAS_CATALOGO

# --- Motor de Simulacao (30/08) -----------------------------------------
# Derivadas de IMPORT REAL: main.py:12 e :199 (servico), :91/:122/:135
# (credenciais), :16 (providers); servico.py:18 (fanout) e :29 (orquestrador,
# import tardio de proposito); worker.py:21 e :71; processamento.py:20,:29,:38;
# drivers.py:141-144,:172-173,:177,:223; santander.py:33,:424 e os irmaos.
#
# Duas coisas que o import NAO conta, e por isso estao comentadas na aresta:
# a entrega do job nao e' chamada de funcao (e' linha no banco, reservada
# depois por lease), e o wake do worker sai pela Machines API do Fly — de um
# processo pro outro, possivelmente de uma VM pra outra.
ARESTAS_MOTOR = [
    {"de": "motor-simulacao.borda", "para": "motor-simulacao.simulacao",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "motor-simulacao.borda", "para": "motor-simulacao.credenciais",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # main.py:16 lista os provedores reais pro cliente saber o que pedir.
    {"de": "motor-simulacao.borda", "para": "motor-simulacao.registro",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "motor-simulacao.simulacao", "para": "motor-simulacao.fila",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # servico.py:29 importa acordar_workers DENTRO da funcao, e engole
    # qualquer excecao (:33): problema na Fly API nunca derruba a criacao do
    # job. Best-effort de verdade.
    {"de": "motor-simulacao.simulacao", "para": "motor-simulacao.orquestrador",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # A UNICA assincrona daqui, e a razao do 202: o dominio grava a simulacao
    # com status `recebida` e responde; quem executa e' o worker, depois, e
    # noutro processo. Nao ha import de servico->worker porque nao ha chamada
    # — o que liga os dois e' a linha no banco, reservada por lease.
    {"de": "motor-simulacao.simulacao", "para": "motor-simulacao.worker",
     "protocolo": "outbox", "sincrono": False, "retry": True},
    # O wake atravessa processo (e VM): acordar_workers chama a Machines API
    # do Fly via WorkerLifecycle (lifecycle.py) pra ligar um slot da
    # motor2037. Nao ha retry aqui — o proximo tick tenta de novo.
    {"de": "motor-simulacao.orquestrador", "para": "motor-simulacao.worker",
     "protocolo": "http", "sincrono": False, "retry": False},
    {"de": "motor-simulacao.worker", "para": "motor-simulacao.fila",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "motor-simulacao.worker", "para": "motor-simulacao.registro",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # worker.py:71 so acorda Machine quando WORKER_ON_DEMAND e' FALSO (:69) —
    # um worker on-demand acordando outro seria laco.
    {"de": "motor-simulacao.worker", "para": "motor-simulacao.orquestrador",
     "protocolo": "chamada", "sincrono": True, "retry": False},
    # processamento.py:38 pergunta se a sessao ja esta quente antes de decidir
    # o caminho do job.
    {"de": "motor-simulacao.worker", "para": "motor-simulacao.rpa.base",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # drivers.py:141-144 e :173: as fabricas dos quatro drivers de browser
    # sao importadas TARDE, dentro de _registrar_drivers_reais, pra nao
    # arrastar Playwright pro processo da API.
    {"de": "motor-simulacao.registro", "para": "motor-simulacao.rpa.bancos",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # drivers.py:162 _pan_dispatch escolhe entre a API do parceiro e o portal.
    {"de": "motor-simulacao.registro", "para": "motor-simulacao.api-parceiro",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # drivers.py:223 configuracao_completa — a selecao pergunta se ha
    # credencial ANTES de escolher o driver real.
    {"de": "motor-simulacao.registro", "para": "motor-simulacao.credenciais",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    {"de": "motor-simulacao.rpa.bancos", "para": "motor-simulacao.rpa.base",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # A seta que importa pra AGENTS.md secao 5: o segredo em claro so existe
    # no momento do login, e so aqui dentro. Cada driver chama
    # obter_segredo_para_uso na hora (santander.py:424, bradesco.py:376,
    # fontecred.py:403, pan_portal.py:378) — nada de segredo no payload da
    # tarefa nem no log.
    {"de": "motor-simulacao.rpa.bancos", "para": "motor-simulacao.credenciais",
     "protocolo": "chamada", "sincrono": True, "retry": True},
    # pan.py:174 obter_configuracao_para_uso: a API de parceiro tambem pega a
    # credencial daqui, e nao de env.
    {"de": "motor-simulacao.api-parceiro", "para": "motor-simulacao.credenciais",
     "protocolo": "chamada", "sincrono": True, "retry": True},
]

ARESTAS_INTERNAS = ARESTAS_INTERNAS + ARESTAS_MOTOR


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
