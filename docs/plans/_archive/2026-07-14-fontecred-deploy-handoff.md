# Handoff — Driver Fontecred + resgate de produção (2026-07-14)

> **Status 2026-07-15: SUPERSEDED** — não usar como checklist de “o que falta”.
>
> O que este doc descreveu já foi absorvido:
> - Fontecred **LIVE** no Motor (prod + git); sessão fria/quente e modal COMUNICADOS estabilizados.
> - Código resgatado de prod (Pan API + eventos) está em `main`.
> - **Lições operacionais (ler isto):** `2026-07-15-playwright-licoes-fontecred.md`
> - **Estado atual:** `docs/contexto-compacto.md` + `docs/handoff-contexto.md`
>
> Texto abaixo permanece só como **histórico** do resgate e do fluxo mapeado. Itens “falta git push /
> testar reCAPTCHA / cadastrar credencial” no TL;DR original estão **obsoletos** se o handoff
> atual e o contexto disserem o contrário.

## TL;DR (histórico 2026-07-14 — não executar)

- Driver Fontecred (Playwright) implementado, testado ao vivo e deployado (na época).
- Trabalho em produção não commitado foi resgatado para o git e reconciliado.
- ~~Falta push / smoke Fly / credencial~~ → ver contexto canônico, não esta lista.

---

## 1. O que foi construído (Fontecred)

Financeira de motos, portal `https://app.fontecred.com.br/login#step-1`. Sem API → RPA Playwright,
espelhando o Santander.

**Fluxo real mapeado:** login (e-mail + senha) → fecha pop-up COMUNICADOS → Propostas → Criar
Proposta → CPF/nascimento/celular → **placa auto-resolve o veículo** → valor de venda + prazo +
checkbox SCR → **Simular** → modais PEP/seguro → resultado **multi-prazo** (24x/36x/48x) +
**entrada mínima**.

**Arquivos (Motor):**
- `app/motor/fontecred.py` — driver + parsers.
- `app/motor/providers.py` — entrada `fontecred` (modo playwright, campos e-mail + senha).
- `app/motor/drivers.py` — `REAL_DRIVERS["fontecred"]`.
- `app/config.py` — `FONTECRED_LOGIN_URL`.
- `app/motor/playwright_base.py` — **flag `stealth`** (ver §5).
- `tests/test_fontecred_driver.py` + `tests/fixtures/fontecred/simulacao_parcelas.html` (18 testes).
- `scripts/probe_fontecred.py` — smoke live headed (creds via env).

**Arquivos (Portal):**
- `templates/simulacoes/form.html` — opção "Fontecred real" (reusa o campo Celular do PAN).
- `app/main.py` — branch de simulação real inclui `fontecred`; rótulo de progresso.

**Validação ao vivo (IP residencial):** `RESULT OK` — entrada mínima R$ 3.956,40 + parcelas
24x/36x/48x lidas do portal, batendo com o fixture.

---

## 2. O PROBLEMA descoberto (e como foi resolvido)

### Sintoma
Ao rodar `fly deploy` do `motor2037`, o `alembic upgrade head` falhou:
`Can't locate revision identified by '0011'`. O banco de produção estava na migration **0011**,
mas o repositório (`main`) só ia até **0009**.

### Causa raiz
`fly deploy` usa a **árvore de trabalho local**, não o git. ~4h antes, alguém deployou o Motor
(e o Portal) a partir de arquivos **não-commitados**. Esses arquivos sumiram da árvore local e
**nunca foram para o git** — existiam só dentro das imagens em produção. Divergência:

| | Repo (`main` antes) | Produção |
|---|---|---|
| Motor migrations | até 0009 | **0011** (0010_pan_api, 0011_simulacao_eventos) |
| Motor código | base | + driver **Pan** (`pan.py`, `api_base.py`), `providers.py`, eventos |
| Portal | base | + UI do Pan, `providers`, `meta_capi`, `relatorios`, `financeiro_calc`, template `registros.html` |

### Resolução (feita nesta sessão)
1. **Extraído o código de produção** das imagens (`fly ssh console ... tar | base64`) para o
   Motor e o Portal.
2. **Diff contra `origin/main`** (ignorando CRLF) isolou o trabalho perdido.
3. **Recuperado no git** (commits `ef48924` no Motor; `830c3ca` inclui o Portal). O que só
   existia nas imagens **agora está versionado**.
4. **Fontecred re-integrado na arquitetura nova** (`providers.py`, não mais o approach antigo).
5. **4 testes de credencial** que falhavam (esperavam provedor `"Pan"` mas o código novo
   normaliza para `"pan"`) foram **corrigidos**.
6. **Deploy refeito** com sucesso (alembic agora bate em 0011 → no-op).

---

## 3. O que está DEPLOYADO agora

- **`motor2037`** — código de prod (Pan/eventos) **+ Fontecred**. Verificado:
  `providers = [santander, fontecred, pan]`, `real_drivers = [fontecred, pan, santander]`.
- **`portal2037`** — estado de prod **+ opção Fontecred** na simulação. Responde HTTP 200.

Testes: **Motor 126 verdes**; **Portal 151 verdes** (1 falha **pré-existente** em
`test_relatorios::...filtro_de_periodo`, dependente de data — não relacionada).

---

