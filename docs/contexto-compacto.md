# Contexto compacto para continuidade

Atualizado em **2026-07-15 (noite)** (front Revy no main `e40cfab`; planos Bradesco + Pan portal;
Fontecred LIVE; workers sob demanda planejados). Leia isto primeiro; detalhes em
`docs/handoff-contexto.md`.
**Playwright / próximos bancos:** lições
[Santander](plans/2026-07-13-playwright-licoes-santander.md) e
[Fontecred](plans/2026-07-15-playwright-licoes-fontecred.md).
**Implementar em seguida:**
[Bradesco](plans/2026-07-15-plano1a-task12-bradesco-implementacao.md) e
[Pan portal dual-path](plans/2026-07-15-plano1a-task12-pan-playwright-implementacao.md).
**Arquitetura workers:** `docs/plans/2026-07-14-plano1a-workers-playwright-sob-demanda.md`.
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

## Checkpoint Fly.io (2026-07-14)

- Org/região: `crm-419` / `gru`; alvo de custo: **US$10/mês**, modo laboratório.
- Apps: `motor2037`, `estoque2037`, `chatbot2037`, `catalogo2037`, `portal2037`,
  `site2037` (landing Revy), `evolution2037`, `n8n2037`; banco `suite-pg`; Redis Upstash
  `suite-redis`. `site2037` ainda **fora** do `down-all.sh` — parar à parte se precisar.
- Uma Machine por app. **Opção A aplicada no Fly (2026-07-14):** backends **always-on** —
  `motor2037`, `estoque2037`, `chatbot2037` (`autostop=false` nas machines; health OK).
  **Portal e Catálogo** autostop; **Evolution e n8n** always-on; Postgres ligado.
- **Motor em produção usa 2048 MB**: 512 MB falhou ao iniciar Chrome; probe headed com 2 GB abriu em
  34,41 s. API+worker ainda estão juntos e always-on. O plano aprovado separa API pequena e workers
  Playwright pré-criados/parados, ligados apenas quando houver tarefa por banco.
- `motor2037` versão **12**: Santander e Fontecred LIVE; Fontecred validado com sessão quente e modal
  COMUNICADOS no próprio Chromium/Xvfb do worker. Health 1/1 passing após o deploy.
- **Teto de RAM da org (mem_overcommit):** revisar antes de iniciar vários browsers; o rollout novo
  começa com 1 slot, depois 2, e só chega a 5 após custo/telemetria.
  Scripts lab:
  - `bash deploy/fly/down-all.sh` — para tudo (não gasta compute; não apaga volume)
  - `bash deploy/fly/up-all.sh` — sobe na ordem certa + reaplica always-on nos backends
  - `bash deploy/fly/up-all.sh --catalogo` — tenta Portal+Catálogo (pode falhar por RAM)
  - `bash deploy/fly/apply-always-on-backends.sh` — redeploy/imagem always-on (quando preciso)
- **Volume churn:** o Fly migra máquinas de host e cada migração forka um volume (órfãos cobrados).
  Limpar com `deploy/fly/clean-orphan-volumes.sh --apply`. Não usar keepalive de máquina ociosa.
- URLs: Portal `https://portal2037.fly.dev`; Catálogo `https://catalogo2037.fly.dev`;
  Evolution Manager `https://evolution2037.fly.dev/manager`; n8n `https://n8n2037.fly.dev`.
- n8n `2.26.8`, 1 GB, volume persistente. Workflow `WhatsApp IA - Somente Nao Salvos` importado e
  webhook de produção `/webhook/whatsapp-ai` registrado. Usuário confirmou mensagem
  Evolution → n8n; resposta completa da IA ainda não foi validada.
- Usuário informou ter substituído os tokens Chatbot e adicionado `X-Webhook-Token`. Ainda confirmar
  a chave Evolution nos nós `Consultar contato na Evolution1`/`Responder WhatsApp1` e a credencial Gemini.
- Evolution: instância `loja1`; WhatsApp `5551980336365`; mensagem recebida confirmada.
- Estoque tem 2 veículos disponíveis, ambos **não publicados**; não aparecem no Catálogo até clicar
  `Publicar no catálogo` no Portal.
