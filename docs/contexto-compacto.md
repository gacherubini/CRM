# Contexto compacto para continuidade

Atualizado em **2026-07-15** (limpeza P0 docs: eixos de prioridade, go-live Fly, banners DONE/SUPERSEDED).
Leia isto primeiro; detalhe operacional recente em `docs/handoff-contexto.md`.
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

**Playwright / próximos bancos:** lições
[Santander](plans/2026-07-13-playwright-licoes-santander.md) e
[Fontecred](plans/2026-07-15-playwright-licoes-fontecred.md).
Campos e decisões por banco:
[mapa](plans/2026-07-13-plano1a-task12-bancos-reconhecimento.md).
Planos prontos (código ainda não):
[Bradesco](plans/2026-07-15-plano1a-task12-bradesco-implementacao.md),
[Pan portal](plans/2026-07-15-plano1a-task12-pan-playwright-implementacao.md).
Workers sob demanda (planejado):
[fan-out](plans/2026-07-14-plano1a-workers-playwright-sob-demanda.md).

## Fonte da verdade (por tema)

| Tema | Única fonte | Não usar como verdade atual |
|---|---|---|
| Estado do produto | **este arquivo** | README %, `design.md`, handoffs pontuais antigos |
| Checkpoint / ops recente | `handoff-contexto.md` (topo) | seções “checkpoint anterior” longas |
| Qual plano implementar | `plans/README.md` + Status no topo do plano | `_archive/`, planos DONE/SUPERSEDED |
| Go-live WhatsApp | `go-live-chatbot.md` | compose local / branch `feat/*` legada |
| Ops Fly lab | `deploy/fly/*.sh` + seção Fly abaixo | checkboxes do plano #7 implementação |
| Lições RPA | `*playwright-licoes-*.md` | reabrir santander/fontecred-impl do zero |

## Eixos de prioridade (escolher um; não misturar na mesma PR)

Não há uma única “próxima task” universal — depende do objetivo:

| Eixo | Próximo incremento | Quando escolher | Plano / doc |
|---|---|---|---|
| **A · Demo loja / WA** | Go-live E2E + publicar estoque no catálogo | Operação ou demo com cliente real no Zap | `go-live-chatbot.md` |
| **B · Multi-banco** | Bradesco Turbo (depois Pan portal se houver HTML de ofertas) | Mais cotações reais no Portal | planos 2026-07-15 Bradesco / Pan |
| **C · CRM dono** | #3B Task 4 (eventos funil) → Task 5 (campanhas) | Funil, origem, metas confiáveis | `#3B` |
| **D · Escala Motor** | Fan-out + workers sob demanda (rollout 1→2→5) | Paralelismo / custo RAM no Fly | plano workers 2026-07-14 |
| **E · Dia a dia loja** | E1 áudio, E6 fotos (após ou em paralelo leve a A) | Uso diário sem depender de banco novo | `#6` |

**Bloqueios conhecidos:**
- Pan portal: falta HTML anonimizado da **tela de ofertas** (Task 0 do plano).
- E11/E12 outbound: só com eixo **A** estável + opt-out.
- Não reabrir Fontecred/Santander sem evidência nova.

> **Histórico de simulações por usuário (Task 16): FEITO** — não reimplementar.

## Checkpoint Fly.io (lab)

- Org/região: `crm-419` / `gru`; alvo de custo lab ~US$10/mês (variável).
- Apps: `motor2037`, `estoque2037`, `chatbot2037`, `catalogo2037`, `portal2037`,
  `site2037` (landing; **fora** do `down-all.sh` — parar à parte se preciso),
  `evolution2037`, `n8n2037`; Postgres `suite-pg`; Redis Upstash `suite-redis`.
- Backends always-on (opção A): Motor, Estoque, Chatbot; Evolution + n8n always-on;
  Portal/Catálogo autostop. Motor ~**2048 MB** (Chrome).
- Santander + Fontecred LIVE no Motor; API+worker ainda na mesma Machine.
- Scripts: `bash deploy/fly/down-all.sh` · `up-all.sh` · `up-all.sh --catalogo` ·
  `apply-always-on-backends.sh` · `clean-orphan-volumes.sh --apply`.
- URLs: Portal `https://portal2037.fly.dev` · Catálogo `https://catalogo2037.fly.dev` ·
  Evolution `…/manager` · n8n `https://n8n2037.fly.dev`.
- WA: transporte Evolution→n8n confirmado; **resposta IA completa** e go-live ainda manuais
  (Gemini + chaves Evolution nos nós HTTP). Ver `go-live-chatbot.md`.
- Estoque lab: veículos podem estar **não publicados** — não saem no catálogo até publicar.
- Segredos: só `deploy/fly/.env.production.local` (ignorado). Nunca imprimir/versionar.

## Regras permanentes

- Workspace = root do git deste repo (ignore paths Windows/outros clones em docs antigos).
- Sem reset/checkout destrutivo sem pedido explícito.
- Não ler/imprimir `.env`, tokens, chaves Gemini/Evolution/Motor/Portal/CAPI ou senhas.
- Estoque = fonte de verdade de veículos. Integrações **só HTTP** entre produtos.
- Ordem estrutural de planos: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6` (+ ops #7).
  Isso **não** substitui a tabela de eixos acima para escolher o trabalho da sessão.
- Credenciais de banco: Portal **9A** → Motor cifrado. `testar-login` ainda placeholder.
- Roadmap #6: **E9 fora**; E2/E4/E7 adiados; **E13–E18** aprovados (esboço); rejeitados C2/C5/C7/C8/C10/C12.

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock, T11, **Santander + Fontecred LIVE**, histórico, timeline/prints, timeout 240s, base **PAN API**, migrations head **0011** | fan-out/workers; credenciais PAN live; Bradesco/Pan portal; `testar-login`; T10 revenda |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, handoff, por-placa, E3, E5, n8n tools | go-live manual; LGPD exclusão |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, placa, por-placa, admin | E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | CRM, sim progress/resultado/histórico, Registros, 9A, E10, CSV, metas vendedor | cards por banco (fan-out); #3B T4/T5; E2E |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA, Pixel browser | SEO/tema; domínio (E18) |
| Site | `site/` | landing + Fly `site2037` | polish marketing; incluir no down-all se desejado |

**Estimativa:** ~**94%** MVP demonstrável (2 cotações reais + histórico) · ~**78%** produção multi-banco/revenda.

Baseline de testes: rodar `pytest -q` no produto; não confiar em contagens antigas de handoff.
Última contagem citada em handoff (pode drift): Motor ~147 · Portal ~152.

## Decisões vigentes (simulação)

- Santander / Fontecred: Playwright headed + Xvfb; Fontecred = sessão fria **e** quente.
- 1 browser por banco; fan-out paralelo aprovado, **não implementado**.
- Entrada: Santander **calculada pelo banco**; Bradesco/Pan portal **opcional** se user mandar;
  Fontecred: celular + placa obrigatórios. Detalhe → mapa de bancos.
- Credenciais só no Motor (Portal é BFF).

## Verificação mínima

```bash
cd motor-simulacao && .venv/bin/python -m pytest tests/test_santander_driver.py tests/test_fontecred_driver.py tests/test_listar_simulacoes.py -q
cd ../portal-gestao && .venv/bin/python -m pytest tests/test_simulacoes.py tests/test_simulacoes_historico.py -q
# migrations motor head esperado: 0011
git status --short
```

(Windows: `.\.venv\Scripts\python.exe` em vez de `.venv/bin/python`.)