## 4. Estado do git (IMPORTANTE)

- **`main`** = exatamente o que está em produção + Fontecred. **NÃO foi feito `git push` ainda.**
- `integ-fontecred` = igual a `main` (branch de trabalho).
- `recover-prod` = só o resgate do Motor (checkpoint intermediário).
- `feat/driver-fontecred` = versão **antiga** do Fontecred (arquitetura pré-refactor,
  **não deploya** — preservada só por histórico).

> A `main` foi **resetada** (`reset --hard`) para o estado deployado; os commits antigos do
> Fontecred (arquitetura velha) saíram da `main` mas seguem em `feat/driver-fontecred`.

---

## 5. Notas técnicas-chave

- **reCAPTCHA v3 no login do Fontecred.** A stealth do Santander (UA falso "Chrome 131" +
  client hints) **quebra** o reCAPTCHA (o token não é gerado e o submit trava). Fix: o
  `FontecredDriver` usa **`stealth = False`** → contexto **vanilla** (UA real, sem spoof), igual
  ao `playwright codegen`. Ver `PlaywrightBankDriver.stealth` / `_new_context_vanilla`.
- **Blur ("clicar fora").** O form do Fontecred só recalcula ao **sair do campo**: o driver dá
  `.blur()` explícito após CPF, nascimento e valor de venda.
- **Placa auto-resolve** o veículo (linha com o modelo aparece → clicar). Prazo é dropdown; o
  resultado devolve todos os prazos de qualquer forma. Entrada é **input baixo** → o portal
  devolve a **mínima exigida**, que o parser lê ("Sua entrada").
- **Nome do provedor:** `fontecred` (minúsculo) — o mock homônimo é `Fontcred` (sem 'e'), então
  não há colisão. Credencial guardada sob `fontecred` (e-mail no campo `usuario`).

---

## 6. O que FALTA fazer (próximos passos)

1. **`git push origin main`** ⚠️ — o resgate de produção só está **local**. Enquanto não der push,
   se esta máquina se perder, o código do Pan/eventos/Portal volta a existir só nas imagens.
   **Este é o passo nº1.** (É outward; por isso não foi feito automaticamente.)
2. **Cadastrar a credencial do Fontecred** no Portal → **Acessos bancos** → provedor Fontecred
   (e-mail + senha do lojista). Sem isso o driver não roda em produção (`sem_credencial`).
3. **Testar o Fontecred ao vivo a partir do IP do Fly** (o `motor-worker`). **Maior risco:** o
   reCAPTCHA v3 + Cloudflare passou do **IP residencial**; do **datacenter do Fly** pode dar score
   baixo/bloquear. Testar: subir o worker (`fly machine start` no `motor2037`) e disparar uma
   simulação Fontecred pelo Portal, ou rodar o `probe_fontecred.py` no worker. Se bloquear →
   plano B: proxy residencial ou rodar o worker fora do Fly.
4. **Verificar a UI:** logar no `portal2037`, ir em Simulação manual → o dropdown deve mostrar
   **"Fontecred real"**; simular com placa+valor+celular.

---

## 7. Riscos / dívidas registradas

- **Pan sem testes no repo.** O driver Pan (`pan.py`, `api_base.py`) foi recuperado **sem testes**
  (não iam na imagem do Motor). Já está em produção assim; herdamos o risco, não o criamos. Vale
  escrever testes do Pan depois.
- **`test_relatorios::...filtro_de_periodo`** falha (dependente de data) — pré-existente.
- **Custo do `motor-worker`** (2 GB, Chromium): não vale auto-sleep (é consumidor de fila + tem
  volume → churn). Manter **start/stop manual** na fase de teste (ver memória `fly-scaling-volumes`).
- **Processo:** o problema todo veio de **deployar sem commitar**. Regra: **commit antes de
  `fly deploy`** (o deploy usa a árvore local, não o git).
- **`app.css` / `base.html` do Portal** apareceram modificados na árvore durante a sessão sem eu
  editá-los; foram alinhados ao conteúdo **de produção** por segurança. Se notar algo visual
  estranho, comparar com a imagem de prod.

---

## 8. Comandos úteis

```powershell
# Testar Fontecred ao vivo (local, headed) — precisa Python 3.12+ p/ playwright estável
cd motor-simulacao
$env:MOTOR_FONTECRED_EMAIL="..."; $env:MOTOR_FONTECRED_SENHA="..."
$env:FONTECRED_CPF="..."; $env:FONTECRED_NASC="2002-12-13"; $env:FONTECRED_CELULAR="..."
$env:FONTECRED_PLACA="..."; $env:FONTECRED_VALOR="21900"
./.venv/Scripts/python.exe scripts/probe_fontecred.py

# Deploy (lembre: usa a árvore local — commite antes!)
cd motor-simulacao && fly deploy --ha=false
cd portal-gestao  && fly deploy --ha=false

# Verificar provedores no motor em prod
fly ssh console -a motor2037 -C "python -c 'from app.motor.providers import nomes_provedores_reais; print(nomes_provedores_reais())'"
```

> Obs: o venv local do Motor teve o Playwright atualizado para **1.61** (o pinado 1.49 não
> compila greenlet no Python 3.14 local). Produção (Docker Python 3.12) segue no 1.49 do
> `requirements.txt` — sem impacto.
