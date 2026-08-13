# Copiloto de Vendas — Fase 1: fundação determinística (sem IA)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar a seção **Copiloto** na Revy Loja com dados reais da operação e alertas proativos, **sem chamar LLM nenhum** — a fatia que precisa continuar de pé quando o provedor de IA cair.

**Architecture:** Um pacote novo `app/loja/copiloto/` dentro do Portal, com funções de consulta tipadas que batem nas fontes donas por HTTP (clients existentes) ou no banco do Portal; um motor de regras determinístico que grava sinais em tabela nova; um worker `threading.Thread` daemon no molde de `app/meta_ads_spend_job.py`; e uma página no shell da Loja com "Resumo de hoje" e bloco de alertas. Nenhum import Python entre produtos.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, Jinja2, pytest, `httpx` (via clients já existentes).

**Spec:** `docs/referencia-viva/specs/2026-08-10-copiloto-negocio-loja-design.md` (revisão 2) — §3.7, §4.1, §4.4, §5, §6.2, §7, §9.

**Planos irmãos (ordem de dependência):**
1. **este** — fundação determinística;
2. `2026-08-11-copiloto-fase2-chat-llm.md` — chat, turno assíncrono, DeepSeek;
3. `2026-08-11-copiloto-fase3-fipe-e-acoes.md` — FIPE + caminho de escrita.

> **Cuidado com a palavra "fase" — ela significa duas coisas diferentes.** Os três planos (F1, F2,
> F3) são **fatias de implementação da v1**: juntas, elas entregam a v1 inteira do §10 do design e
> nada além. Já as "Fase 2" e "Fase 3" **do design** (§4.6, §10) são o roadmap de produto — v2 e
> v3: WhatsApp, memória do dono, busca cautelar, contrato, leitura de PDF. Neste documento, "F1/F2/F3"
> sempre quer dizer plano; "v2/v3" sempre quer dizer roadmap.

## Global Constraints

- **Sem import entre produtos.** Estoque e Chatbot só por HTTP, usando `app/clients/*` já existentes. Nunca `from estoque_api...`.
- **`loja_slug` e `papel` vêm da sessão** (`usuario.loja_slug`, `usuario.papel`), nunca de parâmetro que o chamador escolhe livremente.
- **Toda função que agrega devolve cobertura** `Cobertura(com_dado, total)`. Número parcial sem cobertura declarada é bug.
- **Nunca inventar número.** Fonte fora do ar → campo `None` + `status="indisponivel"`. Zero só quando a fonte respondeu zero.
- **Vocabulário de status fixo:** `ok | vazio | parcial | erro | indisponivel` (mesmo do `SalesOverview`).
- **Flag** `REVY_LOJA_COPILOTO_ENABLED`, default **off**, lida em runtime via helper (não `settings.` snapshot) — padrão `app/config.py:12-46`.
- **Gate duplo:** a rota exige `REVY_LOJA_SHELL_ENABLED=1` **e** `REVY_LOJA_COPILOTO_ENABLED=1` **e** entitlement da loja **e** papel em `ROLES_GESTAO` (`app/loja/types.py:31`).
- **Nunca gravar telefone em claro** em tabela nova (invariante de `app/loja_operacao_auditoria.py:55-56`). Sinal de lead guarda HMAC via `identidade_telefone` ou nada.
- **Migrations:** cada plano tem a sua. Head atual = `0018_redefinicoes_senha`.
- **Comandos** (sempre a partir de `portal-gestao/`):
  - testes: `.\.venv\Scripts\python.exe -m pytest -q`
  - migration: `.\.venv\Scripts\python.exe -m alembic upgrade head`
- **Ao fim de cada task:** commit. Ao fim do plano: `git diff --check` e `git status --short`, preservando mudanças alheias no worktree.

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `app/loja/copiloto/__init__.py` | Pacote vazio (sem re-export — evita import circular com `app.main`). |
| `app/loja/copiloto/tipos.py` | `Cobertura`, `CopilotoContexto`, `SinalCandidato` e o vocabulário de status. Sem dependência de FastAPI/ORM. |
| `app/loja/copiloto/periodo.py` | Janela do período e a **janela anterior comparável** (não existe hoje no repo). |
| `app/loja/copiloto/consultas_vendas.py` | `vendas_resumo`, `ranking_vendedores`, `venda_origem`. |
| `app/loja/copiloto/consultas_estoque.py` | `estoque_parado` + guarda de escopo de loja (§3.7). |
| `app/loja/copiloto/consultas_leads.py` | `leads_status` (re-fiação do `SalesOverview.funil`). |
| `app/loja/copiloto/cache.py` | Cache TTL curto de `build_sales_overview` por `(loja_slug, inicio, fim, papel)`. |
| `app/loja/copiloto/sinais.py` | As 6 regras, **puras**: recebem dado, devolvem `SinalCandidato`. |
| `app/loja/copiloto/sinais_store.py` | Persistência dos sinais: cooldown, dedupe, resolução automática, dispensar. |
| `app/loja/copiloto/resumo.py` | "Resumo de hoje" determinístico (view-model, sem LLM). |
| `app/copiloto_sinais_job.py` | Worker daemon que roda o motor por loja habilitada. |
| `app/web/loja_copiloto.py` | Router da seção (`/app/loja/copiloto` + ações de sinal). |
| `app/templates/loja/copiloto.html` | Página: resumo + alertas. |
| `alembic/versions/0019_copiloto_sinal.py` | Tabela `copiloto_sinal`. |

Arquivos existentes tocados: `app/config.py`, `app/loja/types.py`, `app/loja/entitlements.py`, `app/loja/navigation.py`, `app/models.py`, `app/main.py`, `app/templates/base.html`, `tests/test_loja_navigation.py`.

---

### Task 1: Flag e entitlement do Copiloto

**Files:**
- Modify: `portal-gestao/app/config.py`
- Modify: `portal-gestao/app/loja/types.py`
- Modify: `portal-gestao/app/loja/entitlements.py`
- Modify: `portal-gestao/app/loja/permissions.py`
- Test: `portal-gestao/tests/test_copiloto_flag_entitlement.py`

**Interfaces:**
- Consumes: nada.
- Produces: `revy_loja_copiloto_enabled() -> bool`; `Module.COPILOTO` (valor `"copiloto"`); `EntitlementState.copiloto_enabled: bool`.

**Armadilha:** `module_enabled` (`app/loja/permissions.py:38-47`) é uma cadeia de `if` explícita
que devolve `False` para módulo desconhecido. Acrescentar `Module.COPILOTO` ao enum **sem** tocar
nela cria um valor que existe mas nunca autoriza: o primeiro `require_module(ents, Module.COPILOTO)`
— o padrão da casa — levanta `ModuloNaoContratado` mesmo com o entitlement concedido, e o bug
parece de contrato, não de código. Este task fecha as duas pontas.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_flag_entitlement.py`:

```python
"""Flag global (kill-switch) + entitlement por loja do Copiloto."""
from app.config import revy_loja_copiloto_enabled
from app.loja.entitlements import fail_open, from_allows_processing
from app.loja.types import Module


def test_flag_copiloto_default_off(monkeypatch):
    monkeypatch.delenv("REVY_LOJA_COPILOTO_ENABLED", raising=False)
    assert revy_loja_copiloto_enabled() is False
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    assert revy_loja_copiloto_enabled() is True


def test_fail_open_libera_copiloto_para_quem_tem_cargo():
    """Entitlements off = comportamento legado; a flag de env decide sozinha."""
    assert fail_open("loja-teste", {"dono"}).copiloto_enabled is True
    assert fail_open("loja-teste", set()).copiloto_enabled is False


def test_projecao_gate_copiloto_por_modulo():
    """Com entitlements on, o Copiloto é módulo contratável e pode faltar."""
    consultados = []

    def allows(slug, module=None):
        consultados.append(module)
        return module != Module.COPILOTO.value

    estado = from_allows_processing("loja-teste", allows)
    assert estado.copiloto_enabled is False
    assert estado.vendas_enabled is True
    assert Module.COPILOTO.value in consultados


def test_module_enabled_reconhece_copiloto():
    """Enum novo sem entrada em module_enabled = módulo que nunca autoriza."""
    from app.loja.permissions import module_enabled
    from app.loja.types import EntitlementState

    ligado = fail_open("loja-teste", {"dono"})
    assert module_enabled(ligado, Module.COPILOTO) is True

    desligado = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="projecao",
        copiloto_enabled=False,
    )
    assert module_enabled(desligado, Module.COPILOTO) is False

    inativa = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=False,
        vendas_enabled=False,
        estoque_enabled=False,
        source="projecao",
        copiloto_enabled=True,
    )
    assert module_enabled(inativa, Module.COPILOTO) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_flag_entitlement.py -q`
Expected: FAIL — `ImportError: cannot import name 'revy_loja_copiloto_enabled'`.

- [ ] **Step 3: Write minimal implementation**

Em `app/config.py`, logo depois de `revy_loja_whatsapp_enabled()`:

```python
def revy_loja_copiloto_enabled() -> bool:
    """Seção Copiloto de Vendas da Loja. Default off.

    É kill-switch global do deploy: quem libera loja a loja é o entitlement
    (``Module.COPILOTO``). Só age com ``REVY_LOJA_SHELL_ENABLED=1``.
    """
    return _env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")
```

Em `app/config.py`, dentro de `Settings`, junto das outras flags da Loja:

```python
    revy_loja_copiloto_enabled: bool = _env_bool("REVY_LOJA_COPILOTO_ENABLED", "0")
```

Em `app/loja/types.py`:

```python
class Module(str, Enum):
    """Módulos principais visíveis no shell Revy Loja."""

    VENDAS = "vendas"
    ESTOQUE = "estoque"
    COPILOTO = "copiloto"
```

E em `EntitlementState`, **depois** de `source` (campo sem default vem antes):

```python
    source: str  # fail_open | projecao | control | cache
    copiloto_enabled: bool = False
```

Em `app/loja/entitlements.py`, em `fail_open`, acrescentar ao construtor:

```python
        source="fail_open",
        copiloto_enabled=has_role,
```

E em `from_allows_processing`, no retorno da loja ativa:

```python
        estoque_enabled=bool(allows(loja_slug, Module.ESTOQUE.value)),
        source=source,
        copiloto_enabled=bool(allows(loja_slug, Module.COPILOTO.value)),
```

> Os outros dois construtores de `EntitlementState` (loja inativa, `entitlements.py:47-49`, e o
> fallback de `resolve_entitlements`, `:104-106`) **não** mudam: `copiloto_enabled` tem default
> `False`, que é a resposta certa nos dois casos.

Em `app/loja/permissions.py`, dentro de `module_enabled`, **antes** do `return False` final:

```python
    if mod == Module.COPILOTO.value:
        return entitlements.copiloto_enabled
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_flag_entitlement.py tests/test_loja_navigation.py -q`
Expected: PASS (a suíte de navegação não pode quebrar — `copiloto_enabled` tem default).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/config.py portal-gestao/app/loja/types.py portal-gestao/app/loja/entitlements.py portal-gestao/app/loja/permissions.py portal-gestao/tests/test_copiloto_flag_entitlement.py
git commit -m "feat(copiloto): flag REVY_LOJA_COPILOTO_ENABLED e entitlement por loja"
```

---

### Task 2: Tipos base — cobertura e contexto do ator

**Files:**
- Create: `portal-gestao/app/loja/copiloto/__init__.py`
- Create: `portal-gestao/app/loja/copiloto/tipos.py`
- Test: `portal-gestao/tests/test_copiloto_tipos.py`

**Interfaces:**
- Consumes: nada. (**Atenção:** o `StatusReadModel` de `app/loja/types.py:9` é
  `Literal["ok","vazio","erro","parcial"]` e **não** tem `"indisponivel"` — por isso este task
  define um `StatusCopiloto` próprio em vez de reusar aquele. Não trocar um pelo outro.)
- Produces:
  - `StatusCopiloto = Literal["ok","vazio","parcial","erro","indisponivel"]`;
  - `Cobertura(com_dado: int, total: int)` com `.parcial -> bool`, `.completa -> bool`, `.to_dict() -> dict`;
  - `CopilotoContexto(loja_slug: str, papel: str, ator_email: str, hoje: date, pode_ver_margem: bool)`;
  - `STATUS_INDISPONIVEL = "indisponivel"`.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_tipos.py`:

```python
from datetime import date

import pytest

from app.loja.copiloto.tipos import Cobertura, CopilotoContexto


def test_cobertura_completa_nao_e_parcial():
    c = Cobertura(com_dado=14, total=14)
    assert c.completa is True
    assert c.parcial is False
    assert c.to_dict() == {"com_dado": 14, "total": 14}


def test_cobertura_parcial_quando_falta_dado():
    c = Cobertura(com_dado=6, total=14)
    assert c.completa is False
    assert c.parcial is True


def test_cobertura_vazia_nao_e_parcial():
    """Zero de zero é vazio, não parcial — senão a tela grita à toa."""
    c = Cobertura(com_dado=0, total=0)
    assert c.parcial is False
    assert c.completa is True


def test_cobertura_recusa_com_dado_maior_que_total():
    with pytest.raises(ValueError):
        Cobertura(com_dado=3, total=2)


def test_contexto_normaliza_papel_e_email():
    ctx = CopilotoContexto(
        loja_slug="loja-teste",
        papel=" Dono ",
        ator_email="Dono@Loja.Test",
        hoje=date(2026, 8, 11),
    )
    assert ctx.papel == "dono"
    assert ctx.ator_email == "dono@loja.test"
    assert ctx.pode_ver_margem is True


def test_contexto_vendedor_nao_ve_margem():
    ctx = CopilotoContexto(
        loja_slug="loja-teste",
        papel="vendedor",
        ator_email="v@loja.test",
        hoje=date(2026, 8, 11),
    )
    assert ctx.pode_ver_margem is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_tipos.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/__init__.py` **vazio** (uma linha de docstring só):

```python
"""Copiloto de Vendas da Revy Loja. Sem re-export: evita ciclo com app.main."""
```

Criar `portal-gestao/app/loja/copiloto/tipos.py`:

```python
"""Contratos do Copiloto — sem FastAPI, sem ORM, sem cliente HTTP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

# Mesmo vocabulário do SalesOverview: a tela e o copiloto falam a mesma língua.
StatusCopiloto = Literal["ok", "vazio", "parcial", "erro", "indisponivel"]

STATUS_OK = "ok"
STATUS_VAZIO = "vazio"
STATUS_PARCIAL = "parcial"
STATUS_ERRO = "erro"
STATUS_INDISPONIVEL = "indisponivel"

# Papéis que enxergam o negócio inteiro da loja (dono/gerente + admin).
PAPEIS_GESTAO_COPILOTO = frozenset({"dono", "gerente", "admin_plataforma"})


@dataclass(frozen=True)
class Cobertura:
    """Sobre quantos itens o número vale.

    É a defesa contra o número *silenciosamente parcial* (§6.2 do design):
    margem calculada sobre 6 de 14 vendas não é "a margem do mês".
    """

    com_dado: int
    total: int

    def __post_init__(self) -> None:
        if self.com_dado < 0 or self.total < 0:
            raise ValueError("cobertura não aceita negativo")
        if self.com_dado > self.total:
            raise ValueError("com_dado não pode ser maior que total")

    @property
    def completa(self) -> bool:
        return self.com_dado == self.total

    @property
    def parcial(self) -> bool:
        # 0 de 0 é vazio, não parcial.
        return self.total > 0 and self.com_dado < self.total

    def to_dict(self) -> dict[str, int]:
        return {"com_dado": self.com_dado, "total": self.total}


@dataclass(frozen=True)
class CopilotoContexto:
    """Quem está perguntando. Nunca é preenchido por parâmetro de rota.

    ``loja_slug`` e ``papel`` saem da sessão autenticada. O LLM (fase 2) não
    enxerga nem consegue preencher estes campos.
    """

    loja_slug: str
    papel: str
    ator_email: str
    hoje: date
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "papel", (self.papel or "").strip().casefold())
        object.__setattr__(
            self, "ator_email", (self.ator_email or "").strip().casefold()
        )

    @property
    def pode_ver_margem(self) -> bool:
        return self.papel in PAPEIS_GESTAO_COPILOTO
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_tipos.py -q`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/ portal-gestao/tests/test_copiloto_tipos.py
git commit -m "feat(copiloto): tipos base com cobertura de dado e contexto do ator"
```

---

### Task 3: Período comparável (a janela anterior não existe no repo)

**Files:**
- Create: `portal-gestao/app/loja/copiloto/periodo.py`
- Test: `portal-gestao/tests/test_copiloto_periodo.py`

**Interfaces:**
- Consumes: `app.financeiro_calc.periodo_padrao`, `app.financeiro_calc.hoje_portal`.
- Produces:
  - `Janela(inicio: date, fim: date)` com `.dias -> int` e `.rotulo -> str`;
  - `janela_do_periodo(inicio: str | date | None, fim: str | date | None) -> Janela`;
  - `janela_anterior(janela: Janela) -> Janela`.

**Por que existe:** `sales_overview.py:848` calcula **uma** janela e não há comparação com período anterior em lugar nenhum de `app/` (verificado na revisão 2 do design). "Meu ticket esse mês vs. o passado" depende disto.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_periodo.py`:

```python
from datetime import date

from app.loja.copiloto.periodo import Janela, janela_anterior, janela_do_periodo


def test_janela_do_periodo_aceita_iso_e_date():
    j = janela_do_periodo("2026-08-01", "2026-08-31")
    assert j == Janela(inicio=date(2026, 8, 1), fim=date(2026, 8, 31))
    assert janela_do_periodo(date(2026, 8, 1), date(2026, 8, 31)) == j


def test_janela_conta_dias_inclusivos():
    assert janela_do_periodo("2026-08-01", "2026-08-31").dias == 31
    assert janela_do_periodo("2026-08-11", "2026-08-11").dias == 1


def test_mes_cheio_compara_com_o_mes_anterior_cheio():
    """Agosto inteiro compara com julho inteiro — não com 31 dias corridos."""
    anterior = janela_anterior(janela_do_periodo("2026-08-01", "2026-08-31"))
    assert anterior == Janela(inicio=date(2026, 7, 1), fim=date(2026, 7, 31))


def test_mes_cheio_de_marco_compara_com_fevereiro_curto():
    anterior = janela_anterior(janela_do_periodo("2026-03-01", "2026-03-31"))
    assert anterior == Janela(inicio=date(2026, 2, 1), fim=date(2026, 2, 28))


def test_janela_parcial_recua_o_mesmo_numero_de_dias():
    """Do dia 1 ao 11 compara com os 11 dias imediatamente anteriores."""
    anterior = janela_anterior(janela_do_periodo("2026-08-01", "2026-08-11"))
    assert anterior == Janela(inicio=date(2026, 7, 21), fim=date(2026, 7, 31))


def test_rotulo_do_mes_cheio_e_legivel():
    assert janela_do_periodo("2026-08-01", "2026-08-31").rotulo == "agosto/2026"


def test_rotulo_de_janela_parcial_mostra_as_datas():
    assert (
        janela_do_periodo("2026-08-01", "2026-08-11").rotulo
        == "01/08/2026 a 11/08/2026"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_periodo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.periodo'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/periodo.py`:

```python
"""Janela do período e a janela anterior comparável.

O Portal só sabia calcular UMA janela (``financeiro_calc.periodo_padrao``).
Comparação com período anterior — "meu ticket esse mês vs. o passado" — não
existia em ``app/``; nasce aqui.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.financeiro_calc import periodo_padrao, ultimo_dia_mes

MESES_PT = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


@dataclass(frozen=True)
class Janela:
    inicio: date
    fim: date

    @property
    def dias(self) -> int:
        """Dias inclusivos: 01 a 31 são 31, não 30."""
        return (self.fim - self.inicio).days + 1

    @property
    def mes_cheio(self) -> bool:
        return (
            self.inicio.day == 1
            and self.fim == ultimo_dia_mes(self.inicio)
            and self.inicio.month == self.fim.month
            and self.inicio.year == self.fim.year
        )

    @property
    def rotulo(self) -> str:
        if self.mes_cheio:
            return f"{MESES_PT[self.inicio.month - 1]}/{self.inicio.year}"
        return (
            f"{self.inicio.strftime('%d/%m/%Y')} a {self.fim.strftime('%d/%m/%Y')}"
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
            "rotulo": self.rotulo,
        }


