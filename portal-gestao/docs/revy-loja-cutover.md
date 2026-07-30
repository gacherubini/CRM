# Revy Loja — Cutover de rotas legadas (Fase 8)

**Escopo:** `portal-gestao`  
**Código:** `app/loja/redirects.py` + middleware em `app/main.py`  
**Mapa de rotas (F0):** [`revy-loja-route-map.md`](revy-loja-route-map.md)

## Matriz de flags

| Variável | Default | Efeito |
|---|---|---|
| `REVY_LOJA_SHELL_ENABLED` | `0` | Brand + nav Vendas/Estoque; rotas `/app/loja/*` |
| `REVY_LOJA_ENTITLEMENTS_ENABLED` | `0` | 403 se módulo não contratado; `0` = fail-open |
| `REVY_LOJA_ATENDIMENTO_ENABLED` | `0` | Workspace `/app/loja/atendimento` |
| `REVY_LOJA_REDIRECT_LEGACY` | `0` | 303 de paths legados → shell (só com shell on) |
| `SELLER_AI_ENABLED` | `0` | Seller AI (F7+); sem redirects nesta fase |

### Interação shell × redirect

| Shell | Redirect legacy | Comportamento em `/app`, `/app/leads`, … |
|---|---|---|
| `0` | `0` ou `1` | **Zero redirects.** UI legada intacta. |
| `1` | `0` | Shell (brand/nav) nas páginas legadas; **sem** 303. `/app` = dashboard legado com brand Revy Loja. |
| `1` | `1` | GET HTML nos paths mapeados → **303** para o destino Loja. |

`REVY_LOJA_REDIRECT_LEGACY=1` **sem** shell **não** redireciona (fail-safe).

## Paths redirecionados (redirect + shell on)

Somente **GET** e pedidos que aceitam HTML. Paths **exatos** (sem subrotas).

| Path legado | Destino | Condição |
|---|---|---|
| `/app` | `/app/loja/vendas` | shell + redirect |
| `/app/funil` | `/app/loja/vendas` | shell + redirect |
| `/app/financeiro` | `/app/loja/vendas` | shell + redirect |
| `/app/relatorios` | `/app/loja/vendas` | shell + redirect (HTML; CSV permanece) |
| `/app/estoque` | `/app/loja/estoque` | shell + redirect (**lista only**) |
| `/app/leads` | `/app/loja/atendimento` | + `REVY_LOJA_ATENDIMENTO_ENABLED=1` |
| `/app/conversas` | `/app/loja/atendimento` | + `REVY_LOJA_ATENDIMENTO_ENABLED=1` |

### O que **não** redireciona (CRUD e detalhe seguros)

- `/app/estoque/novo`, `/app/estoque/{id}`, POST de estoque  
- `/app/leads/{id}`, POST de etapa  
- `/app/conversas/{telefone}`, handoff  
- `/app/relatorios/*.csv`, `/app/funil/dados`  
- Qualquer `/app/loja/*`  
- POST / PUT / DELETE  

## Ordem de enablement (piloto)

1. **Deploy com flags off** — regressão zero; suíte portal verde.  
2. **`REVY_LOJA_SHELL_ENABLED=1`** — nav nova; usuários ainda usam URLs legadas; brand “Revy Loja”.  
3. **`REVY_LOJA_ENTITLEMENTS_ENABLED=1`** (opcional, após projeção Control estável) — gates de módulo.  
4. **`REVY_LOJA_ATENDIMENTO_ENABLED=1`** — workspace de Atendimento disponível.  
5. **`REVY_LOJA_REDIRECT_LEGACY=1`** — bookmarks/menus antigos passam a cair no shell.  
6. Só depois: telemetria de uso → remoção de menus legados no template (não nesta entrega de código).

Não ligar redirect antes de shell + (para leads/conversas) atendimento.

## Rollback

| Sintoma | Ação |
|---|---|
| Redirects indesejados / 404 em destino | `REVY_LOJA_REDIRECT_LEGACY=0` (imediato; legado volta a responder 200) |
| Nav/shell problemático | `REVY_LOJA_SHELL_ENABLED=0` (restaura menu legado; redirects param sozinhos) |
| Atendimento instável | `REVY_LOJA_ATENDIMENTO_ENABLED=0` (leads/conversas deixam de redirecionar; rotas legadas OK) |
| Entitlements bloqueando | `REVY_LOJA_ENTITLEMENTS_ENABLED=0` (fail-open) |
| Deploy ruim | Reverter release; flags em env continuam default safe se omitidas |

Nenhuma rota legada é **removida** nesta fase — só redirecionada quando as flags permitem.

## Shell home (`/app`)

| Flags | Resultado |
|---|---|
| shell off | Dashboard legado (como sempre) |
| shell on, redirect off | Dashboard legado **com** brand/nav Revy Loja |
| shell on, redirect on | 303 → `/app/loja/vendas` (overview de Vendas) |

## Testes

```bash
cd portal-gestao
python -m pytest tests/test_loja_redirects.py -q
```

Casos cobertos: flag redirect off → 200; shell+redirect+atendimento → 303; CRUD estoque seguro.

## Referência de implementação

- Domínio puro: `app/loja/redirects.py` (`resolve_legacy_redirect`, `should_consider_request`)  
- Middleware HTTP: `revy_loja_legacy_redirects` em `app/main.py`  
- Helpers de env: `revy_loja_*_enabled()` em `app/config.py` (leitura em runtime)
