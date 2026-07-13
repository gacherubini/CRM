# Handoff técnico — suíte automotiva

> Checkpoint: **2026-07-13 (Santander live OK — pause para próximos bancos)**.  
> Confirme containers/`.env`/n8n antes de editar. Testes unitários ≠ E2E WhatsApp.  
> Leia primeiro: `docs/contexto-compacto.md`. Planos válidos: `docs/plans/README.md`.  
> **Lições Playwright (obrigatório antes do próximo banco):**  
> `docs/plans/2026-07-13-playwright-licoes-santander.md`.  
> Código deve estar em **`main` = origin/main** após o push desta sessão.

## Estado em uma frase

Suíte **demo forte**: Motor com **1º driver real (Santander)** fim-a-fim no Portal; mock dos outros
bancos; Chatbot/Estoque/Catálogo integrados por HTTP. Bot WhatsApp **off de propósito** (n8n importado,
ainda inactive). Próximo foco de código: **próximos bancos (API-first)** ou go-live WhatsApp — **não**
reescrever o piloto Santander sem ler as lições.

## Verificação

| Produto | Testes (aprox.) | Porta host típica |
|---|---:|---|
| Motor | 69+ | `:8000` |
| Chatbot | 88 | `:8001` |
| Estoque | 65 | `:8100` |
| Catálogo | 23 | `:8200` |
| Portal | 113+ | `:9000` |
| **Total** | **~358+** | Evolution `:8080`, n8n `:5678` |

```powershell
cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/ -q
# Worker live:
cd ..\deploy\motor-standalone
docker compose exec -T motor-worker sh -c "pgrep -a Xvfb; pgrep -a python"
```

## Por produto (feito / falta)

### Motor (`motor-simulacao/`, `deploy/motor-standalone`)

- **Feito:**
  - Jobs async, worker/lease, auth+tenancy, cifra, CLI, mock de 5 bancos.
  - **Task 11** credenciais cifradas (Portal 9A).
  - **Task 12 piloto Santander LIVE:**
    - `SantanderDriver` + `PlaywrightBankDriver` (stealth, storage_state, screenshots).
    - Worker Docker: Chromium + **Xvfb headed** (`MOTOR_BROWSER_HEADLESS=0`), `shm_size: 1gb`.
    - Entrypoint limpa lock X órfão (`scripts/worker-entrypoint.sh`).
    - Multi-prazo parseado da tela real; fallback financiado = valor − entrada.
    - Códigos: `portal_bloqueado`, `portal_falhou`, `display_ausente`, `login_timeout`, etc.
  - Processamento não deixa job eterno em `processando` (catch genérico + retry).
- **Falta:**
  - Demais bancos reais (ver reconhecimento + lições).
  - Multi-banco **paralelo** (1 Playwright por banco no mesmo job).
  - `GET /v1/simulacoes` listagem ao vivo.
  - `testar-login` real (hoje **placeholder**).
  - **Task 10** revenda.

### Portal (`portal-gestao/`)

- **Feito:** auth/RBAC, estoque, leads, conversas, **9A Acessos bancos**, E10 Tráfego.
  - Simulação: form → **progresso HTMX** (`/app/simulacoes/job/{id}`) → resultado multi-prazo.
  - `MOTOR_URL` + **`MOTOR_TOKEN`** obrigatórios (sem token a tela Acessos fica vazia).
  - Alertas de erro com códigos legíveis (`resultado.html`).
- **Falta:** lista de simulações ao vivo (#3A.1 Task 16); #3B residual; Playwright E2E;
  retry outbox CAPI.

### Chatbot / Estoque / Catálogo

- Sem mudança crítica nesta sessão. Chatbot: go-live WhatsApp ainda pendente
  (`docs/go-live-chatbot.md`). Estoque = fonte de verdade dos veículos. Catálogo: Pixel browser ok.

## Problemas duros desta sessão (resumo)

1. **Akamai** bloqueia headless_shell → headed + Xvfb.  
2. **Xvfb lock órfão** após restart → entrypoint limpa.  
3. **Material UI** sem placeholder → labels / `type=tel` / roles.  
4. **Falso positivo "Cliente"** na landing → marcadores pós-login específicos.  
5. **Modal simulações anteriores** + overlays Material → fechar X / Escape / aguardar loading.  
6. **Parser** de parcelas e "Valor liberado" no HTML quebrado.  
7. Hot-patch de `.py` exige **restart do worker** (import em memória).

Detalhe operacional: **`docs/plans/2026-07-13-playwright-licoes-santander.md`**.

## Regras permanentes

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`.
- Integrações **só HTTP**. Tokens só no servidor.
- **Nunca** ler/versionar `.env`, tokens Motor/Chatbot, Evolution, Gemini, chaves de cifra, senhas de portal.
- n8n versionado: placeholders. Ordem planos: `#0 → #1A → #4A → #2A → #5A → #3A/#3A.1 → #3B → #6`.
- Parcelas com nome de banco **sem** `real: true` = mock.
- Próximo banco Playwright: **API-first** — só robô se confirmar sem API.

## Próximos passos (ordem sugerida para o próximo agente)

1. **Ler** `docs/plans/2026-07-13-playwright-licoes-santander.md` + `...-bancos-reconhecimento.md`.
2. Escolher banco (Pan/BV/Bradesco preferir **API**; Fontecred candidato Playwright).
3. Credencial da loja em Portal → Acessos; worker com Xvfb saudável.
4. Implementar driver (reutilizar base); **não** copiar seletores do Santander.
5. Alternativa de produto: go-live WhatsApp (`docs/go-live-chatbot.md`) se operação pedir.

## Avisos operacionais

1. `MOTOR_TOKEN` no compose do Portal = mesmo token do cliente Motor.
2. Após editar `santander.py` / entrypoint no container: `docker compose restart motor-worker` e
   `pgrep Xvfb`.
3. Screenshots de falha: volume `motor_browser_data` → `/srv/data/screenshots/`.
4. Não usar `printenv` em containers com tokens.
5. Rebuild Docker pode falhar por DNS do Hub; hot-copy + restart é workaround válido em dev.
