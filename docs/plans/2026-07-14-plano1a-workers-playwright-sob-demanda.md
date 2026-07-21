# Plano #1A — Fan-out multi-banco e workers Playwright sob demanda

> **Status 2026-07-16: DONE (implementado em `main`).** Fan-out multi-banco + workers Playwright
> sob demanda (Fly Machines wake/idle) + orquestrador 512 MB. **Não reimplementar.**
> Teto operacional: **máx. 2 Playwrights** — ver [warm session + batch 2](2026-07-17-plano1a-warm-session-batch2.md).
> Lições e ops: handoff topo + `deploy/fly/*.sh`. Residual: object storage multi-volume se preciso.
>
> **Leitura obrigatória:** `docs/contexto-compacto.md`, `docs/handoff-contexto.md` e
> `docs/plans/2026-07-13-playwright-licoes-santander.md`.

## Objetivo

Transformar uma simulação com vários bancos em tarefas independentes por provedor, executadas em
paralelo. Workers Playwright ficam pré-configurados e parados no Fly.io, são iniciados somente quando
há tarefa e encerram depois de esvaziar a fila. Bancos com API usam um pool leve e não abrem browser.

```text
Usuário cria uma simulação
          │
          ▼
Motor grava o job-pai e uma tarefa por banco
          │
          ├───────────┬───────────┬───────────┬───────────┐
          ▼           ▼           ▼           ▼           ▼
     Santander       PAN       Banco 3     Banco 4     Banco 5
     Playwright      API       worker/API  worker/API  worker/API
          │           │           │           │           │
          └───────────┴───────────┴───────────┴───────────┘
                                  │
                                  ▼
                    resultados/eventos incrementais
                                  │
                                  ▼
              job-pai concluído, parcial ou falhou
```

## Baseline comprovado

- Produção atual: uma Machine `motor2037` combina API, worker, Xvfb e Chromium; fica always-on.
- O loop atual percorre os provedores sequencialmente no mesmo job.
- Em 512 MB, o kernel recusou uma alocação de 512 MB do Chrome e o job terminou por
  `timeout_driver` após 240 segundos.
- Em 2 GB, o health ficou verde e um probe isolado abriu o Chromium headed em **34,41 s**.
- Timeline e prints já existem no Portal em **Registros**; retenção atual de prints: 7 dias.
- Preço consultado em 2026-07-14 para `shared-cpu-2x`/2 GB em `gru`: aproximadamente
  US$ 18,40/mês always-on ou US$ 0,0256/h. Preço é variável; conferir antes do rollout:
  <https://fly.io/docs/about/pricing/>.

## Decisões de arquitetura

1. **Fan-out persistido:** um job-pai cria uma tarefa por banco; não usar threads dentro do job-pai.
2. **Um Chromium por worker:** isolamento de sessão, timeout e memória por banco.
3. **API-first:** PAN e qualquer banco com contrato HTTP não consomem slot Playwright.
4. **Machines pré-criadas e paradas:** não criar/destruir uma Machine a cada simulação.
5. **Wake pela Machines API:** o orquestrador inicia apenas IDs permitidos, usando token deploy
   app-scoped. Não usar token pessoal ou org-wide.
6. **Stop por saída limpa:** worker sem serviço HTTP drena a fila e encerra com código 0; com restart
   policy `on-failure`, saída limpa deixa a Machine parada e crash pode ter retry limitado.
7. **Sem volume compartilhado:** screenshots e storage state precisam de storage privado compatível
   com vários workers; Fly Volume só pode ser montado em uma Machine.
8. **Limite de custo:** paralelismo configurável; começar com 1, depois 2, e liberar 5 apenas após
   medir custo, RAM, WAF e estabilidade.
9. **Compatibilidade:** o pipeline atual permanece atrás de feature flag durante o rollout.

Referências operacionais do Fly:

- Machines sem serviço e lifecycle: <https://fly.io/docs/machines/guides-examples/managing-machines-with-the-api/>
- Restart policy: <https://fly.io/docs/machines/guides-examples/machine-restart-policy/>
- Tokens app-scoped: <https://fly.io/docs/security/tokens/>

## Modelo de dados alvo

### `simulacao_provedores` — nova tabela, migration `0012`

Uma linha por `(simulacao_id, provedor)`:

- `id` UUID;
- `simulacao_id`, `cliente_id`, `provedor`, `tipo_driver` (`api|playwright|mock`);
- `status`: `recebida|acordando_worker|reservada|processando|concluida|rejeitada|falhou|cancelada`;
- `tentativa`, `reserva_token`, `reservada_ate`, `worker_slot_id`;
- `criada_em`, `iniciada_em`, `finalizada_em`, `atualizada_em`;
- `codigo_erro` sanitizado;
- unique constraint `(simulacao_id, provedor)` para impedir duplicidade.

