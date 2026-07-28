# Design — Revy Tráfego separado do Portal da loja

**Data:** 2026-07-28  
**Status:** Aprovado (brainstorming) — aguardando execução dos planos  
**Eixo:** C · CRM / marketing (evolução pós campanhas+ROI DONE)

## Problema

Hoje o **portal-gestao** mistura, no mesmo produto e nos mesmos papéis `dono`/`gerente`:

1. **Operação da loja** — leads, vendas, estoque, simulações, equipe.
2. **Operação de tráfego pago** — Pixel/CAPI, conta Ads, sync de gasto, CRUD de campanhas (UTM, ID Meta, código CTWA), auditorias Pixel/CTWA, ROI detalhado.

O dono da loja não precisa (e não deveria) lidar com tokens, IDs da Meta e auditoria de match quality. A equipe Revy, que opera o tráfego de **várias lojas**, precisa de um cockpit multi-loja com config + resultados + diagnóstico.

## Objetivo

Separar em dois produtos com fronteiras claras:

| Produto | Quem usa | Responsabilidade |
|---|---|---|
| **Revy Tráfego** (`revy-trafego`) | Equipe Revy (agência interna) | Config técnica, campanhas, gastos, ROI, auditorias, diagnóstico de leads/conversas |
| **Portal da loja** (`portal-gestao`) | Dono, gerente, vendedor | CRM + **resultados de negócio** (mesmas métricas de mídia, UI limpa, sem técnico) |

## Decisões fechadas (brainstorming)

| # | Decisão |
|---|---|
| D1 | Gestor de tráfego = **equipe Revy** (não funcionário da loja, não agência externa no MVP). |
| D2 | No portal da loja sobra **só resultados de negócio** de mídia (gasto, leads, vendas, CPL, CPA, ROAS). Sem Pixel, CAPI, IDs Meta, auditoria, CRUD de campanha. |
| D3 | Produto do gestor = **app separado** (deploy, login e URL próprios). |
| D4 | **Fonte da verdade de mídia** migra para o Revy Tráfego (médio prazo). Portal **consome** resultados via API. |
| D5 | **Resultados existem nos dois apps**: gestor precisa saber se está dando certo; cliente vê as **mesmas métricas**, UI diferente. |
| D6 | Cálculo de ROI é **único** (no Revy Tráfego no alvo). Portal não mantém fórmula paralela no destino final. |
| D7 | Acesso multi-loja: **todas as lojas** para qualquer gestor Revy autenticado (seletor simples). Sem atribuição por pessoa no MVP. |
| D8 | Diagnóstico **quase operacional**: gestor pode abrir lead/conversa (via API do Chatbot) para caçar bug de atribuição/CTWA. Não é um segundo CRM. |
| D9 | Primeiro entregável = **Fase 1** (strangler): extrair superfície técnica + multi-loja; portal slim; cutover total de DB/API em fases seguintes. |
| D10 | Abordagem de migração: **strangler** (não big bang). |

## Fora de escopo

- Criar/pausar anúncios na Meta ou Google pelo app.
- Google Conversions API (residual já existente no eixo C).
- Atribuição multi-touch avançada.
- Papel `gestor_trafego` **dentro** do portal da loja (substituído pelo app Revy).
- Atribuição de lojas por gestor (todos veem todas no MVP).
- App mobile.

## Arquitetura alvo

```text
Anúncio → Catálogo / WhatsApp → Lead (chatbot) → Venda (portal)
                │
                ▼
        ┌───────────────────────────────┐
        │  revy-trafego                 │  equipe Revy · multi-loja
        │  fonte da verdade de mídia    │
        │  Pixel/CAPI/Ads · campanhas   │
        │  spend · ROI · auditoria      │
        └───────────────┬───────────────┘
           ▲            │ GET resultados
           │            │ (mesmas métricas)
           │ POST       ▼
           │ venda   portal-gestao (loja)
           │         só negócio + cards ROI
           │
  catalogo GET pixel
  chatbot  leads/conversas (diagnóstico)
  Meta     CAPI + Marketing API
```

### Direção das APIs (alvo)

| Fluxo | Direção | Propósito |
|---|---|---|
| Resultados no portal | Portal → `GET` Revy Tráfego | Cards e ROI da loja |
| Venda confirmada | Portal → `POST` Revy Tráfego | CAPI Purchase + ROI |
| Pixel no site | Catálogo → `GET` Revy Tráfego | Pixel ID público por loja |
| Diagnóstico lead | Revy Tráfego → Chatbot | Lista/detalhe lead e conversa |
| Spend / CAPI | Revy Tráfego → Meta | Como hoje no portal |

