# Design — Worker Playwright em PC local (IP residencial)

> Status: **DESIGN APROVADO, sem código escrito** (2026-08-12). Não presuma que existe
> worker fora do Fly ao ler logs ou depurar.
>
> Substitui a seção "Worker em IP residencial — PLANEJADO" de
> [`motor-simulacao/README.md`](../../../motor-simulacao/README.md), fechando os pontos que
> lá estavam em aberto: escopo, fallback e desativação de slot.

## Problema

`captcha_login` e `portal_bloqueado` têm como causa raiz o IP do Fly: reCAPTCHA v3 e WAF
pontuam mal faixas de nuvem. Santander, Bradesco e Fontecred **não têm API de parceiro** —
para esses três o RPA é permanente, então corrigir o IP é infraestrutura, não remendo.

Este documento é a opção **I** de
[`2026-07-16-fly-rpa-captcha-opcoes.md`](../../plans/2026-07-16-fly-rpa-captcha-opcoes.md),
cujo gatilho de revisão (`captcha_rate` alto) disparou.

**Ganho secundário:** `storage_state` persistente num IP residencial fixo faz o score do
reCAPTCHA v3 subir ao longo do tempo. Hoje a sessão renasce em IP de datacenter a cada job.

## Hipótese a provar

> Executando o mesmo driver do mesmo commit, a partir de IP residencial, o `captcha_login`
> cai para perto de zero.

Se a hipótese for falsa, nada mais neste documento deve ser construído. Ver **Fase 0**.

## Máquina alvo

PC de gabinete do dono: Windows 11, 16 GB DDR4, Intel i7, uso dedicado a servidor com as
telas desligadas.

O teto de **2 browsers simultâneos** (`MOTOR_MAX_BROWSER_WORKERS`) é decisão anti-ban de
captcha/IP, **não** limite de hardware — vale igual no PC. Quatro bancos habilitados não
significam quatro Chromium: o pico real continua sendo 2. Subir esse teto piora o scoring de
IP e derruba os logins, exatamente como no Fly.

## Decisões tomadas

| # | Decisão | Alternativas descartadas |
|---|---|---|
| D1 | Transporte: **WireGuard sidecar + Postgres direto** | Pull HTTPS (código novo demais para um experimento); Tailscale (duas VPNs, terceiro no caminho das credenciais) |
| D2 | Escopo: **PC pega todo `playwright`, com kill switch por banco** | Lista de bancos explícita (esquecer de incluir driver novo vira bug silencioso); tudo-ou-nada sem saída de emergência |
| D3 | Fallback: **dois gatilhos** — órfã e falha técnica | Só fila parada (lead sem resposta); só contagem de falhas (PC desligado nunca falha, job trava para sempre) |
| D4 | Retry: **3 tentativas apenas para erro técnico** | 3 tentativas em tudo (bloqueia conta bancária; 21 min de espera) |
| D5 | Credenciais: **continuam sendo cadastradas no Portal** | Configuração local no PC |
| D6 | Corte: **um banco primeiro (Bradesco), medir, depois os demais** | Migrar os quatro de uma vez |

## Arquitetura

Nada muda para quem chama o Motor. `POST /v1/simulacoes` continua no `app2037`, o contrato
não muda entre mock, Fly e PC, e o cliente nunca sabe onde a simulação rodou.

O que muda é **quem drena a fila**.

```
Fly (nuvem)                                  Casa do dono
├─ app2037   → API, enfileira ──┐
├─ suite-pg  → fila ←───────────┼── WireGuard ──→  PC gabinete
└─ motor2037 → só fallback   ───┘   (iniciado         └─ Docker Compose
                                     de dentro           ├─ wireguard (sidecar)
                                     para fora)          └─ motor-worker
                                                            └─ Chromium + Xvfb
                                                               ↓ IP residencial
                                                            portais dos bancos
```

Ciclo de um job: o `app2037` grava as tarefas por provedor com status `recebida` → o PC faz
`SELECT ... FOR UPDATE SKIP LOCKED` na fila a cada poucos segundos, reserva com lease →
executa → grava resultado → o cliente lê pela API do Fly.

O worker é **cliente, não servidor**: ele abre a conexão para fora. Não há porta aberta no
roteador, não há necessidade de IP fixo, DNS dinâmico nem regra de firewall de entrada.
CGNAT da operadora não atrapalha.

### Componentes no PC

| Container | Papel |
|---|---|
| `wireguard` | Túnel para a rede privada do Fly (6PN, IPv6). Único com pilha de rede própria. |
| `motor-worker` | `network_mode: service:wireguard`. Imagem de produção do Motor, `MOTOR_WORKER_TIPOS=playwright`. |

