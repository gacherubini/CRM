# Card — BV e Motrix no Motor de Simulação

> Aberto em 04/09/2026, depois de os quatro bancos existentes voltarem a OK numa rodada
> limpa.
>
> **Status 04/09/2026, fim do dia: Motrix entregue, BV bloqueado.**
>
> - **Motrix LIVE.** `app/motor/motrix.py` + 22 testes + entrada no `probe_todos`.
>   Rodada ao vivo: 48s, percorre login → produto 950009 → CPF → placa → ofertas. O
>   portal recusa o cliente de teste (`motrix_sem_oferta`), com entrada 0 e com R$ 6.000.
>   Falta **um CPF que o Motrix aprove** para ver parcela e fixar o parser contra captura
>   real em vez de texto sintético.
> - **BV parado.** O passo 1 do card foi respondido — *não há API acessível a esta loja*
>   (evidência no `motor-simulacao/README.md`, seção "Motrix e BV") — mas o login do
>   portal foi **desativado** durante o reconhecimento, depois de três logins em dez
>   minutos. Precisa do gerente de relacionamento antes de qualquer código.
> - Rodada dos cinco em 04/09 17:06: Fontecred 48s OK, Pan 35s OK, Bradesco 55s OK,
>   Santander 136s OK, Motrix 48s RECUSA. Suíte 275 verdes (eram 253).

## Objetivo

Colocar **BV** e **Motrix** de pé no Motor, cada um verificado ao vivo pelo
`scripts/probe_todos.py`, sem quebrar os quatro que já funcionam.

## Estado de partida (04/09/2026)

Quatro bancos OK em rodada local headed: Fontecred 53s, Pan 41s, Bradesco 56s,
Santander 137s. Suíte do Motor: 253 testes verdes.

BV e Motrix **não existem no código**. BV aparece só como taxa fictícia em
`app/motor/mock.py:17`; Motrix não aparece em lugar nenhum do repositório.

Credenciais e dados do cliente de teste **já estão** em `motor-simulacao/.env.local`
(gitignored): `MOTOR_BV_PORTAL_USUARIO/_SENHA`, `MOTOR_MOTRIX_PORTAL_USUARIO/_SENHA`,
e os `PROBE_*` preenchidos.

URLs que o dono passou:

- BV: `https://parceiro.bv.com.br/ng-ppar-base-dashboard/#/`
- Motrix: `https://motrix.joinbank.com.br/sign-in?redirectURL=%2Fdashboard`

## Ordem

1. **BV: confirmar se há API antes de gravar clique.** O reconhecimento de julho registra
   indício de "Iniciar Simulação Financiamento Veículo (V4)" no portal dev do BV, e o
   princípio do repo é API-first. Driver de API não quebra quando o banco troca o layout —
   em 04/09 foram quatro quebras de layout em três drivers.
2. BV por Playwright só se a API não existir ou não estiver acessível à loja.
3. **Motrix: reconhecimento do zero.** Sem doc, sem plano, sem indício de API.

## Arquivos que pode tocar

| Arquivo | O quê |
|---|---|
| `app/motor/providers.py:11` | entrada em `PROVEDORES_REAIS` |
| `app/motor/drivers.py:134` | `REAL_DRIVERS` + `_registrar_drivers_reais` (`:137`) |
| `app/motor/bv.py`, `app/motor/motrix.py` | drivers novos |
| `app/config.py` | URL de login e knobs por banco |
| `scripts/probe_todos.py` | entradas no dict `BANCOS` |
| `tests/test_bv_driver.py`, `tests/test_motrix_driver.py` | testes |

## Invariantes

- ~~**Armadilha:** o conjunto `{"santander","pan","fontecred","bradesco"}` está escrito à
  mão **duas vezes** em `drivers.py`.~~ **Resolvida em 04/09:** virou a constante
  `NOMES_REAIS` em `drivers.py`, usada nos dois lugares. Banco novo entra numa linha só, e
  `test_motrix_esta_no_conjunto_de_nomes_reais` guarda isso.
- Contrato `/v1/simulacoes` não muda. Quem chama nunca sabe se por trás é mock ou Playwright.
- Nome de pessoa, código de loja e segredo não entram no código — vão para `app/config.py`
  lendo env, como `PAN_AGENTE_CERTIFICADO`. O Motor serve várias lojas.
- Espera de oferta usa `config.OFERTAS_TIMEOUT_MS`, nunca número cravado, e o orçamento
  (pior login + espera) tem de caber nos 420s de `MOTOR_DRIVER_TIMEOUT_SECONDS`.
- Teto de 2 browsers simultâneos. O probe roda um banco por vez.

## Não faça

- **Não chute seletor.** Escreva um `scripts/_diag_<banco>.py` (o padrão `scripts/_diag*.py`
  já está no `.gitignore`) que despeje `getBoundingClientRect`, `elementFromPoint` e o
  `getComputedStyle` dos ancestrais. Em 04/09, supor em vez de olhar custou dois
  diagnósticos errados; o diag resolveu cada um em uma rodada. Modelo:
  `scripts/_diag_pan_modal.py`.
- **Não use `except: pass` em passo de formulário.** Toda escrita lê de volta. Quatro bugs
  da mesma família apareceram em 04/09 por causa disso.
- **Não confie em `is_visible()` para modal.** Meça a altura do container.
- **Não commite `AGENTS.md` nem `docs/agents/`** — já estavam modificados por outra sessão.
- Não mexa nos quatro drivers que estão OK, a não ser que quebrem.

## Como saber que acabou

```powershell
cd motor-simulacao
.\.venv\Scripts\python.exe -m pytest -q                       # 253 + os novos
.\.venv\Scripts\python.exe scripts\probe_todos.py --bancos bv,motrix
.\.venv\Scripts\python.exe scripts\probe_todos.py             # os seis, sem regressão
```

macOS: `.venv/bin/python` no lugar de `.\.venv\Scripts\python.exe`.

Depois: `cd .claude/skills/revy-research && python gerar_mapa.py` e commitar junto.

## Docs permitidos (só estes)

1. `motor-simulacao/README.md` — armadilhas e onde editar
2. `docs/referencia-viva/planos/2026-07-13-plano1a-task12-bancos-reconhecimento.md` — a
   linha do BV e o roteiro para pedir API ao gerente do banco
3. `docs/referencia-viva/planos/2026-07-15-playwright-licoes-pan-portal.md` — o portal mais
   parecido com um SPA moderno; a lição do `mahoe` e a seção de 04/09

## Docs proibidos nesta tarefa

As lições de Santander e Fontecred (leia **uma** por vez, e só se precisar), o plano 3-VM,
qualquer coisa em `docs/nao-plano/`, e o resto de `docs/fila/`.

## Em aberto, herdado de 04/09

- O Pan devolve **só o prazo 48** pedindo 24/36/48; os outros três devolvem os três. Pode
  ser o portal, pode ser o parser. Não investigado.
- Bradesco fez a análise SCR em **8s** local contra >4min no Fly. É o gate do
  `README.md:90` para a hipótese de IP residencial. Falta repetir duas ou três vezes para
  fechar o número.
