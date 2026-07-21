# Contexto compacto para continuidade

Atualizado em **2026-07-21** (CRM **A/B/E/D/H/C/F DONE** · **G residual** · funil UI DONE · áudio/fotos backend **publicado e verificado** · Fly **pausado**).
Leia isto primeiro; detalhe operacional recente em `docs/handoff-contexto.md` (topo).
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

**Playwright / bancos:** lições
[Santander](plans/2026-07-13-playwright-licoes-santander.md),
[Fontecred](plans/2026-07-15-playwright-licoes-fontecred.md),
[Pan portal](plans/2026-07-15-playwright-licoes-pan-portal.md).
Campos e decisões por banco:
[mapa](plans/2026-07-13-plano1a-task12-bancos-reconhecimento.md).
**Workers sob demanda + fan-out:** **DONE** (handoff 2026-07-16).
**B+D (2026-07-16/17):** teto **2** Playwrights (`MOTOR_MAX_BROWSER_WORKERS` /
`MOTOR_BROWSER_CONCURRENCY`) + warm session (`MOTOR_WARM_SESSION`, path
`{STORAGE}/{cliente_id}/{provedor}.json`). Docs:
[decisão captcha](plans/2026-07-16-fly-rpa-captcha-opcoes.md),
[warm+batch2](plans/2026-07-17-plano1a-warm-session-batch2.md).
**CRM tráfego pago (2026-07-20):** campanhas + first/last + ROI **DONE** —
[plano](plans/2026-07-20-plano-trafego-pago-crm-campanhas-roi.md) · guia [loja](trafego-pago-loja.md).
**Eixo C (2026-07-21 rev.3):** [conversões / funil / insights](plans/2026-07-21-plano-conversao-atribuicao-insights.md)
— **A/B/E/D/H/C/F concluídas**, incluindo a UI `/app/funil`; resta **G** (Google Conversions).
TikTok API e API de spend seguem parked.
**Eixo E (2026-07-21):** áudio recebido, envio de foto do Estoque no WhatsApp e cadastro automático
de fotos WhatsApp → Estoque → Catálogo têm backend/workflow concluídos. Cadastro textual tem
idempotência persistente; fotos usam sessão curta por vendedor e limpeza administrativa de órfãos.
No Fly, o MVP usa volume persistente criptografado, URL HTTPS e snapshots agendados; ainda é
necessário homologar o transcritor HTTP e executar um restore drill.

## Fonte da verdade (por tema)

| Tema | Única fonte | Não usar como verdade atual |
|---|---|---|
| Estado do produto | **este arquivo** | README %, `design.md`, handoffs pontuais antigos |
| Checkpoint / ops recente | `handoff-contexto.md` (topo) | seções “checkpoint anterior” longas |
| Qual plano implementar | `plans/README.md` + Status no topo do plano | `_archive/`, planos DONE/SUPERSEDED |
| Go-live WhatsApp | `go-live-chatbot.md` | compose local legado / branch `feat/*` |
| Ops Fly lab | `deploy/fly/*.sh` + seção Fly abaixo | checkboxes do plano #7 implementação; conferir estado vivo antes de agir |
| Lições RPA | `*playwright-licoes-*.md` | reabrir santander/fontecred-impl do zero |

## Eixos de prioridade (escolher um; não misturar na mesma PR)

Não há uma única “próxima task” universal — depende do objetivo:

| Eixo | Próximo incremento | Quando escolher | Plano / doc |
|---|---|---|---|
| **A · Demo loja / WA** | E2E real por número autorizado + monitorar primeira conversa | Operação ou demo com cliente real no Zap | `go-live-chatbot.md` |
| **B · Multi-banco** | Estabilizar sim com celular + prints; alinhar âncoras se falhar ao vivo | Mais cotações reais estáveis | handoff topo + lições Playwright |
| **C · CRM dono** | Google Conversions (G) | Conversões outbound Google | A/B/E/D/H/C/F feitas; spend API fora |
| **D · Escala Motor** | Smoke live sessão quente + teto 2; object storage se multi-volume | Estabilidade multi-banco / IP | B+D + warm-batch2 |
| **E · Dia a dia loja** | Restore drill do volume/banco e homologar transcritor | Fechar operação de áudio e foto já publicada | `#6` + `fotos-veiculos-whatsapp.md` |
| **F · Marketing** | Completar landing se o dono entregar HTML | Site/hero polish | `site/` |

**Bloqueios conhecidos:**
- Landing Tailwind nova: HTML do dono ainda incompleto.
- Áudio real: falta URL/token do transcritor HTTP homologado; sem isso há fallback para texto.
- Fotos: fluxo automático e URL HTTPS publicados; volume persistente anexado. Falta o restore drill.
- E11/E12 outbound: só com eixo **A** estável + opt-out.
- Não reabrir Fontecred/Santander sem evidência nova.
- Fly WA foi ligado, verificado e depois totalmente parado por pedido explícito em 2026-07-21.
  Não religar nem ampliar o ambiente sem novo pedido.

