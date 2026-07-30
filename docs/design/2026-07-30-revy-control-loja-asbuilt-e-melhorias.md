# Revy Control + Revy Loja — As-built e Design de Melhorias

**Data:** 2026-07-30  
**Status:** As-built pós-implementação lean (Control F0–F6 + Loja F0–F6/F8)  
**Substitui como referência de evolução:**  
- [`docs/superpowers/specs/2026-07-29-revy-control-design.md`](../superpowers/specs/2026-07-29-revy-control-design.md) (status original: “não implementado”)  
- [`docs/superpowers/specs/2026-07-29-revy-loja-design.md`](../superpowers/specs/2026-07-29-revy-loja-design.md)  
**Planos de implementação:**  
- [`docs/plans/2026-07-29-plano-revy-control.md`](../plans/2026-07-29-plano-revy-control.md)  
- [`docs/plans/2026-07-29-plano-revy-loja.md`](../plans/2026-07-29-plano-revy-loja.md)  
**ADR:** [`docs/adr/0001-suspensao-distribuida.md`](../adr/0001-suspensao-distribuida.md)  
**Vocabulário:** [`CONTEXT.md`](../../CONTEXT.md)

---

## 1. Resultado desejado (atualizado)

Dois produtos de superfície, um ecossistema de serviços:

| Superfície | Quem usa | O que faz | Código / deploy |
|---|---|---|---|
| **Revy Control** | Admin Revy, Gestor Responsável, Gestor Colaborador | Cadastro de lojas, RBAC, pessoas/cargos, contrato, integrações técnicas (Meta/Google/WA), prontidão, tráfego/ROI, auditoria | Processo `revy-trafego` |
| **Revy Loja** | Dono, gerente, vendedor | Operação: Vendas (visão + atendimento) e Estoque (visão + veículos); bancos e equipe operacional | Processo `portal-gestao` |
| **Chatbot API** | Sistemas + n8n | Canais WA, leads, conversas, mensagens, handoff, envio | `chatbot-api` |
| **Motor** | Loja / Chatbot | Simulação multibanco (workers Playwright sob demanda) | `motor-simulacao` |
| **Estoque API** | Loja / Catálogo | Veículos, mídia, publicação | `estoque-api` |
| **Catálogo Público** | Público | Vitrine; eventos de interesse | `catalogo-publico` |

Não há entidade Organização/Rede/Agência. Cada cliente é uma **Loja**.  
**Seller AI** permanece **capacidade diferida** (`SELLER_AI_ENABLED`, default off, sem domínio).

---

## 2. Arquitetura as-built

### 2.1 Diagrama de fronteiras

```text
┌─────────────────────┐     HTTP service token      ┌──────────────────────┐
│   Revy Control      │ ──────────────────────────► │ Chatbot / Estoque /  │
│   (revy-trafego)    │   provisionamento outbox    │ Motor / Portal / Cat │
│                     │ ◄─── aquisição-resumo ────  │                      │
│  /control/v1/*      │                             └──────────────────────┘
│  /app/* (tráfego)   │
│  templates/control  │     eventos venda/gclid     ┌──────────────────────┐
│  app/control/*      │ ◄────────────────────────── │ Revy Loja             │
└─────────────────────┘                             │ (portal-gestao)       │
                                                    │  /app/loja/* shell    │
         ▲                                          │  /app/* legado       │
         │ Meta Ads / Pixel / CAPI                  │  app/loja/* domínio  │
         │ Google Ads API + Data Manager            └──────────────────────┘
         ▼                                                    │
   Meta Graph / Google OAuth                                  │ HTTP
                                                              ▼
                                                    Chatbot · Motor · Estoque
```

### 2.2 Módulos profundos — Revy Control

Diretório: `revy-trafego/app/control/`