### `worker_slots` — inventário operacional

- `id`, `provedor`, `tipo_driver`, `fly_machine_id`, `regiao`;
- `memory_mb`, `habilitado`, `estado_observado`;
- `ultimo_start_em`, `ultimo_stop_em`, `ultima_falha_em`;
- Machine ID não é segredo; token da Fly nunca entra nesta tabela.

### Eventos e resultados

- Adicionar `provedor` opcional a `simulacao_eventos` para filtrar/agrupar a timeline.
- `simulacao_resultados` continua sendo a saída canônica; unique por tarefa/prazo onde aplicável.
- Jobs antigos, sem tarefas-filhas, continuam legíveis pelo contrato atual.

## Estados e agregação do job-pai

- `recebida`: tarefas criadas, nenhuma iniciou.
- `processando`: pelo menos uma tarefa não terminal.
- `concluida`: todas as tarefas concluíram com oferta/resultado válido.
- `parcial`: ao final, pelo menos uma concluiu e pelo menos uma falhou/rejeitou.
- `falhou`: nenhuma tarefa produziu resultado útil.
- `aguardando_intervencao`: nenhuma continua executando e alguma exige ação humana.
- `cancelada`: cancelamento propagado às tarefas ainda não terminais.

Resultados completos aparecem conforme cada banco termina; não esperar todos para mostrar a primeira
oferta. O estado final só é calculado quando todas as tarefas estão terminais.

## Lifecycle dos workers

1. Orquestrador cria as tarefas na mesma transação do job-pai.
2. Para cada provedor Playwright com fila e sem slot iniciado, muda a tarefa para
   `acordando_worker` e chama `POST /v1/apps/{app}/machines/{id}/start`.
3. Respeita rate limit: no máximo 3 starts no burst; para cinco slots, iniciar 3 e escalonar os 2
   restantes logo depois. Falha/retry deve ser idempotente.
4. Machine inicia Xvfb e o worker com `MOTOR_WORKER_PROVEDOR=<nome>`.
5. Worker reserva somente tarefas daquele provedor com lease e heartbeat.
6. Ao terminar, procura mais tarefas do mesmo provedor durante uma janela ociosa configurável
   (inicial: 60 s) para aproveitar rajadas.
7. Sem trabalho, encerra com código 0. Restart `on-failure` não religa a Machine após saída limpa.
8. Em crash, lease expira, tarefa volta à fila e a Machine pode reiniciar até o teto de retries.

## Latência esperada

- Machine pré-criada/parada: alvo de wake P95 abaixo de 15 s.
- Xvfb: poucos segundos.
- Chromium headed: observado em produção **34,41 s**; meta P95 abaixo de 60 s.
- O banco começa depois disso; o portal já mostra `worker_acordando` e `browser_iniciando`.
- Evitar primeira criação/pull durante a simulação: o deploy prepara/atualiza os slots antes.

## Memória e custo

### Política inicial

- API/orquestrador: 512 MB, sem Chromium.
- Worker de API: 512 MB, concorrência limitada e sem browser.
- Worker Playwright: começar em 2 GB, porque este tamanho já foi validado.
- Canário de redução: 1,5 GB; só promover após 30 execuções reais sem OOM, timeout de launch ou
  degradação do portal. 512 MB está proibido para Playwright.

### Guardrails

- `MOTOR_MAX_BROWSER_WORKERS`: 1 no primeiro canário, 2 no rollout e no máximo 5 após aprovação.
- `MOTOR_WORKER_IDLE_STOP_SECONDS`: 60 inicialmente; medir 30–180 s.
- `MOTOR_MONTHLY_WORKER_SECONDS_LIMIT`: alerta/limite operacional por tenant.
- Métricas: worker-seconds/job, custo projetado, wake, browser launch, duração por banco, RAM high-water.

Exemplo apenas para ordem de grandeza: cinco workers de 2 GB por cinco minutos consomem
`5 × 5/60 × US$0,0256 ≈ US$0,011` de compute. Cinco always-on seriam aproximadamente US$92/mês.
Não usar valores fixos no produto; calcular com tarifa configurável/monitoramento.

## Segurança e privacidade

- Gerar token deploy **app-scoped** e guardá-lo como secret somente no processo orquestrador.
- Worker não recebe `FLY_API_TOKEN`; usar configuração de Machine com secrets explicitamente
  permitidos quando possível.
