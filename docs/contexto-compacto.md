# Contexto compacto para continuidade

Atualizado em **2026-07-24** (CRM **A/B/E/D/H/C/F DONE** · **G residual** · funil UI DONE · **grupo único do estoque WA + fotos Evolution** · **Fly 3-VM no ar**).
Leia isto primeiro; detalhe operacional recente em `docs/handoff-contexto.md` (topo).
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.
Ops Fly canônico: `deploy/fly/3vm/README.md` + `bash deploy/fly/up-all.sh --3vm`.
Sessão menu/fotos: [plano 2026-07-22](plans/2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md).

**Playwright / bancos:** lições
[Santander](plans/2026-07-13-playwright-licoes-santander.md),
[Fontecred](plans/2026-07-15-playwright-licoes-fontecred.md),
[Pan portal](plans/2026-07-15-playwright-licoes-pan-portal.md).
Diagnóstico e plano de correção do Bradesco:
[estabilidade Bradesco Playwright](plans/2026-07-24-plano-estabilidade-bradesco-playwright.md).
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
**CTWA (2026-07-22):** [atribuição + CAPI messaging](plans/2026-07-22-plano-ctwa-atribuicao-capi-messaging.md) — **MVP código**
(lead CTWA, match, Purchase messaging, n8n); residual E2E lab Evolution com anúncio real.
**Spend Meta (2026-07-22):** [gasto automático](plans/2026-07-22-plano-meta-spend-api.md) — **MVP + job 24h**;
Google spend fora. TikTok spend parked.
**Eixo E (2026-07-21):** áudio recebido, envio de foto do Estoque no WhatsApp e cadastro automático
de fotos WhatsApp → Estoque → Catálogo têm backend/workflow concluídos. Cadastro textual tem
idempotência persistente; fotos usam sessão curta por grupo e limpeza administrativa de órfãos.
No Fly, o MVP usa volume persistente criptografado, URL HTTPS e snapshots agendados; ainda é
necessário homologar o transcritor HTTP e executar um restore drill.
**Grupo do estoque (2026-07-24):** dono/gerente escolhe um único grupo no Portal; só o JID exato
abre menu, cadastra veículos e envia fotos. Privado/outros grupos são ignorados silenciosamente.
Migration Chatbot `0012`; workflow n8n com 31 nós publicado; app+n8n health passando.
**Eixo G (2026-07-22):** [Multi-WhatsApp por vendedor](plans/2026-07-22-plano-multi-whatsapp-vendedores-campanhas.md)
está **planejado e não implementado**. O desenho mantém um lead por loja/telefone e cria uma conversa
por canal/telefone, liga campanhas a vendedor/canal e preserva o número atual como canal legado.

## Fonte da verdade (por tema)

| Tema | Única fonte | Não usar como verdade atual |
|---|---|---|
| Estado do produto | **este arquivo** | README %, `design.md`, handoffs pontuais antigos |
| Checkpoint / ops recente | `handoff-contexto.md` (topo) | seções “checkpoint anterior” longas |
| Qual plano implementar | `plans/README.md` + Status no topo do plano | `_archive/`, planos DONE/SUPERSEDED |
| Go-live WhatsApp | `go-live-chatbot.md` | compose local legado / branch `feat/*` |
| Ops Fly lab | `deploy/fly/3vm/` + `up-all.sh --3vm` + seção Fly abaixo | monólitos legados / plano #7 só como histórico |
| Lições RPA | `*playwright-licoes-*.md` | reabrir santander/fontecred-impl do zero |

## Eixos de prioridade (escolher um; não misturar na mesma PR)

Não há uma única “próxima task” universal — depende do objetivo:

| Eixo | Próximo incremento | Quando escolher | Plano / doc |
|---|---|---|---|
| **A · Demo loja / WA** | **(1)** escolher Grupo do estoque; **(2)** E2E `menu`/cadastro/fotos no grupo; **(3)** E2E contato novo (IA vendas) | Demo/operação real no Zap | `setup-grupo-whatsapp-estoque.pdf` + `go-live-chatbot.md` + `deploy/fly/3vm/README.md` |
| **B · Multi-banco** | Estabilizar sim com celular + prints; alinhar âncoras se falhar ao vivo | Mais cotações reais estáveis | handoff topo + lições Playwright |
| **C · CRM dono** | **Revy Tráfego** (6.4): deploy lab + cutover workers; ligar flags API | Código Fase 1+2 em main; ops | [plano 6.4](plans/2026-07-28-plano-revy-trafego-separacao.md) · app `revy-trafego/` |
| **D · Escala Motor** | Smoke live sessão quente + teto 2; object storage se multi-volume | Estabilidade multi-banco / IP | B+D + warm-batch2 |
| **E · Dia a dia loja** | Restore drill do volume/banco e homologar transcritor | Fechar operação de áudio e foto já publicada | `#6` + `fotos-veiculos-whatsapp.md` |
| **F · Marketing** | Completar landing se o dono entregar HTML | Site/hero polish | `site/` |
| **G · Multi-WhatsApp** | Task 0: validar contrato real Evolution/CTWA, sessões e capacidade | Vários números de vendedores com leads centralizados | [plano multi-WhatsApp](plans/2026-07-22-plano-multi-whatsapp-vendedores-campanhas.md) |