| Módulo | Responsabilidade | Rotas finas |
|---|---|---|
| `stores.py` | Ciclo da loja (rascunho→…→ativa/suspensa/encerrada), versões | `POST/GET/PATCH /control/v1/lojas*` |
| `access.py` + `session.py` | Vínculos de tráfego, escopo, loja da sessão | seletor de loja + gates |
| `accounts.py`, `invitations.py`, `password_recovery.py` | Acessos Control, convite, reset | `/control/v1/acessos`, `/convites`, `/recuperacoes` |
| `people.py`, `roles.py` | Pessoas canônicas; cargos dono/gerente/vendedor | `/pessoas`, `/lojas/{id}/cargos` |
| `portfolio.py`, `contracts.py` | Módulos contratados + contrato/cobrança (sem pagamento) | `/modulos`, `/contrato` |
| `integrations.py` | Pixel/Meta Ads (wrapper sobre configs legadas) | `/integracoes/*` |
| `readiness.py` | Checks determinísticos + aceite de alerta | `/prontidao` |
| `google_ads*.py` | OAuth, contas, métricas, bindings, outbox conversões | `/google-ads/*` |
| `whatsapp_channels.py` | Port → Chatbot (canais multi-WA) | `/whatsapp-canais/*` |
| `provisioning.py` + `provisioning_outbox.py` + `delivery.py` + `provisioning_job.py` | Snapshot versionado + outbox + worker | delivery interno |
| `portal_import.py` | Import push de usuários do Portal | `POST /imports/portal-usuarios` |
| `dashboard.py` | Overview Admin/gestor | `GET /control/v1/dashboard` + UI |
| `audit.py` | Trilha administrativa | `/auditoria` |
| `types.py` | Comandos/erros/views estáveis | — |

Routers:

- `revy-trafego/app/web/control.py` — API JSON `prefix=/control/v1`
- `revy-trafego/app/web/control_ui.py` — HTML shell Control (dashboard, lojas)
- `revy-trafego/app/main.py` — ainda concentra **tráfego legado** (campanhas, ROI, pixel, login, seletor de loja); monta routers Control no lifespan

Workers (lifespan, todos opt-in por flag):

- Meta spend, Meta CAPI retry (legado Tráfego)
- Provisioning delivery
- Google conversions outbox
- Google Ads metrics sync

### 2.3 Módulos profundos — Revy Loja

Diretório: `portal-gestao/app/loja/`

| Módulo | Responsabilidade |
|---|---|
| `identity.py` | ActorLoja, memberships, loja da sessão (`SESSION_LOJA_KEY`) |
| `entitlements.py` | Resolve Vendas/Estoque; **fail-open** se flag off |
| `permissions.py` | `require_module`, erros de acesso |
| `navigation.py` | Nav só Vendas/Estoque (+ Ajustes contextual) |
| `control_projection.py` | Port + parse de snapshot Control |
| `sales_overview.py` | Read model Visão geral Vendas |
| `estoque_overview.py` | Read model Visão geral Estoque (determinístico) |
| `attendance.py` + `human_messaging.py` | Workspace Atendimento + envio texto |
| `routes.py` | Rotas Atendimento |
| `redirects.py` | Cutover legado → shell (F8) |
| `types.py` | Module, Role, EntitlementState, Nav* |

Routers:

- `portal-gestao/app/web/loja_shell.py` — seleção multi-loja, extras de template
- `portal-gestao/app/web/loja_vendas.py` — `/app/loja/vendas`, equipe, config financeira
- `portal-gestao/app/web/loja_estoque.py` — `/app/loja/estoque*`
- `portal-gestao/app/loja/routes.py` — `/app/loja/atendimento*`
- Middleware `revy_loja_legacy_redirects` em `main.py`
- **`main.py` continua dono** de leads/conversas/vendas/estoque/simulações/equipe legados

### 2.4 Chatbot vs Control vs Loja (ownership)