- Orquestrador só pode iniciar IDs presentes em `worker_slots` e pertencentes ao app esperado.
- Nunca logar token Fly, credencial bancária, CPF, cookies ou HTML do portal.
- Storage state é segredo: cifrar em aplicação antes de enviar ao object storage.
- Screenshots ficam privados, servidos apenas pela API com tenancy/RBAC e `Cache-Control: no-store`.
- Retenção padrão de screenshots: 7 dias; storage state tem ciclo separado e é substituído, não
  versionado indefinidamente.

## Plano de implementação

### Fase 0 — Baseline, flags e contrato

- [ ] Criar flags `MOTOR_FANOUT_ENABLED`, `MOTOR_FLY_AUTOSCALE_ENABLED`,
  `MOTOR_MAX_BROWSER_WORKERS` e `MOTOR_WORKER_IDLE_STOP_SECONDS` com defaults seguros/desligados.
- [ ] Registrar métricas atuais de um job Santander: wake N/A, launch, duração e RAM.
- [ ] Manter testes atuais verdes: Motor 123 e Portal 152.
- [ ] Documentar rollback antes de qualquer alteração de infra.

**Aceite:** deploy com todas as flags desligadas se comporta exatamente como hoje.

### Fase 1 — Tarefas por provedor e migration `0012`

- [ ] Criar `SimulacaoProvedorORM` e `WorkerSlotORM`.
- [ ] Adicionar `provedor` opcional aos eventos.
- [ ] Criar migration linear `0011 -> 0012`, com upgrade/downgrade testados.
- [ ] Criar tarefa por provedor de forma idempotente na criação do job.
- [ ] Não backfillar jobs finalizados; apenas preservar leitura dos resultados antigos.

**Aceite:** retry do POST/idempotency não duplica tarefa; tenancy permanece isolada.

### Fase 2 — Executor de uma tarefa bancária

- [ ] Extrair o corpo por provedor de `_executar_driver` para `processar_tarefa_provedor`.
- [ ] Preservar timeout duro, retry, tentativa, evento e screenshot.
- [ ] Reserva atômica por tarefa com lease/heartbeat e requeue após crash.
- [ ] Agregador recalcula o job-pai sem apagar resultados já concluídos.
- [ ] Adaptar worker atual para modo compatível que ainda pode drenar tarefas sequencialmente.

**Aceite:** cinco mocks concluem com os mesmos resultados; matar o worker não duplica resultado.

### Fase 3 — Fan-out paralelo sem autoscale

- [ ] Executar tarefas independentes com workers locais de teste.
- [ ] Testar conclusão fora de ordem e resultado parcial ao vivo.
- [ ] Propagar cancelamento para tarefas recebidas/reservadas/processando.
- [ ] Garantir no máximo um browser por processo worker.

**Aceite:** cinco drivers fake com delays diferentes iniciam em paralelo e o tempo total se aproxima
do driver mais lento, não da soma.

### Fase 4 — Cliente Fly e orquestrador de slots

- [ ] Criar interface `WorkerLifecycle` e implementação fake para testes.
- [ ] Implementar `FlyMachinesLifecycle` com `httpx`, timeout curto e retry idempotente.
- [ ] Usar token app-scoped, allowlist de machine IDs e escalonamento do rate limit.
- [ ] Eventos: `worker_acordando`, `worker_pronto`, `worker_indisponivel`, `worker_parado`.
- [ ] Se a Fly API estiver indisponível, manter tarefa recuperável e não travar job eternamente.

**Aceite:** chamadas duplicadas de wake não criam Machine nem executam tarefa duas vezes.

### Fase 5 — Entrypoint do worker sob demanda

- [ ] Criar `scripts/on-demand-worker-entrypoint.sh` reutilizando a inicialização segura do Xvfb.
- [ ] Restringir por `MOTOR_WORKER_PROVEDOR` e opcionalmente `MOTOR_WORKER_SLOT_ID`.
- [ ] Drenar a fila, observar idle grace e sair 0.
- [ ] Configurar restart `on-failure` com retries limitados para slots sem serviço HTTP.
- [ ] Sinal SIGTERM encerra browser, libera lease e sai de forma previsível.

**Aceite:** após a última tarefa + idle grace, processo encerra e Machine chega a `stopped`.

### Fase 6 — Object storage privado

- [ ] Introduzir interface `ArtifactStore` com filesystem local e backend Tigris/S3 privado.
- [ ] Migrar novos screenshots para object key; manter leitura fallback dos arquivos antigos.
- [ ] Cifrar storage state antes do upload; rotação/substituição atômica.
- [ ] Expurgo de screenshots por retenção e auditoria de acesso.
- [ ] Testar path traversal, cross-tenant, cache e objeto ausente.

