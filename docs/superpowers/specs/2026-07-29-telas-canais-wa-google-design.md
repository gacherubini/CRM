# Telas de Canais WhatsApp (Loja) e Operação Google Ads (Control) — Design

Data: 2026-07-29

## Problema

Dois conjuntos de capacidade existem só como API, sem nenhuma tela:

1. **Canais WhatsApp (multi-WA).** Modelo `whatsapp_canais`, roteamento por canal, dedupe por canal, filtro `?canal_id=` e testes estão prontos no Chatbot. Nada disso é alcançável por UI: cadastrar um número exige `curl`. Além disso o provider é stub (`EvolutionStubWhatsAppProvider`), então o QR é falso e nenhum número real pareia.
2. **Operação Google Ads.** O dashboard do Control já mostra coluna "Google" e painel "Aquisição Google (7 dias)", mas não existe caminho de UI para conectar OAuth, selecionar conta ou vincular conversion actions. O dashboard só sabe exibir "Google indisponível", sem saída.

## Decisões tomadas

| Decisão | Escolha | Observação |
|---|---|---|
| Onde ficam as telas de canal WhatsApp | **Revy Loja** (operação completa) | Contraria a matriz de donos do as-built (`docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md:126`, que atribui a UI ao Control). Motivo: quem tem o celular na mão para ler o QR de 60s é a loja, não o admin Revy. **O as-built precisa ser atualizado junto.** |
| Onde ficam as telas de Google Ads | **Revy Control** | Alinhado ao as-built (linha 125). O que se conecta é a conta de anúncios, do gestor de tráfego. |
| Provider Evolution | **Adapter real completo** | Cria instância, QR real, estado, logout, webhook. Sem isso "a loja conecta o próprio número" não fecha. |
| Escopo do spec | **Um spec, duas partes independentes** | Parte A e Parte B não compartilham código, para que B possa ser mergeada mesmo se a Evolution travar A. |
| Autorização Google na UI | **Admin Revy ou gestor responsável** | O domínio já implementa a regra (`google_ads.py:718`); a UI não duplica. |

## Parte A — Canais WhatsApp na Loja

### A.1 Princípio central: onde a rede acontece

`register_channel` **continua sem tocar a Evolution** — só persiste o canal com `estado=pendente`. Toda I/O com a Evolution vive em `connect`, que faz *ensure instance* antes de pedir o QR.

Consequências:

- commit do banco falhar nunca deixa instância órfã na Evolution;
- falha de rede nunca deixa canal sem instância — o canal fica `pendente` e o próximo `connect` completa;
- retry é o próprio botão "conectar", idempotente por natureza;
- os testes atuais de `register_channel` seguem válidos sem alteração.

### A.2 Chatbot

**`app/whatsapp_provider.py`** ganha `EvolutionWhatsAppProvider` ao lado do stub, selecionado por `CHATBOT_WHATSAPP_PROVIDER=evolution|stub` (default `stub`).

Mapeamento HTTP (reusa o padrão de `EvolutionWhatsAppOutbound`: mesma env de URL/apikey, apikey nunca logada):

| Operação | Chamada Evolution | Resultado |
|---|---|---|
| ensure instance | `POST /instance/create` com webhook configurado | instância existe (idempotente: instância já existente não é erro) |
| connect | `GET /instance/connect/{instance}` | QR base64 + pairing code |
| status | `GET /instance/connectionState/{instance}` | `open`→`conectado`, `connecting`→`pendente`, `close`→`desconectado` |
| disconnect | `DELETE /instance/logout/{instance}` | `desconectado` |

**Webhook.** Um único workflow n8n serve N instâncias, roteando por `body.instance` (`deploy/fly/3vm/README.md:110-126`). Logo a URL é fixa, vinda de novo env `CHATBOT_EVOLUTION_WEBHOOK_URL` (aponta para `/webhook/whatsapp-ai`). 
A lista de eventos **não deve ser adivinhada nem lida em runtime**. Passo explícito da implementação: rodar `GET /webhook/find/{instance}` contra a instância legado que hoje funciona no lab e fixar o resultado como constante documentada no código (`EVOLUTION_WEBHOOK_EVENTS`), citando a origem em comentário. Assim a criação não depende de existir instância legado no ambiente, e a config nova é igual à que já funciona. Se `CHATBOT_EVOLUTION_WEBHOOK_URL` estiver vazio, `ensure instance` falha com erro explícito em vez de criar instância que não recebe eventos.

**Nome da instância.** Gerado no Chatbot: `{slug-da-loja}-{4 hex}`, sanitizado para `[a-z0-9-]` porque vira segmento de URL. `evolution_instance` passa a **opcional** em `CanalWhatsAppInput` — mudança expand-only; ausente, o Chatbot gera. O proxy do Control (`HttpWhatsAppChannels.register`) continua funcionando sem alteração, e a Loja nunca vê nem escolhe nome de instância.

**Invariantes preservadas:** instância única globalmente; `loja_id` imutável após registro; instância já vinculada a outra loja → 409; remoção é lógica (`/inativar`), nunca apaga histórico.

