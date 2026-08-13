# Motor de Simulação

Contrato `/v1/simulacoes`: recebe a solicitação, enfileira, executa os provedores em
fan-out e devolve os resultados por provedor. **As credenciais dos portais bancários vivem
aqui** — cifradas — e em nenhum outro produto.

## Armadilhas — leia antes de mexer

- **O contrato não muda entre mock e real.** Quem chama (n8n, Chatbot, Portal) nunca sabe
  se por trás é `mock` ou Playwright. Driver novo não altera request nem response.
- **Segredo bancário não sai daqui.** O Portal é só BFF: ele cifra e envia; a execução e a
  chave (`MOTOR_ENCRYPTION_KEY`) pertencem ao Motor. A mesma chave tem de estar no
  `app2037` e no `motor2037` — se divergirem, as credenciais não abrem.
- **O cliente nunca vê mensagem técnica nem página bancária.** Só `codigo_erro` estável por
  provedor.
- **Teto de 2 browsers simultâneos** (`MOTOR_MAX_BROWSER_WORKERS`) — decisão B+D de
  captcha/IP, ver `docs/referencia-viva/planos/2026-07-16-fly-rpa-captcha-opcoes.md`. Subir esse teto piora
  o scoring de IP e derruba os logins.
- **Idempotência:** mesma `Idempotency-Key` + mesmo payload → `200` com o mesmo `id`;
  payload diferente → `409`.
- **`MOTOR_WORKER_PROVEDOR` liga o modo on-demand sozinho** (`app/config.py:108`:
  `WORKER_ON_DEMAND = _flag(...) or bool(WORKER_PROVEDOR)`). Com provedor definido o worker
  drena a fila e **sai `exit 0`** após `MOTOR_WORKER_IDLE_STOP_SECONDS` (`app/worker.py:141`).
  No Fly é o comportamento correto — a Machine para e o orquestrador reacorda. **Fora do Fly
  é o processo morrendo sem ninguém para reiniciar:** use `MOTOR_WORKER_IDLE_STOP_SECONDS=0`,
  que zera `idle_stop` e mantém o loop vivo sem alterar código.
- Antes de escrever um driver Playwright novo, leia as lições dos anteriores em
  `docs/referencia-viva/planos/` (`*licoes-santander*`, `*licoes-fontecred*`, `*licoes-pan-portal*`) —
  são leitura obrigatória. Uma lição por vez, não as três.

## Onde editar

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | API `/v1/simulacoes`, health, métricas |
| `app/servico.py` | Domínio da simulação |
| `app/orquestrador.py` · `app/fanout.py` | Fila, fan-out por provedor, wake de workers Fly |
| `app/worker.py` · `app/processamento.py` | Execução dos jobs |
| `app/motor/drivers.py` · `providers.py` | Registro e seleção de driver |
| `app/motor/{santander,fontecred,bradesco,pan_portal,pan}.py` | Drivers por banco |
| `app/motor/playwright_base.py` · `sessao_browser.py` | Base RPA, sessão quente |
| `app/motor/mock.py` | Driver mock (taxas fictícias) |
| `app/credenciais.py` · `app/cripto.py` | Credenciais cifradas por loja |

