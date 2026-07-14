# Handoff técnico — suíte automotiva

> Checkpoint: **2026-07-14 (deploy Fly.io lab + Evolution → n8n confirmado)**.
> Confirme containers/`.env`/n8n antes de editar. Testes unitários ≠ E2E WhatsApp.  
> Leia primeiro: `docs/contexto-compacto.md`. Planos válidos: `docs/plans/README.md`.  
> **Lições Playwright (obrigatório antes do próximo banco):**  
> `docs/plans/2026-07-13-playwright-licoes-santander.md`.  
> Commits desta sessão estão em **`main` local** (ainda **sem push** — combine antes de enviar).

## Checkpoint de deploy Fly.io — 2026-07-14

### Decisões do ambiente

- Organização `crm-419`, região `gru`, domínios `fly.dev`, uma Machine por aplicação.
- Loja `Moto Center`, slug `moto-center`, WhatsApp `5551980336365`, instância Evolution `loja1`.
- E-mail operacional/admin: `bielcheeeeee@gmail.com`.
- Modo **lab/economia máxima**, alvo informado de **US$10/mês**.
- Segredos/tokens/senhas gerados ficam em `deploy/fly/.env.production.local`, ignorado pelo Git.
  Nunca ler, imprimir, copiar para logs ou versionar esse arquivo.

### Recursos implantados

| Componente | App/recurso | Machine | Estado/configuração relevante |
|---|---|---|---|
| Motor | `motor2037` | `0807560c916d68` | API+worker na mesma Machine; privado/Flycast; autostop |
| Estoque | `estoque2037` | `287e35dbd147e8` | API+outbox na mesma Machine; privado/Flycast; autostop |
| Chatbot | `chatbot2037` | `d8d1375a42e578` | privado/Flycast; autostop |
| Catálogo | `catalogo2037` | `0807560c916768` | público; autostop; volume `catalogo_data` |
| Portal | `portal2037` | `6837936c0d73d8` | público; autostop; volume `portal_data` |
| Evolution | `evolution2037` | `7847926f5d1758` | v2.3.7, 1 GB; autostop; volume `evolution_instances` |
| n8n | `n8n2037` | `0807564f9034e8` | v2.26.8, 1 GB; autosuspend; volume `n8n_data` |
| PostgreSQL | `suite-pg` | `d8946d2f320de8` | Postgres Flex 18.1; 256 MB; volume `pg_data`; ligado |
| Redis | `suite-redis` | Upstash | PAYG; usado pela Evolution |

O volume duplicado do Motor foi removido. Volumes persistentes restantes têm 1 GB e snapshots
agendados. Não criar segunda Machine/volume sem revisar o teto mensal.

### URLs e acessos

- Portal: `https://portal2037.fly.dev`
- Catálogo: `https://catalogo2037.fly.dev` (raiz redireciona para `/l/moto-center`)
- Evolution API: `https://evolution2037.fly.dev/`
- Evolution Manager: `https://evolution2037.fly.dev/manager`
- n8n: `https://n8n2037.fly.dev/` (cadastro inicial/login na própria raiz)
- Portal admin criado com o e-mail acima; senha apenas no arquivo local de segredos.
- Evolution `loja1` criada; conexão/mensagem recebida confirmada pelo usuário.

### Ajustes de deploy já aplicados

- `fly.toml` criados para os produtos e infraestrutura necessária.
- URLs `postgres://` normalizadas para SQLAlchemy/psycopg em Motor, Estoque e Chatbot.
- Motor e Estoque combinam API+worker/outbox para respeitar uma Machine por app.
- Portal e Catálogo corrigidos para CSS HTTPS; Uvicorn do Portal recebe proxy headers.
- Catálogo raiz redireciona para `moto-center`; CSS e página pública responderam 200.
- n8n subiu para 1 GB (512 MB não bastou) e usa `auto_stop_machines = "suspend"`.
- Portal exibiu o frontend Motora correto depois da correção de CSS.

### Estado do n8n/Evolution

- Workflow correto: `WhatsApp IA - Somente Nao Salvos` (18 nós), webhook `POST /webhook/whatsapp-ai`.
- A cópia importada foi preparada com Chatbot em `http://chatbot2037.flycast:8000`, Evolution em
  `https://evolution2037.fly.dev` e instância `loja1`.
- O GET manual no webhook retorna corretamente “not registered for GET”; o nó aceita **POST**.
- Usuário informou ter substituído `__CHATBOT_TOKEN__` nos sete Tool Code e configurado
  `X-Webhook-Token` nos dois nós que chamam `/webhook/mensagem`.
- Ainda **confirmar** no editor:
  1. credencial do `Google Gemini Chat Model1`;
  2. `apikey` Evolution em `Consultar contato na Evolution1`;
  3. `apikey` Evolution em `Responder WhatsApp1`.
- Webhook Evolution deve apontar para
  `https://n8n2037.fly.dev/webhook/whatsapp-ai`, evento `MESSAGES_UPSERT`.
- Entrega Evolution → n8n foi confirmada pelo usuário em 2026-07-14. Ainda falta teste E2E de resposta
  com outro número **não salvo**; mensagens `fromMe=true` representam atendente e pausam o bot.

### Autostop e custo observado

- Eventos reais: Portal ~5m37s, Catálogo ~5m45s, Chatbot ~6m03s e Estoque ~6m07s até autostop.
- Fly não oferece duração customizada de idle; escolhe-se `stop`, `suspend` ou sempre ligado.
- n8n suspenso retoma mais rápido; manter essa configuração no laboratório.
- Evolution dormindo não recebe WhatsApp para se acordar sozinha. Para teste, abrir o Manager/API antes.
- Evolution 1 GB sempre ligada em `gru` foi estimada em ~US$9,20/mês; somada ao Postgres e volumes
  ultrapassa o teto de US$10. Não tornar always-on sem decisão explícita de orçamento/go-live.

### Dados e pendências funcionais

- Estoque: 1 loja, 2 veículos disponíveis, ambos `publicado=false`; publicar pelo Portal para aparecerem
  imediatamente no Catálogo. Catálogo lê a API pública do Estoque; não há importação separada.
- Motor: cliente/credenciais técnicas existem, mas não havia credencial bancária nem simulação no banco
  no checkpoint. Cadastrar banco em Portal → Acessos bancos para simulação real.
- Portal é o frontend principal; Motor e Estoque permanecem APIs privadas por segurança.

### Próximo passo operacional

1. Confirmar Gemini + duas chaves Evolution no workflow.
2. Publicar/salvar o workflow e manter o webhook `MESSAGES_UPSERT` ativo.
3. Acordar Evolution, confirmar `loja1` como `open`, enviar mensagem de outro número não salvo e revisar
   a Execution inteira até `Responder WhatsApp1`.
4. Publicar os veículos desejados no Portal e validar o Catálogo.
5. Só no go-live decidir Evolution always-on e revisar o orçamento.

## Estado em uma frase

Suíte **demo forte**: Motor com **1º driver real (Santander)** fim-a-fim no Portal — agora **devolve a
entrada necessária** (o banco calcula; não é input) e **espera os cards reais** (fix do skeleton). Portal
tem **histórico de simulações por usuário** (Task 16: `GET /v1/simulacoes` + `solicitado_por`). Mock dos
outros bancos; Chatbot/Estoque/Catálogo por HTTP. Transporte WhatsApp Evolution → n8n já foi confirmado,
mas a resposta IA ainda não teve E2E completo. Próximo foco de código: **próximos bancos (API-first)** ou go-live WhatsApp — **não** reescrever
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