| Dado / efeito | Dono | Quem comanda UI | Quem só consome |
|---|---|---|---|
| Loja, contrato, módulos, pessoas/cargos | Control | Control | Loja (projeção) |
| Vínculos gestor de tráfego | Control | Control | — |
| Pixel, CAPI, Meta Ads, Google OAuth | Control (configs no banco tráfego) | Control | Loja (resumo aquisição) |
| Canais WhatsApp / conexões | **Chatbot** | Control (port HTTP) | Loja (label/canal_id) |
| Leads, conversas, mensagens | Chatbot | Loja (atendimento) | Control (diagnóstico) |
| Vendas, metas, atribuição | Loja/Portal | Loja | Control (projeção venda) |
| Credenciais bancárias | Motor (+ UI Loja) | Loja (dono/gerente) | **nunca Control** |
| Veículos | Estoque API | Loja | Catálogo |

### 2.5 Contratos HTTP / evento (as-built)

**Control → destinos (provisionamento)**  
- Snapshot `StoreProvisioningSnapshot` (`schema_version`, `operational[]`, `people[]`, `roles[]`)  
- Entrega via outbox + worker (`REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED`)  
- Destinos: `portal`, `chatbot`, `estoque`, `motor`, `catalogo`  
- Consumo monotônico por versão de envelope (loja + módulos)

**Control → Chatbot (canais)**  
- Port `WhatsAppChannelsPort` / `HttpWhatsAppChannels`  
- Flag `MULTI_WHATSAPP_ENABLED` no Control  
- Chatbot persiste `whatsapp_canais` / conexões; Control projeta saúde/prontidão

**Loja → Control (comercial)**  
- Outbox `venda_confirmada` / `venda_atualizada` (`PORTAL_REVY_TRAFEGO_VENDA_EVENTS`)  
- Payload inclui `gclid`/`gbraid`/`wbraid` em `PurchaseConversion` + `revy_trafego_outbox.py`  
- Residual: E2E lab de ponta a ponta + preservação em todos os hops Catálogo→Chatbot→Lead→Venda

**Loja → Control (leitura)**  
- `GET /control/v1/internal/lojas/{id}/aquisicao-resumo` (`X-Service-Token`)  
- Usado no `SalesOverview` (Google pode ficar `indisponivel` sem inventar zero)

**Loja → Chatbot**  
- Listagens leads/conversas, handoff, `HumanMessagingPort` (send texto, canal da conversa)

**Loja → Motor / Estoque**  
- Clientes HTTP existentes (`clients/motor.py`, `clients/estoque.py`)

### 2.6 Matriz de flags (defaults OFF = seguro)

#### Revy Control (`revy-trafego/app/config.py`)

| Flag | Default | Efeito |
|---|---|---|
| `REVY_CONTROL_ENABLED` | `0` | Superfícies admin Control (API/UI) |
| `REVY_CONTROL_RBAC_ENABLED` | `0` | Escopo por vínculo; sem isso seletor ainda pode ser mais permissivo legado |
| `REVY_CONTROL_DASHBOARD_ENABLED` | `0` | Dashboard Control |
| `REVY_CONTROL_PROVISIONING_DELIVERY_ENABLED` | `0` | Worker outbox de projeção |
| `GOOGLE_ADS_SYNC_ENABLED` | `0` | Sync / superfície Google |
| `GOOGLE_CONVERSIONS_ENABLED` | `0` | Worker outbox conversões |
| `GOOGLE_ADS_METRICS_WORKER_ENABLED` | `0` | Worker métricas (main pode forçar com SYNC) |
| `MULTI_WHATSAPP_ENABLED` | `0` | Multi-canal no Control |
| Secrets Google | vazio | `GOOGLE_ADS_OAUTH_CLIENT_ID/SECRET`, `REDIRECT_URI`, `DEVELOPER_TOKEN` |

#### Revy Loja (`portal-gestao/app/config.py` + helpers runtime)

| Flag | Default | Efeito |
|---|---|---|
| `REVY_LOJA_SHELL_ENABLED` | `0` | Brand + nav + rotas `/app/loja/*` |
| `REVY_LOJA_ENTITLEMENTS_ENABLED` | `0` | Gates de módulo; **off = fail-open** |
| `REVY_LOJA_ATENDIMENTO_ENABLED` | `0` | Workspace Atendimento |
| `REVY_LOJA_REDIRECT_LEGACY` | `0` | 303 legado→shell (exige shell on) |
| `SELLER_AI_ENABLED` | `0` | Placeholder F7; **sem implementação** |

