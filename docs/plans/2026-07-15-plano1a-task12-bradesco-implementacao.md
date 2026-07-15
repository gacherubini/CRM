# Driver Real Bradesco (Turbo Lojista) — Implementation Plan

> **Status 2026-07-15:** plano escrito; **ainda não implementado**.
> Codegen do dono em arquivo local (`Downloads/Bradesco.txt`) — **não versionar** (pode conter senhas).
>
> **Ler antes de codar:** `2026-07-13-playwright-licoes-santander.md`,
> `2026-07-15-playwright-licoes-fontecred.md`,
> `2026-07-13-plano1a-task12-bancos-reconhecimento.md`.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Adicionar driver real `bradesco` via Playwright no portal Turbo Lojista, multi-prazo,
entrada **opcional** (só preencher se o usuário mandar), plugado em `REAL_DRIVERS` sem quebrar
Santander/Fontecred/Pan API.

**Architecture:** `BradescoDriver(PlaywrightBankDriver)` reutiliza browser, storage_state, screenshots
e mapeamento de erros. Fluxo Angular Material em `turbo.bradesco`. Testes com fixtures HTML offline;
smoke live gated `MOTOR_BRADESCO_LIVE=1`.

**Tech Stack:** Python 3.14, Playwright sync, pytest, FastAPI Motor existente.

## Global Constraints

- Workspace: raiz do monorepo; produto em `motor-simulacao/`.
- Baseline de testes: rodar `cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q` e
  registrar a contagem **antes** de começar (não assumir número fixo).
- **Nunca** ler/imprimir/logar `.env`, `MOTOR_ENCRYPTION_KEY`, credenciais, CPF real ou `storage_state`.
- **Nunca** copiar senhas do codegen para o repo, fixtures ou planos.
- Playwright: headed + Xvfb em produção; lições de sessão fria/quente (Fontecred).
- Bradesco é Angular Material → âncoras por **role + texto visível** (lição Santander), não placeholder.
- Entrada: **não obrigatória**. Se `condicoes.entrada` for 0/None, deixar o campo vazio / não preencher.
  Se o user mandar valor, preencher "Valor da entrada (opcional)".
- TDD: teste falha → implementação mínima → passa → commit.
- Um banco por vez; não reabrir Fontecred/Santander sem evidência nova.

## Fluxo mapeado (codegen 2026-07-15)

Portal: `https://turbo.bradesco/originacaolojista/`

| # | Etapa | Ações (codegen) | Notas |
|---|---|---|---|
| 0 | Login | textbox **CPF**, textbox **Senha**, botão **Entrar** | Login do lojista = `usuario`+`senha` da credencial (CPF do lojista, não do cliente) |
| 1 | Início | botão **Nova proposta** | Após login |
| 2 | Pré-análise pessoa | textbox **CPF** (cliente), textbox **Celular**, checkbox `.mat-checkbox-inner-container`, **Avançar** | Celular obrigatório no fluxo real |
| 3 | Veículo | select UF (ex. SP), textbox **Placa (Opcional)**, label do modelo (ex. YAMAHA…), **Confirmar** | Placa opcional no portal; se ausente, precisa de caminho por modelo/valor |
| 4 | Valores | **Valor do veículo**, **Valor da entrada (opcional)**, **Avançar** | Entrada só se user mandar |
| 5 | Simulação | URL `.../simulation`; botão **Fechar** (modal?), **Avançar** | Tratar modal se aparecer |
| 6 | Ofertas | botões `48x de R$…`, `36x…`, `24x…`, `18x…`; `12x Entrada mínima necessária` | Multi-prazo; prazo 12x pode ser bloqueio de entrada mínima |

Regras de negócio do dono:

- **Entrada não é necessária** no Bradesco, a menos que o usuário informe.
- Não enviar proposta final no smoke — só ler parcelas e cancelar/sair.

## File Structure

- `app/motor/bradesco.py` — CRIAR: `BradescoDriver`, parsers, `fabrica_bradesco`
- `app/motor/drivers.py` — MODIFICAR: registrar `REAL_DRIVERS["bradesco"]`
- `app/config.py` — MODIFICAR: URL login default, timeout se necessário
- `tests/fixtures/bradesco/` — CRIAR: HTML de login, passo pessoa, veículo, simulação/ofertas
- `tests/test_bradesco_driver.py` — CRIAR: parsers + fluxo fixture
- `tests/test_bradesco_live.py` — CRIAR: smoke gated
- Portal (se faltar label): lista de financeiras / Acessos bancos — só se o slug `bradesco` não
  aparecer; checar UI existente antes de mexer

