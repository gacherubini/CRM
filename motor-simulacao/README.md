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
  captcha/IP, ver `docs/plans/2026-07-16-fly-rpa-captcha-opcoes.md`. Subir esse teto piora
  o scoring de IP e derruba os logins.
- **Idempotência:** mesma `Idempotency-Key` + mesmo payload → `200` com o mesmo `id`;
  payload diferente → `409`.
- Antes de escrever um driver Playwright novo, leia as lições dos anteriores em
  `docs/plans/` (`*licoes-santander*`, `*licoes-fontecred*`, `*licoes-pan-portal*`) —
  são leitura obrigatória registrada no índice de planos.

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
`docs/plans/2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

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