def janela_do_periodo(
    inicio: str | date | None = None,
    fim: str | date | None = None,
) -> Janela:
    """Normaliza o período com a MESMA regra do painel (mês corrente default)."""
    ini_s = inicio.isoformat() if isinstance(inicio, date) else inicio
    fim_s = fim.isoformat() if isinstance(fim, date) else fim
    d_inicio, d_fim = periodo_padrao(ini_s, fim_s)
    return Janela(inicio=d_inicio, fim=d_fim)


def janela_anterior(janela: Janela) -> Janela:
    """Período comparável imediatamente anterior.

    Mês cheio → mês cheio anterior (fevereiro tem 28 dias e a comparação
    continua honesta). Janela parcial → mesmo número de dias, colado antes.
    """
    if janela.mes_cheio:
        ultimo_dia_anterior = janela.inicio - timedelta(days=1)
        primeiro = ultimo_dia_anterior.replace(day=1)
        ultimo = date(
            ultimo_dia_anterior.year,
            ultimo_dia_anterior.month,
            calendar.monthrange(ultimo_dia_anterior.year, ultimo_dia_anterior.month)[1],
        )
        return Janela(inicio=primeiro, fim=ultimo)

    fim_anterior = janela.inicio - timedelta(days=1)
    inicio_anterior = fim_anterior - timedelta(days=janela.dias - 1)
    return Janela(inicio=inicio_anterior, fim=fim_anterior)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_periodo.py -q`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/periodo.py portal-gestao/tests/test_copiloto_periodo.py
git commit -m "feat(copiloto): janela de periodo com comparacao ao periodo anterior"
```

---

### Task 4: `vendas_resumo` — ticket médio, margem com cobertura e Δ vs período anterior

**Files:**
- Create: `portal-gestao/app/loja/copiloto/consultas_vendas.py`
- Test: `portal-gestao/tests/test_copiloto_consultas_vendas.py`

**Interfaces:**
- Consumes: `Cobertura`, `CopilotoContexto` (Task 2); `Janela`, `janela_do_periodo`, `janela_anterior` (Task 3); `app.financeiro_calc.calcular_metricas_vendas`.
- Produces: `VendasResumo` (dataclass) e `vendas_resumo(db, ctx, *, inicio=None, fim=None) -> VendasResumo`.
  Campos de `VendasResumo`: `status`, `janela`, `janela_comparacao`, `qtd_vendas`, `receita`, `ticket_medio`, `margem`, `cobertura_margem`, `qtd_vendas_anterior`, `receita_anterior`, `ticket_medio_anterior`, `delta_receita_pct`, `delta_ticket_pct`, `delta_qtd`, `to_dict()`.

**Estado real que este task corrige** (verificado no design, §4.1): receita e margem existem (`sales_overview.py:104-107`), **ticket médio não existe** (zero ocorrências de `ticket` no Portal) e **Δ vs período anterior não existe**. Isto é read model novo, não wrapper.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_consultas_vendas.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.consultas_vendas import vendas_resumo
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Venda