### A.3 Loja (portal-gestao)

Escopo vem do token: `CHATBOT_API_TOKEN` é de uma loja só (`config.py:56`), portanto sem seletor de loja e sem endpoint novo no Chatbot — `/v1/whatsapp/canais*` já usa `get_contexto`.

- **Rota** `GET /app/loja/whatsapp` em `app/web/loja_whatsapp.py`, seguindo o padrão de `loja_estoque.py`: `usuario_atual` → `redirecionar_login` → gate de flag → client via `Depends` → read-model → template.
- **Gates:** `REVY_LOJA_SHELL_ENABLED` + nova `REVY_LOJA_WHATSAPP_ENABLED` (default off) + cargo em `ROLES_GESTAO` (dono/gerente).
- **POSTs:** criar (só `e164_or_label`), conectar, desconectar, inativar.
- **Read-model** `app/loja/whatsapp_canais.py` traduzindo estado para linguagem de dono de loja: `conectado`→"Conectado", `pendente`→"Aguardando leitura do QR", `desconectado`→"Caiu — reconectar", `inativo`→"Desativado".
- **`ChatbotClient`** ganha `registrar_canal_whatsapp`, `conectar_canal_whatsapp`, `desconectar_canal_whatsapp`, `inativar_canal_whatsapp`. O docstring atual de `listar_canais_whatsapp` ("read-only; Loja não conecta/desconecta") deixa de valer e deve ser corrigido.
- **Navegação:** item em **Ajustes** (ao lado de "Acessos bancários" e "Equipe", já gated por `ROLES_GESTAO`). O docstring de `loja/navigation.py:24` afirma "Não inclui Meta/Google/WhatsApp" e precisa ser atualizado — WhatsApp passa a entrar, Meta e Google não.

**QR.** Renderizado como `<img src="data:image/png;base64,…">`. Resposta com `Cache-Control: no-store` (o Chatbot já faz isso no `connect`). O QR **nunca** vai para log nem para a trilha de auditoria. Status por polling leve: rota fina `GET /app/loja/whatsapp/canais/{canal_id}/status` devolvendo JSON (`{estado, rotulo}`) a partir de `/v1/whatsapp/canais/{id}/status`, consultada por fetch a cada ~3s **apenas enquanto um QR está na tela**. Fora disso não há polling. Botão explícito "gerar novo QR" quando expira — sem loop automático infinito.

**Auditoria.** `registrar_auditoria_operacao` com ações `canal_criado`, `canal_conectado`, `canal_desconectado`, `canal_inativado`, guardando label e instância. Nunca o QR.

### A.4 Control

Nada novo. O dashboard já projeta saúde de canais e `readiness.py` já considera `active_whatsapp_channels` quando `multi_whatsapp_enabled`.

### A.5 Erros

| Situação | Comportamento |
|---|---|
| Chatbot fora | `ChatbotIndisponivel` → banner honesto; nunca estado inventado |
| 409 instância em outra loja | mensagem clara na tela |
| `MULTI_WHATSAPP_ENABLED` off | esconde "adicionar número"; mostra só o canal legado |
| Evolution fora no `connect` | canal permanece `pendente` + "falha ao criar o número, tentar de novo" |
| QR expirado | botão explícito de novo QR |

### A.6 Testes

- Provider contra `httpx.MockTransport`: create/connect/state/logout, mapeamento dos três estados, falha de rede, instância já existente não é erro.
- `register_channel` sem `instance`: nome gerado único e sanitizado; com `instance` continua idempotente.
- `connect`: faz ensure e é idempotente; canal `pendente` cujo ensure falhou permanece `pendente`.
- Loja: rotas com `ChatbotClient` fake (padrão dos testes existentes) — gates de cargo e flag, QR ausente de log e auditoria, banner de indisponibilidade.
- E2E de lab com dois números reais fecha o residual registrado no as-built (seção 3, item 3).

## Parte B — Operação Google Ads no Control

### B.1 Pré-requisito de ops (não é código)

O callback OAuth é `GET /control/v1/google-ads/oauth/callback` e devolve **JSON** (`control.py:1202-1218`). É esse o `redirect_uri` registrado no Google, então hoje o admin voltaria do Google e veria JSON cru.

Solução: rota HTML nova no `control_ui` que chama `complete_oauth` e redireciona para `/app/control/lojas/{id}?ok=google_conectado`. O `loja_id` sai da connection retornada (resolvida a partir do `state`), sem parâmetro extra na URL.

**Passo manual necessário:** atualizar o `redirect_uri` no Google Cloud Console e o env `GOOGLE_ADS_OAUTH_REDIRECT_URI` para a nova rota HTML. O endpoint JSON permanece para compatibilidade.

### B.2 Onde mora

Painéis novos em `control/loja_detail.html`, seguindo o padrão existente: gate → checagem CSRF → ação → `RedirectResponse(_detail_path(loja_id, "..."), 303)`. **Nenhum endpoint novo de API** — tudo em cima de `control.py:1180-1470`.