Ordem de enablement Loja (canônica): shell → entitlements (após projeção estável) → atendimento → redirect.

---

## 3. Gaps honestos (as-built ≠ “pronto produção”)

### 3.1 Operacionais / humanos

1. **Google OAuth precisa de secrets GCP**  
   Código de OAuth, ports HTTP, outbox e UI existem; **não há** projeto GCP/consent/developer token configurados no lab por este repositório. Sem `GOOGLE_ADS_*` secrets, conexão falha com `GoogleAdsOAuthMisconfigured`.

2. **Motor on-demand**  
   Workers Playwright sob demanda (`WORKER_ON_DEMAND`, Machines Fly, `on-demand-worker-entrypoint.sh`) são **infra do Motor**, não do Control/Loja. A Loja embute simulação via atalhos/rotas legadas; cold-start e slots são pendência operacional do deploy Motor, não de produto Control/Loja.

3. **Multi-WA residual E2E**  
   Modelo de canais, filtro por `canal_id`, envio pelo canal da conversa e testes com fake Chatbot estão no código. **E2E real** Evolution + n8n + dois números no lab permanece residual (recriar instâncias, smoke reativar loja — runbook de provisionamento).

4. **Backup/restore drills**  
   Planos marcam backup Portal/Control como ops/lab; não é entrega de código.

### 3.2 Design / código conscientes

5. **Seller AI deferred**  
   Flag existe; sem tabelas `proximas_acoes` / `followups` / `propostas` / `seller_ai_execucoes`. **Não reabrir como obrigatório do MVP.**

6. **Entitlements fail-open por default**  
   `REVY_LOJA_ENTITLEMENTS_ENABLED=0` → `fail_open()`: se a pessoa tem cargo operacional, Vendas e Estoque ficam liberados. Correto para cutover; **perigoso** se alguém esperar contrato real sem ligar a flag + projeção.

7. **Dual UI paths (legado + shell)**  
   - Control: UI Tráfego em `main.py` + templates `campanhas/`/`trafego/` **e** shell `templates/control/` + `/control/v1`.  
   - Loja: menus e rotas `/app/*` legadas **e** `/app/loja/*`. Redirects só com duas flags.  
   Resultado: usuário pode ver brand Revy Loja com dashboard legado se shell on e redirect off.

8. **Identidade ainda dual**  
   - Control: `AcessoControl` + `Pessoa` (+ sync residual `GestorRevy`).  
   - Loja: `Usuario` do Portal como projeção principal; memberships multi-loja via Control **quando** payload/projeção existem — caminho feliz de login Loja ainda é o legado de uma loja/papel.  
   Cutover de identidade **não** removeu auth do Portal (decisão correta do plano).

9. **Prontidão vs pendências operacionais**  
   `StoreReadiness` checks: `active_owner`, `activatable_owner`, `module_selected` (required); `contract_present`, `meta_pixel`, `whatsapp_channel` (alertas).  
   Credencial bancária **não** entra na prontidão (correto) — aparece como `pendencias_bancos_nao_configurados` no SalesOverview.  
   Gap de clareza de produto: UI nem sempre separa visualmente “bloqueia ativação” vs “pendência de operação”.

10. **main.py ainda grande**  
    Planos pediam main só montagem; as-built extraiu Control/Loja shell mas **não** esvaziou tráfego/portal legado.

11. **Fase 0 inventário lab**  
    Mapa slug real lab, colisões e fixtures Evolution mascaradas ainda abertos no plano Control (bloqueiam ativação remota segura, não o código).

---

## 4. Design melhorado (alvo incremental)

### 4.1 Seams mais claros

