# Handoff técnico — suíte automotiva

> Checkpoint: **2026-07-13 (Santander entrada retornada + fix skeleton; Task 16 histórico LIVE)**.  
> Confirme containers/`.env`/n8n antes de editar. Testes unitários ≠ E2E WhatsApp.  
> Leia primeiro: `docs/contexto-compacto.md`. Planos válidos: `docs/plans/README.md`.  
> **Lições Playwright (obrigatório antes do próximo banco):**  
> `docs/plans/2026-07-13-playwright-licoes-santander.md`.  
> Commits desta sessão estão em **`main` local** (ainda **sem push** — combine antes de enviar).

## Estado em uma frase

Suíte **demo forte**: Motor com **1º driver real (Santander)** fim-a-fim no Portal — agora **devolve a
entrada necessária** (o banco calcula; não é input) e **espera os cards reais** (fix do skeleton). Portal
tem **histórico de simulações por usuário** (Task 16: `GET /v1/simulacoes` + `solicitado_por`). Mock dos
outros bancos; Chatbot/Estoque/Catálogo por HTTP. Bot WhatsApp **off de propósito** (n8n importado, ainda
inactive). Próximo foco de código: **próximos bancos (API-first)** ou go-live WhatsApp — **não** reescrever
o piloto Santander sem ler as lições.

## Verificação

| Produto | Testes (aprox.) | Porta host típica |
|---|---:|---|
| Motor | 106 pass (+**2 falhas pré-existentes**, ver abaixo) | `:8000` |
| Chatbot | 88 | `:8001` |
| Estoque | 65 | `:8100` |
| Catálogo | 23 | `:8200` |
| Portal | 128 | `:9000` |
| **Total** | **~410+** | Evolution `:8080`, n8n `:5678` |

> **2 falhas pré-existentes no Motor** (`test_worker_conclui_com_cinco_provedores`,
> `test_persistencia_do_resultado_apos_worker`): esperam 5 provedores mock e recebem 4. Causa: o driver
> real `Santander` (registrado sob `Santander` e `santander`) sombreia o mock homônimo e é derrubado sem
> credencial em `resolver_drivers`. Confirmado com `git stash` que falham **sem** as mudanças desta sessão.
> Correção candidata: não registrar o real sob o nome `Santander` (maiúsculo) do mock, ou o mock usar outro
> rótulo. **Ainda aberto.**

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
    - Multi-prazo parseado da tela real.
    - **Entrada necessária devolvida pelo banco** (`parse_entrada`): Santander calcula e a tela mostra;
      não é mais enviada como input (`_ajustar_entrada` removido). Novo campo `entrada` em
      `ResultadoDriver`/`ResultadoProvedor`/`ResultadoORM` (**migration 0008**) → exibido no Portal.
      Fallback financiado = valor − entrada(retornada).
    - **Fix skeleton** (`_passo_aguardar_simulacao`): espera o texto **real** do card (`Nx de`) com 2
      leituras estáveis, ignorando o skeleton de carregamento (causa do `parcelas_nao_encontradas`).
    - Códigos: `portal_bloqueado`, `portal_falhou`, `display_ausente`, `login_timeout`, etc.
  - **Listagem `GET /v1/simulacoes`** (Task 16): filtros `status`/`solicitado_por`/`desde`/`ate` +
    paginação `limite`/`offset`, escopada por `cliente_id`; grava `solicitado_por` (header `X-Ator`) no
    create (**migration 0009**). `simulacao_resumo` não decifra payload (CPF omitido).
  - Processamento não deixa job eterno em `processando` (catch genérico + retry).
  - Migrations lineares até **head 0009** (0007 → 0008 entrada → 0009 solicitado_por).
- **Falta:**
  - Demais bancos reais (ver reconhecimento + lições).
  - Multi-banco **paralelo** (1 Playwright por banco no mesmo job).
  - `testar-login` real (hoje **placeholder**).
  - **Task 10** revenda.
  - **2 falhas pré-existentes** (mock 5 provedores, ver tabela de testes acima).

### Portal (`portal-gestao/`)

- **Feito:** auth/RBAC, estoque, leads, conversas, **9A Acessos bancos**, E10 Tráfego.
  - Simulação: form → **progresso HTMX** (`/app/simulacoes/job/{id}`) → resultado multi-prazo, com
    **coluna Entrada** (necessária, devolvida pelo Santander) e whitelist mantendo `entrada`.
  - **Histórico de simulações por usuário (Task 16):** rota `/app/simulacoes/historico` (default "minhas
    sims" por email; toggle "toda a loja" p/ dono/gerente), template `historico.html`, link no form.
    `MotorClient.listar_simulacoes` repassa token do servidor + `X-Ator`=email.
  - `MOTOR_URL` + **`MOTOR_TOKEN`** obrigatórios (sem token a tela Acessos fica vazia).
  - Alertas de erro com códigos legíveis (`resultado.html`).
- **Falta:** #3B residual; Playwright E2E; retry outbox CAPI.
  - **Nota histórico:** sims **anteriores** ao deploy têm `solicitado_por` nulo → não aparecem em "minhas
    sims"; dono vê no escopo "toda a loja". Novas sims populam normalmente.

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
2. **Corrigir as 2 falhas pré-existentes** do Motor (mock `Santander` vs driver real homônimo) — barato e
   destrava a suíte verde.
3. Escolher banco (Pan/BV/Bradesco preferir **API**; Fontecred candidato Playwright).
4. Credencial da loja em Portal → Acessos; worker com Xvfb saudável.
5. Implementar driver (reutilizar base + lição do skeleton); **não** copiar seletores do Santander.
6. Multi-banco paralelo; `testar-login` real; Task 10 revenda.
7. Alternativa de produto: go-live WhatsApp (`docs/go-live-chatbot.md`) se operação pedir.

> **Histórico de simulações por usuário (#3A.1 Task 16): FEITO** nesta sessão — não reimplementar.

## Avisos operacionais

1. `MOTOR_TOKEN` no compose do Portal = mesmo token do cliente Motor.
2. Após editar `santander.py` / entrypoint no container: `docker compose restart motor-worker` e
   `pgrep Xvfb`.
3. Screenshots de falha: volume `motor_browser_data` → `/srv/data/screenshots/`.
4. Não usar `printenv` em containers com tokens.
5. Rebuild Docker pode falhar por DNS do Hub; hot-copy + restart é workaround válido em dev.