**Aceite:** qualquer worker produz print que o Portal autorizado consegue abrir; vendedor sem permissão
continua sem acesso ao arquivo sensível.

### Fase 7 — Infra Fly com slots pré-criados

- [ ] Separar API/orquestrador do worker no deploy; API não precisa carregar processo Chromium.
- [ ] Criar um slot Playwright parado por banco habilitado, inicialmente só Santander.
- [ ] Criar pool leve para drivers API; PAN não recebe Machine de 2 GB.
- [ ] Preparar script idempotente `deploy/fly/sync-motor-worker-machines.sh` para atualizar imagem,
  env, memória e restart policy sem iniciar slots.
- [ ] Criar/revogar token app-scoped e documentar rotação.
- [ ] Alertar volume órfão, memória da organização e Machines presas em `started` sem fila.

**Aceite:** deploy atualiza o slot parado; nova simulação o inicia; fim da fila o para.

### Fase 8 — Portal e observabilidade por banco

- [ ] Mostrar uma faixa/card por banco com estado e duração.
- [ ] Timeline agrupável por provedor, mantendo eventos sanitizados.
- [ ] Atualizar resultados incrementalmente sem esperar o fechamento do job-pai.
- [ ] Exibir `Acordando worker`, `Abrindo navegador`, `Consultando banco`, `Finalizado`.
- [ ] Métricas/alertas de custo, wake, launch, timeout, fila e worker ocioso.

**Aceite:** usuário entende qual banco ainda roda e recebe ofertas dos rápidos primeiro.

### Fase 9 — Rollout progressivo

- [ ] Deploy schema/flags desligadas.
- [ ] Ativar fan-out com execução ainda no worker atual.
- [ ] Canário Santander sob demanda com máximo 1 worker e 2 GB.
- [ ] Rodar pelo menos 30 execuções; medir launch, RAM e erros.
- [ ] Canário 1,5 GB; voltar automaticamente a 2 GB se houver OOM/launch timeout.
- [ ] Adicionar PAN via pool API.
- [ ] Liberar 2 Playwrights paralelos; depois 3–5 conforme bancos reais entrarem.
- [ ] Atualizar custo e capacidade antes de cada aumento.

## Testes obrigatórios

- Unitários: agregação, lifecycle fake, rate limit, retry, allowlist, custo e idle stop.
- Banco: reserva concorrente, lease expirado, idempotência e cancelamento.
- Integração: cinco drivers fake em paralelo, conclusão fora de ordem e parcial.
- Segurança: cross-tenant, token ausente, screenshot/storage state e sanitização.
- Fly canário: slot parado → start → browser pronto → tarefa → exit 0 → stopped.
- Carga: 30 Santander em sequência e burst controlado de 2; cinco browsers somente após aprovação.

## Critérios de aceite finais

1. Uma simulação com cinco bancos cria exatamente cinco tarefas.
2. Bancos habilitados iniciam em paralelo dentro do limite configurado.
3. Falha de um banco não cancela os demais e gera `parcial` quando há oferta válida.
4. Primeira oferta aparece antes do fechamento dos outros bancos.
5. Worker Playwright parado não consome compute de RAM/CPU; após o job volta a `stopped`.
6. Nenhum job fica `processando` além de lease + timeout + margem operacional.
7. Prints continuam protegidos e disponíveis no Portal autorizado.
8. Custo por job e worker-seconds ficam visíveis; cinco workers nunca ficam always-on por engano.
9. Pipeline antigo pode ser reativado por flag durante o rollout.

## Rollback

1. Desligar `MOTOR_FLY_AUTOSCALE_ENABLED` e `MOTOR_FANOUT_ENABLED`.
2. Reativar a Machine atual API+worker de 2 GB.
3. Parar todos os slots on-demand; não destruí-los durante diagnóstico.
4. Tarefas não terminais voltam à fila após lease; resultados concluídos são preservados.
5. Backend filesystem continua lendo prints antigos enquanto o object storage é revertido.
6. Migration `0012` permanece compatível durante rollback de código; downgrade só em janela controlada.

## Fora de escopo deste plano

- Criar cinco drivers bancários reais de uma vez.
- Contornar captcha, 2FA, WAF ou termos dos portais.
- Substituir API oficial por Playwright quando houver contrato API disponível.
- Cobrança comercial ao cliente final; este plano apenas expõe métricas de custo/uso.