| Seam | Melhoria |
|---|---|
| Control domain vs Tráfego legacy | Prefixo de pacote estável `app/control/*`; extrair `app/trafego/*` (campanhas, ROI, pixel jobs) para o mesmo padrão de routers finos |
| Control UI vs API | Manter `/control/v1` JSON como contrato; UI só chama domain services (já parcial) — documentar OpenAPI interna mínima dos endpoints de service-token |
| Loja shell vs legado | Tratar `/app/loja/*` como **única nav canônica** quando shell on; legado só deep-link + redirect |
| Projeção | Um envelope versionado documentado em `docs/contracts/provisioning-v1.md` (schema_version, aggregates, monotonia) |
| Evento comercial | Contrato `venda.confirmada.v1` com click IDs + consentimento; testes de contrato cross-repo |
| Mensagem humana | Port único Chatbot; proibir qualquer send Evolution fora do port (ADR) |

### 4.2 Naming

| Atual | Preferir |
|---|---|
| Deploy/processo `revy-trafego` | Manter deploy name; UI/brand **Revy Control** (já parcial) |
| `portal-gestao` | Manter deploy; brand **Revy Loja** |
| `GestorRevy` | Somente compat; domínio = `AcessoControl` + `Pessoa` |
| `Usuario` Portal | Documentar como **projeção operacional** até cutover; meta = `pessoa_id` na sessão |
| `fail_open` source | Manter nome técnico; UI/ops: “modo legado sem contrato” |
| `LojaOperacionalProjecao` | Manter; expor só via `allows_processing` |

### 4.3 UX / navegação

**Control**

1. Home Admin: lista de lojas + status de prontidão (ready/blocked/alert).  
2. Home Gestor: lojas do vínculo + atalho Tráfego/ROI da loja selecionada.  
3. Ficha da loja em abas: Cadastro | Pessoas/Cargos | Contrato/Módulos | Integrações | WhatsApp | Prontidão | Auditoria.  
4. Tráfego (campanhas, gastos, ROI, auditorias pixel/CTWA) como **módulo interno** da loja selecionada — não home genérica sem loja quando RBAC on.

**Loja**

1. Com shell on: nav **somente** Vendas / Estoque / Ajustes (dono/gerente).  
2. Seletor de loja no header quando multi-membership.  
3. Redirect gradual (já mapeado) até bookmarks antigos sumirem.  
4. Atendimento: deep-link explícito para simulação e confirmação de venda **dentro** do workspace (hoje residual em rotas legadas).  
5. Estados de bloco (ok/vazio/parcial/erro/indisponível) já no SalesOverview — estender o mesmo vocabulário a Estoque e Atendimento.

### 4.4 Caminho de cutover de identidade

Fases recomendadas (sem big bang):

| Fase | Control | Loja |
|---|---|---|
| A (atual) | Pessoa + AcessoControl; GestorRevy legado sincronizado se existir | Login `Usuario`; papel único |
| B | Import Portal → cargos; delivery people/roles | Aceitar memberships multi-loja na sessão se projeção presente; `Usuario` ainda auth |
| C | Convites Loja emitidos só no Control | Login por e-mail resolve pessoa; cria/atualiza projeção `Usuario` local idempotente |
| D | Desativar criação de conta na Loja (já com shell) | Sessão carrega `pessoa_id`; papel = união de cargos da loja |
| E (futuro) | Opcional SSO/cookie compartilhado | Remover senha local se política permitir |

Regra de ouro mantida: **permissões Control nunca vazam para Loja** e vice-versa.

### 4.5 Contratos de evento (alvo)

```text
# Provisioning (Control → services)
{
  "schema_version": 1,
  "event_id": "uuid",
  "loja_id": "...",
  "loja_slug": "...",
  "operational": [
    {"aggregate": "loja", "version": N, "state": "ativa|suspensa|...", "effective_at": "..."},
    {"aggregate": "vendas", "version": N, "state": "ativo|suspenso|..."},
    {"aggregate": "estoque", "version": N, "state": "ativo|suspenso|..."}
  ],
  "people": [{"person_id", "email", "name"}],
  "roles": [{"assignment_id", "person_id", "role", "state", "started_at", "ended_at"}]
}

# Venda confirmada (Loja → Control)
{
  "schema_version": 1,
  "tipo": "venda_confirmada",
  "loja_slug": "...",
  "venda_id": "...",
  "valor": "...",
  "moeda": "BRL",
  "ocorrido_em": "...",
  "gclid": null,
  "gbraid": null,
  "wbraid": null,
  "consentimento": {...},
  "utm": {...}
}
```