### Auth

- **Revy Tráfego:** usuários internos (tabela própria ou bootstrap por env). Papéis internos: `gestor` | `admin`. Sessão cookie HTTP-only. **Não** reutiliza login do dono da loja.
- **Serviço-a-serviço:** token compartilhado (`X-Service-Token` ou padrão já usado `X-Job-Token`) entre portal/catálogo e Revy Tráfego.
- **Chatbot:** Revy Tráfego usa o mesmo token de serviço que o portal já usa para listar leads/conversas.

### Multi-loja

- Toda query de domínio filtra por `loja_slug` quando no contexto de uma loja.
- UI: seletor global de loja (lista de slugs conhecidos — na Fase 1: distinct de campanhas/configs/vendas ou endpoint do portal; depois catálogo de lojas explícito).
- MVP: qualquer gestor autenticado acessa qualquer loja.

## Fronteira de produto (telas)

### Revy Tráfego — tem

- Login interno + seletor de loja.
- **Config Tráfego:** Pixel ID, token CAPI, test event code, flags de evento.
- **Config Ads:** Ad Account, token `ads_read`, sync spend, status última sync.
- **Campanhas:** CRUD, UTM, `meta_campaign_id`, `codigo_ctwa`, gastos manuais/CSV, vínculo Meta.
- **ROI / Resultados:** multi-loja e por loja; CPL, CPA, ROAS; drill-down por campanha/canal/período.
- **Auditorias:** Pixel/CAPI, CTWA.
- **Diagnóstico:** leads por campanha/período; detalhe de lead; conversa (proxy chatbot).
- Jobs: Meta spend sync, CAPI outbox worker (movidos do portal).

### Portal da loja — fica

- Leads, conversas, vendas, funil, estoque, simulações, metas, equipe, financeiras, grupo estoque.
- **Resultados de mídia (somente leitura):** gasto, leads atribuídos, vendas, CPL, CPA, ROAS, melhor campanha, por canal — **mesmas métricas** do gestor, UI limpa, **só a loja do usuário**.
- Permissão **separada** da config: `pode_ver_resultados_midia` (dono/gerente) ≠ `pode_gerir_trafego` (False no portal após Fase 1). O partial `resultados_periodo.html` hoje exige `pode_gerir_trafego` — isso **deve mudar** no slim, senão o dono perde o bloco.
- Confirmar/cancelar venda (continua no portal; notifica Revy Tráfego no alvo).

### Portal da loja — remove (menu e rotas de escrita)

- `/app/trafego` (formulários Pixel/CAPI/Ads).
- `/app/trafego/pixel-auditoria`, `/app/trafego/ctwa-auditoria`.
- `/app/campanhas` (CRUD e lançar gastos).
- Links de checklist de medição que apontam para config técnica (substituir por texto “fale com a Revy” ou omitir passos técnicos).
- Alertas técnicos do dono (ex.: “retente CAPI na aba Tráfego”) → só no Revy Tráfego; no portal no máximo alerta de negócio genérico (“medição incompleta”).

### ROI no portal

- Rota legada `/app/trafego/roi` **some** do menu do cliente.
- Conteúdo de resultados permanece na **Visão geral** (`/app`) e, se útil, em um único item **Resultados** somente leitura (`/app/resultados`) que consome a API do Revy Tráfego (ou dados locais na Fase 1).

## Modelo de dados

### Já existem no portal (a migrar conceitualmente)

- `meta_pixel_config`, `meta_ads_config`, `meta_capi_outbox` (e correlatos)
- `pixel_capi_auditoria`
- `campanhas`, `campanha_gastos`
- Snapshots em `vendas`: `campanha_id_first`, `campanha_id_last`
- Lógica: `campanhas.py`, `roi_calc.py`, `resultados_dono.py`, `meta_pixel.py`, `meta_capi*.py`, `meta_ads_spend*.py`, `pixel_capi_auditoria.py`

### Fase 1 (pragmática)

