# Driver Real Pan (portal lojista / “Buscopan”) — Implementation Plan

> **Status 2026-07-15:** ✅ **IMPLEMENTADO e validado ao vivo pelo dono** (fim-a-fim, lê ofertas).
> Commits `b3a94b1` (fluxo/âncoras) e `fd1a31a` (leitura de ofertas). `PanPortalDriver` em
> `app/motor/pan_portal.py`; dispatcher em `drivers.py` escolhe **API** (config OpenAPI completa)
> ou **portal** (só usuario+senha). `providers.py`: campos de API viraram opcionais. 20 testes
> novos; suíte do Motor 183 verdes. Smoke local: `scripts/probe_pan_portal.py` (headed).
> Smoke live OK: **48x R$ 800,00 / financiado R$ 15.116,80 / entrada R$ 6.783,20**. UF (RJ)
> testada ao vivo. **Lições: `docs/referencia-viva/planos/2026-07-15-playwright-licoes-pan-portal.md`.**
>
> **Importante:** já existe `PanDriver(ApiBankDriver)` em `app/motor/pan.py` (OpenAPI v2). Este
> driver é o **caminho Playwright do portal** `veiculos.bancopan.com.br` (go!PAN) — não removeu a API.
>
> **For agentic workers:** REQUIRED SUB-SKILL: subagent-driven-development ou executing-plans.

**Goal:** Oferecer simulação real Pan via portal web (multi-prazo se a UI expuser), com **entrada
opcional** (preencher só se o usuário mandar), sem remover o driver API.

**Architecture:**

```text
                    ┌─────────────────────────────┐
  pedido "pan" ──►  │  resolver / fábrica Pan     │
                    └─────────────┬───────────────┘
                                  │
              tem config API      │      só usuario+senha portal
              completa?           │
                 sim │            │ não
                     ▼            ▼
              PanDriver      PanPortalDriver
              (ApiBank)      (PlaywrightBankDriver)
```

Preferência: se `obter_configuracao_para_uso` tiver todos os campos OpenAPI → API; senão, se tiver
`usuario`+`senha` → portal. Evitar dois browsers se a API responder.

**Tech Stack:** Python 3.14, Playwright, httpx (API existente), pytest.

## Global Constraints

- Não apagar nem quebrar testes do `PanDriver` API.
- **Nunca** versionar senhas do codegen; se a senha vazou em arquivo local, **trocar no banco**.
- Entrada: **opcional** — se o user mandar, preencher; senão deixar vazio/default do portal.
- Não enviar proposta/contratação no smoke — só simular e ler.
- Sessão fria/quente + timeline (lição Fontecred).
- TDD + commits frequentes.

## Fluxo mapeado (codegen “buscopan” 2026-07-15)

Portal: `https://veiculos.bancopan.com.br/login`

| # | Etapa | Ações (codegen) | Notas |
|---|---|---|---|
| 0 | Login | textbox **Usuário**, textbox **Senha**, botão **Entrar** | Pode haver banner **Got it!** (cookie/onboarding) antes/depois |
| 1 | Cliente | combobox CPF (`-00` no codegen — âncora frágil), textbox telefone (**Ícone do input** — frágil) | Preferir labels/placeholders reais no HTML vivo |
| 2 | Veículo | botão **Busca placa**, combobox **Digite a placa...** | Placa parece caminho principal |
| 3 | Valor | textbox **Valor de venda** | Codegen teve typo `R$ 2.1900` — driver deve formatar moeda BR corretamente |
| 4 | Simular | botão **Simular** | |
| 5 | Pós | `#combo__input`, campos **Entrada:** / **Venda:** | Ajustar entrada se user mandou; ler parcelas na UI pós-simulação |

Regras do dono:

- **Entrada é opcional**; se o user mandar, tem que botar.
- Codegen parou antes de capturar a grade de prazos — **Task 1 inclui completar o mapeamento**
  das parcelas (screenshot/HTML de resultado).

## File Structure

- `app/motor/pan_portal.py` — CRIAR: `PanPortalDriver` (não misturar com OpenAPI em `pan.py`)
- `app/motor/pan.py` — MODIFICAR levemente: fábrica unificada **ou**
- `app/motor/drivers.py` — MODIFICAR: fábrica que escolhe API vs portal
- `tests/fixtures/pan_portal/` — CRIAR
- `tests/test_pan_portal_driver.py` — CRIAR
- `tests/test_pan_portal_live.py` — CRIAR (gated `MOTOR_PAN_PORTAL_LIVE=1`)
- Manter `tests/test_*pan*` API existentes verdes

---

### Task 0: Completar codegen do resultado

O trecho atual não mostra leitura de `24x`/`36x`/parcela. Sem isso o parser é chute.

- [ ] **Step 1:** Dono (ou sessão headed local com credencial cadastrada) roda simulação até a tela
  de ofertas e salva HTML em `tests/fixtures/pan_portal/resultado.html` (**sem** dados sensíveis reais;
  anonimizar CPF/telefone).
- [ ] **Step 2:** Anotar seletores estáveis dos prazos e da entrada mínima (se houver).
- [ ] **Step 3:** Atualizar a tabela de fluxo neste plano.

**Bloqueio:** Task 2 de leitura de ofertas depende disso. Login + preenchimento podem avançar em paralelo.

---

### Task 1: Decisão de resolução API vs portal