---

### Task 0: Gate API (rápido, 15–30 min)

**Files:** nenhum de código se a decisão for Playwright.

- [ ] **Step 1:** Confirmar com o dono/gerente se a loja tem API de simulação Bradesco lojista.
  Se **sim** e houver sandbox + doc → pivotar para `ApiBankDriver` e **pausar** este plano.
- [ ] **Step 2:** Se só portal (caso atual da loja) → seguir Tasks 1–4 Playwright.

**Expected:** decisão escrita no topo deste arquivo (`API | Playwright`).

---

### Task 1: Parsers e fixtures offline

**Files:**
- Create: `tests/fixtures/bradesco/ofertas.html` (HTML sintético com botões de prazo)
- Create: `app/motor/bradesco.py` (só funções puras no início)
- Create: `tests/test_bradesco_driver.py`

**Interfaces:**
- `parse_moeda_br(texto) -> Decimal`
- `parse_parcelas_bradesco(texto_ou_html) -> list[tuple[int, Decimal]]`
  - Casar padrões tipo `48x de R$ 1.234,56` e `48x de R$` + valor próximo
  - Ignorar ou marcar especial `12x Entrada mínima necessária` (sem parcela numérica)
- `PROVEDOR = "bradesco"`
- `LOGIN_URL_DEFAULT = "https://turbo.bradesco/originacaolojista/login"`

- [ ] **Step 1: Escrever testes que falham**

```python
# tests/test_bradesco_driver.py (trecho)
from app.motor.bradesco import parse_moeda_br, parse_parcelas_bradesco


def test_parse_moeda_br():
    assert parse_moeda_br("R$ 1.234,56") == __import__("decimal").Decimal("1234.56")


def test_parse_parcelas_botoes_nx_de_rs():
    html = """
    <button>48x de R$ 890,12</button>
    <button>36x de R$ 1.050,00</button>
    <button>12x Entrada mínima necessária</button>
    """
    pares = parse_parcelas_bradesco(html)
    assert (48, __import__("decimal").Decimal("890.12")) in pares
    assert (36, __import__("decimal").Decimal("1050.00")) in pares
    assert all(p[0] != 12 for p in pares)  # bloqueio sem valor de parcela
```

- [ ] **Step 2: Rodar e ver falhar**

```powershell
cd motor-simulacao
.\.venv\Scripts\python.exe -m pytest tests/test_bradesco_driver.py -v
```

Expected: FAIL (módulo inexistente).

- [ ] **Step 3: Implementar parsers em `bradesco.py`**

- [ ] **Step 4: Testes verdes + commit**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_bradesco_driver.py -q
git add motor-simulacao/app/motor/bradesco.py motor-simulacao/tests/test_bradesco_driver.py motor-simulacao/tests/fixtures/bradesco
git commit -m "feat(motor): parsers e fixtures Bradesco"
```

---

### Task 2: `BradescoDriver` com modo fixture

**Files:**
- Modify: `app/motor/bradesco.py`
- Modify: `tests/test_bradesco_driver.py`
- Fixtures: `login.html`, `nova-proposta.html`, `simulation.html` (mínimo viável)

**Regras de validação pré-browser:**

| Campo | Regra |
|---|---|
| CPF cliente | obrigatório |
| Celular | obrigatório (`celular_obrigatorio`) |
| Valor veículo | obrigatório se portal não resolve só por placa |
| Placa | opcional no portal |
| Entrada | opcional — preencher só se `> 0` |
| UF licenciamento | default sensato (ex. da solicitação ou config loja); codegen usou SP |

- [ ] **Step 1: Teste de validação**

```python
def test_rejeita_sem_celular():
    # montar SolicitacaoSimulacao sem celular → RejeicaoNegocio("celular_obrigatorio")
    ...


def test_entrada_zero_nao_preenche(monkeypatch):
    # com html fixture: garantir que o driver não exige entrada
    ...
```

- [ ] **Step 2: Implementar classe**

```python
class BradescoDriver(PlaywrightBankDriver):
    provedor = PROVEDOR
    # Turbo = Angular Material; stealth=True como Santander (avaliar se captcha/WAF).
    stealth = True

    def login(self, page, usuario: str, senha: str) -> None: ...
    def preencher_e_ler(self, page, sol: SolicitacaoSimulacao) -> list[ResultadoDriver]: ...