- Revy Tráfego **conecta no mesmo Postgres** do portal (mesmo schema) **ou** no mesmo `DATABASE_URL` com schema compartilhado.
- Objetivo da Fase 1: **superfície de produto + auth multi-loja**, não split físico de banco.
- Código de domínio de mídia é **extraído** para o app (cópia ou pacote compartilhado no monorepo — preferir **mover módulos** para `revy-trafego` e portal passar a depender de HTTP para escrita; leitura local ainda ok se tabelas compartilhadas).

### Fase 2 (fonte da verdade)

- Tabelas de mídia “pertencem” ao processo Revy Tráfego.
- Portal **não escreve** mais em `campanhas` / `meta_*`.
- Portal lê resultados só via API.
- Catálogo aponta Pixel para Revy Tráfego.
- Confirmação de venda no portal faz `POST /v1/lojas/{slug}/eventos/venda-confirmada`.

### Vendas e leads

- **Vendas** continuam no portal (CRM).
- **Leads** continuam no chatbot.
- Revy Tráfego **lê** vendas (DB compartilhado Fase 1, ou API portal Fase 2) e leads (HTTP chatbot) para ROI e diagnóstico.

## Contratos HTTP (alvo)

Base URL interna: `REVY_TRAFEGO_URL` (ex.: `http://revy-trafego:9010`).

### Públicos / edge

```http
GET /public/v1/lojas/{loja_slug}/pixel
→ { "pixel_id": "...", "enabled": true }
```

(Mesmo contrato que o portal expõe hoje em `/public/v1/lojas/{slug}/pixel`.)

### Serviço (token)

```http
GET /v1/lojas/{loja_slug}/resultados?periodo=7d|mes&inicio=&fim=
→ {
  "periodo": {...},
  "totais": { "gasto", "leads", "vendas", "faturamento", "cpl", "cpa", "roas" },
  "canais": [...],
  "melhor_campanha": {...} | null,
  "campanhas": [ { "id", "nome", "canal", "gasto", "leads", "vendas", "cpl", "cpa", "roas" } ]
}

GET /v1/lojas/{loja_slug}/resultados/campanhas?periodo=...

POST /v1/lojas/{loja_slug}/eventos/venda-confirmada
Body: {
  "venda_id", "lead_ref", "valor", "moeda",
  "campanha_id_first", "campanha_id_last",
  "telefone_hash_or_e164", ... campos necessários ao CAPI
}
→ { "ok": true, "outbox_id": "..." }
```

Fórmulas (inalteradas em relação ao ROI atual):

- **CPL** = gasto / leads (0 leads → null / “—”)
- **CPA** = gasto / vendas
- **ROAS** = faturamento / gasto (0 gasto → null)
- Match: `utm_campaign_norm` + loja; first/last touch como hoje.

## Segurança e PII

- Tokens CAPI e Ads: ciphertext no servidor (reusar `cripto.py` do portal).
- Listagens de auditoria: telefone mascarado quando possível.
- Detalhe de lead/conversa no Revy Tráfego: acesso autenticado gestor; **audit log** recomendado (`quem`, `loja`, `lead_id`, `quando`) na Fase 1 ou 1.1.
- Multi-tenant: nunca cruzar `loja_slug` sem filtro.

## Migração em fases

### Fase 1 — App + multi-loja + slim do portal (primeiro entregável)

1. Scaffold `revy-trafego/` (FastAPI, Jinja2, Alembic se necessário, pytest, Dockerfile).
2. Auth interna Revy + seletor de loja (todas as lojas).
3. Portar rotas/templates de tráfego, campanhas, ROI, auditorias e jobs.
4. Diagnóstico: proxy leads/conversas do chatbot no contexto da loja.
5. Portal: remover menus/rotas de escrita técnica de tráfego para dono/gerente.
6. Portal: manter resultados na visão geral (cálculo local se DB compartilhado; ou client HTTP se API mínima já existir).
7. Deploy Fly/lab: serviço no bundle ou app irmão; env `REVY_TRAFEGO_*`.
8. Docs: atualizar `trafego-pago-loja.md` (cliente) + guia interno Revy.

**Critério de pronto Fase 1:** gestor Revy opera Pixel/campanhas/ROI multi-loja no app novo; dono da loja **não** vê menus técnicos; medição (CAPI/spend/pixel) **continua funcionando** (mesmo que jobs ainda rodem de um dos dois processos durante cutover controlado).

### Fase 2 — API de resultados + cutover de escrita

