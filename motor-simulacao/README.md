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
- **Portal bancário muda modal sem avisar, e o `codigo_erro` aponta para a tela errada.**
  Em 04/09/2026, três dos quatro drivers quebraram em modal novo, e nenhum acusou o modal:
  o Fontecred dizia `nova_proposta_falhou`, o Pan dizia `campo_nao_encontrado` culpando o
  campo Celular. Antes de acreditar no código, **olhe o screenshot do primeiro evento de
  falha**.
- **`is_visible()` do Playwright não enxerga clipping.** O go!PAN deixa o
  `.mahoe-modal__dialog` no DOM com `height: 0` e `overflow: hidden` quando fechado: o
  título responde "visível" e o clique seguinte estoura o timeout sem explicação. Para saber
  se um diálogo está aberto, meça a altura dele. Detalhe e receita de diagnóstico:
  `.claude/skills/revy-research/learnings/2026-09-04-is-visible-mente-com-modal-recortado.md`.
- **Não espere modal auto-abrir: a sessão quente muda o comportamento.** Com
  `storage_state` salvo o go!PAN não abre o modal de agente/operador; com sessão fria abre.
  Abra pelo controle fixo da tela. Vale para qualquer portal com `MOTOR_WARM_SESSION=1`.
- **Toda escrita em formulário lê de volta.** `except: pass` em passo de formulário deixa o
  driver seguir com o campo vazio e morrer minutos depois num passo inocente. Foram quatro
  casos da mesma família em 04/09; o commit `4879c47` já tinha corrigido isso no Bradesco em
  julho, e é por isso que o Bradesco foi o único a passar de primeira.
- **Espera de oferta usa `config.OFERTAS_TIMEOUT_MS`, nunca número cravado.** O Santander
  tinha `90_000` na mão e desistia com o skeleton na tela em dia lento. Orçamento a
  respeitar: pior login + espera precisa caber em `MOTOR_DRIVER_TIMEOUT_SECONDS` (420s).
- **Login de portal bancário é recurso escasso: gaste um por dia, não um por rodada.**
  Em 04/09/2026 o BV aceitou três logins em dez minutos e no quarto respondeu
  *"Usuário ou senha inválidos… acione seu Gerente de Relacionamento e solicite a
  ativação do login"* — com a mesma credencial que tinha acabado de funcionar. Todo
  script de diagnóstico grava `storage_state` e reusa. **Senha recusada = pare**, não
  tente de novo: a segunda tentativa é que desativa.
- **`mat-input-N` não é seletor.** Em portal Angular Material o id é sequencial por
  sessão: no Motrix o CPF nasce `mat-input-0` e vira `mat-input-1` assim que o campo
  Celular aparece. Ancore no rótulo visível do `mat-form-field`.
- **Campo que só existe em um estado do formulário não é campo ausente.** No Motrix a
  Placa só é renderizada com *Tipo do veículo = Usado* (moto nova não tem placa). Antes
  de concluir que o portal não aceita placa, troque o estado e olhe de novo.
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
| `app/motor/{santander,fontecred,bradesco,pan_portal,pan,motrix}.py` | Drivers por banco |
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

### Ver os drivers reais rodando (headed, na sua máquina)

Um comando roda os cinco bancos ao vivo, um de cada vez, e diz quais quebraram:

```powershell
.\.venv\Scripts\python.exe scripts\probe_todos.py            # Windows
.venv/bin/python scripts/probe_todos.py                      # macOS: .venv/bin/python
.\.venv\Scripts\python.exe scripts\probe_todos.py --bancos fontecred,pan
```

Não precisa de Portal, DB nem Fly. Credenciais e dados do cliente vêm de
`motor-simulacao/.env.local` (**gitignored** — como o `.env.local.exemplo`, que já foi
preenchido com senha real uma vez). Log por etapa, screenshot na falha e tabela final ficam
em `data/probes/<carimbo>/`, também fora do git.

Rodada de referência (04/09/2026, IP residencial, placa de moto a R$ 21.900): Fontecred 48s,
Pan 35s, Bradesco 55s, Santander 136s — os quatro OK — e Motrix 48s **RECUSA**. **O Pan devolve
só o prazo 48**, mesmo pedindo 24/36/48; os outros três devolvem os três. Não investigado.

