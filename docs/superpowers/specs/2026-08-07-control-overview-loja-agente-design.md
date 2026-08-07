# Revy Control (Visão Geral de negócio) + filtro de lojas ativas + Revy Loja (Desempenho do agente)

**Data:** 2026-08-07
**Status:** Design aprovado — pronto para plano de implementação
**Produtos afetados:** `revy-trafego` (Control), `portal-gestao` (Loja), `chatbot-api` (novo endpoint agregado)
**Referências de arquitetura:** `docs/design/2026-07-30-revy-control-loja-asbuilt-e-melhorias.md`

---

## 1. Resultado desejado

Três entregas independentes, decididas com o dono do produto:

1. **Task 1 — Visão Geral de negócio no Revy Control.** A tela `/app/control/dashboard`
   passa a liderar com KPIs de negócio (lojas ativas, vendas no mês, ticket médio, leads na
   rede) e uma tabela "Desempenho por loja", mantendo prontidão/saúde abaixo.
2. **Task 2 — Filtro "só lojas ativas".** O seletor de loja do Control e a Visão Geral
   consideram apenas lojas com status `ativa`. A tela de gestão "Lojas" continua listando todas.
3. **Task 3 — Desempenho do agente no Revy Loja.** Nova página do bot automático
   (Evolution + n8n + Gemini): atendimentos no período, transferidos para humano, gráfico
   de atendimentos por dia e um card placeholder de simulações.

Escopo respeita o escopo do ator (admin vê a rede toda; gestor vê só suas lojas) — é isso
que torna cada informação "privada" por vínculo, sem entidade Organização/Rede nova.

## 2. Decisões travadas com o dono

| Tema | Decisão |
|---|---|
| Metas na Task 1 | **Fora desta fase.** Metas vivem no Portal e ainda não são projetadas no Control. Coluna "Meta" e painel "Meta da rede" ficam para a Fase 2. |
| Leads na Task 1 | **Entram agora**, via Chatbot (o Control já tem `ChatbotClient`). |
| Status considerado "ativo" (Task 2) | Somente `ativa`. Suspensa/encerrada/rascunho/configurando somem do seletor e da Visão Geral. |
| Onde o filtro NÃO se aplica | Tela de gestão "Lojas" (`/app/control/lojas`) continua mostrando todas. |
| Natureza do agente (Task 3) | O **bot automático** (n8n/IA), não a equipe humana. |
| Cards da Task 3 | Atendimentos no período, Transferidos para humano (+%), Gráfico por dia, Simulações (**placeholder "em construção"**, pois a simulação ainda está em ajuste). |
| Fonte de dados da Task 3 | **Approach B:** endpoint agregado novo no Chatbot (`/v1/atendimento/resumo`), agregação exata em SQL por data. |

## 3. Task 1 — Visão Geral de negócio (Control)

### 3.1 Fonte de dados (o que já existe hoje)

| KPI | Fonte | Observação |
|---|---|---|
| Lojas ativas | `lojas.status` (banco Control) | Card mostra "X de Y" (ativas de total no escopo). |
| Vendas no mês | `vendas_projetadas` (banco Control) | Conta vendas confirmadas no mês corrente; Δ vs mês anterior. |
| Ticket médio | `vendas_projetadas.preco_venda` | Média do mês corrente. |
| Leads na rede | Chatbot `listar_leads()` por loja ativa | Loop por loja no escopo (poucas lojas hoje). |
| Conversão (por loja) | vendas ÷ leads | Derivado; requer leads disponíveis. |

### 3.2 Read model

Novo método em `revy-trafego/app/control/dashboard.py`, ex.: `network_overview(actor) -> NetworkOverview`,
reutilizando `self._stores.list(actor)` (respeita escopo). Estruturas:

- `NetworkOverview`:
  - `lojas_ativas: int`, `lojas_total: int`
  - `vendas_mes: int`, `vendas_delta_pct: float | None`
  - `ticket_medio: Decimal | None`
  - `leads_rede: int | None` (None se Chatbot indisponível)
  - `por_loja: tuple[StorePerformance, ...]` (só lojas ativas)
  - `destaques: Highlights` (melhor loja por vendas; ticket médio da rede)
- `StorePerformance`: `store_id, slug, name, vendas: int, leads: int | None, conversao: float | None`

Agregação de vendas em SQL (`func.count`, `func.avg`, filtro por `confirmada_em`/`criada_em` no
mês). Leads via `ChatbotClient.listar_leads()` por loja ativa, contando itens; se a chamada falhar
para uma loja, `leads`/`conversao` daquela loja ficam `None` (nunca zero inventado).

### 3.3 UI (`revy-trafego/app/templates/control/dashboard.html`)

Ordem nova da página, mantendo o gate `REVY_CONTROL_DASHBOARD_ENABLED`:

1. **4 cards de topo:** Lojas ativas ("X de Y") · Vendas no mês (+Δ%) · Ticket médio · Leads na rede.
2. **Tabela "Desempenho por loja"** (só ativas): Loja · Vendas · Leads · Conversão · Status(badge).
   Coluna **Meta omitida** nesta fase.
3. **Painel "Destaques"** no lugar do "Meta da rede": melhor loja por vendas + ticket médio.
   (Placeholder textual: "Metas da rede chegam na próxima fase.")
4. Prontidão/pendências e auditoria **permanecem abaixo**, como hoje.

### 3.4 Degradação

- Chatbot indisponível → cards Leads/Conversão mostram "indisponível"; Vendas/Ticket seguem.
- Sem vendas no mês → cards mostram `0` / "—" em ticket, sem quebrar.

## 4. Task 2 — Filtro "só lojas ativas"

- **Seletor do Control** (`revy-trafego/app/templates/base.html`, dropdown "— selecione loja —"):
  a lista `lojas` injetada no contexto (montada em `revy-trafego/app/main.py`) é filtrada para
  apenas status `ativa`, tanto no caminho RBAC (`item.store.status == ATIVA`) quanto no caminho
  por slug (enriquecer com status na origem da lista).
- **Visão Geral (Task 1):** tabela "Desempenho por loja" lista só ativas; card "Lojas ativas"
  mostra "ativas de total".
- **NÃO muda:** `/app/control/lojas` (gestão) continua listando todas as lojas para ativar/configurar.

## 5. Task 3 — Desempenho do agente (Loja)

### 5.1 Chatbot — novo endpoint agregado (Approach B)

`GET /v1/atendimento/resumo?desde=<ISO>&ate=<ISO>` em `chatbot-api/app/main.py`, escopado à loja
pelo contexto de service-token existente (`ctx.loja_id`). Agregação em SQL sobre `conversas`:

- `atendimentos: int` — `count(conversas)` com `criada_em` no período.
- `transferidos: int` — `count(conversas)` com `status = 'handoff'` no período.
- `transferidos_pct: float | None` — `transferidos / atendimentos` (None se `atendimentos == 0`).
- `por_dia: list[{data: date, atendimentos: int}]` — `group by date(criada_em)`.
- `simulacoes: null` — reservado (placeholder; simulação ainda em ajuste).

Regras: sem inflar zeros; janela default = mês corrente se `desde/ate` ausentes. Novo teste de
serviço no Chatbot cobrindo contagem, handoff e agrupamento por dia.

### 5.2 Loja — cliente + página

- **Cliente:** novo método em `portal-gestao/app/clients/chatbot.py`, ex.
  `resumo_atendimento(desde, ate) -> dict`, chamando o endpoint acima.
- **Rota:** `GET /app/loja/agente` em novo módulo (ou em `portal-gestao/app/loja/routes.py`,
  **declarado antes** da rota `/{workspace_id}` para evitar colisão). Gate
  `REVY_LOJA_ATENDIMENTO_ENABLED` (já existe). Item de nav "Agente" no shell da Loja.
- **Template:** cabeçalho "Agente de atendimento" + status **Ativo/Inativo**; 4 cards
  (Atendimentos, Transferidos + %, Simulações [placeholder "em construção"], e o gráfico);
  **gráfico "Atendimentos por dia"** em barras CSS puras (sem lib externa), com acento de marca
  e legível em tema claro/escuro.
- **Degradação:** Chatbot indisponível → página mostra bloco "indisponível", sem inventar números.

## 6. Flags e segurança

- Task 1: sob `REVY_CONTROL_DASHBOARD_ENABLED` (já existe).
- Task 3: sob `REVY_LOJA_ATENDIMENTO_ENABLED` (já existe).
- Task 2: mudança de comportamento de baixo risco no seletor; sem flag nova (a gestão "Lojas"
  preserva o acesso a todas as lojas).
- Isolamento entre produtos mantido: Control e Loja falam com Chatbot por HTTP/contrato; sem
  import Python entre produtos; nenhum segredo em log.

## 7. Testes / verificação

- **Control:** teste do read model `network_overview` (escopo admin vs gestor; vendas/ticket a
  partir de `vendas_projetadas`; leads mockando `ChatbotClient`; degradação quando Chatbot falha).
- **Control (Task 2):** teste de que o seletor/overview só listam lojas `ativa` e que a gestão
  "Lojas" ainda lista todas.
- **Chatbot:** teste do `/v1/atendimento/resumo` (atendimentos, handoff, por_dia, janela default).
- **Loja:** teste da rota `/app/loja/agente` (render com resumo mockado; degradação; gate off).
- Rodar suíte de cada produto a partir da sua pasta (`python -m pytest -q`).

## 8. Fora de escopo (Fase 2+)

- Projeção de **metas** Portal→Control (coluna Meta e painel "Meta da rede").
- Métricas por atendente humano.
- Card de **simulações** com dado real (depende do ajuste em andamento da simulação).
- Endpoint bulk de leads por rede no Chatbot (hoje: loop por loja no escopo).