1. Expor API de resultados estável; portal passa a consumir só ela para cards ROI.
2. Mover workers CAPI/spend **definitivamente** para Revy Tráfego.
3. Catálogo: `PORTAL_PUBLIC_URL` → URL do Revy Tráfego para pixel (ou `REVY_TRAFEGO_PUBLIC_URL`).
4. Portal: `POST` venda-confirmada; remover outbox CAPI local se aplicável.
5. Remover código morto de config de tráfego do portal.

**Critério de pronto Fase 2:** uma única fonte de ROI; portal sem dependência de models `Campanha`/`MetaPixel*` para UI de resultados.

### Fase 3 (opcional / endurecimento)

- Split físico de schema/DB se custo operacional justificar.
- Atribuição de lojas por gestor.
- Audit log completo de PII.
- Catálogo de lojas primeiro-class no Revy Tráfego.

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| CAPI quebra na troca | Strangler: um processo único envia Purchase até cutover; testes de confirmação de venda |
| Dois ROIs divergentes | API única cedo; Fase 1 tolerar cálculo local só se DB compartilhado e **mesmo** `roi_calc` |
| Pixel do catálogo offline | Manter endpoint público com mesmo path; proxy ou DNS cutover |
| PII no app Revy | Auth forte; audit log; mascarar em listas |
| `main.py` do portal monólito | Extrair por rotas/módulos; não reescrever CRM |

## Mapa de arquivos (previsto)

### Novo: `revy-trafego/`

```text
revy-trafego/
  app/
    main.py
    auth.py              # usuários internos Revy
    config.py
    db.py
    models.py            # mídia (+ leitura vendas se shared DB)
    campanhas.py
    roi_calc.py
    resultados.py
    meta_pixel.py
    meta_capi.py
    meta_capi_messaging.py
    meta_ads_spend.py
    meta_ads_spend_job.py
    meta_capi_job.py
    pixel_capi_auditoria.py
    clients/chatbot.py
    clients/portal.py    # opcional Fase 2
    templates/           # trafego, campanhas, roi, auditoria, diagnostico
    static/
  alembic/               # se schema próprio; Fase 1 pode ser no-op se shared
  tests/
  Dockerfile
  requirements.txt
  README.md
```

### Portal (`portal-gestao/`)

- Remover/guardear rotas de escrita de tráfego.
- Nav: sem Tráfego/CTWA/Pixel/Campanhas para dono.
- Manter/ajustar `resultados_dono` + dashboard.
- Client HTTP `clients/revy_trafego.py` (Fase 1.5/2).
- Confirmação de venda: hook para notificar Revy Tráfego (Fase 2).

### Catálogo

- Config de URL de pixel aponta para Revy Tráfego após cutover.

### Docs

- Spec: este arquivo.
- Planos: `docs/plans/2026-07-28-plano-revy-trafego-separacao.md` (índice) + planos detalhados em `docs/superpowers/plans/`.
- Guia loja: só resultados.
- Guia interno Revy: setup multi-loja.

## Testes (estratégia)

- **Unit:** `roi_calc`, match campanha, normalização pixel/campaign id (portar testes existentes).
- **API:** resultados por loja; isolamento multi-tenant; auth service token.
- **Portal:** dono não acessa `/app/trafego` (403/redirect); vê resultados.
- **Revy Tráfego:** gestor acessa loja A e B; formulários salvam config por slug.
- **Regressão:** confirmar venda ainda enfileira CAPI (onde o worker estiver na fase).

## Critérios de sucesso do produto

1. Dono da loja entende “tráfego está gerando X leads / Y vendas / ROAS Z” sem ver token.
2. Gestor Revy configura e opera N lojas num app só.
3. Números de ROI **iguais** (mesma fórmula/fonte) nos dois lados no alvo.
4. Zero regressão de Pixel no catálogo e Purchase na venda em produção/lab.

## Planos de implementação

| Plano | Conteúdo |
|---|---|
| [Índice / roadmap](../../plans/2026-07-28-plano-revy-trafego-separacao.md) | Visão, fases, ordem, links |
| [Fase 1 detalhada](../plans/2026-07-28-revy-trafego-fase1-app-multi-loja.md) | Scaffold, auth, port de telas, slim portal, deploy |
| [Fase 2 detalhada](../plans/2026-07-28-revy-trafego-fase2-api-cutover.md) | API resultados, venda-confirmada, pixel cutover, limpeza |

---

*Documento gerado a partir do brainstorming 2026-07-28 no monorepo Revy/CRM.*