**Files:**
- Modify: `app/motor/drivers.py` e/ou `app/motor/pan.py`
- Test: estender testes de gating/credencial Pan

- [ ] **Step 1: Testes**

```python
def test_pan_usa_api_quando_config_completa(db, cliente_id):
    # cadastra api_key, secret_key, usuario, senha, id_loja, ...
    # resolver_drivers(..., ["pan"]) → instância ApiBankDriver / PanDriver


def test_pan_usa_portal_quando_so_usuario_senha(db, cliente_id):
    # só usuario+senha → PanPortalDriver
```

- [ ] **Step 2: Implementar `_tem_config_api_pan(cfg) -> bool`** reutilizando `_CAMPOS_CONFIG` de `pan.py`.

- [ ] **Step 3: Commit**

```text
git commit -m "feat(motor): resolve Pan API ou portal por credencial"
```

---

### Task 2: Parsers + `PanPortalDriver` fixture

**Files:**
- Create: `app/motor/pan_portal.py`
- Create: `tests/test_pan_portal_driver.py`
- Create: fixtures mínimas

**Validações pré-browser:**

| Campo | Regra |
|---|---|
| CPF | obrigatório |
| Celular | obrigatório no fluxo codegen |
| Placa | obrigatória no caminho “Busca placa” |
| Valor de venda | obrigatório |
| Entrada | opcional (`> 0` → preencher **Entrada:**) |

- [ ] **Step 1: Testes de parse** com HTML do Task 0 (ou sintético se ainda incompleto).

- [ ] **Step 2: Classe**

```python
class PanPortalDriver(PlaywrightBankDriver):
    provedor = "pan"  # mesmo provedor canônico; real=True
    stealth = True  # reavaliar se o portal quebrar com stealth (lição Fontecred captcha)

    def login(self, page, usuario, senha): ...
    def preencher_e_ler(self, page, sol): ...
```

Fluxo login:

1. `goto` login
2. Fechar **Got it!** se visível
3. Usuário + Senha + Entrar
4. Detectar área autenticada (URL fora de login / marcador estável)

Fluxo simulação:

1. Preencher CPF e celular com âncoras melhores que o codegen (`get_by_label` / placeholder)
2. Busca placa → preencher placa
3. Valor de venda formatado
4. Simular
5. Se `entrada > 0`, preencher **Entrada:** e re-simular se a UI exigir
6. Ler parcelas → `list[ResultadoDriver]` com `provedor="pan"`

- [ ] **Step 3: Testes fixture verdes + commit**

```text
git commit -m "feat(motor): PanPortalDriver com fluxo fixture"
```

---

### Task 3: Integração REAL_DRIVERS + não regredir API

**Files:**
- `drivers.py`, testes Pan existentes, possivelmente portal UI “Acessos bancos”

- [ ] **Step 1:** Garantir que com config API completa os testes HTTP mockados de `pan.py` continuam
  passando **sem** abrir browser.
- [ ] **Step 2:** Com só usuario/senha, `REAL_DRIVERS["pan"]` (ou fábrica) aponta para portal.
- [ ] **Step 3:** Suíte completa `pytest -q`.
- [ ] **Step 4: Commit**

```text
git commit -m "feat(motor): Pan dual-path API e portal lojista"
```

---

### Task 4: Smoke live portal

**Files:**
- `tests/test_pan_portal_live.py`
- handoff / RUNBOOK

```powershell
$env:MOTOR_PAN_PORTAL_LIVE="1"
.\.venv\Scripts\python.exe -m pytest tests/test_pan_portal_live.py -v -s
```

Critérios:

- Login + simulação + ≥1 parcela
- Entrada opcional testada em dois casos (0 e valor > 0) se possível
- Sem contratar/enviar proposta
- Se API também estiver configurada no mesmo cliente de lab, smoke API separado (já existente ou
  `MOTOR_PAN_LIVE` se houver)

- [ ] Commit + lições se necessário (`playwright-licoes-pan-portal.md`)

---

## Códigos de erro estáveis (propostos)

| Código | Quando |
|---|---|
| `celular_obrigatorio` / `placa_obrigatoria` | pré-browser |
| `credencial_invalida` | login portal |
| `pan_configuracao_incompleta` | API path (já existe) |
| `pan_sem_oferta` | sem parcelas (já usado na API; reutilizar) |
| `portal_bloqueado` / `portal_falhou` | WAF / etapa |

## Segurança (obrigatório)

O arquivo de codegen do dono continha **usuário e senha em texto claro**. Antes do smoke:

1. **Não** commitar o `.txt`.
2. Preferir **trocar a senha** do portal Pan se o arquivo foi compartilhado/sincronizado.
3. Cadastrar credencial só via API cifrada do Motor / tela Acessos bancos.

## Ordem de implementação

1. Fechar **Bradesco** (`...-bradesco-implementacao.md`) se for o próximo banco “zero”.
2. Task 0 deste plano (HTML de resultado Pan) pode rodar em paralelo (humano).
3. Implementar dual-path Pan sem misturar PR do Bradesco.

## Relação com o mapa de bancos

Atualizar `2026-07-13-plano1a-task12-bancos-reconhecimento.md`:

- Pan: **API pronta no código** + **fluxo portal mapeado (codegen parcial)** → dual-path.
- Bradesco: fluxo portal mapeado → Playwright (API a confirmar).