def _ctx(papel="dono"):
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel=papel,
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _venda(db, *, preco, custo=None, dia, mes=8, status="confirmada", email="v1@loja.test"):
    db.add(
        Venda(
            loja_slug="loja-teste",
            vendedor_email=email,
            descricao="Honda CB 500F 2020",
            preco_venda=Decimal(str(preco)),
            custo_veiculo=None if custo is None else Decimal(str(custo)),
            status=status,
            criada_em=datetime(2026, mes, dia, 15, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()


def test_ticket_medio_e_receita_do_periodo(db):
    _venda(db, preco=30000, dia=3)
    _venda(db, preco=20000, dia=7)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "ok"
    assert r.qtd_vendas == 2
    assert r.receita == Decimal("50000.00")
    assert r.ticket_medio == Decimal("25000.00")


def test_periodo_sem_venda_e_vazio_e_nao_inventa_ticket(db):
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "vazio"
    assert r.qtd_vendas == 0
    assert r.receita == Decimal("0.00")
    assert r.ticket_medio is None


def test_margem_parcial_declara_cobertura(db):
    _venda(db, preco=30000, custo=24000, dia=3)
    _venda(db, preco=20000, custo=None, dia=7)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "parcial"
    assert r.cobertura_margem.to_dict() == {"com_dado": 1, "total": 2}
    assert r.cobertura_margem.parcial is True
    assert r.margem == Decimal("6000.00")


def test_vendedor_nao_recebe_margem(db):
    _venda(db, preco=30000, custo=24000, dia=3)
    r = vendas_resumo(db, _ctx(papel="vendedor"), inicio="2026-08-01", fim="2026-08-31")
    assert r.margem is None
    assert r.status == "ok"


def test_compara_com_o_mes_anterior(db):
    _venda(db, preco=30000, dia=3, mes=8)
    _venda(db, preco=20000, dia=10, mes=7)
    _venda(db, preco=20000, dia=20, mes=7)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.janela_comparacao.rotulo == "julho/2026"
    assert r.qtd_vendas_anterior == 2
    assert r.receita_anterior == Decimal("40000.00")
    assert r.ticket_medio_anterior == Decimal("20000.00")
    assert r.delta_qtd == -1
    assert r.delta_receita_pct == Decimal("-25.0")
    assert r.delta_ticket_pct == Decimal("50.0")


def test_sem_periodo_anterior_o_delta_e_none_nao_zero(db):
    """Zero de comparação mentiria: "caiu 100%" quando nunca houve mês anterior."""
    _venda(db, preco=30000, dia=3)
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.qtd_vendas_anterior == 0
    assert r.delta_receita_pct is None
    assert r.delta_ticket_pct is None


def test_venda_nao_confirmada_nao_entra(db):
    _venda(db, preco=30000, dia=3, status="registrada")
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.qtd_vendas == 0


def test_venda_de_outra_loja_nao_entra(db):
    db.add(
        Venda(
            loja_slug="outra-loja",
            vendedor_email="x@outra.test",
            descricao="Yamaha MT-03",
            preco_venda=Decimal("31900"),
            status="confirmada",
            criada_em=datetime(2026, 8, 5, 15, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()
    r = vendas_resumo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.qtd_vendas == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_consultas_vendas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.consultas_vendas'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/consultas_vendas.py`:

```python
"""Consultas de vendas do Copiloto.

Reusa ``calcular_metricas_vendas`` (fonte única dos totais do painel) para
que Copiloto e Visão Geral nunca discordem: se um disser 12 vendas e o outro
14, a confiança do dono acaba naquele instante e não volta.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.financeiro_calc import calcular_metricas_vendas
from app.loja.copiloto.periodo import Janela, janela_anterior, janela_do_periodo
from app.loja.copiloto.tipos import (
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)

CENTAVOS = Decimal("0.01")
DECIMO = Decimal("0.1")


def _c(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def _pct(atual: Decimal | None, anterior: Decimal | None) -> Decimal | None:
    """Variação percentual. ``None`` quando não há base — nunca -100% fake."""
    if atual is None or anterior is None or anterior == 0:
        return None
    return ((atual - anterior) / anterior * 100).quantize(
        DECIMO, rounding=ROUND_HALF_UP
    )


def _ticket(receita: Decimal, qtd: int) -> Decimal | None:
    return _c(receita / qtd) if qtd else None


def _dec(valor: Decimal | None) -> str | None:
    return None if valor is None else str(_c(valor))


@dataclass(frozen=True)
class VendasResumo:
    status: str
    janela: Janela
    janela_comparacao: Janela
    qtd_vendas: int
    receita: Decimal
    ticket_medio: Decimal | None
    margem: Decimal | None
    cobertura_margem: Cobertura
    qtd_vendas_anterior: int
    receita_anterior: Decimal
    ticket_medio_anterior: Decimal | None
    delta_qtd: int
    delta_receita_pct: Decimal | None
    delta_ticket_pct: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": self.janela.to_dict(),
            "periodo_comparacao": self.janela_comparacao.to_dict(),
            "qtd_vendas": self.qtd_vendas,
            "receita": _dec(self.receita),
            "ticket_medio": _dec(self.ticket_medio),
            "margem": _dec(self.margem),
            "cobertura_margem": self.cobertura_margem.to_dict(),
            "qtd_vendas_anterior": self.qtd_vendas_anterior,
            "receita_anterior": _dec(self.receita_anterior),
            "ticket_medio_anterior": _dec(self.ticket_medio_anterior),
            "delta_qtd": self.delta_qtd,
            "delta_receita_pct": (
                None if self.delta_receita_pct is None else str(self.delta_receita_pct)
            ),
            "delta_ticket_pct": (
                None if self.delta_ticket_pct is None else str(self.delta_ticket_pct)
            ),
        }


def vendas_resumo(
    db: Session,
    ctx: CopilotoContexto,
    *,
    inicio: str | None = None,
    fim: str | None = None,
) -> VendasResumo:
    """Receita, ticket médio, margem (com cobertura) e Δ vs período anterior."""
    janela = janela_do_periodo(inicio, fim)
    anterior = janela_anterior(janela)

    atual = calcular_metricas_vendas(db, ctx.loja_slug, janela.inicio, janela.fim)
    passado = calcular_metricas_vendas(db, ctx.loja_slug, anterior.inicio, anterior.fim)

    qtd = atual["quantidade"]
    receita = _c(atual["faturamento"])
    receita_ant = _c(passado["faturamento"])
    ticket = _ticket(receita, qtd)
    ticket_ant = _ticket(receita_ant, passado["quantidade"])

    cobertura = Cobertura(
        com_dado=qtd - atual["vendas_lucro_incompleto"],
        total=qtd,
    )
    margem = _c(atual["lucro_bruto"]) if ctx.pode_ver_margem else None

    if qtd == 0:
        status = STATUS_VAZIO
    elif ctx.pode_ver_margem and cobertura.parcial:
        status = STATUS_PARCIAL
    else:
        status = STATUS_OK

    return VendasResumo(
        status=status,
        janela=janela,
        janela_comparacao=anterior,
        qtd_vendas=qtd,
        receita=receita,
        ticket_medio=ticket,
        margem=margem,
        cobertura_margem=cobertura,
        qtd_vendas_anterior=passado["quantidade"],
        receita_anterior=receita_ant,
        ticket_medio_anterior=ticket_ant,
        delta_qtd=qtd - passado["quantidade"],
        delta_receita_pct=_pct(receita, receita_ant),
        delta_ticket_pct=_pct(ticket, ticket_ant),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_consultas_vendas.py -q`
Expected: PASS (8 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/consultas_vendas.py portal-gestao/tests/test_copiloto_consultas_vendas.py
git commit -m "feat(copiloto): vendas_resumo com ticket medio, cobertura de margem e delta"
```

---

### Task 5: `ranking_vendedores` — agregação em SQL, não laço sobre helper

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/consultas_vendas.py`
- Test: `portal-gestao/tests/test_copiloto_ranking_vendedores.py`

**Interfaces:**
- Consumes: `Janela`, `janela_anterior`, `janela_do_periodo`, `CopilotoContexto`, `app.models.Venda`.
- Produces: `LinhaRanking` (`vendedor_email`, `qtd`, `receita`, `ticket_medio`, `posicao`, `posicao_anterior`, `variacao`) e `ranking_vendedores(db, ctx, *, inicio=None, fim=None, limite=10) -> RankingVendedores` (campos: `status`, `janela`, `janela_comparacao`, `linhas`, `to_dict()`).

**Por que SQL:** `_metricas_vendedor` (`sales_overview.py:408-440`) calcula para **um** e-mail e faz `db.query(Venda).all()` sem filtro de data (`:417-426`). Um ranking ingênuo = N vendedores × 2 janelas = **2N varreduras da tabela por pergunta**. Aqui é um `GROUP BY` por janela — duas queries no total.

**Atenção ao fuso:** `calcular_metricas_vendas` filtra em Python convertendo `criada_em` para `America/Sao_Paulo` (`financeiro_calc.py:141-145`). Para não divergir do resto do Portal, o `WHERE` em SQL usa a janela **alargada em 1 dia de cada lado** e o corte fino continua em Python com `_data()`. Alargar é barato; divergir de fuso é bug de confiança.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_ranking_vendedores.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.consultas_vendas import ranking_vendedores
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Venda


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _venda(db, email, preco, dia, mes=8, loja="loja-teste"):
    db.add(
        Venda(
            loja_slug=loja,
            vendedor_email=email,
            descricao="Moto",
            preco_venda=Decimal(str(preco)),
            status="confirmada",
            criada_em=datetime(2026, mes, dia, 15, 0, tzinfo=timezone.utc),
        )
    )
    db.commit()


def test_ordena_por_receita_desc(db):
    _venda(db, "ana@loja.test", 30000, 3)
    _venda(db, "bruno@loja.test", 50000, 4)
    _venda(db, "ana@loja.test", 10000, 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "ok"
    assert [linha.vendedor_email for linha in r.linhas] == [
        "bruno@loja.test",
        "ana@loja.test",
    ]
    assert r.linhas[0].posicao == 1
    assert r.linhas[1].qtd == 2
    assert r.linhas[1].receita == Decimal("40000.00")
    assert r.linhas[1].ticket_medio == Decimal("20000.00")


def test_marca_quem_subiu_e_quem_caiu(db):
    # Julho: ana lidera. Agosto: bruno assume.
    _venda(db, "ana@loja.test", 90000, 10, mes=7)
    _venda(db, "bruno@loja.test", 10000, 12, mes=7)
    _venda(db, "bruno@loja.test", 80000, 4)
    _venda(db, "ana@loja.test", 20000, 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    por_email = {linha.vendedor_email: linha for linha in r.linhas}
    assert por_email["bruno@loja.test"].posicao == 1
    assert por_email["bruno@loja.test"].posicao_anterior == 2
    assert por_email["bruno@loja.test"].variacao == "subiu"
    assert por_email["ana@loja.test"].variacao == "caiu"


def test_vendedor_novo_no_periodo_e_novo_nao_subiu(db):
    _venda(db, "ana@loja.test", 10000, 10, mes=7)
    _venda(db, "ana@loja.test", 10000, 4)
    _venda(db, "caio@loja.test", 50000, 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    por_email = {linha.vendedor_email: linha for linha in r.linhas}
    assert por_email["caio@loja.test"].posicao_anterior is None
    assert por_email["caio@loja.test"].variacao == "novo"


def test_sem_venda_no_periodo_e_vazio(db):
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "vazio"
    assert r.linhas == ()


def test_nao_mistura_outra_loja(db):
    _venda(db, "x@outra.test", 99000, 5, loja="outra-loja")
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "vazio"


def test_respeita_limite(db):
    for i in range(5):
        _venda(db, f"v{i}@loja.test", 1000 * (i + 1), 5)
    r = ranking_vendedores(db, _ctx(), inicio="2026-08-01", fim="2026-08-31", limite=3)
    assert len(r.linhas) == 3
    assert r.linhas[0].vendedor_email == "v4@loja.test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_ranking_vendedores.py -q`
Expected: FAIL — `ImportError: cannot import name 'ranking_vendedores'`.

- [ ] **Step 3: Write minimal implementation**

Acrescentar ao topo de `consultas_vendas.py` os imports:

```python
from datetime import datetime, timedelta, timezone

from app.financeiro_calc import _data
from app.models import Venda
```

E ao fim do arquivo:

```python
@dataclass(frozen=True)
class LinhaRanking:
    vendedor_email: str
    qtd: int
    receita: Decimal
    ticket_medio: Decimal | None
    posicao: int
    posicao_anterior: int | None
    variacao: str  # subiu | caiu | manteve | novo

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendedor_email": self.vendedor_email,
            "qtd": self.qtd,
            "receita": _dec(self.receita),
            "ticket_medio": _dec(self.ticket_medio),
            "posicao": self.posicao,
            "posicao_anterior": self.posicao_anterior,
            "variacao": self.variacao,
        }


@dataclass(frozen=True)
class RankingVendedores:
    status: str
    janela: Janela
    janela_comparacao: Janela
    linhas: tuple[LinhaRanking, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": self.janela.to_dict(),
            "periodo_comparacao": self.janela_comparacao.to_dict(),
            "linhas": [linha.to_dict() for linha in self.linhas],
        }


def _totais_por_vendedor(
    db: Session, loja_slug: str, janela: Janela
) -> dict[str, tuple[int, Decimal]]:
    """{email: (qtd, receita)} das vendas confirmadas da janela.

    O ``WHERE`` alarga a janela em 1 dia de cada lado porque o corte oficial do
    Portal é feito no fuso da loja (``financeiro_calc._data``), não em UTC.
    Alargar é barato; divergir do painel não é.
    """
    inicio_dt = datetime.combine(
        janela.inicio, datetime.min.time(), tzinfo=timezone.utc
    ) - timedelta(days=1)
    fim_dt = datetime.combine(
        janela.fim, datetime.max.time(), tzinfo=timezone.utc
    ) + timedelta(days=1)

    linhas = (
        db.query(Venda.vendedor_email, Venda.preco_venda, Venda.criada_em)
        .filter(
            Venda.loja_slug == loja_slug,
            Venda.status == "confirmada",
            Venda.criada_em >= inicio_dt,
            Venda.criada_em <= fim_dt,
        )
        .all()
    )

    totais: dict[str, tuple[int, Decimal]] = {}
    for email, preco, criada_em in linhas:
        if not (janela.inicio <= _data(criada_em) <= janela.fim):
            continue
        chave = (email or "").strip().casefold()
        qtd, receita = totais.get(chave, (0, Decimal("0")))
        totais[chave] = (qtd + 1, receita + preco)
    return totais


def _posicoes(totais: dict[str, tuple[int, Decimal]]) -> dict[str, int]:
    ordenado = sorted(
        totais.items(), key=lambda item: (-item[1][1], -item[1][0], item[0])
    )
    return {email: i + 1 for i, (email, _) in enumerate(ordenado)}


def ranking_vendedores(
    db: Session,
    ctx: CopilotoContexto,
    *,
    inicio: str | None = None,
    fim: str | None = None,
    limite: int = 10,
) -> RankingVendedores:
    """Vendedores ordenados por receita, com quem subiu e quem caiu."""
    janela = janela_do_periodo(inicio, fim)
    anterior = janela_anterior(janela)

    atual = _totais_por_vendedor(db, ctx.loja_slug, janela)
    passado = _totais_por_vendedor(db, ctx.loja_slug, anterior)

    if not atual:
        return RankingVendedores(
            status=STATUS_VAZIO,
            janela=janela,
            janela_comparacao=anterior,
            linhas=(),
        )

    pos_atual = _posicoes(atual)
    pos_anterior = _posicoes(passado)

    linhas: list[LinhaRanking] = []
    for email, posicao in sorted(pos_atual.items(), key=lambda item: item[1]):
        if posicao > max(1, limite):
            break
        qtd, receita = atual[email]
        antiga = pos_anterior.get(email)
        if antiga is None:
            variacao = "novo"
        elif posicao < antiga:
            variacao = "subiu"
        elif posicao > antiga:
            variacao = "caiu"
        else:
            variacao = "manteve"
        linhas.append(
            LinhaRanking(
                vendedor_email=email,
                qtd=qtd,
                receita=_c(receita),
                ticket_medio=_ticket(_c(receita), qtd),
                posicao=posicao,
                posicao_anterior=antiga,
                variacao=variacao,
            )
        )

    return RankingVendedores(
        status=STATUS_OK,
        janela=janela,
        janela_comparacao=anterior,
        linhas=tuple(linhas),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_ranking_vendedores.py tests/test_copiloto_consultas_vendas.py -q`
Expected: PASS (14 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/consultas_vendas.py portal-gestao/tests/test_copiloto_ranking_vendedores.py
git commit -m "feat(copiloto): ranking de vendedores agregado com variacao de posicao"
```

---

### Task 6: `venda_origem` — de qual anúncio veio a venda

**Files:**
- Create: `portal-gestao/app/loja/copiloto/consultas_origem.py`
- Test: `portal-gestao/tests/test_copiloto_venda_origem.py`

**Interfaces:**
- Consumes: `Cobertura`, `CopilotoContexto`, `Janela`/`janela_do_periodo`, `app.models.Venda`, `app.models.Campanha`.
- Produces:
  - `OrigemVenda` (`venda_id`, `descricao`, `preco_venda`, `confirmada_em`, `campanha_nome`, `campanha_canal`, `utm_campaign`, `primeiro_clique_nome`, `identificada: bool`);
  - `venda_origem_ultima(db, ctx) -> OrigemUltima` (campos `status`, `origem`);
  - `venda_origem_periodo(db, ctx, *, inicio=None, fim=None) -> OrigemPeriodo` (campos `status`, `janela`, `itens`, `cobertura`, `to_dict()`).

**Por que na v1 (§4.2):** é a única pergunta que nenhum concorrente responde e é literalmente a frase de abertura do script de outbound (`docs/nao-plano/vendas/script-venda-outbound.md:79-80`). Lê snapshot local (`Venda.campanha_id_first/last`, `models.py:126-129`) — **não** depende do Revy Tráfego estar de pé, ao contrário de `roi_canais`.

**Regra dura:** venda sem `campanha_id_*` é **não identificada**. Nunca deduzir origem pela data, pela campanha de outra venda ou pela campanha ativa no período.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_venda_origem.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

from app.loja.copiloto.consultas_origem import (
    venda_origem_periodo,
    venda_origem_ultima,
)
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Campanha, Venda


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _campanha(db, id_, nome, utm="agosto-motos"):
    db.add(
        Campanha(
            id=id_,
            loja_slug="loja-teste",
            nome=nome,
            canal="meta",
            utm_campaign=utm,
            utm_campaign_norm=utm,
        )
    )
    db.commit()


def _venda(db, *, dia, first=None, last=None, utm_last=None, preco=30000):
    venda = Venda(
        loja_slug="loja-teste",
        vendedor_email="ana@loja.test",
        descricao=f"Honda CB 500F dia {dia}",
        preco_venda=Decimal(str(preco)),
        status="confirmada",
        criada_em=datetime(2026, 8, dia, 15, 0, tzinfo=timezone.utc),
        confirmada_em=datetime(2026, 8, dia, 16, 0, tzinfo=timezone.utc),
        campanha_id_first=first,
        campanha_id_last=last,
        utm_campaign_last=utm_last,
    )
    db.add(venda)
    db.commit()
    return venda


def test_ultima_venda_com_campanha_devolve_nome_e_utm(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=5, first="camp-1", last="camp-1", utm_last="agosto-motos")
    r = venda_origem_ultima(db, _ctx())
    assert r.status == "ok"
    assert r.origem.identificada is True
    assert r.origem.campanha_nome == "Motos Agosto — Meta"
    assert r.origem.campanha_canal == "meta"
    assert r.origem.utm_campaign == "agosto-motos"


def test_ultima_venda_sem_campanha_nao_deduz(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=4, first="camp-1", last="camp-1")
    _venda(db, dia=6)  # mais recente, sem origem
    r = venda_origem_ultima(db, _ctx())
    assert r.status == "ok"
    assert r.origem.identificada is False
    assert r.origem.campanha_nome is None
    assert r.origem.descricao == "Honda CB 500F dia 6"


def test_sem_venda_nenhuma_e_vazio(db):
    r = venda_origem_ultima(db, _ctx())
    assert r.status == "vazio"
    assert r.origem is None


def test_periodo_declara_cobertura_parcial(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=3, first="camp-1", last="camp-1")
    _venda(db, dia=4, first="camp-1", last="camp-1")
    _venda(db, dia=5)
    r = venda_origem_periodo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "parcial"
    assert r.cobertura.to_dict() == {"com_dado": 2, "total": 3}
    assert len(r.itens) == 3


def test_periodo_com_tudo_identificado_e_ok(db):
    _campanha(db, "camp-1", "Motos Agosto — Meta")
    _venda(db, dia=3, first="camp-1", last="camp-1")
    r = venda_origem_periodo(db, _ctx(), inicio="2026-08-01", fim="2026-08-31")
    assert r.status == "ok"
    assert r.cobertura.completa is True


def test_primeiro_clique_diferente_do_ultimo_aparece(db):
    _campanha(db, "camp-1", "Prospecção — Meta", utm="prospec")
    _campanha(db, "camp-2", "Remarketing — Meta", utm="remkt")
    _venda(db, dia=5, first="camp-1", last="camp-2", utm_last="remkt")
    r = venda_origem_ultima(db, _ctx())
    assert r.origem.campanha_nome == "Remarketing — Meta"
    assert r.origem.primeiro_clique_nome == "Prospecção — Meta"


def test_campanha_apagada_nao_derruba_a_consulta(db):
    """Snapshot aponta para campanha que não existe mais: conta como origem
    conhecida (o id está lá), mas sem nome inventado."""
    _venda(db, dia=5, first="camp-sumiu", last="camp-sumiu", utm_last="agosto")
    r = venda_origem_ultima(db, _ctx())
    assert r.origem.identificada is True
    assert r.origem.campanha_nome is None
    assert r.origem.utm_campaign == "agosto"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_venda_origem.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.consultas_origem'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/consultas_origem.py`:

```python
"""De qual anúncio veio a venda — o diferencial que abre a venda do Revy.

Lê o snapshot gravado na confirmação (``Venda.campanha_id_first/last``,
``models.py:126-129``). É leitura local: não depende do Revy Tráfego responder.

Regra dura: venda sem ``campanha_id_*`` é NÃO IDENTIFICADA. Jamais deduzir
origem pela data, pela campanha de outra venda ou pela campanha ativa.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.financeiro_calc import _data
from app.loja.copiloto.periodo import Janela, janela_do_periodo
from app.loja.copiloto.tipos import (
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)
from app.models import Campanha, Venda

CENTAVOS = Decimal("0.01")


@dataclass(frozen=True)
class OrigemVenda:
    venda_id: str
    descricao: str
    preco_venda: Decimal
    confirmada_em: str | None
    identificada: bool
    campanha_nome: str | None
    campanha_canal: str | None
    utm_campaign: str | None
    primeiro_clique_nome: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "venda_id": self.venda_id,
            "descricao": self.descricao,
            "preco_venda": str(
                self.preco_venda.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
            ),
            "confirmada_em": self.confirmada_em,
            "identificada": self.identificada,
            "campanha_nome": self.campanha_nome,
            "campanha_canal": self.campanha_canal,
            "utm_campaign": self.utm_campaign,
            "primeiro_clique_nome": self.primeiro_clique_nome,
        }


@dataclass(frozen=True)
class OrigemUltima:
    status: str
    origem: OrigemVenda | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "origem": self.origem.to_dict() if self.origem else None,
        }


@dataclass(frozen=True)
class OrigemPeriodo:
    status: str
    janela: Janela
    itens: tuple[OrigemVenda, ...]
    cobertura: Cobertura

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "periodo": self.janela.to_dict(),
            "itens": [item.to_dict() for item in self.itens],
            "cobertura": self.cobertura.to_dict(),
        }


def _nomes_de_campanha(db: Session, loja_slug: str, ids: set[str]) -> dict[str, Campanha]:
    if not ids:
        return {}
    linhas = (
        db.query(Campanha)
        .filter(Campanha.loja_slug == loja_slug, Campanha.id.in_(ids))
        .all()
    )
    return {c.id: c for c in linhas}


def _montar(venda: Venda, campanhas: dict[str, Campanha]) -> OrigemVenda:
    id_last = venda.campanha_id_last or venda.campanha_id_first
    id_first = venda.campanha_id_first
    campanha = campanhas.get(id_last) if id_last else None
    primeira = campanhas.get(id_first) if id_first else None
    primeiro_nome = (
        primeira.nome if primeira is not None and id_first != id_last else None
    )
    return OrigemVenda(
        venda_id=venda.id,
        descricao=venda.descricao,
        preco_venda=venda.preco_venda,
        confirmada_em=(
            venda.confirmada_em.isoformat() if venda.confirmada_em else None
        ),
        # O id do snapshot é a prova de origem; o nome pode ter sumido do CRM.
        identificada=bool(id_last),
        campanha_nome=campanha.nome if campanha else None,
        campanha_canal=campanha.canal if campanha else None,
        utm_campaign=(
            venda.utm_campaign_last
            or venda.utm_campaign_first
            or (campanha.utm_campaign if campanha else None)
        ),
        primeiro_clique_nome=primeiro_nome,
    )


def _vendas_confirmadas(db: Session, loja_slug: str, janela: Janela | None) -> list[Venda]:
    q = db.query(Venda).filter(
        Venda.loja_slug == loja_slug, Venda.status == "confirmada"
    )
    if janela is not None:
        inicio_dt = datetime.combine(
            janela.inicio, datetime.min.time(), tzinfo=timezone.utc
        ) - timedelta(days=1)
        fim_dt = datetime.combine(
            janela.fim, datetime.max.time(), tzinfo=timezone.utc
        ) + timedelta(days=1)
        q = q.filter(Venda.criada_em >= inicio_dt, Venda.criada_em <= fim_dt)
    vendas = q.order_by(Venda.criada_em.desc()).all()
    if janela is None:
        return vendas
    return [v for v in vendas if janela.inicio <= _data(v.criada_em) <= janela.fim]


def venda_origem_ultima(db: Session, ctx: CopilotoContexto) -> OrigemUltima:
    """A pergunta que abre a venda: de onde veio a última moto vendida."""
    vendas = _vendas_confirmadas(db, ctx.loja_slug, None)
    if not vendas:
        return OrigemUltima(status=STATUS_VAZIO, origem=None)
    venda = vendas[0]
    ids = {i for i in (venda.campanha_id_first, venda.campanha_id_last) if i}
    campanhas = _nomes_de_campanha(db, ctx.loja_slug, ids)
    return OrigemUltima(status=STATUS_OK, origem=_montar(venda, campanhas))


def venda_origem_periodo(
    db: Session,
    ctx: CopilotoContexto,
    *,
    inicio: str | None = None,
    fim: str | None = None,
) -> OrigemPeriodo:
    """Origem de todas as vendas do período, com cobertura declarada."""
    janela = janela_do_periodo(inicio, fim)
    vendas = _vendas_confirmadas(db, ctx.loja_slug, janela)
    if not vendas:
        return OrigemPeriodo(
            status=STATUS_VAZIO,
            janela=janela,
            itens=(),
            cobertura=Cobertura(com_dado=0, total=0),
        )

    ids: set[str] = set()
    for v in vendas:
        ids.update(i for i in (v.campanha_id_first, v.campanha_id_last) if i)
    campanhas = _nomes_de_campanha(db, ctx.loja_slug, ids)

    itens = tuple(_montar(v, campanhas) for v in vendas)
    cobertura = Cobertura(
        com_dado=sum(1 for i in itens if i.identificada), total=len(itens)
    )
    return OrigemPeriodo(
        status=STATUS_PARCIAL if cobertura.parcial else STATUS_OK,
        janela=janela,
        itens=itens,
        cobertura=cobertura,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_venda_origem.py -q`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/consultas_origem.py portal-gestao/tests/test_copiloto_venda_origem.py
git commit -m "feat(copiloto): venda_origem com cobertura e sem deducao de campanha"
```

---

### Task 7: `estoque_parado` + guarda de escopo de loja (fail-closed)

**Files:**
- Create: `portal-gestao/app/loja/copiloto/consultas_estoque.py`
- Test: `portal-gestao/tests/test_copiloto_estoque_parado.py`

**Interfaces:**
- Consumes: `CopilotoContexto`, `Cobertura`; client de estoque (duck-typed: precisa de `.listar(**filtros)` e `.obter_loja()`), exceção `app.clients.estoque.EstoqueIndisponivel`.
- Produces:
  - `EscopoLojaDivergente(RuntimeError)`;
  - `garantir_escopo_loja(estoque, loja_slug) -> None` (levanta `EscopoLojaDivergente`);
  - `VeiculoParado` (`id`, `descricao`, `placa`, `preco`, `dias_parado`, `status`);
  - `estoque_parado(estoque, ctx, *, dias_min=30, limite=20) -> EstoqueParado` (campos `status`, `dias_min`, `itens`, `total`, `capital_preso`, `cobertura_data`, `ressalva`, `to_dict()`).

**Duas coisas que este task resolve:**
1. **A lista não existe hoje** — `estoque_overview` só dá histograma (`estoque_overview.py:49-58`) e não soma capital preso. `criado_em` **é** serializado na listagem privada (`estoque-api/app/servico.py:1172`), então dias-parado é computável.
2. **§3.7 — o `EstoqueClient` usa token global do processo** (`app/main.py:389`) e a `estoque-api` deriva `loja_id` da credencial (`estoque-api/app/auth.py:32-35`). Enquanto for single-tenant funciona; no dia do multi-loja, agiria na loja errada **em silêncio**. A guarda confere `obter_loja()["slug"]` contra a sessão e **falha fechado**.

**Ressalva obrigatória na resposta:** `criado_em` é data de cadastro no sistema, não de entrada física do veículo. Em estoque migrado a idade é subestimada. O campo `ressalva` carrega isso para a UI e (fase 2) para o prompt.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_estoque_parado.py`:

```python
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.clients.estoque import EstoqueIndisponivel
from app.loja.copiloto.consultas_estoque import (
    EscopoLojaDivergente,
    estoque_parado,
    garantir_escopo_loja,
)
from app.loja.copiloto.tipos import CopilotoContexto

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def __init__(self, veiculos, *, slug="loja-teste", indisponivel=False):
        self.veiculos = veiculos
        self.slug = slug
        self.indisponivel = indisponivel

    def obter_loja(self):
        if self.indisponivel:
            raise EstoqueIndisponivel("estoque fora")
        return {"slug": self.slug, "nome": "Loja Teste"}

    def listar(self, **filtros):
        if self.indisponivel:
            raise EstoqueIndisponivel("estoque fora")
        return list(self.veiculos)


def _veiculo(id_, dias, preco=25000.0, status="disponivel", **extra):
    return {
        "id": id_,
        "marca": "Honda",
        "modelo": "CB 500F",
        "ano_modelo": 2020,
        "placa": f"ABC{id_}",
        "preco": preco,
        "status": status,
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        **extra,
    }


def test_lista_so_o_que_passou_do_limiar(db):
    estoque = EstoqueStub([_veiculo("v1", 70), _veiculo("v2", 10)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "ok"
    assert [i.id for i in r.itens] == ["v1"]
    assert r.itens[0].dias_parado == 70
    assert r.total == 1


def test_soma_capital_preso(db):
    estoque = EstoqueStub(
        [_veiculo("v1", 70, preco=25000.0), _veiculo("v2", 90, preco=13400.0)]
    )
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.capital_preso == Decimal("38400.00")
    assert r.total == 2


def test_ordena_do_mais_parado_para_o_menos(db):
    estoque = EstoqueStub([_veiculo("v1", 70), _veiculo("v2", 120)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert [i.id for i in r.itens] == ["v2", "v1"]


def test_vendido_e_indisponivel_nao_contam(db):
    estoque = EstoqueStub(
        [
            _veiculo("v1", 200, status="vendido"),
            _veiculo("v2", 200, status="indisponivel"),
            _veiculo("v3", 200, status="reservado"),
        ]
    )
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert [i.id for i in r.itens] == ["v3"]


def test_veiculo_sem_data_nao_vira_zero_dias_e_baixa_a_cobertura(db):
    estoque = EstoqueStub([_veiculo("v1", 70), {"id": "v2", "status": "disponivel"}])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert [i.id for i in r.itens] == ["v1"]
    assert r.cobertura_data.to_dict() == {"com_dado": 1, "total": 2}
    assert r.status == "parcial"


def test_veiculo_sem_preco_nao_inventa_capital(db):
    estoque = EstoqueStub([_veiculo("v1", 70, preco=None)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.itens[0].preco is None
    assert r.capital_preso == Decimal("0.00")


def test_estoque_fora_do_ar_e_indisponivel_nao_zero(db):
    estoque = EstoqueStub([], indisponivel=True)
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "indisponivel"
    assert r.itens == ()
    assert r.total is None
    assert r.capital_preso is None


def test_nada_parado_e_vazio(db):
    estoque = EstoqueStub([_veiculo("v1", 5)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "vazio"
    assert r.total == 0


def test_resposta_carrega_a_ressalva_de_criado_em(db):
    estoque = EstoqueStub([_veiculo("v1", 70)])
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert "cadastro" in r.ressalva.lower()


def test_guarda_falha_fechado_quando_o_estoque_e_de_outra_loja(db):
    estoque = EstoqueStub([_veiculo("v1", 70)], slug="outra-loja")
    with pytest.raises(EscopoLojaDivergente):
        garantir_escopo_loja(estoque, "loja-teste")


def test_estoque_parado_nao_devolve_dado_de_outra_loja(db):
    estoque = EstoqueStub([_veiculo("v1", 70)], slug="outra-loja")
    r = estoque_parado(estoque, _ctx(), dias_min=60, agora=AGORA)
    assert r.status == "erro"
    assert r.itens == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_estoque_parado.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.consultas_estoque'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/consultas_estoque.py`:

```python
"""Consultas de estoque do Copiloto.

§3.7 do design: o ``EstoqueClient`` é instanciado com um token GLOBAL do
processo (``app/main.py:389``) e a ``estoque-api`` deriva o ``loja_id`` da
credencial (``estoque-api/app/auth.py:32-35``), não do pedido. Enquanto o
Portal for uma loja por deploy isso funciona; no dia do multi-loja, agiria na
loja errada em silêncio. Por isso toda consulta aqui passa por
``garantir_escopo_loja`` e FALHA FECHADO.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.clients.estoque import EstoqueIndisponivel
from app.loja.copiloto.tipos import (
    STATUS_ERRO,
    STATUS_INDISPONIVEL,
    STATUS_OK,
    STATUS_PARCIAL,
    STATUS_VAZIO,
    Cobertura,
    CopilotoContexto,
)
from app.loja.estoque_overview import _data_entrada

CENTAVOS = Decimal("0.01")

# Status que ainda prendem capital. Vendido/indisponível não são "parados".
STATUS_ATIVOS = frozenset({"disponivel", "reservado"})

RESSALVA_IDADE = (
    "Dias contados a partir da data de cadastro no sistema, não da entrada "
    "física do veículo. Em estoque migrado a idade real pode ser maior."
)


class EscopoLojaDivergente(RuntimeError):
    """O estoque respondeu com dados de outra loja. Nunca seguir adiante."""


def garantir_escopo_loja(estoque: Any, loja_slug: str) -> None:
    """Confere que a credencial do estoque aponta para a loja da sessão."""
    dados = estoque.obter_loja() or {}
    slug = str(dados.get("slug") or "").strip().casefold()
    esperado = (loja_slug or "").strip().casefold()
    if not slug or slug != esperado:
        raise EscopoLojaDivergente(
            f"estoque respondeu pela loja {slug or '(vazio)'}, sessão é {esperado}"
        )


def _preco(veiculo: dict) -> Decimal | None:
    bruto = veiculo.get("preco")
    if bruto in (None, ""):
        return None
    try:
        valor = Decimal(str(bruto))
    except (ArithmeticError, ValueError):
        return None
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP) if valor > 0 else None


def _descricao(veiculo: dict) -> str:
    partes = [
        str(veiculo.get(campo)).strip()
        for campo in ("marca", "modelo", "versao", "ano_modelo")
        if veiculo.get(campo) not in (None, "")
    ]
    return " ".join(partes) or str(veiculo.get("id") or "veículo")


@dataclass(frozen=True)
class VeiculoParado:
    id: str
    descricao: str
    placa: str | None
    preco: Decimal | None
    dias_parado: int
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "descricao": self.descricao,
            "placa": self.placa,
            "preco": None if self.preco is None else str(self.preco),
            "dias_parado": self.dias_parado,
            "status": self.status,
        }


@dataclass(frozen=True)
class EstoqueParado:
    status: str
    dias_min: int
    itens: tuple[VeiculoParado, ...]
    total: int | None
    capital_preso: Decimal | None
    cobertura_data: Cobertura
    ressalva: str
    erro: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dias_min": self.dias_min,
            "itens": [i.to_dict() for i in self.itens],
            "total": self.total,
            "capital_preso": (
                None if self.capital_preso is None else str(self.capital_preso)
            ),
            "cobertura_data": self.cobertura_data.to_dict(),
            "ressalva": self.ressalva,
            "erro": self.erro,
        }


def _vazio(status: str, dias_min: int, erro: str | None = None) -> EstoqueParado:
    return EstoqueParado(
        status=status,
        dias_min=dias_min,
        itens=(),
        total=None,
        capital_preso=None,
        cobertura_data=Cobertura(com_dado=0, total=0),
        ressalva=RESSALVA_IDADE,
        erro=erro,
    )


def estoque_parado(
    estoque: Any,
    ctx: CopilotoContexto,
    *,
    dias_min: int = 30,
    limite: int = 20,
    agora: datetime | None = None,
) -> EstoqueParado:
    """Veículos parados além do limiar, com dias e capital preso."""
    try:
        garantir_escopo_loja(estoque, ctx.loja_slug)
    except EscopoLojaDivergente as exc:
        return _vazio(STATUS_ERRO, dias_min, erro=str(exc))
    except EstoqueIndisponivel:
        return _vazio(STATUS_INDISPONIVEL, dias_min)

    try:
        veiculos = estoque.listar()
    except EstoqueIndisponivel:
        return _vazio(STATUS_INDISPONIVEL, dias_min)

    ref = agora or datetime.now(timezone.utc)
    ativos = [v for v in (veiculos or []) if v.get("status") in STATUS_ATIVOS]

    com_data = 0
    parados: list[VeiculoParado] = []
    for v in ativos:
        entrada = _data_entrada(v)
        if entrada is None:
            # Sem data não vira "0 dias parado": vira buraco de cobertura.
            continue
        com_data += 1
        dias = max(0, (ref - entrada).days)
        if dias < dias_min:
            continue
        parados.append(
            VeiculoParado(
                id=str(v.get("id") or ""),
                descricao=_descricao(v),
                placa=(str(v["placa"]) if v.get("placa") else None),
                preco=_preco(v),
                dias_parado=dias,
                status=str(v.get("status") or ""),
            )
        )

    parados.sort(key=lambda i: (-i.dias_parado, i.id))
    cobertura = Cobertura(com_dado=com_data, total=len(ativos))
    capital = sum(
        (i.preco for i in parados if i.preco is not None), Decimal("0")
    ).quantize(CENTAVOS, rounding=ROUND_HALF_UP)

    if not parados:
        status = STATUS_PARCIAL if cobertura.parcial else STATUS_VAZIO
    else:
        status = STATUS_PARCIAL if cobertura.parcial else STATUS_OK

    return EstoqueParado(
        status=status,
        dias_min=dias_min,
        itens=tuple(parados[: max(1, limite)]),
        total=len(parados),
        capital_preso=capital,
        cobertura_data=cobertura,
        ressalva=RESSALVA_IDADE,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_estoque_parado.py -q`
Expected: PASS (11 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/consultas_estoque.py portal-gestao/tests/test_copiloto_estoque_parado.py
git commit -m "feat(copiloto): estoque_parado com capital preso e guarda de escopo de loja"
```

---

### Task 8: `leads_status` — re-fiação do funil + "leads sem resposta"

**Files:**
- Create: `portal-gestao/app/loja/copiloto/consultas_leads.py`
- Test: `portal-gestao/tests/test_copiloto_leads_status.py`

**Interfaces:**
- Consumes: `CopilotoContexto`; `app.loja.sales_overview.SalesOverview` (só leitura de `.funil` e `.funil_status`); client de chatbot duck-typed (`.listar_conversas(limit=..., canal_id=...)`), exceção `app.clients.chatbot.ChatbotIndisponivel`.
- Produces: `leads_status(overview, chatbot, *, agora, horas_sem_resposta=4) -> LeadsStatus` com campos `status`, `total_leads`, `taxa_resposta_pct`, `tempo_mediano_primeira_resposta_segundos`, `sem_resposta`, `sem_resposta_status`, `horas_sem_resposta`, `to_dict()`.

**Correção que este task aplica (§4.1):** a revisão 1 do design apontava `ChatbotClient.resumo_atendimento()` como fonte. **Está errado** — ele devolve `{atendimentos, transferidos, transferidos_pct, por_dia, simulacoes}` (`chatbot-api/app/servico.py:1512-1518`), nenhuma das métricas pedidas. As certas vivem em `SalesOverview.funil` (`sales_overview.py:929-945`): `taxa_resposta_pct` e `tempo_mediano_primeira_resposta_segundos`.

**Decisão que este plano fecha (era pendência do design):** "leads sem resposta" = **conversa em handoff (`bot_ativo=False`) cuja última mensagem é do cliente (`direcao="entrada"`) e passou de N horas**. Se o bot está ligado, o bot está respondendo — não é lead abandonado. É derivável hoje de `listar_conversas()` e não inventa fila que não existe.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_leads_status.py`:

```python
from datetime import date, datetime, timedelta, timezone

from app.clients.chatbot import ChatbotIndisponivel
from app.loja.copiloto.consultas_leads import leads_status
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.sales_overview import SalesOverview

AGORA = datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


def _overview(funil=None, funil_status="ok"):
    return SalesOverview(
        status="ok",
        periodo_inicio=date(2026, 8, 1),
        periodo_fim=date(2026, 8, 31),
        timezone="America/Sao_Paulo",
        escopo="loja",
        funil=funil,
        funil_status=funil_status,
    )


class ChatbotStub:
    def __init__(self, conversas, indisponivel=False):
        self.conversas = conversas
        self.indisponivel = indisponivel

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("chatbot fora")
        return list(self.conversas)


def _conversa(*, bot_ativo, direcao, horas):
    return {
        "telefone": "5511987654321",
        "bot_ativo": bot_ativo,
        "status": "aberta" if bot_ativo else "handoff",
        "ultima_mensagem": {
            "texto": "e aí, tem?",
            "direcao": direcao,
            "criada_em": (AGORA - timedelta(hours=horas)).isoformat(),
        },
    }


def test_repassa_metricas_do_funil():
    overview = _overview(
        funil={
            "total_leads": 40,
            "taxa_resposta_pct": "82.5",
            "tempo_mediano_primeira_resposta_segundos": 320,
        }
    )
    r = leads_status(overview, ChatbotStub([]), ctx=_ctx(), agora=AGORA)
    assert r.status == "ok"
    assert r.total_leads == 40
    assert r.taxa_resposta_pct == "82.5"
    assert r.tempo_mediano_primeira_resposta_segundos == 320


def test_conta_conversa_em_handoff_esperando_ha_horas():
    conversas = [
        _conversa(bot_ativo=False, direcao="entrada", horas=6),
        _conversa(bot_ativo=False, direcao="entrada", horas=1),
    ]
    r = leads_status(
        _overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA,
        horas_sem_resposta=4,
    )
    assert r.sem_resposta == 1
    assert r.sem_resposta_status == "ok"


def test_bot_ligado_nao_e_lead_abandonado():
    conversas = [_conversa(bot_ativo=True, direcao="entrada", horas=10)]
    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)
    assert r.sem_resposta == 0


def test_ultima_mensagem_da_loja_nao_conta():
    conversas = [_conversa(bot_ativo=False, direcao="saida", horas=10)]
    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)
    assert r.sem_resposta == 0


def test_conversa_sem_ultima_mensagem_nao_conta():
    conversas = [{"telefone": "5511999", "bot_ativo": False, "ultima_mensagem": None}]
    r = leads_status(_overview(), ChatbotStub(conversas), ctx=_ctx(), agora=AGORA)
    assert r.sem_resposta == 0


def test_chatbot_fora_do_ar_marca_indisponivel_nao_zero():
    r = leads_status(
        _overview(), ChatbotStub([], indisponivel=True), ctx=_ctx(), agora=AGORA
    )
    assert r.sem_resposta is None
    assert r.sem_resposta_status == "indisponivel"


def test_funil_com_erro_nao_vira_zero_leads():
    r = leads_status(
        _overview(funil=None, funil_status="erro"),
        ChatbotStub([]),
        ctx=_ctx(),
        agora=AGORA,
    )
    assert r.total_leads is None
    assert r.status in {"parcial", "erro"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_leads_status.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.consultas_leads'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/consultas_leads.py`:

```python
"""Leads e atendimento, do ponto de vista do dono.

As métricas de funil vêm de ``SalesOverview.funil`` (``sales_overview.py:929-945``)
— NÃO de ``ChatbotClient.resumo_atendimento()``, que devolve outra coisa
(``chatbot-api/app/servico.py:1512-1518``).

"Sem resposta" tem uma definição só, e ela é honesta: conversa em handoff
(bot desligado, humano é o responsável) cuja última mensagem é do cliente e
passou do limiar de horas. Bot ligado = bot respondendo, não é abandono.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.clients.chatbot import ChatbotIndisponivel
from app.loja.copiloto.tipos import (
    STATUS_ERRO,
    STATUS_INDISPONIVEL,
    STATUS_OK,
    STATUS_PARCIAL,
    CopilotoContexto,
)

LIMITE_CONVERSAS = 200


def _dt(valor: Any) -> datetime | None:
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class LeadsStatus:
    status: str
    total_leads: int | None
    taxa_resposta_pct: str | None
    tempo_mediano_primeira_resposta_segundos: int | None
    sem_resposta: int | None
    sem_resposta_status: str
    horas_sem_resposta: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_leads": self.total_leads,
            "taxa_resposta_pct": self.taxa_resposta_pct,
            "tempo_mediano_primeira_resposta_segundos": (
                self.tempo_mediano_primeira_resposta_segundos
            ),
            "sem_resposta": self.sem_resposta,
            "sem_resposta_status": self.sem_resposta_status,
            "horas_sem_resposta": self.horas_sem_resposta,
        }


def contar_sem_resposta(
    conversas: list[dict],
    *,
    agora: datetime,
    horas: int,
) -> int:
    limite_segundos = horas * 3600
    total = 0
    for conversa in conversas or []:
        if conversa.get("bot_ativo") is not False:
            continue
        ultima = conversa.get("ultima_mensagem") or None
        if not isinstance(ultima, dict):
            continue
        if (ultima.get("direcao") or "").strip().casefold() != "entrada":
            continue
        criada = _dt(ultima.get("criada_em"))
        if criada is None:
            continue
        if (agora - criada).total_seconds() >= limite_segundos:
            total += 1
    return total


def leads_status(
    overview: Any,
    chatbot: Any,
    *,
    ctx: CopilotoContexto,
    agora: datetime | None = None,
    horas_sem_resposta: int = 4,
) -> LeadsStatus:
    """Leads do período + quantos estão esperando gente há horas."""
    ref = agora or datetime.now(timezone.utc)
    funil = getattr(overview, "funil", None) or {}
    funil_status = getattr(overview, "funil_status", STATUS_INDISPONIVEL)

    total_leads = funil.get("total_leads")
    taxa = funil.get("taxa_resposta_pct")
    tempo = funil.get("tempo_mediano_primeira_resposta_segundos")

    sem_resposta: int | None = None
    sem_resposta_status = STATUS_INDISPONIVEL
    try:
        conversas = chatbot.listar_conversas(limit=LIMITE_CONVERSAS)
        sem_resposta = contar_sem_resposta(
            conversas, agora=ref, horas=horas_sem_resposta
        )
        sem_resposta_status = STATUS_OK
    except ChatbotIndisponivel:
        pass
    except Exception:
        # Client sem o método (fake antigo) degrada igual: nunca zero inventado.
        pass

    if funil_status == STATUS_ERRO and sem_resposta_status != STATUS_OK:
        status = STATUS_ERRO
    elif funil_status in {STATUS_ERRO, STATUS_INDISPONIVEL} or sem_resposta is None:
        status = STATUS_PARCIAL
    else:
        status = STATUS_OK

    return LeadsStatus(
        status=status,
        total_leads=total_leads,
        taxa_resposta_pct=taxa,
        tempo_mediano_primeira_resposta_segundos=tempo,
        sem_resposta=sem_resposta,
        sem_resposta_status=sem_resposta_status,
        horas_sem_resposta=horas_sem_resposta,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_leads_status.py -q`
Expected: PASS (7 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/consultas_leads.py portal-gestao/tests/test_copiloto_leads_status.py
git commit -m "feat(copiloto): leads_status a partir do funil + leads sem resposta"
```

---

### Task 9: Cache TTL do `build_sales_overview`

**Files:**
- Create: `portal-gestao/app/loja/copiloto/cache.py`
- Test: `portal-gestao/tests/test_copiloto_cache.py`

**Interfaces:**
- Consumes: nada do repo (só `time`).
- Produces: `CacheTTL(ttl_segundos: float)` com `.obter(chave, produtor)`, `.invalidar(prefixo=None)`, `.tamanho`; instância de módulo `cache_overview` e helper `chave_overview(loja_slug, papel, inicio, fim) -> str`.

**Por que existe (§3.5):** `build_sales_overview()` faz 3–4 round-trips HTTP sequenciais e chama `chatbot.listar_leads()` **3× sem memoização** (`sales_overview.py:1014`, `:659`, `financeiro_calc.py:223`, `:781`), com timeout 5s + 1 retry cada. **Não há cache algum no Portal.** Sem isto, o "Resumo de hoje" e cada regra do motor de sinais refazem o fan-out inteiro.

**Limite deliberado:** TTL curto (90s default) e cache **em processo**. Não é Redis, não é compartilhado entre máquinas, e é isso mesmo — a alternativa é infra nova que a v1 não pede.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_cache.py`:

```python
from app.loja.copiloto.cache import CacheTTL, chave_overview


def test_segunda_chamada_nao_reexecuta_o_produtor():
    relogio = {"t": 1000.0}
    cache = CacheTTL(ttl_segundos=90, agora=lambda: relogio["t"])
    chamadas = []

    def produtor():
        chamadas.append(1)
        return "overview"

    assert cache.obter("k", produtor) == "overview"
    assert cache.obter("k", produtor) == "overview"
    assert len(chamadas) == 1


def test_expira_depois_do_ttl():
    relogio = {"t": 1000.0}
    cache = CacheTTL(ttl_segundos=90, agora=lambda: relogio["t"])
    chamadas = []

    def produtor():
        chamadas.append(1)
        return "overview"

    cache.obter("k", produtor)
    relogio["t"] += 91
    cache.obter("k", produtor)
    assert len(chamadas) == 2


def test_chaves_diferentes_nao_se_misturam():
    cache = CacheTTL(ttl_segundos=90)
    assert cache.obter("a", lambda: 1) == 1
    assert cache.obter("b", lambda: 2) == 2
    assert cache.obter("a", lambda: 99) == 1


def test_producao_que_levanta_nao_fica_cacheada():
    cache = CacheTTL(ttl_segundos=90)
    chamadas = []

    def explode():
        chamadas.append(1)
        raise RuntimeError("boom")

    for _ in range(2):
        try:
            cache.obter("k", explode)
        except RuntimeError:
            pass
    assert len(chamadas) == 2


def test_invalidar_por_prefixo_da_loja():
    cache = CacheTTL(ttl_segundos=90)
    cache.obter("loja-a:x", lambda: 1)
    cache.obter("loja-b:x", lambda: 2)
    cache.invalidar(prefixo="loja-a:")
    assert cache.tamanho == 1


def test_chave_do_overview_separa_papel_e_periodo():
    a = chave_overview("loja-teste", "dono", "2026-08-01", "2026-08-31")
    b = chave_overview("loja-teste", "vendedor", "2026-08-01", "2026-08-31")
    c = chave_overview("loja-teste", "dono", "2026-07-01", "2026-07-31")
    assert a != b != c and a != c
    assert a.startswith("loja-teste:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.cache'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/cache.py`:

```python
"""Cache TTL em processo para o fan-out caro do SalesOverview.

``build_sales_overview`` faz 3–4 round-trips HTTP em sequência e chama
``listar_leads()`` três vezes sem memoização. Três perguntas seguidas sobre o
mesmo mês fariam o fan-out três vezes.

Escopo consciente: é cache POR PROCESSO, não distribuído. TTL curto — o dono
prefere um número 60s velho a esperar 20s por ele.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

TTL_PADRAO_SEGUNDOS = 90.0


class CacheTTL:
    def __init__(
        self,
        ttl_segundos: float = TTL_PADRAO_SEGUNDOS,
        *,
        agora: Callable[[], float] = time.monotonic,
    ):
        self.ttl = float(ttl_segundos)
        self._agora = agora
        self._dados: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    @property
    def tamanho(self) -> int:
        with self._lock:
            return len(self._dados)

    def obter(self, chave: str, produtor: Callable[[], Any]) -> Any:
        agora = self._agora()
        with self._lock:
            item = self._dados.get(chave)
            if item is not None and agora - item[0] < self.ttl:
                return item[1]
        # Produz fora do lock: o produtor faz I/O de segundos.
        valor = produtor()
        with self._lock:
            self._dados[chave] = (self._agora(), valor)
        return valor

    def invalidar(self, *, prefixo: str | None = None) -> None:
        with self._lock:
            if prefixo is None:
                self._dados.clear()
                return
            for chave in [k for k in self._dados if k.startswith(prefixo)]:
                self._dados.pop(chave, None)


def chave_overview(
    loja_slug: str,
    papel: str,
    inicio: str | None,
    fim: str | None,
) -> str:
    """Papel entra na chave: vendedor e dono veem escopos diferentes."""
    return f"{loja_slug}:overview:{papel}:{inicio or '-'}:{fim or '-'}"


cache_overview = CacheTTL()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_cache.py -q`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/cache.py portal-gestao/tests/test_copiloto_cache.py
git commit -m "feat(copiloto): cache TTL em processo para o fan-out do sales overview"
```

---

### Task 10: Tabela `copiloto_sinal` (model + migration)

**Files:**
- Modify: `portal-gestao/app/models.py`
- Create: `portal-gestao/alembic/versions/0019_copiloto_sinal.py`
- Test: `portal-gestao/tests/test_copiloto_sinal_model.py`

**Interfaces:**
- Consumes: `app.models.Base`, `agora`, `novo_id`.
- Produces: `CopilotoSinal` com colunas `id`, `loja_slug`, `regra`, `entidade_ref`, `severidade`, `titulo`, `detalhe`, `dados_json`, `acao_sugerida_json`, `estado`, `criado_em`, `atualizado_em`, `resolvido_em`, `dispensado_em`. Constantes `SINAL_ESTADOS`, `SINAL_SEVERIDADES`, `SINAL_REGRAS`.

**Convenção da casa:** JSON vai em coluna `Text` serializada à mão (`payload_json`, `models.py:251`), não em tipo `JSON` — o Portal roda SQLite nos testes e Postgres em produção.

**Sem `UniqueConstraint` de cooldown:** o cooldown é regra de tempo (Task 12), não de unicidade. Constraint aqui viraria erro de integridade em vez de "ainda em cooldown".

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_sinal_model.py`:

```python
import json

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import CopilotoSinal


def test_grava_e_le_sinal_com_dados_json(db):
    sinal = CopilotoSinal(
        loja_slug="loja-teste",
        regra="estoque_parado",
        entidade_ref="v1",
        severidade="atencao",
        titulo="3 motos passaram de 60 dias",
        detalhe="R$ 38.400 de capital preso.",
        dados_json=json.dumps({"capital_preso": "38400.00", "total": 3}),
    )
    db.add(sinal)
    db.commit()
    db.refresh(sinal)
    assert sinal.id
    assert sinal.estado == "novo"
    assert json.loads(sinal.dados_json)["total"] == 3
    assert sinal.criado_em is not None


def test_estado_invalido_e_recusado_pelo_banco(db):
    db.add(
        CopilotoSinal(
            loja_slug="loja-teste",
            regra="estoque_parado",
            severidade="atencao",
            titulo="x",
            detalhe="y",
            estado="inventado",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_severidade_invalida_e_recusada_pelo_banco(db):
    db.add(
        CopilotoSinal(
            loja_slug="loja-teste",
            regra="estoque_parado",
            severidade="apocaliptico",
            titulo="x",
            detalhe="y",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'CopilotoSinal' from 'app.models'`.

- [ ] **Step 3: Write minimal implementation**

Ao fim de `portal-gestao/app/models.py`:

```python
# --- Copiloto de Vendas -----------------------------------------------------

SINAL_ESTADOS = ("novo", "visto", "resolvido", "dispensado")
SINAL_SEVERIDADES = ("info", "atencao", "critico")
SINAL_REGRAS = (
    "estoque_parado",
    "lead_sem_resposta",
    "meta_em_risco",
    "margem_incompleta",
    "cadastro_incompleto",
    "atribuicao_baixa",
)


class CopilotoSinal(Base):
    """Alerta proativo do Copiloto.

    Gerado por REGRA DETERMINÍSTICA — o LLM não participa. É o que mantém a
    seção útil quando o provedor de IA está fora do ar.

    Nunca guarda telefone em claro (mesma disciplina de
    ``loja_operacao_auditoria``): sinais de lead são agregados.
    """

    __tablename__ = "copiloto_sinal"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('novo', 'visto', 'resolvido', 'dispensado')",
            name="ck_copiloto_sinal_estado",
        ),
        CheckConstraint(
            "severidade IN ('info', 'atencao', 'critico')",
            name="ck_copiloto_sinal_severidade",
        ),
        Index(
            "ix_copiloto_sinal_loja_regra_entidade",
            "loja_slug",
            "regra",
            "entidade_ref",
        ),
        Index("ix_copiloto_sinal_loja_estado", "loja_slug", "estado", "criado_em"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    loja_slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    regra: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # Id do veículo / meta / o que a regra observa. None = sinal agregado da loja.
    entidade_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    severidade: Mapped[str] = mapped_column(String(20), nullable=False)
    titulo: Mapped[str] = mapped_column(String(240), nullable=False)
    detalhe: Mapped[str] = mapped_column(String(600), nullable=False)
    dados_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acao_sugerida_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="novo")
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora, nullable=False
    )
    resolvido_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispensado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Criar `portal-gestao/alembic/versions/0019_copiloto_sinal.py`:

```python
"""cria copiloto_sinal (alertas proativos do Copiloto de Vendas)

Revision ID: 0019_copiloto_sinal
Revises: 0018_redefinicoes_senha
"""

import sqlalchemy as sa
from alembic import op


revision = "0019_copiloto_sinal"
down_revision = "0018_redefinicoes_senha"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copiloto_sinal",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_slug", sa.String(length=120), nullable=False),
        sa.Column("regra", sa.String(length=40), nullable=False),
        sa.Column("entidade_ref", sa.String(length=120), nullable=True),
        sa.Column("severidade", sa.String(length=20), nullable=False),
        sa.Column("titulo", sa.String(length=240), nullable=False),
        sa.Column("detalhe", sa.String(length=600), nullable=False),
        sa.Column("dados_json", sa.Text(), nullable=True),
        sa.Column("acao_sugerida_json", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispensado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('novo', 'visto', 'resolvido', 'dispensado')",
            name="ck_copiloto_sinal_estado",
        ),
        sa.CheckConstraint(
            "severidade IN ('info', 'atencao', 'critico')",
            name="ck_copiloto_sinal_severidade",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_copiloto_sinal_loja_slug", "copiloto_sinal", ["loja_slug"], unique=False
    )
    op.create_index(
        "ix_copiloto_sinal_regra", "copiloto_sinal", ["regra"], unique=False
    )
    op.create_index(
        "ix_copiloto_sinal_loja_regra_entidade",
        "copiloto_sinal",
        ["loja_slug", "regra", "entidade_ref"],
        unique=False,
    )
    op.create_index(
        "ix_copiloto_sinal_loja_estado",
        "copiloto_sinal",
        ["loja_slug", "estado", "criado_em"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_copiloto_sinal_loja_estado", table_name="copiloto_sinal")
    op.drop_index("ix_copiloto_sinal_loja_regra_entidade", table_name="copiloto_sinal")
    op.drop_index("ix_copiloto_sinal_regra", table_name="copiloto_sinal")
    op.drop_index("ix_copiloto_sinal_loja_slug", table_name="copiloto_sinal")
    op.drop_table("copiloto_sinal")
```

- [ ] **Step 4: Run test + migration**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_model.py -q`
Expected: PASS (3 testes).

Run: `.\.venv\Scripts\python.exe -m alembic upgrade head`
Expected: aplica `0019_copiloto_sinal` sem erro; `alembic current` mostra `0019_copiloto_sinal`.

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/models.py portal-gestao/alembic/versions/0019_copiloto_sinal.py portal-gestao/tests/test_copiloto_sinal_model.py
git commit -m "feat(copiloto): tabela copiloto_sinal com constraints de estado e severidade"
```

---

### Task 11: As 6 regras determinísticas (funções puras)

**Files:**
- Create: `portal-gestao/app/loja/copiloto/sinais.py`
- Test: `portal-gestao/tests/test_copiloto_sinais_regras.py`

**Interfaces:**
- Consumes: `VendasResumo` (Task 4), `EstoqueParado` (Task 7), `OrigemPeriodo` (Task 6), `LeadsStatus` (Task 8), `Janela` (Task 3), `app.loja.estoque_overview.EstoqueOverview`.
- Produces:
  - `SinalCandidato(regra, entidade_ref, severidade, titulo, detalhe, dados, acao_sugerida=None)`;
  - `regra_estoque_parado(parado) -> list[SinalCandidato]`
  - `regra_lead_sem_resposta(leads) -> list[SinalCandidato]`
  - `regra_meta_em_risco(metas, janela, *, hoje) -> list[SinalCandidato]`
  - `regra_margem_incompleta(vendas) -> list[SinalCandidato]`
  - `regra_cadastro_incompleto(overview_estoque) -> list[SinalCandidato]`
  - `regra_atribuicao_baixa(origem, *, minimo_vendas=3, limite_pct=30.0) -> list[SinalCandidato]`

**Princípio que barateia tudo (§5):** o alerta é determinístico e o LLM **não participa**. Custo previsível (roda por loja, não por pergunta), zero alucinação no canal mais visível, e continua funcionando com o provedor de IA fora do ar.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_sinais_regras.py`:

```python
from datetime import date
from decimal import Decimal

from app.loja.copiloto.consultas_estoque import (
    RESSALVA_IDADE,
    EstoqueParado,
    VeiculoParado,
)
from app.loja.copiloto.consultas_leads import LeadsStatus
from app.loja.copiloto.consultas_origem import OrigemPeriodo, OrigemVenda
from app.loja.copiloto.consultas_vendas import VendasResumo
from app.loja.copiloto.periodo import Janela, janela_do_periodo
from app.loja.copiloto.sinais import (
    regra_atribuicao_baixa,
    regra_cadastro_incompleto,
    regra_estoque_parado,
    regra_lead_sem_resposta,
    regra_margem_incompleta,
    regra_meta_em_risco,
)
from app.loja.copiloto.tipos import Cobertura
from app.loja.estoque_overview import EstoqueOverview, LacunaCadastro

JANELA = janela_do_periodo("2026-08-01", "2026-08-31")


def _parado(itens):
    return EstoqueParado(
        status="ok" if itens else "vazio",
        dias_min=60,
        itens=tuple(itens),
        total=len(itens),
        capital_preso=sum((i.preco or Decimal("0") for i in itens), Decimal("0")),
        cobertura_data=Cobertura(com_dado=len(itens), total=len(itens)),
        ressalva=RESSALVA_IDADE,
    )


def _veiculo(id_, dias, preco):
    return VeiculoParado(
        id=id_,
        descricao=f"Honda CB 500F {id_}",
        placa="ABC1D23",
        preco=Decimal(str(preco)),
        dias_parado=dias,
        status="disponivel",
    )


def _vendas(qtd, com_custo):
    return VendasResumo(
        status="parcial" if com_custo < qtd else "ok",
        janela=JANELA,
        janela_comparacao=JANELA,
        qtd_vendas=qtd,
        receita=Decimal("100000.00"),
        ticket_medio=Decimal("10000.00"),
        margem=Decimal("9000.00"),
        cobertura_margem=Cobertura(com_dado=com_custo, total=qtd),
        qtd_vendas_anterior=0,
        receita_anterior=Decimal("0.00"),
        ticket_medio_anterior=None,
        delta_qtd=qtd,
        delta_receita_pct=None,
        delta_ticket_pct=None,
    )


def test_estoque_parado_gera_um_sinal_por_veiculo():
    sinais = regra_estoque_parado(_parado([_veiculo("v1", 70, 25000), _veiculo("v2", 95, 13400)]))
    assert [s.entidade_ref for s in sinais] == ["v1", "v2"]
    assert all(s.regra == "estoque_parado" for s in sinais)
    assert sinais[0].acao_sugerida["acao"] == "ajustar_preco"
    assert sinais[0].acao_sugerida["veiculo_id"] == "v1"


def test_estoque_parado_escala_severidade_com_o_tempo():
    sinais = regra_estoque_parado(_parado([_veiculo("v1", 65, 25000), _veiculo("v2", 130, 25000)]))
    por_id = {s.entidade_ref: s for s in sinais}
    assert por_id["v1"].severidade == "atencao"
    assert por_id["v2"].severidade == "critico"


def test_estoque_sem_parado_nao_gera_sinal():
    assert regra_estoque_parado(_parado([])) == []


def test_lead_sem_resposta_dispara_e_e_agregado_sem_telefone():
    leads = LeadsStatus(
        status="ok",
        total_leads=10,
        taxa_resposta_pct="80.0",
        tempo_mediano_primeira_resposta_segundos=300,
        sem_resposta=2,
        sem_resposta_status="ok",
        horas_sem_resposta=4,
    )
    sinais = regra_lead_sem_resposta(leads)
    assert len(sinais) == 1
    assert sinais[0].entidade_ref is None
    assert "2" in sinais[0].titulo
    assert sinais[0].acao_sugerida["href"] == "/app/loja/atendimento"


def test_lead_sem_resposta_indisponivel_nao_dispara():
    leads = LeadsStatus(
        status="parcial",
        total_leads=None,
        taxa_resposta_pct=None,
        tempo_mediano_primeira_resposta_segundos=None,
        sem_resposta=None,
        sem_resposta_status="indisponivel",
        horas_sem_resposta=4,
    )
    assert regra_lead_sem_resposta(leads) == []


def test_meta_em_risco_quando_o_ritmo_nao_alcanca():
    metas = [
        {
            "tipo": "faturamento",
            "alvo": Decimal("200000"),
            "realizado": Decimal("50000"),
            "pct": 25.0,
            "indisponivel": False,
        }
    ]
    sinais = regra_meta_em_risco(metas, JANELA, hoje=date(2026, 8, 25))
    assert len(sinais) == 1
    assert sinais[0].regra == "meta_em_risco"
    assert sinais[0].dados["falta"] == "150000.00"
    assert sinais[0].dados["dias_restantes"] == 7


def test_meta_no_ritmo_nao_dispara():
    metas = [
        {
            "tipo": "faturamento",
            "alvo": Decimal("200000"),
            "realizado": Decimal("180000"),
            "pct": 90.0,
            "indisponivel": False,
        }
    ]
    assert regra_meta_em_risco(metas, JANELA, hoje=date(2026, 8, 25)) == []


def test_meta_indisponivel_nao_dispara():
    metas = [
        {
            "tipo": "lucro_bruto",
            "alvo": Decimal("50000"),
            "realizado": Decimal("0"),
            "pct": 0.0,
            "indisponivel": True,
        }
    ]
    assert regra_meta_em_risco(metas, JANELA, hoje=date(2026, 8, 25)) == []


def test_margem_incompleta_conta_as_vendas_sem_custo():
    sinais = regra_margem_incompleta(_vendas(qtd=14, com_custo=8))
    assert len(sinais) == 1
    assert sinais[0].dados["sem_custo"] == 6
    assert "subestimada" in sinais[0].detalhe


def test_margem_completa_nao_dispara():
    assert regra_margem_incompleta(_vendas(qtd=14, com_custo=14)) == []


def test_cadastro_incompleto_usa_as_lacunas_do_overview():
    overview = EstoqueOverview(
        status="ok",
        contagens=None,
        idade=None,
        lacunas=(
            LacunaCadastro(
                id="v1", placa="ABC", marca="Honda", modelo="CB", status="disponivel",
                faltas=("foto", "preco"),
            ),
        ),
        total_lacunas=3,
    )
    sinais = regra_cadastro_incompleto(overview)
    assert len(sinais) == 1
    assert sinais[0].dados["total"] == 3


def test_cadastro_sem_lacuna_nao_dispara():
    overview = EstoqueOverview(
        status="ok", contagens=None, idade=None, lacunas=(), total_lacunas=0
    )
    assert regra_cadastro_incompleto(overview) == []


def _origem(identificadas, total):
    itens = tuple(
        OrigemVenda(
            venda_id=f"v{i}",
            descricao="Moto",
            preco_venda=Decimal("20000"),
            confirmada_em=None,
            identificada=i < identificadas,
            campanha_nome=None,
            campanha_canal=None,
            utm_campaign=None,
            primeiro_clique_nome=None,
        )
        for i in range(total)
    )
    return OrigemPeriodo(
        status="parcial",
        janela=JANELA,
        itens=itens,
        cobertura=Cobertura(com_dado=identificadas, total=total),
    )


def test_atribuicao_baixa_dispara_acima_do_limite():
    sinais = regra_atribuicao_baixa(_origem(identificadas=9, total=14))
    assert len(sinais) == 1
    assert sinais[0].dados["sem_origem"] == 5


def test_atribuicao_boa_nao_dispara():
    assert regra_atribuicao_baixa(_origem(identificadas=13, total=14)) == []


def test_atribuicao_com_poucas_vendas_nao_dispara():
    """1 venda sem origem em 2 é 50%, mas não é sinal — é ruído."""
    assert regra_atribuicao_baixa(_origem(identificadas=1, total=2)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinais_regras.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.sinais'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/sinais.py`:

```python
"""Regras determinísticas de alerta. O LLM não participa.

Cada regra é uma função PURA: recebe um read model já montado e devolve
candidatos a sinal. Quem busca dado é o worker (``app/copiloto_sinais_job.py``);
quem persiste e aplica cooldown é ``sinais_store.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

CENTAVOS = Decimal("0.01")

DIAS_CRITICO_ESTOQUE = 120
LIMITE_PCT_META_RISCO = 0.85  # ritmo projetado abaixo de 85% do alvo


def _brl(valor: Decimal | None) -> str:
    if valor is None:
        return "R$ 0,00"
    texto = f"{valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP):,.2f}"
    return "R$ " + texto.replace(",", "@").replace(".", ",").replace("@", ".")


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


@dataclass(frozen=True)
class SinalCandidato:
    regra: str
    severidade: str  # info | atencao | critico
    titulo: str
    detalhe: str
    entidade_ref: str | None = None
    dados: dict[str, Any] = field(default_factory=dict)
    acao_sugerida: dict[str, Any] | None = None


def regra_estoque_parado(parado: Any) -> list[SinalCandidato]:
    """Um sinal por veículo — o dono age veículo a veículo, não em lote."""
    if getattr(parado, "status", "") in {"erro", "indisponivel"}:
        return []
    saida: list[SinalCandidato] = []
    for item in getattr(parado, "itens", ()) or ():
        severidade = "critico" if item.dias_parado >= DIAS_CRITICO_ESTOQUE else "atencao"
        saida.append(
            SinalCandidato(
                regra="estoque_parado",
                severidade=severidade,
                entidade_ref=item.id,
                titulo=f"{item.descricao} parada há {item.dias_parado} dias",
                detalhe=(
                    f"{_brl(item.preco)} de capital preso neste veículo. "
                    "Vale revisar o preço."
                ),
                dados={
                    "veiculo_id": item.id,
                    "dias_parado": item.dias_parado,
                    "preco": None if item.preco is None else str(item.preco),
                    "ressalva": getattr(parado, "ressalva", ""),
                },
                acao_sugerida={"acao": "ajustar_preco", "veiculo_id": item.id},
            )
        )
    return saida


def regra_lead_sem_resposta(leads: Any) -> list[SinalCandidato]:
    """Agregado: nunca guarda telefone, nem em hash — o link leva à fila."""
    total = getattr(leads, "sem_resposta", None)
    if not total:
        return []
    horas = getattr(leads, "horas_sem_resposta", 4)
    return [
        SinalCandidato(
            regra="lead_sem_resposta",
            severidade="critico",
            titulo=(
                f"{total} {_plural(total, 'lead', 'leads')} "
                f"há mais de {horas}h sem resposta"
            ),
            detalhe=(
                "Estão em atendimento humano e a última mensagem é do cliente."
            ),
            dados={"sem_resposta": total, "horas": horas},
            acao_sugerida={"acao": "abrir", "href": "/app/loja/atendimento"},
        )
    ]


def regra_meta_em_risco(
    metas: list[dict],
    janela: Any,
    *,
    hoje: date,
) -> list[SinalCandidato]:
    """Dispara quando o ritmo do período projeta abaixo do alvo."""
    dias_restantes = max(0, (janela.fim - hoje).days)
    decorridos = max(1, (hoje - janela.inicio).days + 1)
    saida: list[SinalCandidato] = []
    for meta in metas or []:
        if meta.get("indisponivel"):
            continue
        alvo = meta.get("alvo")
        realizado = meta.get("realizado")
        if alvo in (None, 0) or realizado is None:
            continue
        alvo = Decimal(str(alvo))
        realizado = Decimal(str(realizado))
        if realizado >= alvo:
            continue
        projetado = realizado / Decimal(decorridos) * Decimal(janela.dias)
        if projetado >= alvo * Decimal(str(LIMITE_PCT_META_RISCO)):
            continue
        falta = (alvo - realizado).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
        saida.append(
            SinalCandidato(
                regra="meta_em_risco",
                severidade="atencao",
                entidade_ref=str(meta.get("tipo") or ""),
                titulo=(
                    f"Faltam {dias_restantes} "
                    f"{_plural(dias_restantes, 'dia', 'dias')} e {_brl(falta)} "
                    "para bater a meta"
                ),
                detalhe=(
                    f"No ritmo atual o período fecha em {_brl(projetado)} "
                    f"de {_brl(alvo)}."
                ),
                dados={
                    "tipo": meta.get("tipo"),
                    "alvo": str(alvo.quantize(CENTAVOS)),
                    "realizado": str(realizado.quantize(CENTAVOS)),
                    "falta": str(falta),
                    "projetado": str(projetado.quantize(CENTAVOS)),
                    "dias_restantes": dias_restantes,
                },
            )
        )
    return saida


def regra_margem_incompleta(vendas: Any) -> list[SinalCandidato]:
    cobertura = getattr(vendas, "cobertura_margem", None)
    if cobertura is None or not cobertura.parcial:
        return []
    sem_custo = cobertura.total - cobertura.com_dado
    return [
        SinalCandidato(
            regra="margem_incompleta",
            severidade="atencao",
            titulo=(
                f"{sem_custo} de {cobertura.total} "
                f"{_plural(cobertura.total, 'venda', 'vendas')} sem custo informado"
            ),
            detalhe="Sua margem está subestimada enquanto o custo não entrar.",
            dados={
                "sem_custo": sem_custo,
                "com_custo": cobertura.com_dado,
                "total": cobertura.total,
            },
            acao_sugerida={"acao": "abrir", "href": "/app/loja/vendas/lista"},
        )
    ]


def regra_cadastro_incompleto(overview_estoque: Any) -> list[SinalCandidato]:
    total = int(getattr(overview_estoque, "total_lacunas", 0) or 0)
    if total <= 0:
        return []
    return [
        SinalCandidato(
            regra="cadastro_incompleto",
            severidade="info",
            titulo=(
                f"{total} {_plural(total, 'veículo', 'veículos')} "
                "com cadastro incompleto"
            ),
            detalhe="Falta foto ou dado obrigatório — some da vitrine e do bot.",
            dados={"total": total},
            acao_sugerida={"acao": "abrir", "href": "/app/loja/estoque"},
        )
    ]


def regra_atribuicao_baixa(
    origem: Any,
    *,
    minimo_vendas: int = 3,
    limite_pct: float = 30.0,
) -> list[SinalCandidato]:
    """Transforma a fraqueza da atribuição em produto (§4.2).

    Em vez de o buraco ficar invisível, o dono é avisado — e fechar a cadeia
    melhora o dado que sustenta o fosso do Revy.
    """
    cobertura = getattr(origem, "cobertura", None)
    if cobertura is None or cobertura.total < minimo_vendas:
        return []
    sem_origem = cobertura.total - cobertura.com_dado
    if sem_origem <= 0:
        return []
    pct = sem_origem / cobertura.total * 100
    if pct < limite_pct:
        return []
    return [
        SinalCandidato(
            regra="atribuicao_baixa",
            severidade="atencao",
            titulo=(
                f"{sem_origem} de {cobertura.total} vendas sem campanha de origem"
            ),
            detalhe="Seu ROI está incompleto: essas vendas não voltam para nenhum anúncio.",
            dados={
                "sem_origem": sem_origem,
                "com_origem": cobertura.com_dado,
                "total": cobertura.total,
                "pct_sem_origem": round(pct, 1),
            },
        )
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinais_regras.py -q`
Expected: PASS (15 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/sinais.py portal-gestao/tests/test_copiloto_sinais_regras.py
git commit -m "feat(copiloto): seis regras deterministicas de alerta proativo"
```

---

### Task 12: Persistência dos sinais — dedupe, cooldown e resolução automática

**Files:**
- Create: `portal-gestao/app/loja/copiloto/sinais_store.py`
- Test: `portal-gestao/tests/test_copiloto_sinais_store.py`

**Interfaces:**
- Consumes: `SinalCandidato` (Task 11), `app.models.CopilotoSinal` (Task 10).
- Produces:
  - `ResultadoSincronizacao(criados, atualizados, resolvidos, em_cooldown, dispensados_ignorados)` com `.resumo() -> str`;
  - `sincronizar_sinais(db, loja_slug, candidatos, *, agora=None, cooldown_horas=24) -> ResultadoSincronizacao`;
  - `listar_sinais_abertos(db, loja_slug, *, limite=20) -> list[CopilotoSinal]`;
  - `contar_sinais_novos(db, loja_slug) -> int`;
  - `marcar_visto(db, loja_slug, sinal_id) -> bool`;
  - `dispensar(db, loja_slug, sinal_id) -> bool`.

**As três regras anti-spam (§5):**
1. **Dedupe:** mesma `(regra, entidade_ref)` já aberta → atualiza texto, não cria segundo card.
2. **Dispensado não volta.** O dono já disse "não me incomode com isso".
3. **Resolvido fecha sozinho** quando a condição sai, e respeita `cooldown_horas` antes de poder reabrir.

**Escopo de loja em toda função:** `sinal_id` sozinho nunca basta — todo acesso filtra por `loja_slug` da sessão.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_sinais_store.py`:

```python
import json
from datetime import datetime, timedelta, timezone

from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import (
    contar_sinais_novos,
    dispensar,
    listar_sinais_abertos,
    marcar_visto,
    sincronizar_sinais,
)
from app.models import CopilotoSinal

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _cand(entidade="v1", titulo="Parada há 70 dias", regra="estoque_parado"):
    return SinalCandidato(
        regra=regra,
        severidade="atencao",
        titulo=titulo,
        detalhe="R$ 25.000,00 de capital preso.",
        entidade_ref=entidade,
        dados={"veiculo_id": entidade},
        acao_sugerida={"acao": "ajustar_preco", "veiculo_id": entidade},
    )


def test_cria_sinal_novo(db):
    r = sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    assert r.criados == 1
    sinal = db.query(CopilotoSinal).one()
    assert sinal.estado == "novo"
    assert json.loads(sinal.acao_sugerida_json)["acao"] == "ajustar_preco"


def test_segunda_passada_atualiza_em_vez_de_duplicar(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    r = sincronizar_sinais(
        db, "loja-teste", [_cand(titulo="Parada há 71 dias")],
        agora=AGORA + timedelta(days=1),
    )
    assert r.criados == 0
    assert r.atualizados == 1
    assert db.query(CopilotoSinal).count() == 1
    assert db.query(CopilotoSinal).one().titulo == "Parada há 71 dias"


def test_condicao_que_sai_resolve_o_sinal_sozinho(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    r = sincronizar_sinais(db, "loja-teste", [], agora=AGORA + timedelta(hours=1))
    assert r.resolvidos == 1
    sinal = db.query(CopilotoSinal).one()
    assert sinal.estado == "resolvido"
    assert sinal.resolvido_em is not None


def test_resolvido_nao_reabre_dentro_do_cooldown(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    sincronizar_sinais(db, "loja-teste", [], agora=AGORA + timedelta(hours=1))
    r = sincronizar_sinais(
        db, "loja-teste", [_cand()], agora=AGORA + timedelta(hours=2),
        cooldown_horas=24,
    )
    assert r.criados == 0
    assert r.em_cooldown == 1


def test_resolvido_reabre_depois_do_cooldown(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    sincronizar_sinais(db, "loja-teste", [], agora=AGORA + timedelta(hours=1))
    r = sincronizar_sinais(
        db, "loja-teste", [_cand()], agora=AGORA + timedelta(hours=30),
        cooldown_horas=24,
    )
    assert r.criados == 1


def test_dispensado_nunca_volta(db):
    sincronizar_sinais(db, "loja-teste", [_cand()], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert dispensar(db, "loja-teste", sinal.id) is True
    r = sincronizar_sinais(
        db, "loja-teste", [_cand()], agora=AGORA + timedelta(days=30)
    )
    assert r.criados == 0
    assert r.dispensados_ignorados == 1


def test_nao_mexe_em_sinal_de_outra_loja(db):
    sincronizar_sinais(db, "loja-a", [_cand()], agora=AGORA)
    r = sincronizar_sinais(db, "loja-b", [], agora=AGORA + timedelta(hours=1))
    assert r.resolvidos == 0
    assert db.query(CopilotoSinal).one().estado == "novo"


def test_dispensar_de_outra_loja_nao_funciona(db):
    sincronizar_sinais(db, "loja-a", [_cand()], agora=AGORA)
    sinal = db.query(CopilotoSinal).one()
    assert dispensar(db, "loja-b", sinal.id) is False
    assert db.query(CopilotoSinal).one().estado == "novo"


def test_listar_abertos_ignora_resolvido_e_dispensado(db):
    sincronizar_sinais(
        db, "loja-teste", [_cand("v1"), _cand("v2"), _cand("v3")], agora=AGORA
    )
    alvo = (
        db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "v2").one()
    )
    dispensar(db, "loja-teste", alvo.id)
    sincronizar_sinais(
        db, "loja-teste", [_cand("v1")], agora=AGORA + timedelta(hours=1)
    )
    abertos = listar_sinais_abertos(db, "loja-teste")
    assert [s.entidade_ref for s in abertos] == ["v1"]


def test_contador_de_novos_cai_quando_marca_visto(db):
    sincronizar_sinais(db, "loja-teste", [_cand("v1"), _cand("v2")], agora=AGORA)
    assert contar_sinais_novos(db, "loja-teste") == 2
    sinal = (
        db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "v1").one()
    )
    assert marcar_visto(db, "loja-teste", sinal.id) is True
    assert contar_sinais_novos(db, "loja-teste") == 1
    # Visto continua aberto na lista — só sai do contador.
    assert len(listar_sinais_abertos(db, "loja-teste")) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinais_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.sinais_store'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/sinais_store.py`:

```python
"""Persistência dos sinais: dedupe, cooldown, resolução automática.

Anti-spam em três regras:
1. mesma (regra, entidade_ref) já aberta → atualiza, não duplica;
2. dispensado NUNCA volta — o dono já disse que não quer;
3. resolvido fecha sozinho e respeita cooldown antes de poder reabrir.

Todo acesso filtra por ``loja_slug``: id de sinal sozinho nunca basta.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.loja.copiloto.sinais import SinalCandidato
from app.models import CopilotoSinal

ESTADOS_ABERTOS = ("novo", "visto")
COOLDOWN_PADRAO_HORAS = 24


@dataclass
class ResultadoSincronizacao:
    criados: int = 0
    atualizados: int = 0
    resolvidos: int = 0
    em_cooldown: int = 0
    dispensados_ignorados: int = 0

    def resumo(self) -> str:
        return (
            f"criados={self.criados} atualizados={self.atualizados} "
            f"resolvidos={self.resolvidos} cooldown={self.em_cooldown} "
            f"dispensados={self.dispensados_ignorados}"
        )


def _chave(regra: str, entidade_ref: str | None) -> tuple[str, str]:
    return (regra, entidade_ref or "")


def _aware(momento: datetime | None) -> datetime | None:
    if momento is None:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def sincronizar_sinais(
    db: Session,
    loja_slug: str,
    candidatos: Iterable[SinalCandidato],
    *,
    agora: datetime | None = None,
    cooldown_horas: int = COOLDOWN_PADRAO_HORAS,
) -> ResultadoSincronizacao:
    """Reconcilia os candidatos desta passada com o que já está gravado."""
    ref = agora or datetime.now(timezone.utc)
    resultado = ResultadoSincronizacao()

    candidatos = list(candidatos)
    por_chave = {_chave(c.regra, c.entidade_ref): c for c in candidatos}

    existentes = (
        db.query(CopilotoSinal).filter(CopilotoSinal.loja_slug == loja_slug).all()
    )
    indice: dict[tuple[str, str], list[CopilotoSinal]] = {}
    for linha in existentes:
        indice.setdefault(_chave(linha.regra, linha.entidade_ref), []).append(linha)

    # 1) Candidatos → cria, atualiza ou ignora.
    for chave, candidato in por_chave.items():
        linhas = indice.get(chave, [])
        aberto = next((l for l in linhas if l.estado in ESTADOS_ABERTOS), None)
        if aberto is not None:
            aberto.severidade = candidato.severidade
            aberto.titulo = candidato.titulo
            aberto.detalhe = candidato.detalhe
            aberto.dados_json = json.dumps(candidato.dados, ensure_ascii=False)
            aberto.acao_sugerida_json = (
                json.dumps(candidato.acao_sugerida, ensure_ascii=False)
                if candidato.acao_sugerida
                else None
            )
            aberto.atualizado_em = ref
            resultado.atualizados += 1
            continue

        if any(l.estado == "dispensado" for l in linhas):
            resultado.dispensados_ignorados += 1
            continue

        resolvidos = [l for l in linhas if l.estado == "resolvido"]
        if resolvidos:
            ultimo = max(
                resolvidos,
                key=lambda l: _aware(l.resolvido_em) or _aware(l.criado_em) or ref,
            )
            marco = _aware(ultimo.resolvido_em) or _aware(ultimo.criado_em)
            if marco is not None and ref - marco < timedelta(hours=cooldown_horas):
                resultado.em_cooldown += 1
                continue

        db.add(
            CopilotoSinal(
                loja_slug=loja_slug,
                regra=candidato.regra,
                entidade_ref=candidato.entidade_ref,
                severidade=candidato.severidade,
                titulo=candidato.titulo,
                detalhe=candidato.detalhe,
                dados_json=json.dumps(candidato.dados, ensure_ascii=False),
                acao_sugerida_json=(
                    json.dumps(candidato.acao_sugerida, ensure_ascii=False)
                    if candidato.acao_sugerida
                    else None
                ),
                estado="novo",
                criado_em=ref,
                atualizado_em=ref,
            )
        )
        resultado.criados += 1

    # 2) Abertos sem candidato correspondente → a condição saiu.
    for chave, linhas in indice.items():
        if chave in por_chave:
            continue
        for linha in linhas:
            if linha.estado not in ESTADOS_ABERTOS:
                continue
            linha.estado = "resolvido"
            linha.resolvido_em = ref
            linha.atualizado_em = ref
            resultado.resolvidos += 1

    db.commit()
    return resultado


def listar_sinais_abertos(
    db: Session, loja_slug: str, *, limite: int = 20
) -> list[CopilotoSinal]:
    ordem = {"critico": 0, "atencao": 1, "info": 2}
    linhas = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == loja_slug,
            CopilotoSinal.estado.in_(ESTADOS_ABERTOS),
        )
        .all()
    )
    linhas.sort(
        key=lambda s: (
            ordem.get(s.severidade, 9),
            -(_aware(s.criado_em) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        )
    )
    return linhas[: max(1, limite)]


def contar_sinais_novos(db: Session, loja_slug: str) -> int:
    return (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == loja_slug,
            CopilotoSinal.estado == "novo",
        )
        .count()
    )


def _transicionar(
    db: Session, loja_slug: str, sinal_id: str, estado: str
) -> bool:
    sinal = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.id == sinal_id,
            CopilotoSinal.loja_slug == loja_slug,
        )
        .first()
    )
    if sinal is None or sinal.estado not in ESTADOS_ABERTOS:
        return False
    agora_utc = datetime.now(timezone.utc)
    sinal.estado = estado
    sinal.atualizado_em = agora_utc
    if estado == "dispensado":
        sinal.dispensado_em = agora_utc
    db.commit()
    return True


def marcar_visto(db: Session, loja_slug: str, sinal_id: str) -> bool:
    return _transicionar(db, loja_slug, sinal_id, "visto")


def dispensar(db: Session, loja_slug: str, sinal_id: str) -> bool:
    return _transicionar(db, loja_slug, sinal_id, "dispensado")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinais_store.py -q`
Expected: PASS (10 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/sinais_store.py portal-gestao/tests/test_copiloto_sinais_store.py
git commit -m "feat(copiloto): store de sinais com dedupe, cooldown e resolucao automatica"
```

---

### Task 13: Worker do motor proativo

**Files:**
- Create: `portal-gestao/app/copiloto_sinais_job.py`
- Modify: `portal-gestao/app/main.py` (lifespan `:332-347`)
- Modify: `portal-gestao/tests/conftest.py` (desligar o worker nos testes)
- Test: `portal-gestao/tests/test_copiloto_sinais_job.py`

**Interfaces:**
- Consumes: `sincronizar_sinais` (Task 12), todas as regras (Task 11), todas as consultas (Tasks 4–8), `cache_overview` (Task 9), `build_sales_overview`.
- Produces:
  - `avaliar_loja(db, loja_slug, *, estoque, chatbot, agora=None) -> list[SinalCandidato]`;
  - `CopilotoSinaisWorker` (`start`, `stop`, `run_once`, `last_result`);
  - `start_worker(db_factory)`, `stop_worker()`, `get_worker()`.

**Padrão obrigatório:** cópia estrutural de `app/meta_ads_spend_job.py:41-166` — `threading.Thread` daemon, `threading.Event` para parar, `run_once()` síncrono e testável, `start_worker/stop_worker` module-level. Ciclo de vida no lifespan (`app/main.py:332-347`).

**Env novas:** `PORTAL_COPILOTO_SINAIS_ENABLED` (default `1`, mas **só roda se `REVY_LOJA_COPILOTO_ENABLED=1`**), `PORTAL_COPILOTO_SINAIS_INTERVAL_SECONDS` (default `1800`), `PORTAL_COPILOTO_SINAIS_INITIAL_DELAY_SECONDS` (default `60`).

**Uma passada por loja habilitada.** Lojas = `loja_slug` distintos em `LojaOperacionalProjecao` com `state="ativa"`.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_sinais_job.py`:

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from conftest import seed_loja_operacional

from app.copiloto_sinais_job import CopilotoSinaisWorker, avaliar_loja
from app.db import SessionLocal
from app.models import CopilotoSinal, Venda

AGORA = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class EstoqueStub:
    def __init__(self, veiculos=None, slug="loja-teste"):
        self.veiculos = veiculos if veiculos is not None else []
        self.slug = slug

    def obter_loja(self):
        return {"slug": self.slug}

    def listar(self, **filtros):
        return list(self.veiculos)


class ChatbotStub:
    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        return []

    def listar_leads(self, etapa=None):
        return []


def _veiculo_parado(dias=90):
    return {
        "id": "v1",
        "marca": "Honda",
        "modelo": "CB 500F",
        "ano_modelo": 2020,
        "preco": 25000.0,
        "status": "disponivel",
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        "tem_foto": True,
    }


def test_avaliar_loja_gera_candidato_de_estoque_parado(db):
    seed_loja_operacional(db)
    db.commit()
    candidatos = avaliar_loja(
        db,
        "loja-teste",
        estoque=EstoqueStub([_veiculo_parado()]),
        chatbot=ChatbotStub(),
        agora=AGORA,
    )
    regras = {c.regra for c in candidatos}
    assert "estoque_parado" in regras


def test_avaliar_loja_gera_margem_incompleta(db):
    seed_loja_operacional(db)
    for i in range(4):
        db.add(
            Venda(
                loja_slug="loja-teste",
                vendedor_email="ana@loja.test",
                descricao="Moto",
                preco_venda=Decimal("20000"),
                custo_veiculo=Decimal("16000") if i == 0 else None,
                status="confirmada",
                criada_em=AGORA - timedelta(days=2),
            )
        )
    db.commit()
    candidatos = avaliar_loja(
        db, "loja-teste", estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    regras = {c.regra for c in candidatos}
    assert "margem_incompleta" in regras
    assert "atribuicao_baixa" in regras


def test_run_once_persiste_sinais_da_loja_ativa(db):
    seed_loja_operacional(db)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["lojas"] == 1
    assert db.query(CopilotoSinal).filter(CopilotoSinal.regra == "estoque_parado").count() == 1


def test_run_once_desligado_nao_toca_o_banco(db):
    seed_loja_operacional(db)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=False,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    assert worker.run_once()["ok"] is False
    assert db.query(CopilotoSinal).count() == 0


def test_loja_inativa_nao_e_avaliada(db):
    seed_loja_operacional(db, loja_slug="loja-teste", state="suspensa", version=2)
    db.commit()
    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueStub([_veiculo_parado()]),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    assert worker.run_once()["lojas"] == 0
    assert db.query(CopilotoSinal).count() == 0


def test_falha_em_uma_loja_nao_derruba_o_ciclo(db):
    seed_loja_operacional(db, loja_slug="loja-teste")
    seed_loja_operacional(db, loja_slug="loja-2")
    db.commit()

    class EstoqueQuebrado(EstoqueStub):
        def listar(self, **filtros):
            raise RuntimeError("boom")

    worker = CopilotoSinaisWorker(
        db_factory=SessionLocal,
        enabled=True,
        estoque_factory=lambda: EstoqueQuebrado(slug="loja-teste"),
        chatbot_factory=lambda: ChatbotStub(),
        agora=lambda: AGORA,
    )
    resultado = worker.run_once()
    assert resultado["ok"] is True
    assert resultado["erros"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinais_job.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.copiloto_sinais_job'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/copiloto_sinais_job.py`:

```python
"""Motor proativo do Copiloto: roda as regras por loja e grava os sinais.

Molde estrutural: ``app/meta_ads_spend_job.py`` (thread daemon + Event +
``run_once`` síncrono). Nada de LLM aqui — é regra determinística, e é isso que
mantém o alerta funcionando com o provedor de IA fora do ar.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.config import revy_loja_copiloto_enabled
from app.loja.copiloto.consultas_estoque import estoque_parado
from app.loja.copiloto.consultas_leads import leads_status
from app.loja.copiloto.consultas_origem import venda_origem_periodo
from app.loja.copiloto.consultas_vendas import vendas_resumo
from app.loja.copiloto.periodo import janela_do_periodo
from app.loja.copiloto.sinais import (
    SinalCandidato,
    regra_atribuicao_baixa,
    regra_cadastro_incompleto,
    regra_estoque_parado,
    regra_lead_sem_resposta,
    regra_margem_incompleta,
    regra_meta_em_risco,
)
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.loja.copiloto.tipos import CopilotoContexto
from app.loja.estoque_overview import montar_estoque_overview
from app.meta_ads_spend_job import env_flag, env_float
from app.models import LojaOperacionalProjecao

logger = logging.getLogger(__name__)

DIAS_ESTOQUE_PARADO = 60
HORAS_LEAD_SEM_RESPOSTA = 4


def lojas_ativas(db: Session) -> list[str]:
    linhas = (
        db.query(LojaOperacionalProjecao.loja_slug)
        .filter(
            LojaOperacionalProjecao.aggregate == "loja",
            LojaOperacionalProjecao.state == "ativa",
        )
        .all()
    )
    return sorted({linha[0] for linha in linhas})


def avaliar_loja(
    db: Session,
    loja_slug: str,
    *,
    estoque,
    chatbot,
    agora: datetime | None = None,
) -> list[SinalCandidato]:
    """Roda as 6 regras da loja e devolve os candidatos desta passada."""
    ref = agora or datetime.now(timezone.utc)
    ctx = CopilotoContexto(
        loja_slug=loja_slug,
        papel="dono",  # motor roda no escopo da loja, não de uma pessoa
        ator_email="sistema@copiloto",
        hoje=ref.date(),
    )
    janela = janela_do_periodo(None, None)

    candidatos: list[SinalCandidato] = []

    parado = estoque_parado(
        estoque, ctx, dias_min=DIAS_ESTOQUE_PARADO, agora=ref, limite=50
    )
    candidatos.extend(regra_estoque_parado(parado))

    try:
        veiculos = estoque.listar()
    except Exception:
        veiculos = None
    if veiculos is not None:
        candidatos.extend(
            regra_cadastro_incompleto(montar_estoque_overview(veiculos, agora=ref))
        )

    vendas = vendas_resumo(db, ctx, inicio=None, fim=None)
    candidatos.extend(regra_margem_incompleta(vendas))

    from app.financeiro_calc import metas_view_periodo
    from decimal import Decimal

    metas = metas_view_periodo(
        db,
        loja_slug,
        janela.inicio,
        janela.fim,
        {
            "quantidade": Decimal(vendas.qtd_vendas),
            "faturamento": vendas.receita,
            "lucro_bruto": vendas.margem or Decimal("0"),
        },
        vendas.cobertura_margem.completa,
    )
    candidatos.extend(regra_meta_em_risco(metas, janela, hoje=ref.date()))

    origem = venda_origem_periodo(db, ctx, inicio=None, fim=None)
    candidatos.extend(regra_atribuicao_baixa(origem))

    from app.loja.sales_overview import build_sales_overview

    try:
        overview = build_sales_overview(
            db, loja_slug=loja_slug, papel="dono", chatbot=chatbot
        )
    except Exception:
        overview = None
    if overview is not None:
        candidatos.extend(
            regra_lead_sem_resposta(
                leads_status(
                    overview,
                    chatbot,
                    ctx=ctx,
                    agora=ref,
                    horas_sem_resposta=HORAS_LEAD_SEM_RESPOSTA,
                )
            )
        )

    return candidatos


class CopilotoSinaisWorker:
    """Thread daemon que avalia as regras por loja em intervalo fixo."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Session],
        interval_seconds: float | None = None,
        initial_delay_seconds: float | None = None,
        enabled: bool | None = None,
        estoque_factory: Callable[[], object] | None = None,
        chatbot_factory: Callable[[], object] | None = None,
        agora: Callable[[], datetime] | None = None,
    ):
        self.db_factory = db_factory
        self.interval = float(
            interval_seconds
            if interval_seconds is not None
            else env_float("PORTAL_COPILOTO_SINAIS_INTERVAL_SECONDS", 1800.0)
        )
        self.initial_delay = float(
            initial_delay_seconds
            if initial_delay_seconds is not None
            else env_float("PORTAL_COPILOTO_SINAIS_INITIAL_DELAY_SECONDS", 60.0)
        )
        # Duas chaves diferentes, de propósito:
        #  - `enabled` é o interruptor do PROCESSO (roda worker aqui?), snapshot no boot;
        #  - a flag de produto `REVY_LOJA_COPILOTO_ENABLED` é lida A CADA CICLO, igual às
        #    rotas. Snapshotá-la aqui criaria o descasamento "rota abre, worker dorme".
        # `enabled=` explícito é decisão já tomada pelo chamador (testes): vale sozinho.
        self._gate_flag = enabled is None
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = env_flag("PORTAL_COPILOTO_SINAIS_ENABLED", True)
        self._estoque_factory = estoque_factory
        self._chatbot_factory = chatbot_factory
        self._agora = agora or (lambda: datetime.now(timezone.utc))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_result: dict | None = None

    def _clients(self):
        if self._estoque_factory and self._chatbot_factory:
            return self._estoque_factory(), self._chatbot_factory()
        from app.main import get_chatbot_client, get_estoque_client

        return get_estoque_client(), get_chatbot_client()

    def start(self) -> None:
        if not self.enabled:
            logger.info("copiloto_sinais_job: desligado")
            return
        if self.interval <= 0 or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="copiloto-sinais", daemon=True
        )
        self._thread.start()
        logger.info("copiloto_sinais_job: iniciado interval=%ss", self.interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None

    def _ligado(self) -> bool:
        if not self.enabled:
            return False
        return revy_loja_copiloto_enabled() if self._gate_flag else True

    def run_once(self) -> dict:
        if not self._ligado():
            payload = {"ok": False, "motivo": "desligado", "lojas": 0, "erros": 0}
            self.last_result = payload
            return payload

        ref = self._agora()
        db = self.db_factory()
        lojas = 0
        erros = 0
        try:
            estoque, chatbot = self._clients()
            for loja_slug in lojas_ativas(db):
                try:
                    candidatos = avaliar_loja(
                        db, loja_slug, estoque=estoque, chatbot=chatbot, agora=ref
                    )
                    resultado = sincronizar_sinais(
                        db, loja_slug, candidatos, agora=ref
                    )
                    lojas += 1
                    logger.info(
                        "copiloto_sinais_job loja=%s %s", loja_slug, resultado.resumo()
                    )
                except Exception as exc:
                    # Uma loja quebrada não pode derrubar o ciclo das outras.
                    db.rollback()
                    erros += 1
                    logger.warning(
                        "copiloto_sinais_job: falha loja=%s tipo=%s",
                        loja_slug,
                        type(exc).__name__,
                    )
            payload = {"ok": True, "lojas": lojas, "erros": erros}
        except Exception as exc:
            payload = {"ok": False, "erro": type(exc).__name__, "lojas": lojas, "erros": erros}
        finally:
            db.close()
        self.last_result = payload
        return payload

    def _run(self) -> None:
        if self.initial_delay > 0 and self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval):
                break


_worker: CopilotoSinaisWorker | None = None


def get_worker() -> CopilotoSinaisWorker | None:
    return _worker


def start_worker(db_factory: Callable[[], Session]) -> CopilotoSinaisWorker | None:
    global _worker
    if _worker is not None:
        return _worker
    _worker = CopilotoSinaisWorker(db_factory=db_factory)
    _worker.start()
    return _worker


def stop_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
```

Em `app/main.py`, importar junto dos outros jobs e ligar no lifespan:

```python
from app import copiloto_sinais_job  # junto dos demais imports de job
```

```python
@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Em testes (PORTAL_SKIP_INIT / pytest) o job fica off via env no conftest.
    if os.getenv("PORTAL_SKIP_INIT") != "1":
        meta_ads_spend_job.start_worker(SessionLocal)
        meta_capi_job.start_worker(SessionLocal)
        revy_trafego_outbox_job.start_worker(
            SessionLocal,
            enabled=settings.revy_trafego_venda_events_enabled,
        )
        copiloto_sinais_job.start_worker(SessionLocal)
    try:
        yield
    finally:
        meta_ads_spend_job.stop_worker()
        meta_capi_job.stop_worker()
        revy_trafego_outbox_job.stop_worker()
        copiloto_sinais_job.stop_worker()
```

Em `tests/conftest.py`, junto das outras env de teste (antes dos imports de `app`):

```python
os.environ["PORTAL_COPILOTO_SINAIS_ENABLED"] = "0"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinais_job.py -q`
Expected: PASS (6 testes).

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS — o worker novo não pode alterar a suíte existente (fica off no conftest).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/copiloto_sinais_job.py portal-gestao/app/main.py portal-gestao/tests/conftest.py portal-gestao/tests/test_copiloto_sinais_job.py
git commit -m "feat(copiloto): worker do motor proativo de alertas"
```

---

### Task 14: "Resumo de hoje" determinístico + chips vivos

**Files:**
- Create: `portal-gestao/app/loja/copiloto/resumo.py`
- Test: `portal-gestao/tests/test_copiloto_resumo.py`

**Interfaces:**
- Consumes: `vendas_resumo`, `ranking_vendedores`, `venda_origem_ultima`, `estoque_parado`, `leads_status`, `build_sales_overview`, `cache_overview`/`chave_overview`.
- Produces: `ResumoHoje` (`gerado_em`, `janela`, `vendas`, `ranking`, `origem_ultima`, `parado`, `leads`, `chips`, `to_dict()`) e `montar_resumo_hoje(db, ctx, *, estoque, chatbot, agora=None) -> ResumoHoje`; `Chip(texto, pergunta)`.

**Por que sem LLM (§7):** este é o caminho mais usado da tela. Tirar o modelo daqui zera alucinação no lugar de maior tráfego, mantém o botão funcionando quando o provedor cai, e não gasta token. Os **chips de sugestão** são gerados do dado real ("3 motos paradas +60d"), não fixos — resolvem o chat em branco de graça.

**Degradação por bloco:** cada bloco carrega o próprio status. Uma fonte fora não pode zerar as outras.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_resumo.py`:

```python
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.clients.chatbot import ChatbotIndisponivel
from app.clients.estoque import EstoqueIndisponivel
from app.loja.copiloto.resumo import montar_resumo_hoje
from app.loja.copiloto.tipos import CopilotoContexto
from app.models import Venda

AGORA = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _ctx():
    return CopilotoContexto(
        loja_slug="loja-teste",
        papel="dono",
        ator_email="dono@loja.test",
        hoje=date(2026, 8, 11),
    )


class EstoqueStub:
    def __init__(self, veiculos=None, indisponivel=False):
        self.veiculos = veiculos or []
        self.indisponivel = indisponivel

    def obter_loja(self):
        if self.indisponivel:
            raise EstoqueIndisponivel("fora")
        return {"slug": "loja-teste"}

    def listar(self, **filtros):
        if self.indisponivel:
            raise EstoqueIndisponivel("fora")
        return list(self.veiculos)


class ChatbotStub:
    def __init__(self, indisponivel=False):
        self.indisponivel = indisponivel

    def listar_conversas(self, busca=None, limit=50, offset=0, *, canal_id=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("fora")
        return []

    def listar_leads(self, etapa=None):
        if self.indisponivel:
            raise ChatbotIndisponivel("fora")
        return []


def _parado(dias=90):
    return {
        "id": "v1",
        "marca": "Honda",
        "modelo": "CB 500F",
        "preco": 25000.0,
        "status": "disponivel",
        "criado_em": (AGORA - timedelta(days=dias)).isoformat(),
        "tem_foto": True,
    }


def _venda(db, preco=30000):
    db.add(
        Venda(
            loja_slug="loja-teste",
            vendedor_email="ana@loja.test",
            descricao="Honda CB 500F 2020",
            preco_venda=Decimal(str(preco)),
            status="confirmada",
            criada_em=AGORA - timedelta(days=2),
        )
    )
    db.commit()


def test_resumo_traz_os_cinco_blocos(db):
    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub([_parado()]), chatbot=ChatbotStub(), agora=AGORA
    )
    assert r.vendas.qtd_vendas == 1
    assert r.ranking.status == "ok"
    assert r.origem_ultima.status == "ok"
    assert r.parado.total == 1
    assert r.leads is not None
    assert r.janela.rotulo == "agosto/2026"


def test_estoque_fora_nao_derruba_vendas(db):
    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub(indisponivel=True), chatbot=ChatbotStub(),
        agora=AGORA,
    )
    assert r.parado.status == "indisponivel"
    assert r.vendas.status == "ok"
    assert r.vendas.qtd_vendas == 1


def test_chip_de_estoque_parado_usa_numero_real(db):
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub([_parado()]), chatbot=ChatbotStub(), agora=AGORA
    )
    textos = [chip.texto for chip in r.chips]
    assert any("1 " in t and "parad" in t.lower() for t in textos)


def test_chip_de_origem_aparece_quando_ha_venda(db):
    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    perguntas = [chip.pergunta for chip in r.chips]
    assert any("última venda" in p.lower() for p in perguntas)


def test_sem_dado_nenhum_ainda_devolve_chips_base(db):
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub(), chatbot=ChatbotStub(), agora=AGORA
    )
    assert len(r.chips) >= 1


def test_to_dict_e_serializavel(db):
    import json

    _venda(db)
    r = montar_resumo_hoje(
        db, _ctx(), estoque=EstoqueStub([_parado()]), chatbot=ChatbotStub(), agora=AGORA
    )
    assert json.dumps(r.to_dict())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_resumo.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.loja.copiloto.resumo'`.

- [ ] **Step 3: Write minimal implementation**

Criar `portal-gestao/app/loja/copiloto/resumo.py`:

```python
"""Resumo de hoje — determinístico, sem LLM.

É o caminho mais usado da seção. Tirar o modelo daqui zera alucinação no lugar
de maior tráfego, mantém o botão de pé quando o provedor de IA cai e não gasta
token nenhum.

Os chips de sugestão saem do dado real ("3 motos paradas +60d"), não de uma
lista fixa — resolvem o chat em branco de graça.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.loja.copiloto.cache import cache_overview, chave_overview
from app.loja.copiloto.consultas_estoque import estoque_parado
from app.loja.copiloto.consultas_leads import LeadsStatus, leads_status
from app.loja.copiloto.consultas_origem import venda_origem_ultima
from app.loja.copiloto.consultas_vendas import ranking_vendedores, vendas_resumo
from app.loja.copiloto.periodo import Janela, janela_do_periodo
from app.loja.copiloto.tipos import CopilotoContexto

DIAS_PARADO_RESUMO = 60
TOP_RANKING = 3


@dataclass(frozen=True)
class Chip:
    """Sugestão viva: o texto é o que aparece, a pergunta é o que vai ao chat."""

    texto: str
    pergunta: str

    def to_dict(self) -> dict[str, str]:
        return {"texto": self.texto, "pergunta": self.pergunta}


@dataclass(frozen=True)
class ResumoHoje:
    gerado_em: str
    janela: Janela
    vendas: Any
    ranking: Any
    origem_ultima: Any
    parado: Any
    leads: LeadsStatus | None
    chips: tuple[Chip, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gerado_em": self.gerado_em,
            "periodo": self.janela.to_dict(),
            "vendas": self.vendas.to_dict(),
            "ranking": self.ranking.to_dict(),
            "origem_ultima": self.origem_ultima.to_dict(),
            "estoque_parado": self.parado.to_dict(),
            "leads": self.leads.to_dict() if self.leads else None,
            "chips": [c.to_dict() for c in self.chips],
        }


def _overview_cacheado(db: Session, ctx: CopilotoContexto, chatbot: Any):
    """Fan-out caro atrás do cache TTL (§3.5)."""
    from app.loja.sales_overview import build_sales_overview

    chave = chave_overview(ctx.loja_slug, ctx.papel, None, None)

    def _produzir():
        try:
            return build_sales_overview(
                db, loja_slug=ctx.loja_slug, papel=ctx.papel, chatbot=chatbot
            )
        except Exception:
            return None

    return cache_overview.obter(chave, _produzir)


def _chips(vendas: Any, parado: Any, leads: LeadsStatus | None) -> tuple[Chip, ...]:
    chips: list[Chip] = []

    if vendas.qtd_vendas:
        chips.append(
            Chip(
                texto="De onde veio a última venda",
                pergunta="De onde veio a última moto que eu vendi?",
            )
        )
    if getattr(parado, "total", None):
        n = parado.total
        chips.append(
            Chip(
                texto=f"{n} parada{'s' if n != 1 else ''} +{parado.dias_min}d",
                pergunta=(
                    f"Quais veículos estão parados há mais de {parado.dias_min} dias "
                    "e quanto de capital está preso neles?"
                ),
            )
        )
    if leads is not None and leads.sem_resposta:
        chips.append(
            Chip(
                texto=f"{leads.sem_resposta} sem resposta",
                pergunta="Quantos leads ninguém respondeu e há quanto tempo?",
            )
        )
    if vendas.cobertura_margem.parcial:
        faltam = vendas.cobertura_margem.total - vendas.cobertura_margem.com_dado
        chips.append(
            Chip(
                texto=f"{faltam} venda(s) sem custo",
                pergunta="Quais vendas estão sem custo informado?",
            )
        )

    # Base: a tela nunca fica sem sugestão, mesmo em loja recém-criada.
    chips.append(
        Chip(texto="Resultado do mês", pergunta="Como foi meu mês vs. o mês passado?")
    )
    return tuple(chips[:5])


def montar_resumo_hoje(
    db: Session,
    ctx: CopilotoContexto,
    *,
    estoque: Any,
    chatbot: Any,
    agora: datetime | None = None,
) -> ResumoHoje:
    """Conjunto fixo de leituras + view-model. Nenhuma chamada de LLM."""
    ref = agora or datetime.now(timezone.utc)
    janela = janela_do_periodo(None, None)

    vendas = vendas_resumo(db, ctx)
    ranking = ranking_vendedores(db, ctx, limite=TOP_RANKING)
    origem = venda_origem_ultima(db, ctx)
    parado = estoque_parado(estoque, ctx, dias_min=DIAS_PARADO_RESUMO, agora=ref)

    overview = _overview_cacheado(db, ctx, chatbot)
    leads = (
        leads_status(overview, chatbot, ctx=ctx, agora=ref)
        if overview is not None
        else None
    )

    return ResumoHoje(
        gerado_em=ref.isoformat(),
        janela=janela,
        vendas=vendas,
        ranking=ranking,
        origem_ultima=origem,
        parado=parado,
        leads=leads,
        chips=_chips(vendas, parado, leads),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_resumo.py -q`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/resumo.py portal-gestao/tests/test_copiloto_resumo.py
git commit -m "feat(copiloto): resumo de hoje deterministico com chips vivos"
```

---

### Task 15: Seção "Copiloto" no shell — rota, nav, rename e tela

**Files:**
- Create: `portal-gestao/app/web/loja_copiloto.py`
- Create: `portal-gestao/app/templates/loja/copiloto.html`
- Modify: `portal-gestao/app/loja/navigation.py`
- Modify: `portal-gestao/app/templates/base.html` (dict `loja_icons`, `:49-64`)
- Modify: `portal-gestao/app/main.py` (`include_router`, junto de `:2365-2371`)
- Modify: `portal-gestao/tests/test_loja_navigation.py`
- Test: `portal-gestao/tests/test_copiloto_pagina.py`

**Interfaces:**
- Consumes: `montar_resumo_hoje` (Task 14), `listar_sinais_abertos`/`contar_sinais_novos`/`marcar_visto`/`dispensar` (Task 12), `revy_loja_copiloto_enabled` (Task 1).
- Produces: rotas `GET /app/loja/copiloto`, `POST /app/loja/copiloto/sinais/{sinal_id}/visto`, `POST /app/loja/copiloto/sinais/{sinal_id}/dispensar`; `build_nav(..., copiloto_enabled: bool | None = None)`.

**Três decisões que este task fecha:**
1. **Posição da seção:** "Copiloto" é a **primeira** seção do nav — é a tela de "o que fazer hoje", que o design (§1) coloca acima do "mostrar número". Só aparece com flag + entitlement + papel de gestão, então lojas sem o módulo veem o nav de hoje, intacto.
2. **Gate off = 404** (`JSONResponse`, molde de `loja_vendas.py:51-52`). O design (§9) apontou a incoerência entre `_flag_off_response` (404) e `RedirectResponse(303)` nos `loja_*`; aqui a escolha é 404, porque com a flag off a seção **não existe**.
3. **Renomeação junto:** `NavItem(label="Agente")` (`navigation.py:77`) vira **"Agente do WhatsApp"**. Rota, template e conteúdo ficam onde estão — só o rótulo muda.

**Invariantes que esta seção quebra de propósito** (registrar, para não virar bug reportado):
- `navigation.py:1` diz "somente Vendas e Estoque" — o docstring muda.
- `README-COMERCIAL.md` diz que IA não aparece como área principal separada — **superado** por decisão do dono de 2026-08-11.

- [ ] **Step 1: Write the failing test**

Criar `portal-gestao/tests/test_copiloto_pagina.py`:

```python
from conftest import csrf_da_resposta, login

from app.db import SessionLocal
from app.loja.copiloto.sinais import SinalCandidato
from app.loja.copiloto.sinais_store import sincronizar_sinais
from app.models import CopilotoSinal


def _ligar(monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_ENTITLEMENTS_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")


def _semear_sinal(loja="loja-teste"):
    db = SessionLocal()
    try:
        sincronizar_sinais(
            db,
            loja,
            [
                SinalCandidato(
                    regra="estoque_parado",
                    severidade="atencao",
                    titulo="Honda CB 500F parada há 70 dias",
                    detalhe="R$ 25.000,00 de capital preso.",
                    entidade_ref="v1",
                    dados={"veiculo_id": "v1"},
                )
            ],
        )
        return db.query(CopilotoSinal).one().id
    finally:
        db.close()


def test_flag_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "1")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "0")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404


def test_shell_off_retorna_404(client, monkeypatch):
    monkeypatch.setenv("REVY_LOJA_SHELL_ENABLED", "0")
    monkeypatch.setenv("REVY_LOJA_COPILOTO_ENABLED", "1")
    login(client)
    assert client.get("/app/loja/copiloto", follow_redirects=False).status_code == 404


def test_vendedor_recebe_403(client, monkeypatch):
    _ligar(monkeypatch)
    login(client, papel="vendedor", email="v@loja.test")
    assert client.get("/app/loja/copiloto").status_code == 403


def test_dono_abre_a_pagina_com_resumo(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app/loja/copiloto")
    assert r.status_code == 200
    assert "Copiloto de Vendas" in r.text
    assert "Resumo de hoje" in r.text


def test_pagina_lista_o_sinal_aberto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    _semear_sinal()
    r = client.get("/app/loja/copiloto")
    assert "Honda CB 500F parada há 70 dias" in r.text


def test_nav_mostra_a_secao_copiloto(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    r = client.get("/app")
    assert 'href="/app/loja/copiloto"' in r.text
    assert "Agente do WhatsApp" in r.text


def test_dispensar_sinal_exige_csrf(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": "invalido"},
        follow_redirects=False,
    )
    assert r.status_code in (303, 403)
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()


def test_dispensar_sinal_com_csrf_valido(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal()
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "dispensado"
    finally:
        db.close()


def test_sinal_de_outra_loja_nao_e_dispensavel(client, monkeypatch):
    _ligar(monkeypatch)
    login(client)
    sinal_id = _semear_sinal(loja="outra-loja")
    pagina = client.get("/app/loja/copiloto")
    r = client.post(
        f"/app/loja/copiloto/sinais/{sinal_id}/dispensar",
        data={"csrf": csrf_da_resposta(pagina)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.query(CopilotoSinal).one().estado == "novo"
    finally:
        db.close()
```

Editar `portal-gestao/tests/test_loja_navigation.py`: em `test_nav_somente_vendas_e_estoque_com_acessos_bancarios`, trocar `"Agente",` por `"Agente do WhatsApp",` na lista `labels`. E acrescentar ao fim do arquivo:

```python
def test_nav_sem_copiloto_quando_entitlement_falta():
    """Copiloto é módulo contratável: sem entitlement, não aparece."""
    sections = build_nav(_store(), _ents(), shell_enabled=True, copiloto_enabled=True)
    assert "Copiloto" not in [s.title for s in sections]


def test_nav_copiloto_e_a_primeira_secao_quando_liberado():
    ents = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
        copiloto_enabled=True,
    )
    sections = build_nav(_store(), ents, shell_enabled=True, copiloto_enabled=True)
    assert [s.title for s in sections][0] == "Copiloto"
    labels = [i.label for i in flatten_nav(sections)]
    assert labels[0] == "Copiloto de Vendas"


def test_nav_copiloto_nao_aparece_para_vendedor():
    ents = EntitlementState(
        loja_slug="loja-teste",
        loja_ativa=True,
        vendas_enabled=True,
        estoque_enabled=True,
        source="test",
        copiloto_enabled=True,
    )
    sections = build_nav(
        _store(roles=("vendedor",)), ents, shell_enabled=True, copiloto_enabled=True
    )
    assert "Copiloto" not in [s.title for s in sections]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_pagina.py tests/test_loja_navigation.py -q`
Expected: FAIL — `404` na página do Copiloto e `TypeError: build_nav() got an unexpected keyword argument 'copiloto_enabled'`.

- [ ] **Step 3: Write minimal implementation**

**(a)** `app/loja/navigation.py` — trocar o docstring da linha 1:

```python
"""Navegação permitida do shell Revy Loja (Copiloto, Vendas e Estoque).

Copiloto entrou em 2026-08-11 por decisão do dono e é a primeira seção: a
tela de "o que fazer hoje" vem antes das telas de "quanto deu".
"""
```

Trocar a assinatura e o rótulo do agente:

```python
def build_nav(
    store: StoreContext,
    entitlements: EntitlementState,
    *,
    shell_enabled: bool = True,
    whatsapp_enabled: bool | None = None,
    copiloto_enabled: bool | None = None,
) -> tuple[NavSection, ...]:
```

Logo depois do bloco `if whatsapp_enabled is None:`:

```python
    if copiloto_enabled is None:
        copiloto_enabled = revy_loja_copiloto_enabled()
```

(e no import do topo: `from app.config import revy_loja_copiloto_enabled, revy_loja_whatsapp_enabled`)

Depois de `sections: list[NavSection] = []`, **antes** do bloco de Vendas:

```python
    # Copiloto: só dono/gerente, só com flag + entitlement do módulo.
    if (
        copiloto_enabled
        and entitlements.copiloto_enabled
        and entitlements.loja_ativa
        and roles & ROLES_GESTAO
    ):
        sections.append(
            NavSection(
                title="Copiloto",
                items=(
                    NavItem(
                        label="Copiloto de Vendas",
                        href="/app/loja/copiloto",
                        section="Copiloto",
                        module=Module.COPILOTO.value,
                        active_prefix="/app/loja/copiloto",
                    ),
                ),
            )
        )
```

E dentro da seção Vendas, trocar `label="Agente"` por `label="Agente do WhatsApp"`.

**(b)** `app/templates/base.html` — acrescentar ao dict `loja_icons` (senão `test_shell_nav_todos_os_itens_tem_icone` quebra):

```jinja
        '/app/loja/copiloto': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v2"/><path d="M5 8h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z"/><path d="M9 13h.01M15 13h.01"/><path d="M2 12v3M22 12v3"/></svg>',
```

**(c)** Criar `portal-gestao/app/web/loja_copiloto.py`:

```python
"""Rotas da seção Copiloto de Vendas (Revy Loja).

Gate quádruplo: shell + flag do Copiloto + entitlement do módulo + papel de
gestão. Com qualquer um faltando a seção NÃO EXISTE (404) — não redireciona.

Nesta fase não há LLM nenhum: resumo determinístico + alertas de regra.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

router = APIRouter()

from app.auth import usuario_atual  # noqa: E402
from app.config import revy_loja_copiloto_enabled, revy_loja_shell_enabled  # noqa: E402
from app.db import get_db  # noqa: E402
from app.loja.copiloto.resumo import montar_resumo_hoje  # noqa: E402
from app.loja.copiloto.sinais_store import (  # noqa: E402
    contar_sinais_novos,
    dispensar,
    listar_sinais_abertos,
    marcar_visto,
)
from app.loja.copiloto.tipos import PAPEIS_GESTAO_COPILOTO, CopilotoContexto  # noqa: E402
from app.main import (  # noqa: E402
    contexto,
    csrf_valido,
    get_chatbot_client,
    get_estoque_client,
    redirecionar_login,
    templates,
)
from app.models import Usuario  # noqa: E402

_PAGINA = "/app/loja/copiloto"


def _secao_ativa() -> bool:
    # Lê env em runtime (evita snapshot de Settings poluído entre testes).
    return revy_loja_shell_enabled() and revy_loja_copiloto_enabled()


def _nao_existe() -> JSONResponse:
    return JSONResponse({"detail": "Not Found"}, status_code=404)


def _sem_permissao(request: Request, usuario: Usuario):
    return templates.TemplateResponse(
        "erro.html",
        contexto(request, usuario, erro="O Copiloto é do dono e do gerente da loja."),
        status_code=403,
    )


def _pode(usuario: Usuario) -> bool:
    return (usuario.papel or "").strip().casefold() in PAPEIS_GESTAO_COPILOTO


def _ctx(usuario: Usuario) -> CopilotoContexto:
    """loja_slug e papel SEMPRE da sessão — nunca de parâmetro de rota."""
    return CopilotoContexto(
        loja_slug=usuario.loja_slug,
        papel=usuario.papel,
        ator_email=usuario.email,
        hoje=datetime.now(timezone.utc).date(),
    )


@router.get(_PAGINA, response_class=HTMLResponse)
def copiloto_home(
    request: Request,
    db: Session = Depends(get_db),
    estoque=Depends(get_estoque_client),
    chatbot=Depends(get_chatbot_client),
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _secao_ativa():
        return _nao_existe()
    if not _pode(usuario):
        return _sem_permissao(request, usuario)

    ctx = _ctx(usuario)
    resumo = montar_resumo_hoje(db, ctx, estoque=estoque, chatbot=chatbot)
    return templates.TemplateResponse(
        "loja/copiloto.html",
        contexto(
            request,
            usuario,
            db=db,
            resumo=resumo,
            sinais=listar_sinais_abertos(db, ctx.loja_slug),
            sinais_novos=contar_sinais_novos(db, ctx.loja_slug),
        ),
    )


async def _acao_sinal(
    request: Request,
    sinal_id: str,
    db: Session,
    operacao,
):
    usuario = usuario_atual(request, db)
    if not usuario:
        return redirecionar_login()
    if not _secao_ativa():
        return _nao_existe()
    if not _pode(usuario):
        return _sem_permissao(request, usuario)

    form = await request.form()
    if not csrf_valido(request, form.get("csrf")):
        return RedirectResponse(f"{_PAGINA}?erro=sessao", status_code=303)

    # loja_slug da sessão: id de sinal sozinho nunca autoriza nada.
    ok = operacao(db, usuario.loja_slug, sinal_id)
    destino = f"{_PAGINA}?ok=1" if ok else f"{_PAGINA}?erro=sinal"
    return RedirectResponse(destino, status_code=303)


@router.post(_PAGINA + "/sinais/{sinal_id}/visto")
async def copiloto_sinal_visto(
    request: Request, sinal_id: str, db: Session = Depends(get_db)
):
    return await _acao_sinal(request, sinal_id, db, marcar_visto)


@router.post(_PAGINA + "/sinais/{sinal_id}/dispensar")
async def copiloto_sinal_dispensar(
    request: Request, sinal_id: str, db: Session = Depends(get_db)
):
    return await _acao_sinal(request, sinal_id, db, dispensar)
```

**(d)** `app/main.py` — registrar junto dos outros routers da Loja:

```python
app.include_router(loja_copiloto.router)
```

(e adicionar `loja_copiloto` ao import de `app.web`, no mesmo estilo dos demais)

**(e)** Criar `portal-gestao/app/templates/loja/copiloto.html`:

```jinja
{% extends "base.html" %}
{% block title %}Copiloto de Vendas — Revy Loja{% endblock %}
{% block page_title %}Copiloto{% endblock %}
{% block content %}
<div class="page-heading">
  <div>
    <span class="eyebrow">Copiloto</span>
    <h1>Copiloto de Vendas</h1>
    <p>O que precisa da sua atenção hoje — e os números por trás disso.</p>
  </div>
</div>

{% if sinais %}
<section class="panel" aria-labelledby="copiloto-alertas">
  <div class="panel-header">
    <h2 id="copiloto-alertas">Precisa de atenção</h2>
    {% if sinais_novos %}<span class="badge">{{ sinais_novos }} novo(s)</span>{% endif %}
  </div>
  <div class="panel-body">
    <ul class="copiloto-sinais">
      {% for sinal in sinais %}
      <li class="copiloto-sinal severidade-{{ sinal.severidade }}">
        <div>
          <strong>{{ sinal.titulo }}</strong>
          <p class="muted">{{ sinal.detalhe }}</p>
        </div>
        <div class="copiloto-sinal-acoes">
          <form action="/app/loja/copiloto/sinais/{{ sinal.id }}/visto" method="post">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button class="button secondary" type="submit">Já vi</button>
          </form>
          <form action="/app/loja/copiloto/sinais/{{ sinal.id }}/dispensar" method="post">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button class="button ghost" type="submit">Dispensar</button>
          </form>
        </div>
      </li>
      {% endfor %}
    </ul>
  </div>
</section>
{% endif %}

<section class="panel" aria-labelledby="copiloto-resumo">
  <div class="panel-header">
    <h2 id="copiloto-resumo">Resumo de hoje</h2>
    <span class="muted">{{ resumo.janela.rotulo }}</span>
  </div>
  <div class="panel-body copiloto-resumo">
    <div class="kpi">
      <span>Vendas</span>
      <strong>{{ resumo.vendas.qtd_vendas }}</strong>
      {% if resumo.vendas.delta_qtd %}<small>{{ resumo.vendas.delta_qtd }} vs. {{ resumo.vendas.janela_comparacao.rotulo }}</small>{% endif %}
    </div>
    <div class="kpi">
      <span>Receita</span>
      <strong>{{ formatar_brl(resumo.vendas.receita) }}</strong>
    </div>
    <div class="kpi">
      <span>Ticket médio</span>
      <strong>{% if resumo.vendas.ticket_medio %}{{ formatar_brl(resumo.vendas.ticket_medio) }}{% else %}—{% endif %}</strong>
    </div>
    {% if resumo.vendas.margem is not none %}
    <div class="kpi">
      <span>Margem</span>
      <strong>{{ formatar_brl(resumo.vendas.margem) }}</strong>
      {% if resumo.vendas.cobertura_margem.parcial %}
      <small>calculada sobre {{ resumo.vendas.cobertura_margem.com_dado }} de {{ resumo.vendas.cobertura_margem.total }} vendas</small>
      {% endif %}
    </div>
    {% endif %}
  </div>
</section>

<section class="panel" aria-labelledby="copiloto-origem">
  <div class="panel-header"><h2 id="copiloto-origem">De onde veio a última venda</h2></div>
  <div class="panel-body">
    {% if resumo.origem_ultima.status == 'vazio' %}
    <p class="muted">Nenhuma venda confirmada ainda.</p>
    {% elif resumo.origem_ultima.origem.identificada %}
    <p><strong>{{ resumo.origem_ultima.origem.descricao }}</strong> veio de
      <strong>{{ resumo.origem_ultima.origem.campanha_nome or resumo.origem_ultima.origem.utm_campaign }}</strong>.</p>
    {% else %}
    <p class="muted">A última venda ({{ resumo.origem_ultima.origem.descricao }}) está sem campanha de origem.</p>
    {% endif %}
  </div>
</section>

<section class="panel" aria-labelledby="copiloto-parado">
  <div class="panel-header"><h2 id="copiloto-parado">Estoque parado</h2></div>
  <div class="panel-body">
    {% if resumo.parado.status == 'indisponivel' %}
    <p class="muted">O estoque está indisponível agora — nenhum número aqui.</p>
    {% elif not resumo.parado.itens %}
    <p class="muted">Nada parado há mais de {{ resumo.parado.dias_min }} dias.</p>
    {% else %}
    <p><strong>{{ resumo.parado.total }}</strong> veículo(s) parado(s) há mais de
      {{ resumo.parado.dias_min }} dias — {{ formatar_brl(resumo.parado.capital_preso) }} de capital preso.</p>
    <p class="muted">{{ resumo.parado.ressalva }}</p>
    {% endif %}
  </div>
</section>

{% if resumo.chips %}
<section class="panel" aria-labelledby="copiloto-chips">
  <div class="panel-header"><h2 id="copiloto-chips">Perguntas frequentes</h2></div>
  <div class="panel-body copiloto-chips">
    {% for chip in resumo.chips %}<span class="chip" title="{{ chip.pergunta }}">{{ chip.texto }}</span>{% endfor %}
  </div>
</section>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_copiloto_pagina.py tests/test_loja_navigation.py -q`
Expected: PASS (9 + 12 testes).

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: PASS — suíte inteira.

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/web/loja_copiloto.py portal-gestao/app/templates/loja/copiloto.html portal-gestao/app/loja/navigation.py portal-gestao/app/templates/base.html portal-gestao/app/main.py portal-gestao/tests/test_copiloto_pagina.py portal-gestao/tests/test_loja_navigation.py
git commit -m "feat(copiloto): secao Copiloto no shell da Loja e rename Agente do WhatsApp"
```

---

## Fechamento do plano

- [ ] Rodar a suíte completa: `.\.venv\Scripts\python.exe -m pytest -q`
- [ ] Rodar a migration: `.\.venv\Scripts\python.exe -m alembic upgrade head` e conferir `alembic current` = `0019_copiloto_sinal`
- [ ] `git diff --check` e `git status --short` — preservar mudanças alheias no worktree
- [ ] Atualizar `docs/nao-plano/historico/README.md` com a linha do Copiloto Fase 1
- [ ] **Não deployar ainda:** `REVY_LOJA_COPILOTO_ENABLED` fica off até a Fase 2. Lembrete da casa: `fly deploy` usa a árvore local — commitar antes.

## Self-Review

**Cobertura do spec (v1 determinística):**

| Item do design | Task |
|---|---|
| §9 flag + entitlement por loja | 1 |
| §6.2 regra de cobertura | 2 (tipo), 4/6/7 (uso) |
| §4.1 `vendas_resumo` (ticket, Δ) | 3 + 4 |
| §4.1 `ranking_vendedores` | 5 |
| §4.1 `venda_origem` / §4.2 | 6 |
| §4.1 `estoque_parado` + §3.7 guarda | 7 |
| §4.1 `leads_status` (backing corrigido) | 8 |
| §3.5 cache do fan-out | 9 |
| §3.6 tabela de sinal | 10 |
| §5 as 6 regras | 11 |
| §5 cooldown / dispensado / resolvido | 12 |
| §5 worker por loja | 13 |
| §7 "Resumo de hoje" + chips vivos | 14 |
| §7 seção, rename, 404 coerente | 15 |

**Fora deste plano, de propósito** (estão nos planos irmãos): chat/LLM/turno assíncrono e tabelas
`copiloto_conversa`/`copiloto_turno` (F2); `roi_canais` (F2 — não precisa de consulta nova, lê o
overview já cacheado por este plano); `consultar_fipe`, ações de escrita e auditoria (F3).

**Consistência de tipos verificada:** `Cobertura` (Task 2) é usada com a mesma assinatura em 4, 6, 7 e 11; `CopilotoContexto` idem em 4–8, 13, 14, 15; `SinalCandidato` (11) é o input de `sincronizar_sinais` (12) e o output de `avaliar_loja` (13); `Janela` (3) atravessa 4, 5, 6, 11, 14. `estoque_parado` recebe `agora=` em 7, 13 e 14 — mesmo nome de parâmetro.

**Riscos conhecidos que o plano aceita:** cache é por processo (não distribuído); `criado_em` como proxy de entrada física do veículo (ressalva exposta na resposta); "leads sem resposta" depende de `bot_ativo=False`, então loja que nunca faz handoff nunca dispara essa regra.