Estado dos bancos e mapa de campos por provedor:
`docs/referencia-viva/planos/2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

## Ciclo de vida do job

`recebida → processando → concluida | parcial | falhou | aguardando_intervencao`

A criação responde `202` com `status: recebida`; o worker executa e atualiza. Resultados
parciais são normais (um banco responde, outro falha).

## Rodar e testar

```bash
cd motor-simulacao
python -m pytest -q
python -m alembic upgrade head      # head: confira com `alembic heads`
```

Stack isolada com Docker (API + Postgres + worker):
[`../deploy/motor-standalone/README.md`](../deploy/motor-standalone/README.md).

## Deploy

A **API** roda no bundle `app2037` (`127.0.0.1:8004`) com `MOTOR_ORCHESTRATOR_ONLY=1` e
`MOTOR_WORKER_TIPOS=api,mock`. Os **slots Playwright** ficam no app `motor2037`, em `gru`,
`stopped` no idle, acordados pela Machines API. Detalhes:
[`../deploy/fly/3vm/README.md`](../deploy/fly/3vm/README.md).

## Worker em IP residencial — PLANEJADO, não implementado

> **Status (2026-08-13): design aprovado, sem código de orquestração PC×Fly.**
> Card: [`docs/fila/2026-08-12-worker-playwright-pc-local.md`](../docs/fila/2026-08-12-worker-playwright-pc-local.md).
> Não presuma que existe worker fora do Fly ao ler logs ou depurar.
> Gate: `scripts/probe_bradesco.py` no IP residencial **antes** de construir encanamento.

**Por que sair do datacenter.** `captcha_login` e `portal_bloqueado` têm como causa raiz o
IP do Fly: reCAPTCHA v3 e WAF pontuam mal faixas de nuvem. Santander, Bradesco e Fontecred
**não têm API de parceiro** (Pan e BV têm) — para esses três o RPA é permanente, então
corrigir o IP é infraestrutura, não remendo. Catálogo de opções e a decisão anterior (B+D)
estão em `docs/referencia-viva/planos/2026-07-16-fly-rpa-captcha-opcoes.md`; isto é a opção **I** daquele doc,
cujo gatilho de revisão (`captcha_rate` alto) disparou.

**Ganho secundário:** `storage_state` persistente num IP residencial fixo faz o score do
reCAPTCHA v3 subir ao longo do tempo — hoje a sessão renasce em IP de datacenter a cada job.

**Antes de construir qualquer encanamento**, rode `scripts/probe_bradesco.py` na máquina
residencial contra o portal real. Se o captcha não disparar, a hipótese está provada; se
disparar, a causa não era IP e o resto do trabalho é desnecessário.

**Como configurar** (worker Playwright numa máquina fora do Fly):

| Variável | Valor | Motivo |
|---|---|---|
| `MOTOR_WORKER_PROVEDOR` | `bradesco` | filtra a fila desse banco |
| `MOTOR_WORKER_IDLE_STOP_SECONDS` | `0` | **obrigatório** — sem isso o worker sai `exit 0` (ver Armadilhas) |
| `MOTOR_WORKER_TIPOS` | `playwright` | só drivers de browser |
| `MOTOR_STORAGE_STATE_DIR` | volume persistente | sessão quente sobrevive a restart |
| `MOTOR_ENCRYPTION_KEY` | idêntica à do `app2037` | senão as credenciais não abrem |

1. **Rede:** `fly wireguard create` gera um peer; a máquina entra na rede privada e alcança
   o `suite-pg` por DNS interno. O Postgres **não** é exposto publicamente. IP residencial
   dinâmico não atrapalha — quem inicia a conexão é a máquina local.
2. **Execução:** Docker (WSL2 no Windows) com a imagem de produção, para manter paridade de
   Chromium/Xvfb e não abrir janela de browser na tela de quem usa o PC.
3. **Desativar o slot do banco em `worker_slots`.** Se a Machine do Fly continuar sendo
   acordada, as duas disputam a mesma tarefa; se a do Fly ganhar o lease, o captcha continua
   e o teste fica inconclusivo.
4. O worker local **não** acorda Machines do Fly: `acordar_workers` só roda quando
   `WORKER_ON_DEMAND` é falso (`app/worker.py:66-70`), e o provedor definido o mantém ligado.

**Riscos aceitos:** máquina desligada, queda de internet ou reboot do Windows param aquele
banco (não há fallback automático nesta v1); e a `MOTOR_ENCRYPTION_KEY` passa a existir numa
máquina pessoal — exige disco cifrado e `.env` fora do git.

**Em aberto:** escopo inicial (recomendação é migrar só o Bradesco, como experimento com
hipótese mensurável — `captcha_login` cair para perto de zero — antes de mover os outros
três) e o procedimento exato de desativar um slot sem quebrar o orquestrador.