Monotonia: versão menor ou igual **não reativa** estado mais restritivo.

### 4.6 Prontidão vs pendências operacionais

| Classe | Exemplos | Bloqueia ativação? | Onde aparece |
|---|---|---|---|
| **Required readiness** | dono ativável, módulo selecionado | Sim | Control prontidão |
| **Alert readiness** | pixel, WA, contrato ausente | Não (se aceito com motivo) | Control + aceite auditado |
| **Pendência operacional** | banco sem credencial, foto faltando, lead sem responsável | Não | Loja (Sales/Estoque overview) |
| **Degradação externa** | Google OAuth revogado, Chatbot down | Não ativa/desativa loja sozinho | Integrações / blocos `indisponivel` |

UI alvo: badges distintos (`Bloqueio` / `Alerta` / `Operação` / `Integração`).

### 4.7 Modelo de erro e degradação

| Falha | Comportamento canônico |
|---|---|
| Control indisponível (Loja com entitlements on) | Usar projeção local se existir; **fail-closed** se nunca houve projeção |
| Control indisponível (entitlements off) | Fail-open legado |
| Chatbot down no Atendimento | Lista/workspace com `erros_bloco`; sem envio; sem inventar leads |
| Motor down | Bloco simulação indisponível; venda/lead seguem |
| Estoque down | Visão estoque erro; Vendas segue se não depender do veículo |
| Google metrics fail | `google_status=indisponivel`; **nunca** ROAS/CAC zero inventado |
| Meta spend fail | Alerta medição; ROI parcial |
| Suspensão projetada | Gates nos serviços (ADR 0001); captura passiva inbound WA |
| Outbox Google/CAPI falha | Não reverte venda; retry idempotente |

---

## 5. Key Decisions

### 5.1 Must keep (não reabrir sem ADR)

1. **Dois produtos de superfície, vários serviços** — sem monólito único.  
2. **Sem Organização/Agência** — loja isolada.  
3. **Control = estrutura + integrações técnicas; Loja = operação comercial.**  
4. **Credenciais bancárias só na Loja/Motor.**  
5. **Chatbot dono de canais, conversas e mensagens.**  
6. **Flags default OFF + expand/contract.**  
7. **Sem Mutate de campanhas Google/Meta** — só medição/atribuição.  
8. **Número WA não muda de loja; sem finalidade fixa por número.**  
9. **Seller AI assistivo e diferido** — não bloqueia MVP.  
10. **Suspensão distribui gates por serviço** (ADR 0001); menu não é controle.  
11. **Fail-open de entitlements com flag off** como estratégia de cutover.  
12. **Process names `revy-trafego` / `portal-gestao`** durante migração.

### 5.2 Should change (melhorias prioritárias)

1. **Separar visualmente dual path** — banner “modo legado” ou forçar redirect em lab assim que shell estável.  
2. **Documentar e versionar contratos** de provisioning e venda em artefato único (não só fixtures soltas).  
3. **Identidade Loja: caminho B→D** (membership multi-loja real na sessão sem depender só de `Usuario.papel`).  
4. **Atendimento: deep-link simulação + venda no workspace** (fechar residual F4).  
5. **Extrair tráfego de `main.py`** para routers `app/web/trafego.py` (simetria com Control).  
6. **Readiness UI** com classes Required/Alert/Ops.  
7. **Checklist de secrets Google** no runbook F7 (ops) separado do “código complete”.  
8. **Telemetria de flags** (qual loja/piloto com shell/entitlements/atendimento) antes de remover menus legados.  
9. **gclid/gbraid/wbraid E2E** como gate de Google “realmente útil”, não só OAuth connect.  
10. **Nomenclatura de templates/rotas** alinhar `control_*` e `loja_*` de forma consistente (já bom no domínio; main ainda misturado).

