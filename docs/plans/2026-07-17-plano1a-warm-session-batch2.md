# Plano #1A — Warm session + batch 2 (latência multi-banco)

> **Status 2026-07-17:** **Fases 0–2 no código** (flags, path canônico, semáforo batch 2 no worker,
> eventos de sessão/slot). Keep-alive / fan-out Fly (fases 3–4) ainda abertos.  
> Complementa (não substitui) o [fan-out / workers sob demanda](2026-07-14-plano1a-workers-playwright-sob-demanda.md).  
> Lições obrigatórias: [Santander](2026-07-13-playwright-licoes-santander.md),
> [Fontecred](2026-07-15-playwright-licoes-fontecred.md).  
> Mapa de bancos: [reconhecimento](2026-07-13-plano1a-task12-bancos-reconhecimento.md).

## Problema que este plano resolve

Multi-banco **já foi pensado/tentado em paralelo**. A dor que sobra não é só “somar tempos no `for`”:

1. **Concorrência alta (ex.: 4 Playwrights)** no mesmo egress (IP Fly/datacenter) aumenta
   pressão de WAF, RAM e chance de `portal_bloqueado` / timeout — o vendedor sente **demora**.
2. **Login frio em toda simulação** custa dezenas de segundos e é o passo que o portal mais vigia
   (auth, captcha, score).

**Ideia do dono (canônica aqui):**

- rodar Playwright **de 2 em 2** (não 4 de uma vez);
- reutilizar **sessão já logada** (cookies / `storage_state` / tokens de browser) para **não logar de novo**.

Este plano formaliza isso como o **primeiro incremento útil de escala do Motor (eixo D)**,
antes (ou em paralelo controlado) do autoscale Fly completo.

## Fora de escopo

- Contornar captcha/2FA/WAF com “hack” (proxy residencial fica como **plano B de rede**, §6).
- Implementar Bradesco/Pan portal (planos próprios).
- Substituir fan-out de machines; só define **regras de concorrência e sessão** que o fan-out deve respeitar.
- Redesign completo do Portal (cards por banco): mínimo de eventos para medir; UI polida = depois.

## Relação com o plano de workers (14/07)

| Tema | Workers sob demanda (14/07) | Este plano (17/07) |
|---|---|---|
| Tarefa por banco | sim (modelo de dados) | consome o mesmo modelo **ou** compat no worker atual |
| Paralelismo | 1 → 2 → 5 machines | **teto operacional = 2** Playwright até métricas ok |
| Sessão | storage state cifrado + object store (fase 6) | **warm path obrigatório** no driver/worker **agora** |
| Custo RAM | start/stop machines | batch 2 + reuso de sessão (menos login = menos tempo ligado) |
| WAF/IP | “medir ao subir para 5”; contornar = fora | **mitiga** com menos concorrência + menos logins |

**Regra:** se os dois planos divergirem, **concorrência e sessão deste doc vencem** até revisão
explícita. Fan-out sem warm session e sem teto 2 **não** é rollout aceitável em produção.

## Baseline já existente no código

Não reinventar:

- `PlaywrightBankDriver` carrega/salva path de `storage_state` no contexto.
- Fontecred: sessão **fria vs quente** (redirect do `/login`, modal COMUNICADOS, não procurar
  credencial se já autenticado) — lição permanente.
- Env: `MOTOR_STORAGE_STATE_DIR` (volume no worker).
- Timeout driver 240s; lease job 300s.
- Plano workers já cita `MOTOR_MAX_BROWSER_WORKERS` com rollout **2** — este plano **fixixa 2
  como default de produto** até evidência, não só “passo do canário”.

## Decisões

1. **Batch 2:** no máximo **2** drivers Playwright `real` em execução simultânea **por Motor**
   (global lab; multi-tenant depois se necessário). Drivers **API/mock não contam**.
2. **Fila em ondas:** se a simulação pede 4 bancos Playwright, sobem 2; ao terminar um, entra o
   próximo (work-stealing simples), não “espera os 2 acabarem para liberar os 2 seguintes”
   (prefere liberar slot assim que livre).
3. **Warm session first:** todo driver Playwright tenta `storage_state` do
   `(cliente_id, provedor)` antes de preencher login. Login frio só se ausente/expirado/rejeitado.
4. **Persistir sessão** após login OK (e de preferência após fluxo estável na área logada),
   sobrescrevendo o state anterior (não versionar infinito).
5. **Três caminhos de sessão (obrigatório nos testes):**
   - frio (sem arquivo / arquivo inválido) → login completo;
   - quente (state válido) → área logada sem re-auth;
   - expirado (state presente mas portal pede login) → login + regravar state.