Base: [`deploy/motor-standalone/docker-compose.yml`](../../../deploy/motor-standalone/docker-compose.yml),
**sem** o serviço `postgres` e **sem** o `motor-api` — o banco é o `suite-pg` do Fly.

**Por que o WireGuard é container e não app do Windows:** WSL2 tem pilha de rede própria com
IPv6 capenga por NAT, e a rede privada do Fly é IPv6. Túnel no host Windows provavelmente não
alcança o container. Com `network_mode: service:wireguard` o túnel vive na mesma pilha de rede
do worker e o WSL2 sai do caminho.

### Variáveis do worker local

| Variável | Valor | Motivo |
|---|---|---|
| `MOTOR_WORKER_TIPOS` | `playwright` | só drivers de browser; `api` (Credere, Pan, BV) fica no Fly |
| `MOTOR_WORKER_IDLE_STOP_SECONDS` | `0` | **obrigatório** — sem isso o worker sai `exit 0` e ninguém o reinicia (ver Armadilhas do README do Motor) |
| `MOTOR_WORKER_PROVEDOR` | *(vazio)* | D2: pega todos os provedores; o filtro é o kill switch |
| `MOTOR_WORKER_EXCLUIR_PROVEDORES` | *(vazio)* | **novo** — kill switch, lista separada por vírgula |
| `MOTOR_EXECUTOR_ID` | `local-pc` | **novo** — identifica a origem na medição |
| `MOTOR_STORAGE_STATE_DIR` | volume persistente | sessão quente sobrevive a restart; é o que faz o score subir |
| `MOTOR_ENCRYPTION_KEY` | idêntica à do `app2037` | senão as credenciais não abrem |
| `MOTOR_BROWSER_HEADLESS` | `0` | headed sob Xvfb — Akamai bloqueia `headless_shell` |
| `MOTOR_MAX_BROWSER_WORKERS` | `2` | teto anti-ban, não mexer |

`MOTOR_WORKER_PROVEDOR` vazio é intencional e tem consequência: `WORKER_ON_DEMAND` é
`_flag(...) or bool(WORKER_PROVEDOR)` (`app/config.py:108`). Sem provedor definido,
`MOTOR_WORKER_ON_DEMAND` **não pode** ser `1`, senão o worker local passa a chamar
`acordar_workers` e acorda Machines do Fly contra si mesmo.

## Mudanças no Motor

Cinco, todas em `motor-simulacao`. Nenhuma altera o contrato público nem toca em Portal,
Chatbot, Estoque ou Catálogo.

### M1 — Carência antes de acordar o Fly

`acordar_workers` (`app/orquestrador.py:77`) é chamado na criação da simulação
(`app/servico.py:161`). Passa a ignorar tarefa com menos de `MOTOR_FALLBACK_GRACE_SECONDS`
de vida.

**Sem isso o experimento inteiro fica inconclusivo:** o Fly ganha o lease antes do PC em todo
job, o captcha continua e ninguém sabe se o IP residencial resolveu. É a armadilha nº 3 da
seção "Worker em IP residencial" do README do Motor, agora resolvida por código em vez de
procedimento manual de desativar slot.

### M2 — Sweeper de tarefa órfã

Hoje só existe devolução de tarefa cujo **lease expirou** (`app/processamento.py:615`) — ou
seja, worker que pegou e morreu. Não existe nada que detecte "ninguém pegou".

Novo tick periódico: tarefa `playwright` em `recebida` há mais de
`MOTOR_FALLBACK_GRACE_SECONDS`, sem reserva, marca evento e libera `acordar_workers` para
aquele provedor.

Cobre PC desligado, queda de internet, reboot por Windows Update. Sem M2 a decisão D3 não
existe e o job fica preso para sempre.

### M3 — Retry com taxonomia

`MAX_TENTATIVAS_DRIVER` (`app/processamento.py:40`) vai de `2` para `3`.
`MOTOR_DRIVER_TIMEOUT_SECONDS` cai de `420` para `240` — 3 × 420s são 21 minutos de espera
para um lead no WhatsApp.

O que conta para as 3 tentativas e o que não conta, mantendo a taxonomia que já existe em
`_executar_driver_com_retry` (`app/processamento.py:293-359`):