`RECUSA` e `FALHA` são estados diferentes no relatório e no código de saída: recusa é o banco
dizendo não (`RejeicaoNegocio`) com o driver funcionando, e **não reprova a rodada**; só
`FALHA`/`ERRO`/`VAZIO` devolvem 1. O Motrix respondeu *"Não há oferta de crédito disponível para
este cliente"* com entrada 0 e com entrada R$ 6.000 — não é a entrada, é o cliente de teste. Para
ver o Motrix devolvendo parcela é preciso um CPF que ele aprove.

Antes de mexer em seletor de portal, escreva um `scripts/_diag*.py` (padrão já no
`.gitignore`) que despeje o DOM: `getBoundingClientRect`, `elementFromPoint` e o
`getComputedStyle` dos ancestrais. Em 04/09, supor em vez de olhar custou dois diagnósticos
errados; o diag resolveu cada um em uma rodada. Modelo: `scripts/_diag_pan_modal.py`.

Stack isolada com Docker (API + Postgres + worker):
[`../deploy/motor-standalone/README.md`](../deploy/motor-standalone/README.md).

## Motrix e BV — o que foi apurado em 04/09/2026

### Motrix: LIVE, mas sem oferta para o cliente de teste

Driver em `app/motor/motrix.py`, registrado, testado (22 testes) e provado ao vivo.
Percorre login → produto 950009 → CPF → placa → ofertas em ~48s. O portal recusa o
cliente de teste; o caminho todo funciona.

**Não vira driver de API, e a razão importa.** O portal é um SPA sobre
`api-joinbank.ukam.io/v3`, e `POST /v3/auth/sign-in` devolve bearer token de ~24h com
`{accessId, password, type:"app"}`. Só que toda chamada leva junto um header
`x-version-<sufixo>` no formato `<timestamp>.<sha256>`, assinado pelo JS da página. Sem
ele a API responde 401 — testado com token válido em seis formatos de `Authorization`.
Reproduzir a assinatura é contornar controle anti-automação e quebra a cada build deles.

O que falta: **um CPF que o Motrix aprove.** Sem isso não há captura real do painel de
ofertas, e o parser (`parse_ofertas`) está fixado só contra texto sintético — os testes
dizem isso na cara. Quando aparecer uma oferta de verdade, troque
`tests/fixtures/motrix/sem_oferta.txt` por uma captura do painel cheio e confira se o
formato `24x R$ 1.212,76` é mesmo o que o portal usa.

### BV: parado, e não por falta de código

O login foi **desativado** no meio do reconhecimento (ver a armadilha de login acima).
Antes disso deu tempo de responder a pergunta que o card fazia:

**Não há API de simulação acessível a esta loja.** Três evidências:

1. A doc da "Iniciar Simulação Financiamento Veículo (V4)" mora em
   `developers-des.bancovotorantim.com.br` — host de ambiente DES que **nem resolve** no
   DNS público. A própria página diz que o acesso passa pela Governança SOA do BV.
2. O portal público `developers-sandbox.bvopen.com.br` publica sim APIs veiculares
   ("Parceiros F&I", "Parceiros F&I - Digitais", "BV Condição Financiamento Parceiro"),
   mas para *parceiro digital/F&I* sob contrato — o caminho é "Quero ser parceiro".
3. Logado no portal da loja, o menu inteiro é: Usuário · Gerente de relacionamento ·
   Área do cliente (Boleto fácil, Validador de boletos) · Acessos rápidos (Usuários,
   Dúvidas frequentes) · Sair. **Nenhuma** entrada de integração, API, token ou
   credencial.

Então BV é Playwright, como o card já previa no passo 2. E o portal ajuda: por trás do
SPA Angular existe REST same-origin (`ppar-base-dealer-simulador-rs`), com
`POST /api/auth/v2/login`, `/api/security/token/csrf` e `/api/integration/jwt`. Login por
HTTP puro está fora (Akamai Bot Manager + reCAPTCHA Enterprise invisível + senha cifrada
em RSA com chave de `/api/criptografia/publickey/obterchave`), mas **Playwright para o
login + HTTP para a simulação** é um caminho a medir quando o acesso voltar.

Para destravar: pedir ao gerente de relacionamento a reativação do login — e, na mesma
conversa, perguntar se a loja pode ser habilitada nas APIs de parceiro F&I. O roteiro
pronto está em
`docs/referencia-viva/planos/2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

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