### 5.3 Explicitly deferred

- Seller AI, próximas ações persistentes, follow-ups, propostas (Loja F7).  
- WhatsApp Cloud API adapter.  
- Pagamentos/cobrança automática.  
- Remoção física de rotas legadas (só após telemetria).  
- Renomear repositórios/processos Fly.

---

## 6. Open Questions (product owner)

1. **Política de visibilidade do vendedor** — `VENDEDOR_VE_FILA_SEM_RESPONSAVEL`: manter fila aberta ou só “meus” + reatribuição por gerente? (design Loja pedia aceite explícito.)  
2. **Quando ligar `REVY_LOJA_ENTITLEMENTS_ENABLED` em lab/piloto** — após quantas lojas com projeção estável?  
3. **Google no MVP comercial** — piloto com Meta only é aceitável por quantos meses?  
4. **Multi-WA em produção** — quantos números por loja no primeiro piloto e quem opera reconexão (só Gestor Responsável)?  
5. **Cutover de equipe** — a partir de qual data a Loja deixa de permitir qualquer mutação estrutural mesmo com shell off (forçar Control)?  
6. **SLA de degradação** — se Control fica 30min offline, Loja com entitlements on deve falhar fechado ou cachear projeção por quanto tempo?  
7. **Marca em URLs públicas** — manter `/trafego` no edge ou planejar `/control`?  
8. **Admin Revy opera venda?** — hoje admin_plataforma tem papéis largos no Portal; deve continuar ou ser “só break-glass”?  
9. **Contrato atrasado** — continua só alerta, ou no futuro suspende após N dias?  
10. **Prioridade de limpeza** — preferir fechar E2E multi-WA lab ou extrair main.py/tráfego primeiro?

---

## 7. PR Plan (incremental, sem rewrite)

Ordem pensada para **risco baixo** e valor de clareza/produto. Cada PR deve manter flags default OFF e suítes verdes.

### PR-1 — Contratos versionados documentados  
**Escopo:** `docs/contracts/provisioning-v1.md` + `venda-confirmada-v1.md`; alinhar fixtures em `portal-gestao/docs/revy-loja-fixtures-contratos.md`.  
**Não mexe em runtime.**  
**Gate:** review produto/eng.

### PR-2 — Banner dual-path + telemetria de flags  
**Escopo:** template Loja/Control mostra “Shell legado ativo” quando shell on e path não `/app/loja/*` (ou Control sem dashboard); log estruturado de flags no boot.  
**Gate:** UX ok; sem redirect forçado.

### PR-3 — Readiness UI: Required vs Alert vs Ops  
**Escopo:** `templates/control/loja_detail.html` (ou equivalente) + mapear checks; link “pendências operacionais” → Loja quando aplicável.  
**Gate:** testes readiness existentes verdes.

### PR-4 — Identidade Loja fase B (memberships na sessão)  
**Escopo:** ao receber projeção people/roles, `identity.actor_from_usuario` usa memberships multi-loja; seletor real; testes isolamento.  
**Gate:** sem mudar auth password; flag entitlements ainda default off.

### PR-5 — Atendimento deep-link simulação/venda  
**Escopo:** botões no workspace → rotas existentes com query `lead_ref`/`telefone`; sem unificar formulários ainda.  
**Gate:** F4 testes + smoke manual.

### PR-6 — Click IDs E2E harden  
**Escopo:** garantir preservação gclid/gbraid/wbraid Catálogo→Chatbot→Portal outbox→Control Google outbox; testes de contrato.  
**Gate:** unit + se possível lab.

### PR-7 — Extrair tráfego de `revy-trafego/app/main.py`  
**Escopo:** `app/web/trafego_*.py` routers; main só montagem/lifespan/auth.  
**Gate:** diff mecânico + suite revy-trafego.