**Bloqueios conhecidos:**
- Landing Tailwind nova: HTML do dono ainda incompleto.
- Áudio real: falta URL/token do transcritor HTTP homologado; sem isso há fallback para texto.
- Fotos: download Evolution via **HTTPS público**; parser Long size OK; grupo validado antes do
  download. Falta E2E humano completo + restore drill do volume.
- Menu cadastro: código/deploy DONE; falta escolher o grupo no Portal e fechar o E2E.
- E11/E12 outbound: só com eixo **A** estável + opt-out.
- Não reabrir Fontecred/Santander sem evidência nova.
- Stack 3-VM **no ar** (pedido do dono). Subir/desligar: `up-all.sh --3vm` / `down-all.sh --3vm`.
  Não destruir apps/volumes sem pedido explícito.
- Números da equipe são legado/identificação; com grupo escolhido não autorizam menu no privado.

> **Histórico de simulações por usuário (Task 16): FEITO** — não reimplementar.  
> **Campanhas + ROI (E8 / #3B T5): FEITO** — não reimplementar.  
> **Roteamento por grupo: FEITO** — IA só `isSaved=false`; estoque só no JID selecionado.

## Ambiente de trabalho (2026-07-21+)

| Onde | Estado |
|---|---|
| **Local** | Dev — `deploy/*/docker-compose.yml` + apps Python |
| **Fly.io lab** (`crm-419` / `gru`) | **ON (3-VM)** — ver tabela abaixo |

### Inventário Fly válido

| App | Papel | Estado típico |
|---|---|---|
| `suite-pg` | Postgres | always-on |
| `evolution2037` | WhatsApp Evolution | always-on |
| `app2037` | Bundle: chatbot, estoque, portal, catálogo, site, motor-api, nginx | always-on |
| `n8n2037` | Orquestração n8n (webhook WA) | always-on quando lab ativo |
| `motor2037` | Playwright por banco | on-demand (stopped idle) |

Monólitos legados (`portal2037`, `catalogo2037`, `estoque2037`, `chatbot2037`, `site2037` isolado, etc.) **removidos** — não recriar sem pedido.

## Checkpoint Fly.io (3-VM — 2026-07-21+)

- Org/região: `crm-419` / `gru`.
- Docs/ops: `deploy/fly/3vm/README.md` · scripts `up-all.sh --3vm` · `down-all.sh --3vm --yes`.
- Segredos: `deploy/fly/3vm/.secrets.local` e `deploy/fly/.env.production.local` (gitignored).
  **Nunca** versionar `workflow-fly.ready.json` (tokens reais).
- Workflow canônico: `n8n/workflow-ai-nao-salvos.json` + `prepare-workflow.ps1` (HTTPS
  `app2037.fly.dev` / `evolution2037.fly.dev`).
- Roteamento: `POST /v1/operacao/roteamento` — cliente só se `is_saved=false`; estoque somente
  quando `grupo_jid` é igual ao grupo escolhido no Portal. Outros grupos/imagens privadas ignoram.
- Hosts: `https://app2037.fly.dev` · `https://n8n2037.fly.dev` · `https://evolution2037.fly.dev`.

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
| Chatbot #2A | `chatbot-api/` `:8001` (Fly: `app2037`) | leads, handoff, por-placa, E3/E5, áudio efêmero/fallback, foto automática com sessão por grupo, envio da capa, first/last UTM, sim privada + handoff; grupo único do estoque por loja; privado/outros grupos ignorados; webhook endurecido | escolher grupo + E2E WA; transcritor HTTP real; retenção/expurgo; multi-WhatsApp por vendedor planejado |
| Estoque #4A | `estoque-api/` `:8100` (Fly: `app2037`) | CRUD, idempotência persistente, placa, admin, galeria/capa, upload validado, volume/rota pública HTTPS, snapshots, limpeza periódica e transporte outbox testado | executar restore drill |
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
# migrations: motor head 0013 · portal 0008 funil_eventos · chatbot 0012 grupo_estoque · estoque 0007 idempotência
git status --short
```

(Windows: `.\.venv\Scripts\python.exe` se usar venv por pasta.)