6. **Reuso no mesmo processo (opcional fase 2):** se o mesmo worker processa outra tarefa do
   **mesmo** provedor dentro de `MOTOR_WORKER_IDLE_STOP_SECONDS`, preferir manter browser/contexto
   quente em vez de relaunch Chromium (~30s).
7. **Ordem de prioridade na fila multi-banco:**
   1. API/mock;
   2. Playwright com sessão quente conhecida;
   3. Playwright frio/desconhecido.
8. **Segurança:** `storage_state` = segredo (cookies de lojista). Nunca logar, nunca commitar,
   path só no volume/object store privado; permissões de arquivo restritas.
9. **Feature flags:**
   - `MOTOR_BROWSER_CONCURRENCY=2` (default 2; 1 = serial seguro; >2 exige aprovação);
   - `MOTOR_WARM_SESSION=1` (default on para drivers que já suportam storage_state);
   - fan-out Fly continua em flags do plano 14/07, desligadas até canário.

## Arquitetura alvo (simples)

```text
Simulação com N bancos
        │
        ▼
   resolver drivers
        │
        ├─ API/mock ──────────────────► pool leve (sem teto 2)
        │
        └─ Playwright ──► fila com semáforo (max 2)
                              │
                              ▼
                    carregar storage_state?
                     /              \
                  quente            frio/expirado
                    │                  │
              área logada          login + gravar state
                    │                  │
                    └──── simular ─────┘
                              │
                              ▼
                    liberar slot → próximo da fila
```

Sem obrigar multi-machine no primeiro incremento: o semáforo pode viver **no worker atual**
(processo único) **ou** em contagem de tarefas `processando` no banco quando houver fan-out.

## Fases de implementação

### Fase 0 — Contrato e métricas (sem mudar comportamento)

- [x] Documentar no Motor: env `MOTOR_BROWSER_CONCURRENCY`, `MOTOR_WARM_SESSION`, path
  `storage_state` por `(cliente_id, provedor)`.
- [x] Eventos sanitizados (se ainda não existirem de forma estável):
  - `sessao_quente` | `sessao_fria` | `sessao_expirada` | `sessao_gravada`
  - `browser_slot_aguardando` | `browser_slot_adquirido` | `browser_slot_liberado`
  - (implementados: quente/fria/gravada + slot adquirido/liberado; `sessao_expirada` e
    `browser_slot_aguardando` ficam para refinamentos)
- [ ] Baseline de 10 sims Santander e 10 Fontecred (lab): % quente vs frio, duração p50/p95,
  `portal_bloqueado`, tempo até primeira oferta se multi-banco.

**Aceite:** flags lidas; métricas manuais ou logs suficientes; suíte atual verde.

### Fase 1 — Warm session endurecido (maior ROI isolado)

- [x] Path canônico de state:  
  `{MOTOR_STORAGE_STATE_DIR}/{cliente_id}/{provedor}.json`  
  (legado `{provedor}.json` ainda é lido se o canônico não existir).
- [x] Garantir Santander + Fontecred: load state no context (via `ctx.storage_state_path`);
  save após fluxo estável via `_salvar_storage_state` + evento `sessao_gravada`.
- [x] Testes unitários de path/frio/classificação browser (`tests/test_sessao_browser.py`).
- [ ] Smoke worker live: segunda simulação consecutiva do mesmo banco deve emitir `sessao_quente`
  e duração de login ≈ 0 (lab Fly — pendente).

**Aceite:** 2 sims seguidas no mesmo provedor (lab) sem preencher senha na segunda, quando o
portal aceitar a sessão.

### Fase 2 — Semáforo batch 2 no worker atual

- [x] `processar_job`: API/mock primeiro (sem teto); Playwright com
  `ThreadPoolExecutor(max_workers=MOTOR_BROWSER_CONCURRENCY)` e lock de DB.
- [x] Ordem browsers: sessão quente antes de fria.
- [x] Teste: 4 fakes `usa_browser` + concurrency=2 → pico ≤ 2 e wall clock em ondas
  (`test_batch2_quatro_browsers_nao_passa_de_dois_simultaneos`).

**Aceite (lab com fakes):** 4 drivers fake com delay, concurrency=2 → wall clock em ondas,
pico ≤ 2.

### Fase 3 — Alinhar fan-out (plano 14/07) a este doc

- [ ] `MOTOR_MAX_BROWSER_WORKERS` default **2** (não 5).
- [ ] Orquestrador não inicia o 3º slot Playwright se já há 2 `processando`/`acordando_worker`.
- [ ] Storage state: se N machines, **não** compartilhar Fly Volume; ou 1 state por slot de
  provedor (1 machine por banco) **ou** object storage cifrado (fase 6 do plano workers).