- Segredos ficam somente em `deploy/fly/.env.production.local` (ignorado). Nunca ler/imprimir/versionar.

## Regras permanentes

- Workspace canônico atual: pasta do repositório CRM (clone local do usuário). Docs antigos podem
  citar path Windows de outra máquina — **ignorar path absoluto**; use o root do git.
- Sem reset/checkout destrutivo sem pedido explícito.
- Não ler/imprimir `.env`, tokens, chaves Gemini/Evolution/Motor/Portal/CAPI ou senhas.
- Estoque = fonte de verdade. Integrações só por **HTTP** entre produtos.
- Ordem: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6` (+ ops #7 Fly).
- Simulação: **mock** até driver `real: true`. **Santander e Fontecred = reais**. **Pan** = API no
  código (live depende de credenciais developer); portal lojista planejado como fallback. **Bradesco**
  planejado Playwright Turbo (codegen). No Santander a **entrada é calculada pelo banco**. Bradesco/
  Pan portal: **entrada opcional** (só se o user mandar). Fontecred: celular e placa obrigatórios;
  sessão fria/quente separadas.
- Senhas de portal: Dashboard **9A** → Motor cifrado (Task 11).
- Bot WhatsApp: transporte Evolution → n8n confirmado, mas go-live da IA ainda depende da credencial
  Gemini, da chave Evolution nos dois nós HTTP e de um teste E2E com resposta.
- Roadmap #6: **E9 fora do core**; E2/E4/E7 adiados; **E13–E18** aprovados (notif, reserva, PDF,
  troco, onboarding, domínio catálogo); rejeitados C2/C5/C7/C8/C10/C12.

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock, T11, **Santander + Fontecred LIVE**, histórico, **timeline/prints**, timeout 240 s, base **PAN API**, migrations head **0011**, **147 testes** | implementar fan-out/workers sob demanda; credenciais PAN; próximo banco API-first; T10 |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, handoff, por-placa, E3, E5, n8n tools | go-live manual; LGPD |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, placa, por-placa | E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | CRM, progresso/resultado/histórico, **Registros ao vivo + prints protegidos**, 9A, E10, CSV e metas por vendedor, **152 testes** | cards por banco no fan-out; #3B Task 4/5; E2E |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA, Pixel browser | containers reais; SEO |

**Estimativa:** ~**94%** MVP demonstrável (duas cotações reais + histórico) · ~**78%** produção/revenda multi-banco.

## Decisões vigentes

- Santander e Fontecred: Playwright headed + Xvfb; Fontecred exige reconhecimento de sessão
  persistida antes de procurar o formulário de login.
- 1 browser por banco (isolamento); fan-out paralelo sob demanda aprovado, ainda a implementar.
- Credenciais só no Motor (Portal só BFF).
- `testar-login` ainda placeholder — simulação real é a prova de credencial.

## Próxima sequência (sugerida)

1. **Go-live WhatsApp** E2E (`docs/go-live-chatbot.md`) + publicar estoque no Catálogo.
2. #3B **Task 4** (eventos do funil) e **Task 5** (campanhas metadados).
3. **E1** áudio + **E6** fotos (uso diário loja).
4. Implementar o plano de **fan-out/workers sob demanda** em rollout 1→2→5; próximo banco API-first.
   Antes de qualquer novo Playwright, ler as lições Santander + Fontecred.
5. **E11/E12** outbound (só com WA estável + opt-out).
6. Backlog C1–C12: **só o que o dono confirmar** (seção no plano #6).

> **Histórico de simulações por usuário (Task 16): FEITO** — não reimplementar.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/test_santander_driver.py tests/test_fontecred_driver.py tests/test_listar_simulacoes.py -q
# Suíte completa esperada neste checkpoint: 147 pass
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_simulacoes.py tests/test_simulacoes_historico.py -q
cd ..\deploy\motor-standalone
docker compose exec -T motor-worker sh -c "pgrep -a Xvfb"
docker compose exec -T motor-api sh -c "cd /srv && alembic current"   # deve ser 0011 (head)
git status --short
```