| Exceção | Repete? | Vai para o Fly? | Motivo |
|---|---|---|---|
| `ErroTransitorio`, `TimeoutError` | sim, 3× | sim, após 3 | rede, portal lento, instabilidade — repetir tem chance real |
| `Exception` inesperada (`browser_ausente`, `display_ausente`, `erro_inesperado`) | sim, 3× | sim, após 3 | Chromium morto, Xvfb caído — o Fly pode estar são |
| `DriverDeadlineExceeded` | não | sim | já esgotou o deadline; repetir é gastar mais 240s |
| `RejeicaoNegocio` | **não** | **não** | o banco analisou e disse não; a resposta seria a mesma |
| `IntervencaoNecessaria` (captcha, 2FA) | **não** | **não** | mandar captcha para o datacenter é levar o caso difícil ao ambiente mais fraco — é a causa raiz, não a cura |
| Credencial inválida | **não** | **não** | **3 logins errados bloqueiam a conta bancária da loja**; depois disso nenhum banco simula, em lugar nenhum |

Credencial inválida ganha curto-circuito explícito, integrado ao `registrar_falha_login` que
já existe (`app/credenciais.py:245`).

### M4 — Kill switch por banco e por tipo

`MOTOR_WORKER_EXCLUIR_PROVEDORES`: o worker local pega tudo de `playwright` **menos** o que
estiver na lista. Aplicado na seleção de tarefa (`app/processamento.py:656`), junto do filtro
`WORKER_PROVEDOR` que já existe.

O corte entre PC e Fly para drivers de API é por `tipo_driver`, **não** por nome de banco.
Credere (planejada, agregadora com API), Pan e BV ficam no Fly automaticamente, sem regra
nova: chamada HTTP não sofre captcha e não se importa com IP residencial.

### M5 — Origem da execução (migration)

**Lacuna encontrada no design:** `simulacao_tentativas` (`app/models_db.py:206`) guarda
provedor, status, duração e `codigo_erro`, mas **não** guarda onde a tarefa rodou. Sem isso é
impossível comparar PC e Fly, que é exatamente o que a hipótese precisa provar.

Nova coluna `executor` em `simulacao_tentativas`, preenchida a partir de `MOTOR_EXECUTOR_ID`
(`local-pc` / `fly-motor2037`). Migration pequena; `app/observabilidade.py:81-108` já agrupa
tentativas por provedor e status — é estender o `group_by`, não escrever do zero.

Sem M5 o projeto não tem como se declarar bem-sucedido nem fracassado.

## Credenciais

Não muda nada, e isso é o requisito: **as senhas nunca são configuradas no PC.**

O dono cadastra login e senha no Portal (Revy Control), de qualquer navegador ou celular. O
Portal é BFF: cifra com Fernet (`app/cripto.py:29`) e envia. O Motor guarda **só cifrado** no
`suite-pg`. O worker chama `obter_segredo_para_uso` (`app/credenciais.py:219`) e decifra em
memória, no instante de digitar no portal do banco.

No PC não existe tela de credencial, arquivo de senha nem lista de bancos. Existe **uma
chave** (`MOTOR_ENCRYPTION_KEY`) que abre o cofre na hora do uso. Trocar a senha do Bradesco
continua sendo abrir o Control e trocar; o PC pega a nova no próximo job, sem reiniciar nada.

## A máquina Windows

**Docker Desktop exige sessão de usuário logada.** Um PC que reinicia por Windows Update às
3h e para na tela de login fica com os containers parados até alguém sentar nele — o que
derrota o propósito de ser servidor.

Solução: o PC se comporta como appliance.

| Item | Configuração | Por quê |
|---|---|---|
| Login | Automático (`netplwiz`) | container sobe sem humano após reboot |
| Docker Desktop | "Start when you log in" + `restart: unless-stopped` | recuperação sozinha |
| Tela | Bloqueada por tarefa agendada após o login | ninguém mexe na máquina |
| Monitor | `powercfg /change monitor-timeout-ac 5` | economia; **não afeta o worker** |
| Suspensão | `standby-timeout-ac 0` e `powercfg /hibernate off` | PC dormindo derruba o túnel e some da fila |
| Fast Startup | Desativado | senão o shutdown não é shutdown e o Docker acorda em estado inconsistente |
| Placa de rede | Gerenciamento de energia desligado | Windows suspende adaptador ocioso e o WireGuard cai sem avisar |
| Windows Update | Horário ativo fora do pico de leads | reboot é coberto por M2, mas melhor não cair no pico |

**Telas desligadas não são problema.** O Chromium roda headed dentro do container, sob Xvfb,
numa tela virtual. Ele não sabe se existe monitor físico. Desligar a tela, desconectar o HDMI
ou levar o monitor para outro cômodo não muda nada no comportamento do worker.

## Segurança

Risco aceito e mitigado: a `MOTOR_ENCRYPTION_KEY` passa a existir numa máquina pessoal.

- BitLocker ligado — é o que justifica ter a chave ali.
- `.env` com permissão restrita dentro do WSL, fora do git (ver `.gitignore` da raiz).
- RDP desabilitado, ou restrito à rede local.
- Nenhuma porta no roteador: o túnel é de dentro para fora.
- **Procedimento de rotação escrito antes de precisar dele:** trocar a chave em `app2037` e
  `motor2037` e recadastrar credenciais não é coisa para descobrir no susto de um roubo.

