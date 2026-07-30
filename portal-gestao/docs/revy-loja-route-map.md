# Revy Loja — Mapa de rotas e classificação de config (Fase 0)

**Data:** 2026-07-29  
**Escopo:** `portal-gestao`  
**Flags (default OFF):** `REVY_LOJA_SHELL_ENABLED`, `REVY_LOJA_ENTITLEMENTS_ENABLED`,
`REVY_LOJA_ATENDIMENTO_ENABLED`, `REVY_LOJA_REDIRECT_LEGACY`, `SELLER_AI_ENABLED`

Com as flags desligadas, a UI e as rotas legadas permanecem. Rollback = desligar flags
(e reverter deploy se necessário). Nenhuma rota legada é removida nesta fase.

## Navegação principal → destino Revy Loja

| Rota / item atual | Destino Loja | Fase | Notas |
|---|---|:---:|---|
| `/app` Visão geral | **Vendas → Visão geral** (`/app/loja/vendas` → `/app`) | 1 stub / 3 | Shell aponta para o dashboard atual |
| `/app/leads` | **Vendas → Atendimento** | 1 stub / 4 | Stub: `/app/loja/atendimento` → `/app/leads` |
| `/app/conversas` | **Vendas → Atendimento** | 4 | Workspace unificado |
| `/app/vendas` | **Vendas → Atendimento / Visão** | 3–4 | Registro/confirmação permanece |
| `/app/simulacoes` | Embutido em Atendimento | 4 | Não é módulo principal |
| `/app/funil` | **Vendas → Visão geral** | 3 | KPI/funil no overview |
| `/app/financeiro` | **Vendas → Visão geral** | 3 | Margem/receita no overview |
| `/app/relatorios` | **Vendas → Visão geral** | 3 | Export permanece acessível por URL |
| `/app/metas` | **Vendas → Visão geral** | 3 | |
| `/app/vendedor` | **Vendas → Visão geral** (escopo vendedor) | 3 | |
| `/app/estoque` | **Estoque → Veículos** (`/app/loja/estoque/veiculos`) | 1 / 2 | |
| `/app/estoque/*` CRUD | **Estoque → Veículos** | 2 | |
| Visão indicadores estoque | **Estoque → Visão geral** (`/app/loja/estoque`) | 2 | Stub F1 redireciona à lista |
| `/app/financeiras` | Config financeira contextual (dono/gerente) | 1 / 5 | No shell: Ajustes → Acessos bancários |
| `/app/loja/vendas/configuracoes-financeiras` | Alias → `/app/financeiras` | 5 | Shell on only |
| `/app/equipe` | Equipe view-only com shell on (estrutura no Control) | 5 | Mutações 403 com shell; legado com flag off |
| `/app/loja/equipe` | Lista read-only (nome, papel, ativo) | 5 | Shell on; Ajustes → Equipe |
| `/app/operacao/numeros` | **Control** (técnico WhatsApp/grupo) | Control | Não aparece no shell Loja |
| `/app/configuracoes` | Misto → Control / operacional | — | Ver classificação |
| `/app/trafego/*`, `/app/campanhas/*` | **Revy Tráfego / Control** | — | Fora do shell Loja |
| Login `/login`, logout | Shell / sessão | 1 | + `loja_slug` em sessão multi-loja |

### Redirects e stubs (F1)

| Nova rota | Comportamento |
|---|---|
| `GET /app/loja/vendas` | 303 → `/app` (se shell on + vendas ok) |
| `GET /app/loja/atendimento` | 303 → `/app/leads` |
| `GET /app/loja/estoque` | 303 → `/app/estoque` |
| `GET /app/loja/estoque/veiculos` | 303 → `/app/estoque` |
| `POST /app/loja/selecionar` | Troca `session["loja_slug"]` |

## Classificação de configurações

| Config / tela | Classe | Onde fica |
|---|---|---|
| Papéis / convites / multi-loja | **Estrutural** | Revy Control (projeção no Portal) |
| Módulos contratados Vendas/Estoque | **Estrutural** | Control → `LojaOperacionalProjecao` |
| Estado loja ativa/suspensa | **Estrutural** | Control → projeção |
| Pixel / CAPI / Ads / CTWA | **Técnica** | Revy Tráfego / Control |
| Campanhas, spend, ROI técnico | **Técnica** | Revy Tráfego |
| Tokens WhatsApp / Evolution / grupo estoque | **Técnica** | Control + Chatbot |
| Credenciais portais bancários | **Financeira** | Revy Loja (dono/gerente) |
| Metas comerciais | **Operacional** | Revy Loja |
| Atribuição / handoff / etapas lead | **Operacional** | Revy Loja + Chatbot |
| Preço / custo / publicação veículo | **Operacional** | Estoque API via Loja |
| Timezone, secrets de serviço, flags | **Técnica** | Env / deploy |

## Rollback

1. `REVY_LOJA_SHELL_ENABLED=0` — restaura nav legada em `base.html`.
2. `REVY_LOJA_ENTITLEMENTS_ENABLED=0` — fail-open; sem 403 de módulo.
3. `REVY_LOJA_REDIRECT_LEGACY=0` — desliga 303 de paths legados (F8; default).
4. Rotas `/app/*` legadas nunca removidas em F0–F1 / F8 (só redirect opcional).
5. Projeção `loja_operacional_projecao` permanece (provisioning já existente).

Cutover completo (ordem de enablement): [`revy-loja-cutover.md`](revy-loja-cutover.md).

## Baseline de testes (comandos)

Não reexecutados integralmente neste trabalho (809 no plano). Comandos por serviço:

```bash
# Portal
cd portal-gestao && python -m pytest -q

# Chatbot / Estoque / Catálogo / Motor / Revy Tráfego
cd chatbot-api && python -m pytest -q
cd estoque-api && python -m pytest -q
cd catalogo-publico && python -m pytest -q
cd motor-simulacao && python -m pytest -q
cd revy-trafego && python -m pytest -q
```

Contagens de referência do plano (2026-07-29): Chatbot 170, Portal 293, Estoque 87,
Catálogo 37, Motor 222 → **809**.