> **Histórico de simulações por usuário (Task 16): FEITO** — não reimplementar.  
> **Campanhas + ROI (E8 / #3B T5): FEITO** — não reimplementar.

## Ambiente de trabalho (2026-07-21)

| Onde | Estado |
|---|---|
| **Local** | Continua disponível para desenvolvimento — `deploy/*/docker-compose.yml` + apps Python |
| **Fly.io lab** (`crm-419` / `gru`) | **OFF** — Portal, Catálogo, Site, Motor, Estoque, Chatbot, n8n, Evolution e Postgres confirmados `stopped`; apps/volumes/dados preservados |

Apps Fly (referência, **não alterar** sem pedido): `motor2037`, `estoque2037`, `chatbot2037`,
`catalogo2037`, `portal2037`, `site2037`, `evolution2037`, `n8n2037`, Postgres `suite-pg`.

## Checkpoint Fly.io (lab — validado e pausado em 2026-07-21)

- Org/região: `crm-419` / `gru`.
- Scripts: `bash deploy/fly/down-all.sh` · `up-all.sh` · `up-all.sh --catalogo` ·
  `apply-always-on-backends.sh` · `clean-orphan-volumes.sh --apply`.
- Segredos: só `deploy/fly/.env.production.local` (ignorado). Nunca imprimir/versionar.
- Antes do shutdown, Estoque e Chatbot estavam com health passando e migrations **`0007 (head)`**.
  Volume `estoque_media` criptografado de 1 GB permanece anexado; limpeza automática executou.
- n8n persistiu o workflow `SBAUPjrUlYa4gtgE` ativo com **25 nós**; atualização feita com
  `n8n/update_live_workflow.js` e backup SQLite consistente antes da troca. O canônico no repo é
  `n8n/workflow-ai-nao-salvos.json`; o publicador troca os hosts compose pelos hosts Fly via flags.
- Evolution estava saudável e a instância `loja1` estava **open** antes do shutdown.
- Estado atual: todas as nove Machines da suíte estão **stopped**. Para voltar, executar
  `bash deploy/fly/up-all.sh` por pedido do dono e conferir o go-live; não recriar/importar dados.

## Regras permanentes

- Workspace = root do git deste repo (ignore paths Windows/outros clones em docs antigos).
- Sem reset/checkout destrutivo sem pedido explícito.
- Não ler/imprimir `.env`, tokens, chaves Gemini/Evolution/Motor/Portal/CAPI ou senhas.
- Estoque = fonte de verdade de veículos. Integrações **só HTTP** entre produtos.
- Ordem estrutural de planos: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6` (+ ops #7).
  Isso **não** substitui a tabela de eixos acima para escolher o trabalho da sessão.
- Credenciais de banco: Portal **9A** → Motor cifrado. `testar-login` ainda placeholder.
- Roadmap #6: **E9 fora**; E2/E4/E7 adiados; **E8/E10 feitos**; **E13–E18** aprovados (esboço).

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, fan-out, workers on-demand, **Santander/Fontecred/Bradesco/Pan portal LIVE**, warm session teto 2, prints blob JPEG, migrations head **0013** | `testar-login` real; T10 revenda; object storage multi-volume |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, handoff, por-placa, E3, E5, áudio efêmero/fallback, foto automática com sessão por vendedor, envio da capa via WhatsApp, first/last UTM, sim privada + handoff; **cadastro por número autorizado via gatilho `cadastro` + `/v1/operacao/roteamento`** (sessão em `cadastro_expira_em`, TTL 30min); webhook endurecido; Fly validado e pausado | E2E WA real; transcritor HTTP real; retenção/expurgo administrativo (sem autosserviço) |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, idempotência persistente, placa, admin, galeria/capa, upload validado, volume/rota pública HTTPS, snapshots, limpeza periódica e transporte outbox testado; Fly validado e pausado | executar restore drill |
| Portal | `portal-gestao/` `:9000` | CRM, sim multi-banco, 9A, CAPI retry, gastos/ROI/resultados; funil completo backend+UI; event bus Meta; retry HTTP seguro | Google; E2E Playwright |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA, Pixel PageView/Lead/ViewContent | SEO/tema; domínio (E18) |
| Site | `site/` | landing + hero poster | polish visual residual |

**Estimativa:** ~**99%** MVP multi-banco + CRM demonstrável · ~**92%** preparação para produção
(restam E2E WA real, transcritor real, restore drill, Google e polish ops). Percentuais são estimativas de escopo,
não cobertura de testes.

Baseline de testes: rodar `pytest -q` no produto; não confiar em contagens antigas de handoff.

## Decisões vigentes (simulação)

- Santander / Fontecred: Playwright headed + Xvfb; Fontecred = sessão fria **e** quente.
- 1 browser por banco; fan-out + workers sob demanda **implementados** (wake paralelo no Fly).
- Entrada: Santander **calculada pelo banco**; Bradesco/Pan portal **opcional** se user mandar;
  Fontecred/Bradesco/Pan: **celular** no form do Portal. Detalhe → mapa de bancos.
- Credenciais só no Motor (Portal é BFF).

## Verificação mínima

```bash
cd motor-simulacao && python -m pytest tests/test_santander_driver.py tests/test_fontecred_driver.py -q
cd ../portal-gestao && python -m pytest tests/test_campanhas.py tests/test_roi.py -q
cd ../chatbot-api && python -m pytest tests/test_audio.py tests/test_inventory.py tests/test_vehicle_photo.py -q
cd ../estoque-api && python -m pytest tests/test_rbac_fotos_auditoria.py -q
python ../n8n/validate_workflow.py
# migrations: motor head 0013 · portal 0008 funil_eventos · chatbot 0008 cadastro/sessão+nome · estoque 0007 idempotência
git status --short
```

(Windows: `.\.venv\Scripts\python.exe` se usar venv por pasta.)