- [ ] Idle grace: manter 60–180s para reaproveitar browser no mesmo slot após rajada.

**Aceite:** com fan-out ligado e 4 bancos Playwright, no máximo 2 machines headed ligadas.

### Fase 4 — Keep-alive de sessão (opcional, alto valor em loja real)

- [ ] Job periódico (ou CLI) por `(cliente, provedor)` com state: abrir portal, checar marcador
  autenticado, renovar state **sem** criar proposta.
- [ ] Códigos: `sessao_renovada` | `sessao_expirou_keep_alive`.
- [ ] Só após Fase 1 estável; não bloquear fan-out.

**Aceite:** sessão Fontecred/Santander permanece quente por um dia de operação típica da loja
(medido em lab).

### Fase 5 — Observabilidade e critérios de go-live multi-banco

- [ ] Dashboard/logs: % sessão quente, tempo p95 por provedor, fila de slot, `portal_bloqueado`.
- [ ] Só aumentar concurrency de 2 → 3 após 30 execuções multi-banco sem aumento de bloqueio.
- [ ] Portal: mensagem clara se slot em espera (`Aguardando vaga de navegador (2 em uso)`).

## Plano B de rede (IP / WAF) — só se batch 2 + warm não bastar

Documentado para não misturar com o núcleo:

1. Medir se `portal_bloqueado` cai com concurrency 2 e sessão quente.
2. Se **ainda** bloquear no IP Fly: proxy residencial **por loja** no context Playwright **ou**
   worker RPA fora do Fly (VPS/rede loja), API do Motor continua no Fly.
3. Isso **não** entra nas fases 0–3 sem evidência de bloqueio residual.

## Segurança e privacidade

- Não logar conteúdo de `storage_state`, cookies, HTML de login, senha, CPF.
- Screenshots: regra atual (RBAC, no-store, retenção 7 dias).
- State em disco: permissão restrita no volume; backup de volume = tratar como secret.
- Rotação: apagar state se credencial for trocada no Portal 9A.

## Testes obrigatórios

| Tipo | O quê |
|---|---|
| Unit | path do state; classificação frio/quente/expirado; semáforo 2 |
| Driver | Fontecred/Santander: não chama fill de senha em sessão quente (mock) |
| Integração | 4 fakes + concurrency 2 → wall clock em ondas |
| Segurança | state não aparece em evento/log; path traversal no cliente_id rejeitado |
| Live (gated) | 2 sims reais seguidas; segunda com `sessao_quente` |

## Critérios de aceite finais

1. Default de produto: **no máximo 2** Playwright simultâneos.
2. Segunda simulação do mesmo banco no mesmo worker **prefere** sessão quente.
3. Multi-banco com 4 Playwrights **não** abre 4 Chromiums ao mesmo tempo.
4. Drivers API não competem no semáforo de browser.
5. Eventos permitem auditar quente vs frio e espera de slot.
6. Nenhuma regressão: job serial com 1 banco continua igual; flags permitem concurrency=1.
7. Plano workers 14/07, quando implementado, herda concurrency=2 e warm session.

## Rollback

1. `MOTOR_BROWSER_CONCURRENCY=1` (serial).
2. `MOTOR_WARM_SESSION=0` força login frio (debug / state corrompido).
3. Apagar state de um provedor:  
   `rm` no path do volume (ops) sem rebuild.
4. Fan-out Fly desligado se slots competirem mal com o semáforo.

## Ordem sugerida vs outros planos Motor

```text
1) Este plano — Fases 0–1 (warm)     ← ROI imediato em 1 banco
2) Este plano — Fase 2 (batch 2)     ← ROI multi-banco sem 4 IPs quentes
3) Fan-out workers 14/07 — modelo de tarefas + slots, com teto 2
4) Bradesco / Pan portal             ← mais bancos, já sob regras 2+warm
5) Keep-alive (Fase 4) e UI cards
```

Não misturar na mesma PR: warm session + Bradesco + fan-out Fly completo.

## Referências de código

- `motor-simulacao/app/motor/playwright_base.py` — launch, context, `storage_state`
- `motor-simulacao/app/motor/fontecred.py` / `santander.py` — fluxos frio/quente
- `motor-simulacao/app/processamento.py` — loop de provedores (hoje sequencial)
- `docs/plans/2026-07-14-plano1a-workers-playwright-sob-demanda.md` — fan-out
- `MOTOR_STORAGE_STATE_DIR`, volume worker Fly