### PR-8 — Extrair blocos legados de `portal-gestao/app/main.py` (fase 1)  
**Escopo:** leads/conversas/vendas em `app/web/legacy_*.py` sem mudar paths.  
**Gate:** suite portal.

### PR-9 — Runbook lab F7 unificado  
**Escopo:** checklist secrets Google, flags Control, flags Loja, multi-WA Evolution, smoke reativar loja; referenciar runbook provisionamento.  
**Não é código de produto.**

### PR-10 — Piloto flags (ops, não merge grande)  
**Escopo:** lab: `REVY_CONTROL_ENABLED=1` + RBAC + delivery; uma loja com `REVY_LOJA_SHELL_ENABLED=1` → entitlements → atendimento → redirect.  
**Gate:** rollback por flag documentado em cutover.

### PR-11 — Remoção de menus legados (só após telemetria)  
**Escopo:** esconder itens duplicados no `base.html` quando shell+redirect on; **não apagar rotas**.  
**Gate:** PO + 2 semanas piloto estável.

### PR-12 — Seller AI (diferido)  
**Escopo:** somente quando F4 E2E lab estável; design dedicado; flag continua off.  
**Não entra no caminho crítico atual.**

---

## 8. Mapa rápido de rotas canônicas

### Control API (`/control/v1`, exige `REVY_CONTROL_ENABLED`)

- Pessoas, acessos, convites, recuperações  
- Lojas CRUD + estado + módulos + contrato + cargos + gestores  
- Prontidão + aceite alerta  
- Integrações pixel/meta-ads  
- WhatsApp canais (connect/disconnect/inativar)  
- Google Ads OAuth, accounts, metrics, conversion-actions/bindings  
- Dashboard, auditoria, import portal  
- Internal: aquisição-resumo (service token)

### Control UI

- Templates `templates/control/*` + gates `REVY_CONTROL_DASHBOARD_ENABLED`  
- Tráfego legado: `/app` campanhas, ROI, pixel (main)

### Loja shell (`REVY_LOJA_SHELL_ENABLED`)

| Rota | Flag extra |
|---|---|
| `GET /app/loja/vendas` | shell |
| `GET /app/loja/vendas/dados` | shell |
| `GET /app/loja/estoque` | shell |
| `GET /app/loja/estoque/veiculos` → legado lista | shell |
| `GET/POST /app/loja/atendimento*` | atendimento |
| `POST /app/loja/selecionar` | shell |
| `GET /app/loja/equipe` | shell |
| Redirects `/app`, `/app/funil`, … | shell + redirect (+ atendimento para leads/conversas) |

---

## 9. Critérios de “pronto para piloto” (não “código complete”)

- [ ] Inventário slug lab sem colisões  
- [ ] Backup/restore ensaiado Portal + Control  
- [ ] Flags Control + delivery on em lab com uma loja  
- [ ] Projeção consumida e monotônica nos 5 destinos  
- [ ] Shell Loja on; entitlements on **somente** se projeção ok  
- [ ] Atendimento + envio texto em 1 número WA  
- [ ] (Opcional piloto) 2 números multi-WA E2E  
- [ ] Meta ROI operacional; Google opcional se secrets GCP ok  
- [ ] Rollback por flag testado  
- [ ] Seller AI **não** é critério

---

## 10. Referências de código (âncoras)

- Control domain: `revy-trafego/app/control/`  
- Control HTTP: `revy-trafego/app/web/control.py`, `control_ui.py`  
- Flags Control: `revy-trafego/app/config.py`  
- Loja domain: `portal-gestao/app/loja/`  
- Loja HTTP: `portal-gestao/app/web/loja_*.py`, `app/loja/routes.py`  
- Cutover: `portal-gestao/docs/revy-loja-cutover.md`  
- ADR suspensão: `docs/adr/0001-suspensao-distribuida.md`  
- Motor on-demand: `motor-simulacao/app/worker.py`, `scripts/on-demand-worker-entrypoint.sh`