O PC também ganha acesso de escrita ao banco da suíte inteiro, não só à fila. É o preço de
D1; a opção de pull HTTPS resolveria isso e continua sendo a evolução natural se o
experimento virar permanente.

## Medição

**Baseline antes do corte:** `captcha_login` por provedor no Fly nos últimos 30 dias.

**Depois:** a mesma taxa agrupada por `executor` (M5). A hipótese se confirma se o
`captcha_login` de `local-pc` cair para perto de zero enquanto o de `fly-motor2037`
permanece no baseline.

**Alerta de PC fora do ar:** todo disparo do sweeper (M2) significa que o PC não pegou um
job. Vira aviso no grupo de WhatsApp, reaproveitando
[`2026-08-05-plano-alerta-grupo-estoque-simulacao.md`](../../plans/2026-08-05-plano-alerta-grupo-estoque-simulacao.md).
Sem alerta, o PC pode passar uma semana desligado e a descoberta vem pela conta do Fly.

## Testes

Os quatro comportamentos novos são testáveis sem browser e sem rede, com relógio injetado, no
`pytest` do Motor:

- **M1** tarefa recém-criada **não** aciona `acordar_workers`; passada a carência, aciona.
- **M2** tarefa `recebida` além da carência e sem reserva é varrida; tarefa reservada com
  lease vivo **não** é.
- **M3** `ErroTransitorio` repete 3× e depois libera o Fly; `RejeicaoNegocio`,
  `IntervencaoNecessaria` e credencial inválida terminam na primeira e **nunca** liberam o
  Fly.
- **M4** provedor na lista de exclusão não é reservado pelo worker local; driver `api` nunca
  é reservado por worker `playwright`.
- **M5** `executor` é gravado em `simulacao_tentativas` e a agregação de observabilidade
  separa por origem.

Exigem a máquina real:

- Smoke de conectividade: simulação **`mock`** atravessando o túnel — prova a rede sem gastar
  login de banco.
- Smoke real: uma simulação de **um** banco, com evidência de health, eventos do job e logs
  sem segredos.

## Fases

| Fase | Escopo | Depende de |
|---|---|---|
| **0** | `scripts/probe_*.py` no PC contra os portais reais | — |
| **1** | M1–M5 com testes, sem tocar em infra | Fase 0 positiva |
| **2** | Windows: Docker, WireGuard sidecar, energia, autostart, smoke `mock` | Fase 0 positiva |
| **3** | Corta **Bradesco** para o PC, desativa o slot dele no Fly, mede alguns dias | 1 e 2 |
| **4** | Traz os demais bancos | Fase 3 com número bom |

Fases 1 e 2 são independentes e podem correr em paralelo.

**Fase 0 é gate, não formalidade.** É meia hora de trabalho e responde a pergunta que
justifica o projeto inteiro. Se o captcha não disparar do IP residencial, a hipótese está
provada e vale construir tudo. Se disparar igual, a causa não era o IP — e as fases 1 a 4
foram evitadas.

Já existem probes prontos para os quatro bancos — `probe_bradesco.py`,
`probe_santander_login.py`, `probe_fontecred.py` e `probe_pan_portal.py` em
`motor-simulacao/scripts/`. Rodar os quatro no PC custa quase o mesmo que rodar um e produz
o mapa de quais bancos o IP residencial resolve, o que informa a ordem da fase 4. Não é
preciso VPN nem Docker para a fase 0: o probe fala direto com o portal do banco.

**Fase 3 é o segundo gate.** Se o `captcha_login` do `local-pc` não melhorar sobre o
baseline, o trabalho para ali e a fase 4 não acontece.

## Riscos aceitos

- Máquina desligada, queda de internet ou reboot do Windows param os bancos migrados até o
  fallback do Fly assumir — com a latência da carência somada.
- `MOTOR_ENCRYPTION_KEY` em máquina pessoal (mitigado acima).
- O PC enxerga o banco inteiro da suíte, não só a fila (consequência de D1).
- Fallback para o Fly reintroduz o captcha nos casos em que dispara — é degradação
  consciente, não regressão.

## Fora de escopo

- Migrar drivers de API (Credere, Pan, BV) para o PC — não têm o problema.
- Segunda máquina residencial ou alta disponibilidade do worker local.
- Pull por HTTPS (opção 2 de D1) — evolução posterior, se o experimento virar permanente.
- Escrever drivers novos de banco. Este documento é a infraestrutura; drivers novos passam a
  rodar no PC automaticamente por D2, sem mudança de configuração.
