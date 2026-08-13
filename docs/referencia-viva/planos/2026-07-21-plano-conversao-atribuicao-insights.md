# Plano — Conversões, funil, insights, UX de gastos, resultados do dono e Google

> **FRONTEIRA FUTURA:** arquitetura e RBAC abaixo registram o que foi entregue no Portal.
> Configuração técnica, mídia e conversões outbound migram ao [Revy Control](2026-07-29-plano-revy-control.md);
> o [Revy Loja](2026-07-29-plano-revy-loja.md) conserva apenas a visão comercial.

> **Status 2026-07-29: CONCLUÍDO NO ESCOPO — A/B/E/D/H/C/F feitos; Fase G movida
> para o [plano do Revy Control](2026-07-29-plano-revy-control.md#fase-4--google-ads-conexão-leitura-e-conversões).**
> **Rev. 3:** + **UX de resultados do dono** (bloco no dashboard, alertas, drill-down campanha,
> onboarding de medição). Rev. 2 já tinha gastos lote/CSV, event bus e Google.
> Origem: conversa Meta + Google + TikTok / Revy Analytics + UX de leitura de resultados.
> **Não** reimplementar E8/E10 MVP nem campanhas/ROI já em `main` (`8e7ec5f`).

**Status:** **DONE NO ESCOPO / GOOGLE MOVIDO AO CONTROL** — eixo **C · CRM dono**
**Detalha / estende:** `#3B` Task 4; **E10**; **E8** (insights + UX gastos + leitura de ROI); event bus.
**Não implementa:** E9 redes; Ad Manager; TikTok Events API; **API de spend**.
**Depende de:** campanhas + ROI (feito), CAPI Purchase MVP (feito), first/last + fbclid/gclid (feito).

**Goal:** O dono (1) confia no Purchase Meta, (2) lança gastos com UX boa, (3) **enxerga resultado em 30s no dashboard**, (4) vê funil/insights/drill-down, (5) publica `purchase` para Meta e projeta a venda ao Control, (6) completa checklist de medição na 1ª semana.

**Architecture:** Portal dono de métricas, gastos e conversões outbound. Camada de **leitura** (`resultados_dono.py` ou helpers em `roi_calc`) agrega ROI por canal/período e alertas sem duplicar SQL solto nas views. `confirm_sale` → `publish_conversion` → adapters. Design visual alinhado a `docs/nao-plano/brand/revy-brand-kit.md` (sem neon/gradiente “IA”; métricas honestas).

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, Jinja2, pytest, httpx; CSS do Portal (`app.css` + blocos scoped no template quando necessário). Google pertence agora ao plano do Control.

---

## O que é “apenas UX” vs integração

Isto responde direto à pergunta *“o que seria apenas UX? eu gostaria disso”*.

| Item | Tipo | O que o dono vê | Backend |
|---|---|---|---|
| **Canais extras** (TikTok, OLX…) no select | **Só UX + enum** | Rótulo na campanha / ROI | String validada; **sem API** |
| **Insights no ROI** | **Só UX + cálculo** | Frases (“ROAS 11,8…”) | Função pura; **sem API** |
| **Gastos em lote** (1 tela, N campanhas) | **Só UX** | Preenche a semana de uma vez | Continua `CampanhaGasto` |
| **Import CSV de gastos** | **UX + parse de arquivo** | Sobe planilha | Mesmas rows; **sem OAuth Ads** |
| **Bloco Resultados no dashboard** | **Só UX** | 30s: gasto → vendas → ROAS por canal | Agrega ROI existente |
| **Alertas de dado / tráfego** | **Só UX** | Faixa no topo: sem gasto, venda sem UTM, CAPI falhou | Queries leves |
| **Drill-down da campanha** | **Só UX** | História: funil + últimas vendas + gastos | Join leads/vendas |
| **Onboarding medição** | **Só UX** | Checklist 5 passos até “medindo de verdade” | Flags derivados |
| Status “último Purchase” na Tráfego | UX sobre integração | Verde/vermelho | Outbox já existe |
| **Event bus** | **Arquitetura** | Quase invisível | Refator + testes |
| **Google Conversions** | **Movido ao Control** | Resultado comercial treina Ads | OAuth, leitura e upload fora do Portal |
| API **puxar spend** do Ads | Integração pesada | Gasto sozinho | **Fora deste plano** |
| TikTok Events API | Integração | Idem Meta | **Parked** |

### Resumo do que você pediu

| Pedido | Entra no plano? | Natureza |
|---|---|---|
| Melhor UX de gastos | **Sim** — lote + CSV (**E**) | **Apenas UX** |
| Insights ROI | **Sim** (**D**) | **Apenas UX** |
| Resultados no dashboard | **Sim** (**H1**) | **Apenas UX** + design |
| Alertas operacionais | **Sim** (**H2**) | **Apenas UX** |
| Drill-down campanha | **Sim** (**H5**) | **Apenas UX** |
| Onboarding medição | **Sim** (**H9**) | **Apenas UX** |
| Event bus | **Sim** (**F**) | Arquitetura |
| Google conversion | **Sim, no Control** (**G movida**) | Integração API |
| Puxar gasto via API | **Não** (parked) | Não é UX |
| TikTok API | **Não** ainda | Parked |

O fluxo **1 gasto por campanha** (`/app/campanhas/{id}`) **permanece** como fallback; a UX nova **adiciona** caminhos melhores, não remove o antigo.

---

## Global Constraints

- **Multi-loja:** filtrar sempre por `loja_slug` / `loja_id`.
- **RBAC:** dono/gerente: tráfego, gastos, tokens, ROI, funil. Vendedor: origem no lead; **sem** token nem editar gasto.
- **Sem Ad Manager:** não criar/pausar anúncios.
- **Gasto:** modelo `CampanhaGasto` inalterado em conceito (`valor`, `referencia`, `nota`, `campanha_id`). UX = como o dono **entra** esses dados.
- **Sem API de spend** neste plano (não sincronizar custo do Ads Manager via Marketing API).
- **Atribuição honesta:** first/last; sem multi-touch causal.
- **Money:** `Decimal` + centavos.
- **Outbound conversions:** falha Meta/Google **nunca** quebra confirmação de venda.
- **Event bus:** `confirm_sale` não chama redes direto; só `publish_conversion(...)`.
- **E9 fora.** **TDD.** UI em **português BR**.
- **Não substitui** go-live WhatsApp (eixo A).

---

## Contexto do que já existe (não reimplementar)

| Peça | Onde | Estado |
|---|---|---|
| Pixel browser + `event_id` | `catalogo-publico` | Feito |
| CAPI Purchase + outbox 1 tentativa | `meta_capi.py` | MVP |
| Config `/app/trafego` | Portal | Feito |
| Campanhas + `CampanhaGasto` + ROI | Portal | Feito |
| Gasto 1-a-1 no detalhe da campanha | `campanhas/detalhe.html` | Feito (fallback) |
| First/last, fbclid, gclid | Chatbot + catálogo | Feito |
| Funil contagens básicas | `funil_periodo` | Feito (sem eventos/tempo) |
| `CANAIS_ROTULO` | meta, google, indicacao, organico, outro | Feito |
| Guia loja | `docs/nao-plano/tutoriais/trafego-pago-loja.md` | Feito |

---

## Decisões de produto (rev. 3)

| Tema | Decisão |
|---|---|
| UX gastos | **Lote + CSV** (**E**); 1-a-1 permanece |
| Insights ROI | **D** |
| **Resultados no dashboard** | **H1** — bloco no `/app` |
| **Alertas** | **H2** — faixa no dashboard |
| **Drill-down campanha** | **H5** |
| **Onboarding medição** | **H9** — checklist dismissível |
| API spend | **Fora** |
| Funil eventos | **C** |
| Event bus + Meta | **F** |
| Google Conversions | **G** |
| TikTok Events API | **Parked** |
| Design bloco resultados | Spec em **Fase H — Design** (brand kit Revy) |

---

## Fases e LOE

| Fase | Nome | Tipo | LOE |
|---|---|---|---|
| **A** | CAPI Meta residual | Integração polish | S–M |
| **B** | Canais extras | **Só UX** | XS |
| **E** | UX gastos: lote + CSV | **Só UX** (item 4 entrada) | S–M |
| **D** | Insights no ROI | **Só UX** (item 4 leitura) | S |
| **H** | UX resultados dono (1, 2, 5, 9) | **Só UX** + design | M |
| **C** | Funil eventos e tempos | Feature CRM | M |
| **F** | Event bus + adapter Meta | Arquitetura | M |
| **G** | Google Conversions | Integração API | L–XL |

**Ordem:** `A → B → E → D → H → C → F → G`

```text
A  Meta confíavel
B  Canais
E  Gastos lote + CSV     ← item 4 (entrada)
D  Insights ROI          ← item 4 (leitura)
H  Resultados no dashboard
   H1  bloco Resultados da semana/mês
   H2  alertas
   H5  drill-down campanha
   H9  onboarding medição
C  Funil
F  Event bus
G  Google
```

**Dependências H:** H1/H2 usam ROI atual; melhoram após E+D. H5 usa vendas+gastos. H9 usa CAPI após A; Google segue o plano do Control.

---

## Mapa de arquivos

| Arquivo | Fases | Papel |
|---|---|---|
| `app/meta_capi.py` | A, F | match/retry; MetaAdapter |
| `app/conversions/*` | F | bus + adapters atuais |
| `app/models.py` | C, H9 | FunilEvento; flag dismiss onboarding se server-side |
| `app/campanhas.py` | B, E, H5 | canais; lote/CSV; detalhe |
| `app/roi_calc.py` | D, H1 | insights; por canal |
| `app/resultados_dono.py` (novo) | H | `resumo_periodo`, `alertas_trafego`, `checklist_medicao` |
| `app/funil_eventos.py` | C | eventos |
| `app/main.py` | todas | rotas |
| `app/static/css/app.css` | H | resultados / alertas / checklist |
| `templates/dashboard.html` | H1, H2, H9 | |
| `templates/partials/resultados_periodo.html` | H1 | partial |
| `templates/partials/alertas_trafego.html` | H2 | |
| `templates/campanhas/detalhe.html` | H5, E | drill-down |
| `templates/campanhas/gastos_lote.html` | E | |
| `templates/trafego/form.html` | A, G | |
| `templates/trafego/roi.html` | D | |
| `templates/funil/dashboard.html` | C | |
| `tests/test_resultados_dono.py` | H | |
| `tests/test_*` | demais | |

---

## Fase A — CAPI Meta residual

### Aceite

- Purchase com `ph` (hash telefone) quando lead resolvível.
- `fbclid`/`fbc` quando houver no lead.
- `event_id` estável `purchase-{venda_id}`.
- Confirmar venda nunca quebra se CAPI falhar.
- Retry de `pending`/`failed` (botão na Tráfego).
- UI: último envio (status, erro truncado) sem expor token.

### Tasks

- [x] **A1** Testes + enrich telefone (e email opcional) em `montar_payload_purchase` / enqueue best-effort via `lead_ref`.
- [x] **A2** fbclid/fbc no payload quando disponível.
- [x] **A3** `processar_outbox_pendentes` + POST retentar + métricas na `trafego/form.html`.
- [x] Entrega consolidada: CAPI match e retry na aba Tráfego.

---

## Fase B — Canais extras (**só UX**)

### Aceite

Novos valores em `CANAIS_ROTULO`: `tiktok`, `olx`, `marketplace`, `facebook_marketplace` (+ atuais). Validação rejeita desconhecido. ROI só exibe o rótulo.

### Tasks

- [x] **B1** Estender `CANAIS_ROTULO` + testes form + parágrafo em `trafego-pago-loja.md`.
- [x] Entrega consolidada: canais TikTok/OLX/Marketplace no cadastro.

---

## Fase E — UX de gastos: lote + CSV (**só UX**)

### Objetivo

Parar de obrigar o dono a abrir N campanhas. **Mesmo** `CampanhaGasto`; entrada melhor.

### E1 — Lançamento em lote

**Rota:** `GET/POST /app/campanhas/gastos/lote` (dono/gerente).

**UI:**

- Data de referência única (default: hoje).
- Tabela: campanhas **ativas** da loja | input valor (vazio = pular) | nota opcional global ou por linha.
- Submit cria um `CampanhaGasto` por linha com valor > 0.
- Link a partir de lista de campanhas e/ou ROI: “Lançar gastos da semana”.

**Aceite:**

- 3 campanhas, 2 com valor → 2 rows; a terceira intacta.
- CSRF + RBAC.
- Valores BRL com `parse_brl_valor` (mesmo do detalhe).
- Detalhe da campanha **continua** aceitando gasto unitário.

### E2 — Import CSV (template Revy)

**Formato canônico (UTF-8, `;` ou `,` detectado):**

```text
utm_campaign;valor;referencia;nota
seminovos-julho;1200,00;2026-07-14;semana 2
fan-160-google;800;2026-07-14;
```

- Match campanha: `utm_campaign_norm` da loja (mesmo normalizar do ROI).
- Linha sem match → erro listado; **não** aborta as linhas ok (ou dry-run: preferir **transação por linha** com relatório final “2 ok, 1 erro”).
- Sem criar campanha automática no MVP (erro: “cadastre a campanha primeiro”).
- Download de template vazio em `/app/campanhas/gastos/csv/modelo`.

**Aceite:**

- CSV válido cria gastos; utm desconhecido aparece no resumo de erros.
- Não é export do Ads Manager genérico na v1 (só template Revy) — documentar no guia.

### Tasks

- [x] **E1.1** Testes lote (2 gastos, skip vazio, RBAC).
- [x] **E1.2** Rotas + template `gastos_lote.html` + nav.
- [x] **E2.1** Testes parse CSV (ok + utm inválido + valor inválido).
- [x] **E2.2** Upload + modelo download + doc guia.
- [x] Entrega consolidada: lançamento em lote e import CSV de gastos de mídia.

### Fora da Fase E

- OAuth / Insights API para puxar spend.
- Editar/apagar gasto em massa (só se já existir delete unitário; não expandir).

---

## Fase D — Insights no ROI (**só UX**)

### Aceite

`gerar_insights_roi(linhas, totais, ...) -> list[str]` puro; 3–8 frases; sem LLM; bloco no topo de `/app/trafego/roi`.

Templates (omitir se zero):

- melhor ROAS com gasto e vendas;
- comparação de conversão (vendas/leads) entre 2 canais;
- N ativas sem gasto no período;
- linha “sem campanha” se existir.

### Tasks

- [x] **D1** Testes + função + template ROI.
- [x] Entrega consolidada: insights automáticos no dashboard ROI.

---

## Fase C — Funil de eventos e tempos (#3B Task 4)

### Tipos mínimos

`lead_criado`, `primeira_resposta`, `simulacao_solicitada` (se dado), `etapa_manual`, `venda_registrada`, `venda_confirmada`, `perda` (se status existir).

Campos: `id`, `loja_slug`, `lead_ref`, `tipo`, `ocorrido_em`, `ator_email?`, `payload_json?`, `idempotency_key` UNIQUE com loja.

### Fonte

Portal emite o que controla (vendas, etapa manual); materializa `lead_criado` / `primeira_resposta` via API Chatbot quando possível. Sem ler Postgres do Chatbot.

### Aceite

Idempotência; UI `/app/funil` (ou seção) com etapas + tempo lead→venda; vazio não inventa dados; testes com timestamps fixos.

### Tasks

- [x] **C1** Model + migration + `registrar_evento` idempotente.
- [x] **C2** Emissores em venda/etapa.
- [x] **C3** Materialização sanitizada a partir do Chatbot (best-effort).
- [x] **C4a** Agregações + endpoint backend protegido `/app/funil/dados`.
- [x] **C4b** UI `/app/funil`, RBAC dono/gerente, período, coorte, etapas, tempos e empty state.
- [x] Entrega consolidada da Fase C; #3B Task 4 marcada como DONE.

---

## Fase F — Event bus + adapter Meta

### Objetivo

`confirm_sale` deixa de importar `enfileirar_purchase_venda` como efeito colateral solto. Publica conversão; Meta (e depois Google) escutam.

### Desenho mínimo

```text
# app/conversions/types.py
@dataclass
class PurchaseConversion:
    loja_slug: str
    venda_id: str
    event_id: str          # purchase-{venda_id}
    value: Decimal
    currency: str          # BRL
    lead_ref: str | None
    phone: str | None
    email: str | None
    fbclid: str | None
    gclid: str | None
    # ...

# app/conversions/bus.py
def publish_conversion(kind: str, payload: PurchaseConversion, db: Session) -> None:
    for adapter in adapters_habilitados(db, payload.loja_slug):
        adapter.handle(kind, payload, db)  # cada um: try/except, outbox, nunca propaga
```

- Adapter Meta: move/adapta lógica atual de `meta_capi.enfileirar_purchase_venda`.
- Teste: mock 2 adapters → ambos `handle` chamados; um lança → outro ainda roda; venda já commitada.
- Compat: se config Meta ausente, no-op (como hoje).

### Aceite

- Um único ponto de disparo no fluxo de confirmação de venda.
- Testes de bus sem rede.
- Comportamento Meta equivalente ao pós-Fase A (regressão CAPI).

### Tasks

- [x] **F1** types + bus + teste multi-adapter.
- [x] **F2** MetaAdapter; `main` usa só `publish_conversion`; call direta preservada só como compatibilidade.
- [x] **F3** Garantir testes CAPI/A ainda passam.
- [x] Entrega consolidada: event bus de conversões com adapter Meta.

---

## Fase G — Google Ads Conversions — movida

Esta fase não deve mais ser implementada no Portal. A separação do Revy Tráfego e a
arquitetura atual do Google mudaram sua fronteira:

- OAuth, contas, métricas, saúde e mapeamento ficam no **Revy Control**;
- Google Ads API faz leitura; Data Manager API recebe as conversões;
- o Revy Loja apenas publica o evento comercial versionado;
- configuração técnica não é responsabilidade de dono/gerente no Portal.

Implementar somente pela
[Fase 4 do plano Revy Control](2026-07-29-plano-revy-control.md#fase-4--google-ads-conexão-leitura-e-conversões)
e pela
[pesquisa oficial](../research/2026-07-29-google-ads-revy-control.md).

---

## Fase H — UX de resultados do dono (itens 1, 2, 5, 9)

> Item **4** = fases **E** (lote/CSV) + **D** (insights). Não duplicar tasks aqui; H **consome** esses dados no dashboard.

**RBAC:** bloco H1, alertas H2 e checklist H9 só para **dono/gerente** (`pode_gerir_trafego` ou `pode_ver_financeiro` — preferir quem já vê ROI). Vendedor no `/app` **não** vê gasto/ROAS (mantém home de estoque como hoje).

---

### Design system do bloco (obrigatório na implementação)

Referência: `docs/nao-plano/brand/revy-brand-kit.md` + tokens já em `app/static/css/app.css` (`--ink`, `--paper`, `--surface`, `--line`, `--green`, `--amber`, `--ink-muted`, `--radius`, `--shadow`).

| Princípio | Aplicação |
|---|---|
| **Sério, não dashboard de startup** | Sem gradiente neon, glow, confetti, “IA” |
| **Números grandes, labels curtos** | `strong` ~24–28px; label uppercase 11px tracking |
| **Uma ideia por card** | Canal ou KPI isolado; não lotar |
| **Honestidade** | Se gasto=0 → ROAS “—” e texto “Lance o gasto para ver ROAS”; nunca inventar |
| **Mobile** | Cards empilham 1 col &lt;560px; 2 col tablet; row desktop |
| **Ações óbvias** | Botões secundários: “Lançar gastos” · “ROI completo” · “Campanhas” |
| **Copy BR de loja** | “Custo por moto” ao lado de CPA; “Cada R$1 virou R$X” sob ROAS |

#### Wireframe H1 — bloco no `/app` (abaixo do heading, **acima** do grid de estoque)

```text
┌─ alertas (H2), se houver ─────────────────────────────────────┐
│ ⚠ 2 campanhas ativas sem gasto · 3 vendas sem UTM    [ver]   │
└───────────────────────────────────────────────────────────────┘

┌─ Resultados do tráfego ────────────────── [7 dias ▾] [ROI →] ─┐
│  eyebrow: TRÁFEGO PAGO · h2: Resultados                       │
│  sub: 14/07 – 20/07 · last touch · gastos lançados no Revy    │
│                                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ Gasto    │ │ Leads    │ │ Motos    │ │ ROAS     │         │
│  │ R$ 5,2k  │ │ 84       │ │ 12       │ │ 9,4 x    │ highlight│
│  │ no Revy  │ │ c/ UTM   │ │ vendidas │ │ R$1→R$9,4│         │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
│                                                               │
│  Por canal                                                    │
│  ┌─ Meta ─────────────┐ ┌─ Google ──────────┐ ┌─ Outros ───┐ │
│  │ R$ 3,2k · 9 motos  │ │ R$ 2,0k · 3 motos │ │ —          │ │
│  │ ROAS 8,4           │ │ ROAS 12,1         │ │            │ │
│  │ ████████░░         │ │ ██████████        │ │            │ │
│  └────────────────────┘ └───────────────────┘ └────────────┘ │
│                                                               │
│  Melhor campanha  Fan 160 Julho · ROAS 11,8 · 5 vendas  [→]   │
│  ─────────────────────────────────────────────────────────── │
│  [ Lançar gastos ]  [ Ver ROI ]  [ Campanhas ]                │
└───────────────────────────────────────────────────────────────┘

┌─ checklist medição (H9) se incompleto ────────────────────────┐
│ Medindo de verdade?  ●●●○○ 3/5                                │
│ ☑ Pixel  ☑ Campanha+UTM  ☐ Gasto  ☐ Venda c/ lead  ☐ Purchase│
│                              [Dispensar] [Continuar setup]    │
└───────────────────────────────────────────────────────────────┘

… resto do dashboard (estoque) …
```

#### CSS / componentes (nomes sugeridos)

```css
/* app.css — prefixo revy-results para não colidir */
.revy-results { /* panel com border --line, radius, shadow leve */ }
.revy-results__hero { display: grid; gap: 12px; grid-template-columns: repeat(4, 1fr); }
.revy-results__kpi { /* igual .roi-card do roi.html — reutilizar padrões */ }
.revy-results__kpi--accent { background: var(--ink); color: var(--paper); }
.revy-results__channels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.revy-results__channel { /* surface; barra ROAS como .roas-bar */ }
.revy-results__best { /* linha com borda top; link para detalhe campanha */ }
.revy-alert-strip { /* amber soft bg; border left 3px amber; lista compacta */ }
.revy-onboarding { /* panel; progress dots; checklist com check verde */ }
```

Reutilizar estilos de `trafego/roi.html` (`.roi-card`, `.roas-bar`) via classes compartilhadas em `app.css` se possível — **não** copiar CSS só no dashboard.

#### Empty states

| Situação | UI |
|---|---|
| Nenhuma campanha | “Cadastre a primeira campanha com UTM” + CTA Campanhas |
| Campanhas sem gasto | KPIs de leads/vendas ok; ROAS “—”; CTA “Lançar gastos” em destaque |
| Chatbot offline | Bloco mostra gasto/vendas locais; leads “—” + alert “Chatbot offline” |
| Vendedor | Bloco **omitido** (não vazio genérico) |

---

### H1 — Bloco “Resultados” no dashboard (`/app`)

**Objetivo:** em &lt;30s o dono vê se o anúncio pagou a conta.

**Dados (período default: últimos 7 dias, timezone do Portal):**

- Totais: gasto, leads atribuídos, vendas confirmadas atribuídas, ROAS, (opcional) faturamento
- Por `canal` (meta / google / demais agrupados em “Outros” se &lt;3 canais com gasto)
- “Melhor campanha” = maior ROAS com gasto&gt;0 e vendas&gt;0; senão mais vendas
- Toggle ou links: **7 dias** | **Este mês** (query `?resultados=7d|mes`)

**Implementação:**

- `resultados_dono.resumo_periodo(...)` puro, reusando `calcular_roi_loja` / `totais_roi`
- `dashboard()` em `main.py` só monta contexto se `pode_gerir_trafego`
- Partial Jinja incluído em `dashboard.html`

**Aceite:**

- [x] Dono vê bloco; vendedor não.
- [x] Com fixture de campanhas/gastos/vendas, números batem com `/app/trafego/roi` mesmo período.
- [x] Empty states conforme tabela.
- [x] Layout responsivo sem overflow horizontal no bloco.
- [x] Entrega consolidada: bloco Resultados de tráfego no dashboard do dono.

---

### H2 — Alertas operacionais

**Faixa** no topo do dashboard (e opcionalmente no ROI), só se houver itens.

| Código | Condição | Copy | CTA |
|---|---|---|---|
| `campanhas_sem_gasto` | Ativas com gasto 0 no período do bloco | “{n} campanha(s) ativa(s) sem gasto no período” | Lançar gastos |
| `vendas_sem_utm` | Confirmadas no período sem lead/campanha match | “{n} venda(s) sem campanha no ROI” | Relatório/vendas |
| `leads_sem_utm` | (se chatbot ok) leads período sem utm_campaign | “{n}% dos leads sem UTM” | Guia / campanhas |
| `capi_falhou` | Último outbox Meta `failed` | “Purchase Meta falhou — retentar na Tráfego” | `/app/trafego` |
| `pixel_nao_config` | Sem pixel_id ou token | “Configure o Pixel para fechar o ciclo” | `/app/trafego` |

**Regras:** máx. 4 alertas; priorizar capi/pixel &gt; vendas sem utm &gt; sem gasto. Sem alertas → não renderiza a faixa.

**Aceite:**

- [x] Testes unitários por condição.
- [x] UI `revy-alert-strip` acessível (`role="status"`).
- [x] Entrega consolidada: alertas de tráfego no dashboard.

---

### H5 — Drill-down da campanha

**Onde:** enriquecer `GET /app/campanhas/{id}` (detalhe já existe com gastos).

**Seções novas (ordem visual):**

1. **Hero da campanha** — nome, canal chip, status, utm_campaign monoespaçado, período
2. **KPIs do período** (default mês atual ou query) — gasto, leads, vendas, ROAS, CPA (mesma matemática ROI)
3. **Mini-funil** — leads → (sims se dado fácil) → vendas; se sim não disponível, só leads/vendas
4. **Últimas vendas** — tabela: data, descrição/moto, valor, vendedor; só confirmadas com match da campanha
5. **Gastos** — lista atual + link “Lançar em lote”
6. **Ações** — copiar URL exemplo catálogo com UTMs pré-preenchidos (se base URL configurável ou placeholder)

**Aceite:**

- [x] Vendas listadas batem com ROI da campanha no mesmo período.
- [x] Campanha sem vendas: empty “Nenhuma venda atribuída neste período”.
- [x] Entrega consolidada: drill-down de resultados no detalhe da campanha.

---

### H9 — Onboarding “Medindo de verdade”

**Checklist de 5 passos** (derivado, não workflow externo):

| # | Passo | Done quando |
|---|---|---|
| 1 | Pixel / CAPI configurado | `MetaPixelConfig` com pixel_id + token (ou purchase off explícito documentado) |
| 2 | Campanha com UTM | ≥1 campanha ativa com `utm_campaign` |
| 3 | Gasto lançado | ≥1 `CampanhaGasto` da loja |
| 4 | Venda com lead | ≥1 venda confirmada com `lead_ref` não vazio |
| 5 | Purchase enviado | ≥1 outbox Meta `delivered` (ou skipped se purchase desligado — aí passo 5 = “Purchase desligado”) |

**UI:** card no dashboard (dono) enquanto `completo &lt; 5` e não dismissado.
**Dismiss:** POST com CSRF; persistir em cookie assinado **ou** coluna em config Meta/loja (`medicao_onboarding_dismiss_em`). Preferir **server** se já houver config por loja.

**Aceite:**

- [x] Progresso 3/5 renderiza checks corretos com fixture.
- [x] Dismiss esconde; não bloqueia uso.
- [x] CTA “Continuar setup” vai ao próximo passo pendente (tráfego / campanhas / gastos / vendas).
- [x] Entrega consolidada: checklist de onboarding de medição de tráfego.

---

### Tasks H (checklist)

- [x] **H0** `resultados_dono.py` + testes puros (resumo, alertas, checklist).
- [x] **H1** Bloco no `dashboard.html` + CSS + design spec acima.
- [x] **H2** Alertas no dashboard.
- [x] **H5** Detalhe campanha com KPIs + vendas.
- [x] **H9** Checklist + dismiss.
- [x] **H-doc** Uma seção em `trafego-pago-loja.md`: “Como ler o bloco Resultados”.

---

## Parked / fora

| Item | Motivo |
|---|---|
| TikTok Events API | Mesmo bus; só com spend real em TikTok |
| API spend (auto custo Ads) | Não é UX; LOE alto; match campaign id |
| Multi-touch / DDA Google | Fora do núcleo |
| LLM insights | Templates bastam |
| E9 social | Fora do core |
| Criar anúncios no Revy | Fora |

---

## Critério de DONE (rev. 3)

- [x] **A** CAPI match + retry + status UI
- [x] **B** Canais extras
- [x] **E** Lote + CSV de gastos (1-a-1 ainda funciona)
- [x] **D** Insights ROI
- [x] **H1** Bloco Resultados no dashboard (design + números = ROI)
- [x] **H2** Alertas operacionais
- [x] **H5** Drill-down campanha (KPIs + vendas)
- [x] **H9** Onboarding medição dismissível
- [x] **C** Eventos, tempos, materialização, endpoint e UI `/app/funil`; #3B T4 concluída
- [x] **F** Event bus; fluxo principal publica Meta só via adapter
- [x] **G movida** para a Fase 4 do Revy Control; não implementar no Portal
- [x] Guia Google passa a pertencer à entrega do Revy Control
- [x] **Sem** API de spend; **sem** TikTok API

---

## Referências

- [Tráfego pago DONE](2026-07-20-plano-trafego-pago-crm-campanhas-roi.md)
- [Plano #3B](2026-07-11-plano3b-dashboard-dono-vendas-metas.md)
- [Plano #6](2026-07-11-plano6-evolucoes-roadmap.md)
- [Brand kit](../../nao-plano/brand/revy-brand-kit.md)
- [Guia loja](../trafego-pago-loja.md)
- [Plano Revy Control](2026-07-29-plano-revy-control.md)
- [Pesquisa Google](../research/2026-07-29-google-ads-revy-control.md)
- [Contexto](../contexto-compacto.md)

---

## Notas para o implementador

1. Não misturar com go-live WA / site / novo banco na mesma PR.
2. Fase E **não** puxa spend de API.
3. **H** não inventa métrica: só reutiliza `roi_calc` / vendas / outbox.
4. Design H: copiar linguagem visual do ROI (`roi-card`), não inventar tema paralelo.
5. F antes de G.
6. Nunca logar tokens nem PII em claro.
7. Graph API: manter versão já em `meta_capi.py`.
