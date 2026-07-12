# Handoff técnico — suíte automotiva

> Checkpoint de 2026-07-12 (noite). Documento autocontido para a próxima IA/humano.
> Confirme o estado real (containers, `.env`, n8n) antes de editar. Nunca trate números de testes
> antigos como prova de E2E WhatsApp.

## 1. Objetivo e arquitetura

Suíte revendível para lojas de carros/motos, produtos instaláveis juntos ou separados:

1. Motor de Simulação
2. Estoque API/admin
3. Chatbot WhatsApp + Estoque Lite + Motor opcional
4. Portal/CRM do vendedor
5. Catálogo público (ainda não)
6. Extensões vendas/metas (#3B / #6)

Integrações por **HTTP** apenas. Estoque = fonte de verdade dos veículos. Tokens só no servidor.

Ordem dos planos: #0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6. Ignore `LEGADO`.

## 2. Regras de trabalho

- Workspace Windows: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Não use `git reset --hard` / limpeza destrutiva sem pedido explícito.
- **Nunca** leia, imprima ou versione: `.env`, tokens Motor/Chatbot, `EVOLUTION_API_KEY`,
  chave Gemini, `MOTOR_ENCRYPTION_KEY`.
- `deploy/*/ .env` é ignorado pelo git; use só `.env.example` no repositório.
- Workflow n8n **versionado** deve manter placeholders
  (`__INSTANCE__`, `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__`).
  O workflow **rodando** no volume Docker pode ter segredos reais — não faça export→commit cego.

## 3. O que foi feito nesta sessão (E2E WhatsApp)

### 3.1 Chatbot → Motor HTTP

- Configurei `deploy/chatbot-standalone/.env` (local, não commitado):
  - `SIMULATION_PROVIDER=http`
  - `MOTOR_URL=http://host.docker.internal:8000`
  - `MOTOR_TOKEN` = credencial permanente do cliente Motor `chatbot-standalone`
- Rebuild da imagem `chatbot-api` (a imagem antiga **não tinha** `MOTOR_TOKEN` no código).
- Validado: `POST /v1/simular` → job Motor → **5 resultados mock** (`concluida`).

### 3.2 n8n / Evolution

Problemas encontrados e contornados:

| Problema | Resolução |
|---|---|
| Placeholders `__INSTANCE__` / `__EVOLUTION_KEY__` / `__CHATBOT_TOKEN__` no runtime | Substituídos **no workflow ativo** via CLI n8n (não no JSON do git) |
| `toolHttpRequest` → `supplyData` but no `execute` (n8n 2.29) | Tools viraram **Code Tool** + `helpers.httpRequest` |
| Gate JS com `Extrair1.first()` inválido | Corrigido para `$('Extrair1').first().json` |
| Lead 409 LGPD (`nome` sem consentimento) | Tool omite nome genérico e retenta sem nome |
| Schema exigia `nome` obrigatório | Schema manual: required só `telefone` + `interesse` |
| Gemini `2.5-flash` / `3.5-flash` 404/503 | Runtime em `models/gemini-3.1-flash-lite`, maxOut 250 |
| Contato `isSaved=true` bloqueava gate | Gate TEMP no runtime: atende todos — **reverter antes de produção** |

### 3.3 E2E WhatsApp observado

Fluxo real com cliente (ex. Anna / Onix):

1. Mensagem chega Evolution → webhook n8n `whatsapp-ai`
2. Chatbot registra mensagem / handoff
3. IA consulta estoque → Onix real R$ 68.000
4. Lead (interesse) e simulação via Motor
5. Resposta no WhatsApp com parcelas

**Importante:** parcelas com nomes Pan/BV/Bradesco/Santander/Fontcred são do **mock do Motor**
(taxas fictícias em `motor-simulacao/app/motor/mock.py`). Não é cotação bancária real.

### 3.4 Comandos úteis n8n (dentro do container)

```bash
docker exec chatbot-standalone-n8n-1 n8n list:workflow
docker exec chatbot-standalone-n8n-1 n8n export:workflow --id=wAiNaoSalvos0001 --output=/tmp/wf.json
docker exec chatbot-standalone-n8n-1 n8n import:workflow --input=/tmp/wf.json
docker exec chatbot-standalone-n8n-1 n8n publish:workflow --id=wAiNaoSalvos0001
docker restart chatbot-standalone-n8n-1
```

Workflow ativo conhecido: **WhatsApp IA - Somente Nao Salvos** (`wAiNaoSalvos0001`).
Pode existir cópia inativa com outro ID — ignorar ou apagar na UI.

## 4. Estado por produto

### Motor (`motor-simulacao/`, compose `deploy/motor-standalone`, `:8000`)

- Async jobs, worker, lease, auth Bearer + tenancy, CLI cliente/credencial.
- Migrations: `0003` job async, `0004` auth, `0005` lease.
- Provedores: mock apenas (`real: false` em `/v1/provedores`).
- Falta Task 10 completa: kill worker ao vivo, restore completo, rotação operacional de credencial.

### Chatbot (`chatbot-api/`, compose `deploy/chatbot-standalone`, `:8001`)

- Tenancy, conversas, mensagens, leads, consentimento, estoque público, handoff auto em saída manual.
- `HttpSimulationProvider` com polling.
- Pendências de produção: auth do webhook Evolution, unique `provider_message_id`, corrida `origem_bot`,
  LGPD em `mensagens.texto`, webhooks `lead.*` / `handoff.requested`, readiness real.

### Estoque (`estoque-api/`, `:8100` no compose chatbot)

- CRUD, tenancy/RBAC, público, outbox, admin parcial.
- Pendências: E2E outbox + receptor, revenda/restore, fechar admin.

### Portal (`portal-gestao/`, `:9000`)

- Design Motora, auth/sessão, dashboard + estoque.
- **Leads** (lista + detalhe) e **Conversas + handoff** (thread + Assumir/Devolver) já reais
  (Plano #3A.1 Tasks 10,12 + client Task 4) — branch `feat/dashboard-leads-conversas`.
  Verificado ao vivo (login → conversas/leads reais → handoff PATCH). 36 testes.
- Requer `CHATBOT_API_TOKEN` no `.env` do portal p/ Leads/Conversas acenderem (setado local).
- Simulações/Equipe/Config ainda placeholder “em breve”.
- Chatbot API ganhou `GET /v1/conversas` e `GET /v1/conversas/{telefone}/mensagens`
  (tenancy, sem provider_message_id) — Plano #3A.1 Task 11, 38 testes.
- Follow-up: mensagens antigas têm mojibake (double-encoding na ingestão do webhook), corrigir na entrada.

## 5. Serviços e portas (checkpoint)

| Serviço | Host |
|---|---|
| Motor API | `localhost:8000` |
| Chatbot API | `localhost:8001` |
| Estoque API | `localhost:8100` |
| Evolution | `localhost:8080` |
| n8n | `localhost:5678` |
| Portal | `localhost:9000` |

Containers “up” não provam WhatsApp `open` nem workflow publicado. Confirmar:

```powershell
# Evolution instance open
# n8n: workflow Active + Publish
# Chatbot env: SIMULATION_PROVIDER=http e MOTOR_* setados (sem imprimir token)
docker compose -f deploy/chatbot-standalone/docker-compose.yml exec -T chatbot-api python -c "from app import config; print(config.SIMULATION_PROVIDER, bool(config.MOTOR_TOKEN))"
```

## 6. Arquivos versionados relevantes

- `n8n/workflow-ai-nao-salvos.json` — template com placeholders e Code Tools (evolução desejada).
- `n8n/workflow-echo.json` — eco simples.
- `docs/contexto-compacto.md` — ler primeiro.
- `docs/handoff-contexto.md` — este arquivo.
- `deploy/motor-standalone/RUNBOOK.md`
- `portal-gestao/**` — portal MVP UI.

Scripts temporários de patch em `n8n/_*.py` **não** devem ser commitados se contiverem lógica one-off;
preferir o JSON limpo + este handoff.

## 7. Próximos passos (ordem)

1. **Produção n8n:** reverter gate para `isSaved === false`; validar Evolution após apagar contato.
2. **Segurança canal:** auth webhook, dedupe unique, buffer/debounce, ordem envio vs `origem_bot`.
3. **LGPD:** não persistir CPF em claro em mensagens; endpoint exclusão.
4. **Motor Task 10** e **Estoque outbox E2E** em ambiente temporário.
5. **Portal** leads/conversas/handoff (#3A.1).
6. **Driver bancário real** (sair do mock) — decisão em hold no design.

## 8. Verificação mínima

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\chatbot-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\estoque-api; .\.venv\Scripts\python.exe -m pytest -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest -q

cd ..\deploy\motor-standalone; docker compose ps
cd ..\chatbot-standalone; docker compose ps
cd ..\..\portal-gestao; docker compose ps

git status --short
```

## 9. Estado comercial

- Demo controlada **com WhatsApp real + estoque real + simulação mock**: sim.
- Produção / revenda completa: **não**.
- Estimativa backend: ~**80%** para demo; o divisor restante é segurança, LGPD, restore e bancos reais.

## 10. Avisos para a próxima IA

1. Se o E2E “sumir”, primeiro confira: Evolution `open`, n8n **Published**, placeholders **não** voltaram,
   `SIMULATION_PROVIDER=http`, token Motor válido.
2. Não use `printenv` em containers com `MOTOR_TOKEN` / apikey (já vazou uma vez e foi rotacionado).
3. Ao editar Code nodes no n8n via script, preserve `$('NomeDoNo')` — PowerShell come `$`.
4. Import n8n em modo regular **desativa** o workflow; precisa `publish:workflow` + **restart** do container.
5. Mensagens de simulação no WhatsApp com 5 bancos = **sempre mock** até existir driver `real: true`.
