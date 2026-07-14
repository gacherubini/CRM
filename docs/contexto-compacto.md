# Contexto compacto para continuidade

Atualizado em **2026-07-14** (deploy Fly.io lab + Evolution → n8n; **sessão #3B CSV/metas-vendedor + 6
fixes Motor + evolution/n8n always-on**). Leia isto primeiro; detalhes em `docs/handoff-contexto.md`.  
**Playwright / próximos bancos:** `docs/plans/2026-07-13-playwright-licoes-santander.md`.  
Planos válidos: `docs/plans/README.md`. **Ignore** `docs/plans/_archive/`.

## Checkpoint Fly.io (2026-07-14)

- Org/região: `crm-419` / `gru`; alvo de custo: **US$10/mês**, modo laboratório.
- Apps: `motor2037`, `estoque2037`, `chatbot2037`, `catalogo2037`, `portal2037`,
  `evolution2037`, `n8n2037`; banco `suite-pg`; Redis Upstash `suite-redis`.
- Uma Machine por app. **Opção A aplicada no Fly (2026-07-14):** backends **always-on** —
  `motor2037`, `estoque2037`, `chatbot2037` (`autostop=false` nas machines; health OK).
  **Portal e Catálogo** autostop; **Evolution e n8n** always-on; Postgres ligado.
- **Teto de RAM da org (mem_overcommit):** com backends+n8n+evo+pg always-on (~4.3GB),
  **Portal e Catálogo não sobem ao mesmo tempo** (só um dos dois + suite). Motor lab em **512MB**
  (RPA real: subir para 2048 e parar Portal/Catálogo se necessário).
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
- Simulação: **mock** até driver `real: true`. **Santander = real** (piloto live). No Santander a
  **entrada é calculada pelo banco** e devolvida (campo `entrada` no resultado) — não é input.
  Demais: híbrido **API-first** + Playwright só se não houver API.
- Senhas de portal: Dashboard **9A** → Motor cifrado (Task 11).
- Bot WhatsApp: transporte Evolution → n8n confirmado, mas go-live da IA ainda depende da credencial
  Gemini, da chave Evolution nos dois nós HTTP e de um teste E2E com resposta.
- Roadmap #6: **E9 fora do core**; E2/E4/E7 adiados; **E13–E18** aprovados (notif, reserva, PDF,
  troco, onboarding, domínio catálogo); rejeitados C2/C5/C7/C8/C10/C12.

## Estado por produto

| Produto | Pasta / porta | Feito (essencial) | Aberto |
|---|---|---|---|
| Motor #1A | `motor-simulacao/` `:8000` | async, auth, worker, mock, T11, **T12 Santander live** (headed+Xvfb, **entrada retornada**, fix skeleton), **listagem `GET /v1/simulacoes` + `solicitado_por`** (T16), migrations head 0009, **suíte 108 verde** | outros bancos; 1 PW/banco paralelo; T10 |
| Chatbot #2A | `chatbot-api/` `:8001` | leads, handoff, por-placa, E3, E5, n8n tools | go-live manual; LGPD |
| Estoque #4A | `estoque-api/` `:8100` | CRUD, placa, por-placa | E2E outbox; restore |
| Portal | `portal-gestao/` `:9000` | CRM, **progresso sim + resultado multi-prazo (coluna Entrada)**, **histórico de sims por usuário (T16)**, 9A, E10, **#3B Task 8 CSV export** (`financeiro_calc.py`+`relatorios.py`), **#3B metas por vendedor UI** | #3B Task 4 (funil) e Task 5 (campanhas); E2E |
| Catálogo #5A | `catalogo-publico/` `:8200` | vitrine, CTA, Pixel browser | containers reais; SEO |

**Estimativa:** ~**93%** MVP demonstrável (cotação real Santander + histórico) · ~**76%** produção/revenda multi-banco.

## Decisões vigentes

- Santander: Playwright headed + Xvfb (headless_shell = Akamai).
- 1 browser por banco (isolamento); multi-banco paralelo ainda a implementar.
- Credenciais só no Motor (Portal só BFF).
- `testar-login` ainda placeholder — simulação real é a prova de credencial.

## Próxima sequência (sugerida)

1. **Go-live WhatsApp** E2E (`docs/go-live-chatbot.md`) + publicar estoque no Catálogo.
2. #3B **Task 4** (eventos do funil) e **Task 5** (campanhas metadados).
3. **E1** áudio + **E6** fotos (uso diário loja).
4. **Próximo banco** / multi-banco — API-first; lições Santander se Playwright.
5. **E11/E12** outbound (só com WA estável + opt-out).
6. Backlog C1–C12: **só o que o dono confirmar** (seção no plano #6).

> **Histórico de simulações por usuário (Task 16): FEITO** — não reimplementar.

## Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/test_santander_driver.py tests/test_listar_simulacoes.py -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_simulacoes.py tests/test_simulacoes_historico.py -q
cd ..\deploy\motor-standalone
docker compose exec -T motor-worker sh -c "pgrep -a Xvfb"
docker compose exec -T motor-api sh -c "cd /srv && alembic current"   # deve ser 0009 (head)
git status --short
```