```

Fluxo `preencher_e_ler` (espelho do codegen, âncoras estáveis):

1. `get_by_role("button", name="Nova proposta")`
2. CPF + Celular + checkbox + Avançar
3. UF + Placa (se houver) + seleção veículo + Confirmar
4. Valor do veículo; entrada **só se** `sol.condicoes.entrada > 0`; Avançar
5. Fechar modal se botão Fechar visível; Avançar
6. Ler botões `Nx de R$` → `ResultadoDriver` multi-prazo
7. Não clicar em enviar proposta; opcional Cancelar

Sessão:

- Reutilizar `storage_state` (login quente vs frio — lição Fontecred).
- Timeline com etapas: `login_confirmado`, `nova_proposta`, `pessoa_ok`, `veiculo_ok`,
  `valores_ok`, `ofertas_lidas`.
- Screenshots em falha via base.

- [ ] **Step 3: Fixture mode** (`html_simulacao=` ou env `MOTOR_BRADESCO_FIXTURE_HTML`) para CI sem browser.

- [ ] **Step 4: Testes verdes + commit**

```text
git commit -m "feat(motor): BradescoDriver com fluxo fixture"
```

---

### Task 3: Registrar em `REAL_DRIVERS` + gating credencial

**Files:**
- Modify: `app/motor/drivers.py`
- Modify: `tests/test_gating_real.py` ou equivalente existente
- Portal: confirmar que "Bradesco" aparece em Acessos bancos (credencial usuario/senha)

- [ ] **Step 1: Teste**

```python
def test_bradesco_em_real_drivers():
    from app.motor import drivers as D
    D.garantir_drivers_reais()  # nome real da função no código
    assert "bradesco" in D.REAL_DRIVERS
```

- [ ] **Step 2: Registrar**

```python
# drivers.py — junto aos outros
from app.motor.bradesco import fabrica_bradesco
REAL_DRIVERS["bradesco"] = fabrica_bradesco()
# incluir "bradesco" no set de nomes conhecidos em resolver_drivers
```

- [ ] **Step 3: Credencial** via `PUT /v1/provedores/bradesco/credenciais` com
  `{ "usuario": "<cpf-lojista>", "senha": "<senha>" }` (só no ambiente, nunca no git).

- [ ] **Step 4: Suíte completa + commit**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git commit -m "feat(motor): registra driver real bradesco"
```

---

### Task 4: Smoke live gated

**Files:**
- Create: `tests/test_bradesco_live.py`
- Update: RUNBOOK / handoff com env `MOTOR_BRADESCO_LIVE=1`

- [ ] **Step 1: Smoke local headed (dono)**

```powershell
$env:MOTOR_BRADESCO_LIVE="1"
# credencial já no DB local ou via API
.\.venv\Scripts\python.exe -m pytest tests/test_bradesco_live.py -v -s
```

Critérios:

- Login OK
- Ofertas com ≥1 prazo numérico
- Sem envio de proposta
- Timeline sem PII

- [ ] **Step 2: Deploy motor se live OK** (só após ok local; pedir confirmação para Fly).

- [ ] **Step 3: Doc de lições** se houver surpresa (WAF, Material, modal):
  `docs/plans/2026-07-XX-playwright-licoes-bradesco.md`

- [ ] **Step 4: Commit final**

```text
git commit -m "test(motor): smoke live Bradesco gated"
```

---

## Códigos de erro estáveis (propostos)

| Código | Quando |
|---|---|
| `celular_obrigatorio` | sem celular na solicitação |
| `credencial_invalida` | login rejeitado |
| `portal_bloqueado` | WAF / access denied |
| `bradesco_sem_oferta` | sem botões de prazo legíveis |
| `entrada_minima_necessaria` | só prazos bloqueados (ex. 12x) |
| `portal_falhou` | etapa inesperada |

## O que precisa do dono

1. Credencial lojista Bradesco Turbo (cadastrar no portal/Motor — **não colar no chat em commit**).
2. Confirmar se placa sozinha resolve o veículo ou se o fluxo real exige escolha manual do modelo.
3. Confirmar UFs/modelos mais usados.
4. Rodar 1 simulação manual se o codegen desatualizar.

## Riscos

- Angular Material: re-render, modais, skeleton de cards (lição Santander).
- Campo checkbox genérico `.mat-checkbox-inner-container` é frágil — preferir label acessível.
- `page.goto` forçado no codegen (step-vehicle / simulation) pode ser desnecessário se o botão Avançar
  navegar sozinho; preferir clique + wait de URL/locator.
- ToS do portal; uso só com conta da loja.

## Ordem vs Pan portal

Implementar **Bradesco primeiro** (banco novo zero no REAL_DRIVERS Playwright), depois Pan portal
(`2026-07-15-plano1a-task12-pan-playwright-implementacao.md`) para não misturar PRs.