### B.3 Autorização

`control_ui` ganha `_actor_for_store_mutation(request, db)`: igual a `_admin_for_mutation`, sem o bloqueio `papel != "admin"`. Cada handler Google captura `AccessDenied` e renderiza a mesma página 403. A regra "admin ou gestor responsável" continua num lugar só, no domínio (`_assert_can_manage_connection`, `google_ads.py:718`). `_admin_for_mutation` segue intacto para os handlers que já existem.

### B.4 Quatro painéis, na ordem do fluxo real

1. **Conexão** — status, `customer_id` selecionado, `has_refresh_token`; botões "Conectar Google Ads" (POST → `start_oauth` → 303 para `auth_url`) e "Desconectar". Refresh token nunca renderizado; o helper JSON já o exclui e a UI segue a mesma regra.
2. **Conta** — "Sincronizar contas" e lista com radio + "Selecionar". Contas gerenciadoras (MCC) renderizadas **desabilitadas com o motivo visível**, porque `GoogleAdsManagerAccountNotSelectable` é erro esperado e não deve ser descoberto por tentativa.
3. **Conversões** — vínculo `revy_event_type` → conversion action, com a action num `select` populado por `/conversion-actions`. Não campo livre: `resource_name` tem até 240 chars. Gated por `GOOGLE_CONVERSIONS_ENABLED`.
4. **Métricas** — "Sincronizar agora" com intervalo de datas (default últimos 7 dias) e o resumo que `/metrics/summary` já devolve.

Todos gated por `GOOGLE_ADS_SYNC_ENABLED`; com a flag off, os painéis não aparecem.

### B.5 Estados vazios e erros

| Situação | Comportamento |
|---|---|
| `GoogleAdsOAuthMisconfigured` (secrets vazias) | painel diz "Google não configurado neste ambiente"; sem botão que falha |
| `GoogleAdsNotConnected` | destaca painel 1 como próximo passo |
| `GoogleAdsNoSelectedAccount` | destaca painel 2 como próximo passo |
| `GoogleAdsTokenExchangeError` / state inválido | banner de erro na página de detalhe |
| `AccessDenied` | 403 padrão do Control |

### B.6 Testes

`build_google_ads_ports` já devolve ports Fake sem credenciais — é o seam pronto. Cobrir: painéis escondidos com flag off; colaborador (nem admin nem responsável) bloqueado; gestor responsável autorizado; CSRF negado; `oauth/start` redirecionando para `auth_url`; callback HTML caindo no detalhe com `ok=`; conta MCC renderizada desabilitada.

### B.7 Ganho verificável

Depois desta parte, a coluna "Google" e o painel "Aquisição Google (7 dias)" do dashboard saem de "indisponível" — hoje existem sem nenhum caminho de UI para ficarem verdes.

## Flags e envs

| Env | Onde | Default | Efeito |
|---|---|---|---|
| `MULTI_WHATSAPP_ENABLED` | Chatbot | `0` | Permite mais de um canal ativo por loja; sem isso `connect`/`status`/`disconnect` são 404 e o 2º `register` é 409 |
| `MULTI_WHATSAPP_ENABLED` | Control | `0` | Não é usado por tela nova: libera os endpoints proxy existentes e faz `readiness.py` contar `active_whatsapp_channels` na saúde do dashboard |
| `CHATBOT_WHATSAPP_PROVIDER` | Chatbot | `stub` | `evolution` liga o adapter real |
| `CHATBOT_EVOLUTION_WEBHOOK_URL` | Chatbot | vazio | URL do webhook n8n gravada em instância nova |
| `REVY_LOJA_WHATSAPP_ENABLED` | Loja | `0` | Tela de canais em Ajustes |
| `GOOGLE_ADS_SYNC_ENABLED` | Control | `0` | Painéis Google (já existe) |
| `GOOGLE_CONVERSIONS_ENABLED` | Control | `0` | Painel de conversões (já existe) |
| `GOOGLE_ADS_OAUTH_REDIRECT_URI` | Control | — | Repontar para a rota HTML nova |

Ordem de enablement da Parte A: provider real validado em lab → `MULTI_WHATSAPP_ENABLED=1` → `REVY_LOJA_WHATSAPP_ENABLED=1`.

## Fora de escopo

- Adapter WhatsApp Cloud API (só Evolution).
- Operar Google Ads pela Loja (exigiria proxy Loja→Control e um segundo `redirect_uri`).
- Cadastrar canal pela tela do Control (o proxy HTTP continua existindo e funcionando; só não ganha UI).
- Seller AI e qualquer coisa atrás de `SELLER_AI_ENABLED`.

## Documentação a atualizar junto

- `docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md:126` — dono da UI de canais passa a ser a Loja.
- `revy-trafego/README.md:196` — `MULTI_WHATSAPP_ENABLED` deixa de ser "sem efeito operacional".
- Docstrings que afirmam o contrário do novo desenho: `portal-gestao/app/clients/chatbot.py:205` e `portal-gestao/app/loja/navigation.py:24`.
