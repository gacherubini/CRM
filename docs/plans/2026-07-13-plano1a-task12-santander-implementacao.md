# Driver Real Santander — Fase 1 (Motor) — Implementation Plan

> **Status 2026-07-13 (LIVE OK — pause):** piloto Santander **fim-a-fim no portal real** (login →
> step-personal → step-offers → multi-prazo no Portal). Worker headed+Xvfb; parsers de parcela e
> financiado corrigidos. **Não reabrir o fluxo Santander** sem ler  
> `2026-07-13-playwright-licoes-santander.md`.
>
> **Entregue na sessão live:** Dockerfile Chromium+Xvfb, entrypoint, stealth anti-Akamai, seletores
> Material (sem placeholder), modal sims anteriores, progresso HTMX no Portal, códigos de erro.
> **Aberto:** smoke pytest gated `MOTOR_SANTANDER_LIVE=1`; `testar-login` real; multi-banco paralelo;
> fase 2 Chatbot CNH/UF se operação pedir.
>
> **Próximo agente:** outro banco (API-first) — **não** este checklist do zero. Template em
> `...-bancos-reconhecimento.md` + lições.
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o 1º driver de simulação `real: true` — Santander via Playwright, multi-prazo — plugado no motor de drivers existente, sem quebrar o mock.

**Architecture:** Estende o contrato de simulação (CNH/placa/UF/finalidade/multi-prazo), introduz um `DriverContext` e uma base `PlaywrightBankDriver` reutilizável, e um `SantanderDriver` que loga no portal, preenche os 5 passos e lê a parcela de cada prazo. Drivers reais só são resolvidos quando há credencial (Task 11) para o cliente+provedor. Testes rodam contra fixtures locais; um smoke `--live` (gated) valida contra o portal real.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Alembic, Pydantic v2, Playwright (sync API) + Chromium, pytest.

## Global Constraints

- Workspace: `C:\Users\guilh\Documents\codigo\bot-whatsapp-financiamento`; produto em `motor-simulacao/`.
- Rodar testes: `cd motor-simulacao; .\.venv\Scripts\python.exe -m pytest -q` (baseline: 69 passam).
- **Nunca** ler/imprimir/logar `.env`, `MOTOR_ENCRYPTION_KEY`, credenciais ou `storage_state`.
- Integrações entre produtos só por HTTP; esta fase é **só Motor**.
- Simulação com nomes de banco no mock = **fictícia**. Driver real só com `real: true` + credencial.
- Playwright é **último recurso** (só porque o Santander não tem API) — ver design `docs/plans/2026-07-13-plano1a-task12-santander-design.md`.
- Compat retroativa: o mock e o contrato antigo (`prazo_meses` único) continuam funcionando.
- TDD: teste falha → implementação mínima → teste passa → commit. Commits frequentes.

## File Structure

- `app/motor/base.py` — MODIFICAR: novos campos no contrato (Pessoa/Veiculo/Condicoes/Solicitacao).
- `app/models_db.py` — MODIFICAR: colunas novas em `SimulacaoORM`.
- `alembic/versions/0007_simulacao_campos_reais.py` — CRIAR: migration.
- `app/main.py` — MODIFICAR: request model aceita campos novos.
- `app/servico.py` — MODIFICAR: persistir campos novos ao criar job.
- `app/processamento.py` — MODIFICAR: `DriverContext`, reconstrução do contrato, multi-resultado.
- `app/motor/drivers.py` — MODIFICAR: `DriverContext`, assinatura do `Driver`, `REAL_DRIVERS`, gating.
- `app/motor/playwright_base.py` — CRIAR: `PlaywrightBankDriver` (base reutilizável).
- `app/motor/santander.py` — CRIAR: `SantanderDriver`.
- `app/config.py` — MODIFICAR: prazos padrão, dir de screenshots, storage_state, timeouts do browser.
- `requirements.txt` + `Dockerfile` — MODIFICAR: Playwright + Chromium.
- `tests/fixtures/banco_fake/` e `tests/fixtures/santander/` — CRIAR: páginas HTML de fixture.
- `tests/test_contrato_campos_reais.py`, `tests/test_multiprazo.py`, `tests/test_gating_real.py`,
  `tests/test_playwright_base.py`, `tests/test_santander_driver.py`, `tests/test_santander_live.py` — CRIAR.

---

### Task 1: Estender o contrato de simulação

**Files:**
- Modify: `app/motor/base.py`
- Test: `tests/test_contrato_campos_reais.py`

**Interfaces:**
- Produces: `Pessoa.cnh: Optional[bool]`; `Veiculo.placa/uf_licenciamento/finalidade: Optional[str]`, `Veiculo.valor: Optional[float]`; `Condicoes.prazos_meses: list[int]` (com `prazo_meses` retrocompatível); `SolicitacaoSimulacao` inalterada na forma externa.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_contrato_campos_reais.py
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo


def test_pessoa_aceita_cnh_opcional():
    p = Pessoa(cpf="52998224725", nascimento="1990-01-01", cnh=True)
    assert p.cnh is True
    assert Pessoa(cpf="52998224725", nascimento="1990-01-01").cnh is None


def test_veiculo_aceita_placa_uf_finalidade_e_valor_opcional():
    v = Veiculo(placa="ABC1D23", uf_licenciamento="SP", finalidade="comum")
    assert v.placa == "ABC1D23" and v.uf_licenciamento == "SP" and v.finalidade == "comum"
    assert v.valor is None  # valor vem do portal


def test_condicoes_multiprazo_e_retrocompat():
    c = Condicoes(entrada=1000, prazos_meses=[24, 36, 48])
    assert c.prazos_meses == [24, 36, 48]
    # contrato antigo: prazo_meses único é aceito e vira lista de 1
    c2 = Condicoes(entrada=0, prazo_meses=60)
    assert c2.prazos_meses == [60]
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_contrato_campos_reais.py -v`
Expected: FAIL (`cnh`/`placa`/`prazos_meses` inexistentes).

- [ ] **Step 3: Implementar os modelos**

```python
# app/motor/base.py — substituir Pessoa, Veiculo, Condicoes
from typing import List, Literal, Optional
from pydantic import BaseModel, model_validator


class Pessoa(BaseModel):
    cpf: str
    nascimento: str
    renda: Optional[float] = None
    cnh: Optional[bool] = None


class Veiculo(BaseModel):
    categoria: str = "moto"
    valor: Optional[float] = None  # nulo quando o portal do banco resolve pela placa
    placa: Optional[str] = None
    uf_licenciamento: Optional[str] = None
    finalidade: Optional[Literal["comum", "pcd"]] = None


class Condicoes(BaseModel):
    entrada: float = 0
    prazo_meses: Optional[int] = None
    prazos_meses: List[int] = []

    @model_validator(mode="after")
    def _normaliza_prazos(self) -> "Condicoes":
        if not self.prazos_meses and self.prazo_meses is not None:
            object.__setattr__(self, "prazos_meses", [self.prazo_meses])
        if self.prazo_meses is None and self.prazos_meses:
            object.__setattr__(self, "prazo_meses", self.prazos_meses[0])
        return self
```

- [ ] **Step 4: Rodar o teste e ver passar**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_contrato_campos_reais.py -v`
Expected: PASS. Depois rode a suíte inteira: `.\.venv\Scripts\python.exe -m pytest -q` — 69 + 3 devem passar (mock usa `prazo_meses`, ainda válido).

- [ ] **Step 5: Commit**

```bash
git add app/motor/base.py tests/test_contrato_campos_reais.py
git commit -m "feat(motor): contrato de simulacao ganha cnh/placa/uf/finalidade + multi-prazo"
```

---

### Task 2: Colunas do job + migration 0007

**Files:**
- Modify: `app/models_db.py:100-125` (SimulacaoORM)
- Create: `alembic/versions/0007_simulacao_campos_reais.py`
- Test: `tests/test_migration_campos_reais.py`

**Interfaces:**
- Produces: `SimulacaoORM.placa/uf_licenciamento/finalidade: str|None`, `SimulacaoORM.cnh: bool|None`, `SimulacaoORM.prazos_meses: list|None (JSON)`.

- [ ] **Step 1: Escrever o teste da migration**

```python
# tests/test_migration_campos_reais.py
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect


def test_upgrade_adiciona_colunas_e_downgrade_remove(tmp_path):
    url = f"sqlite:///{tmp_path/'m.db'}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    cols = {c["name"] for c in inspect(create_engine(url)).get_columns("simulacoes")}
    assert {"placa", "uf_licenciamento", "finalidade", "cnh", "prazos_meses"} <= cols
    command.downgrade(cfg, "0006")
    cols2 = {c["name"] for c in inspect(create_engine(url)).get_columns("simulacoes")}
    assert not ({"placa", "uf_licenciamento", "finalidade", "cnh", "prazos_meses"} & cols2)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_migration_campos_reais.py -v`
Expected: FAIL (colunas não existem).

- [ ] **Step 3: Adicionar as colunas no ORM**

```python
# app/models_db.py — dentro de SimulacaoORM, após 'provedores'
    cnh: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    placa: Mapped[str | None] = mapped_column(String(7), nullable=True)
    uf_licenciamento: Mapped[str | None] = mapped_column(String(2), nullable=True)
    finalidade: Mapped[str | None] = mapped_column(String(8), nullable=True)
    prazos_meses: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Criar a migration**

```python
# alembic/versions/0007_simulacao_campos_reais.py
"""simulacao: campos do driver real (cnh/placa/uf/finalidade/multi-prazo)"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("simulacoes", sa.Column("cnh", sa.Boolean(), nullable=True))
    op.add_column("simulacoes", sa.Column("placa", sa.String(length=7), nullable=True))
    op.add_column("simulacoes", sa.Column("uf_licenciamento", sa.String(length=2), nullable=True))
    op.add_column("simulacoes", sa.Column("finalidade", sa.String(length=8), nullable=True))
    op.add_column("simulacoes", sa.Column("prazos_meses", sa.JSON(), nullable=True))


def downgrade() -> None:
    for col in ("prazos_meses", "finalidade", "uf_licenciamento", "placa", "cnh"):
        op.drop_column("simulacoes", col)
```

- [ ] **Step 5: Rodar e ver passar; depois a suíte**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_migration_campos_reais.py -q` → PASS.
Run: `.\.venv\Scripts\python.exe -m pytest -q` → tudo verde (fixtures usam `create_all`, colunas entram).

- [ ] **Step 6: Commit**

```bash
git add app/models_db.py alembic/versions/0007_simulacao_campos_reais.py tests/test_migration_campos_reais.py
git commit -m "feat(motor): colunas de campos reais no job + migration 0007"
```

---

### Task 3: API e criação do job aceitam/persistem os campos novos

**Files:**
- Modify: `app/main.py` (request model de `POST /v1/simulacoes`), `app/servico.py` (criação do job)
- Test: `tests/test_criar_simulacao_campos_reais.py`

**Interfaces:**
- Consumes: contrato do Task 1, colunas do Task 2.
- Produces: job criado com `placa/uf_licenciamento/finalidade/cnh/prazos_meses` persistidos; `servico` grava esses campos e o payload cifrado continua com cpf/nascimento/renda.

> **Nota de leitura:** abra `app/main.py` e `app/servico.py` e localize o modelo Pydantic do corpo de `POST /v1/simulacoes` e a função que cria o `SimulacaoORM`. Os nomes exatos dos campos do request espelham `SolicitacaoSimulacao` (pessoa/veiculo/condicoes). Adicione os campos novos ao modelo do request e ao insert do ORM, seguindo o padrão já existente para `valor`/`entrada`/`prazo_meses`.

- [ ] **Step 1: Escrever o teste (via API, com cliente autenticado)**

```python
# tests/test_criar_simulacao_campos_reais.py
# Reutilize as fixtures existentes de cliente/token da suíte (ver tests/conftest.py).
def test_cria_job_com_campos_reais(client, auth_headers, db_session):
    from app.models_db import SimulacaoORM
    body = {
        "pessoa": {"cpf": "52998224725", "nascimento": "1990-01-01", "cnh": True},
        "veiculo": {"placa": "ABC1D23", "uf_licenciamento": "SP", "finalidade": "comum"},
        "condicoes": {"entrada": 1000, "prazos_meses": [24, 36, 48]},
        "provedores": ["santander"],
    }
    r = client.post("/v1/simulacoes", json=body, headers=auth_headers)
    assert r.status_code in (201, 202)
    sim = db_session.query(SimulacaoORM).get(r.json()["id"])
    assert sim.placa == "ABC1D23" and sim.uf_licenciamento == "SP"
    assert sim.finalidade == "comum" and sim.cnh is True
    assert sim.prazos_meses == [24, 36, 48]
```

> Se os nomes de fixture (`client`, `auth_headers`, `db_session`) diferirem no `tests/conftest.py`, use os equivalentes de lá — não invente fixtures novas.

- [ ] **Step 2: Rodar e ver falhar** → FAIL (campos ignorados/inexistentes no request ou não persistidos).

- [ ] **Step 3: Implementar** — adicionar os campos ao modelo Pydantic do request (espelhando Task 1) e gravá-los no `SimulacaoORM` na função de criação em `servico.py`, ao lado de `valor/entrada/prazo_meses`. `cpf/nascimento/renda` continuam no `payload_cifrado`. `cnh` (não sensível) vai na coluna `cnh`.

- [ ] **Step 4: Rodar e ver passar** → PASS; depois `pytest -q` verde.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/servico.py tests/test_criar_simulacao_campos_reais.py
git commit -m "feat(motor): API/criacao de job aceitam cnh/placa/uf/finalidade/multi-prazo"
```

---

### Task 4: `DriverContext` + assinatura do Driver aceitando contexto e retorno lista

**Files:**
- Modify: `app/motor/drivers.py`, `app/motor/mock.py` (se os drivers do mock forem definidos lá — o registro está em `drivers.py`), `app/processamento.py`
- Test: `tests/test_driver_context.py`

**Interfaces:**
- Produces:
  - `class DriverContext` (dataclass) com `db: Session | None`, `cliente_id: str | None`, `screenshot_dir: str | None`.
  - `Driver = Callable[[SolicitacaoSimulacao, "DriverContext | None"], "ResultadoDriver | list[ResultadoDriver]"]`.
  - Drivers do mock passam a aceitar `(sol, ctx=None)` e continuam devolvendo **um** `ResultadoDriver`.
  - `processamento._executar_driver(...)` passa a devolver `list[ResultadoDriver]` (normaliza único→lista) e registra uma tentativa por chamada.

- [ ] **Step 1: Escrever o teste**

```python
# tests/test_driver_context.py
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import DriverContext, resolver_drivers


def _sol():
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01"),
        veiculo=Veiculo(valor=10000), condicoes=Condicoes(entrada=0, prazo_meses=24),
        provedores=["mock"],
    )


def test_driver_mock_aceita_contexto_opcional_e_devolve_resultado():
    pares = resolver_drivers(["mock"])
    nome, driver = pares[0]
    r = driver(_sol(), DriverContext())  # aceita ctx
    assert r.status == "concluida"
    r2 = driver(_sol(), None)  # ctx opcional
    assert r2.status == "concluida"
```

- [ ] **Step 2: Rodar e ver falhar** → FAIL (drivers do mock são `def _driver(sol)`; `DriverContext` não existe).

- [ ] **Step 3: Implementar em `drivers.py`**

```python
# app/motor/drivers.py — adicionar
from dataclasses import dataclass
from sqlalchemy.orm import Session


@dataclass
class DriverContext:
    db: "Session | None" = None
    cliente_id: str | None = None
    screenshot_dir: str | None = None


# atualizar a assinatura do driver do mock:
def _driver_banco(banco: str, taxa: Decimal) -> "Driver":
    def _driver(sol: SolicitacaoSimulacao, ctx: "DriverContext | None" = None) -> ResultadoDriver:
        financiado = Decimal(str(max((sol.veiculo.valor or 0) - sol.condicoes.entrada, 0)))
        prazo = sol.condicoes.prazo_meses or (sol.condicoes.prazos_meses or [0])[0]
        parcela = calcula_parcela_price(financiado, taxa, prazo)
        return ResultadoDriver(provedor=banco, status="concluida", valor_parcela=parcela,
                               taxa_am=taxa * 100, prazo_meses=prazo, valor_financiado=financiado)
    return _driver
```

- [ ] **Step 4: Normalizar retorno em `_executar_driver`**

Em `app/processamento.py`, altere `_executar_driver` para: (a) chamar `driver(sol, ctx)`; (b) tratar retorno único **ou** lista, normalizando para `list[ResultadoDriver]`; (c) registrar uma tentativa por chamada; (d) manter o mesmo mapeamento das exceções (`IntervencaoNecessaria`/`RejeicaoNegocio`/`ErroTransitorio`), mas devolvendo **lista** (com um único item de erro). Assinatura nova:

```python
def _executar_driver(db, sim, nome, driver, sol, ctx=None) -> list[ResultadoDriver]:
    prazo = sol.condicoes.prazo_meses
    for tentativa in range(1, MAX_TENTATIVAS_DRIVER + 1):
        inicio = time.perf_counter()
        try:
            res = driver(sol, ctx)
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "concluida", None)
            return res if isinstance(res, list) else [res]
        except IntervencaoNecessaria as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "aguardando_intervencao", e.codigo)
            return [ResultadoDriver(nome, "aguardando_intervencao", prazo_meses=prazo, codigo_erro=e.codigo)]
        except RejeicaoNegocio as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "rejeitada", e.codigo)
            return [ResultadoDriver(nome, "rejeitada", prazo_meses=prazo, codigo_erro=e.codigo)]
        except (ErroTransitorio, TimeoutError) as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            codigo = getattr(e, "codigo", "timeout")
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "erro_transitorio", codigo)
            if tentativa >= MAX_TENTATIVAS_DRIVER:
                return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro=codigo)]
    return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro="desconhecido")]
```

> A chamada em `processar_job` (Task 5) passa a consumir a **lista**.

- [ ] **Step 5: Rodar e ver passar** → PASS. `pytest -q` deve continuar verde (Task 5 ajusta o consumidor; se `processar_job` quebrar agora, é esperado até a Task 5 — rode só `tests/test_driver_context.py` neste commit).

- [ ] **Step 6: Commit**

```bash
git add app/motor/drivers.py app/processamento.py tests/test_driver_context.py
git commit -m "feat(motor): DriverContext e driver com retorno normalizado para lista"
```

---

### Task 5: `processar_job` persiste multi-resultado por provedor

**Files:**
- Modify: `app/processamento.py` (`processar_job`, `_reconstruir_solicitacao`)
- Test: `tests/test_multiprazo.py`

**Interfaces:**
- Consumes: `_executar_driver -> list[ResultadoDriver]` (Task 4), colunas do job (Task 2).
- Produces: `processar_job` persiste **N** `ResultadoORM` por provedor; retomada pula provedor já presente; `_reconstruir_solicitacao` popula os campos novos e `prazos_meses`.

- [ ] **Step 1: Escrever o teste com um driver fake multi-prazo**

```python
# tests/test_multiprazo.py
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import ResultadoDriver
from app import processamento
# Use as fixtures de db/sessão e criação de job da suíte (ver conftest).

def _driver_multi(sol, ctx=None):
    return [ResultadoDriver("banco_x", "concluida", valor_parcela=100 + p, taxa_am=1.9,
                            prazo_meses=p, valor_financiado=9000) for p in sol.condicoes.prazos_meses]

def test_processa_job_persiste_um_resultado_por_prazo(db_session, cria_job):
    sim = cria_job(prazos_meses=[24, 36, 48], provedores=["banco_x"])
    processamento.processar_job(db_session, sim.id, drivers=[("banco_x", _driver_multi)],
                                reserva_token=sim.reserva_token)
    sim = db_session.get(type(sim), sim.id)
    prazos = sorted(r.prazo_meses for r in sim.resultados)
    assert prazos == [24, 36, 48]
    assert sim.status == "concluida"
```

> `cria_job` deve reservar o job (status `processando`, `reserva_token`). Se a suíte não tiver esse helper, crie-o no teste reutilizando `servico`/`reservar_proximo_job`.

- [ ] **Step 2: Rodar e ver falhar** → FAIL (só persiste 1 por provedor; retomada keyed por provedor).

- [ ] **Step 3: Ajustar `_reconstruir_solicitacao`**

```python
# app/processamento.py — _reconstruir_solicitacao
def _reconstruir_solicitacao(sim: SimulacaoORM) -> SolicitacaoSimulacao:
    pessoal = json.loads(cripto.decifrar(sim.payload_cifrado)) if sim.payload_cifrado else {}
    prazos = list(sim.prazos_meses) if sim.prazos_meses else ([sim.prazo_meses] if sim.prazo_meses else [])
    return SolicitacaoSimulacao(
        referencia_externa=sim.referencia_externa,
        pessoa=Pessoa(cpf=pessoal.get("cpf", ""), nascimento=pessoal.get("nascimento", ""),
                      renda=pessoal.get("renda"), cnh=sim.cnh),
        veiculo=Veiculo(categoria=sim.categoria or "moto",
                        valor=float(sim.valor) if sim.valor is not None else None,
                        placa=sim.placa, uf_licenciamento=sim.uf_licenciamento, finalidade=sim.finalidade),
        condicoes=Condicoes(entrada=float(sim.entrada or 0), prazos_meses=prazos),
        provedores=sim.provedores or ["mock"],
    )
```

- [ ] **Step 4: Ajustar `processar_job` para persistir lista**

No laço de `processar_job`, troque a montagem de `existentes` para agrupar por provedor (um provedor presente ⇒ pular), e substitua o `db.add(ResultadoORM(...))` único por um laço que persiste **cada** item de `res_lista = _executar_driver(db, sim, nome, driver, sol, ctx)`, num único checkpoint por provedor. `resultados` acumula a lista achatada (para `_status_geral`). Passe `ctx=DriverContext(db=db, cliente_id=sim.cliente_id, screenshot_dir=config.SCREENSHOT_DIR)` (config na Task 8). Exemplo do trecho:

```python
    existentes_por_prov = {}
    for r in sim.resultados:
        existentes_por_prov.setdefault(r.provedor, []).append(r)
    resultados = [
        ResultadoDriver(r.provedor, r.status, valor_parcela=r.valor_parcela, taxa_am=r.taxa_am,
                        prazo_meses=r.prazo_meses, valor_financiado=r.valor_financiado, codigo_erro=r.codigo_erro)
        for linhas in existentes_por_prov.values() for r in linhas
    ]
    ctx = DriverContext(db=db, cliente_id=sim.cliente_id, screenshot_dir=config.SCREENSHOT_DIR)
    for nome, driver in pares:
        if nome in existentes_por_prov:
            continue
        sim.reservada_ate = _agora() + timedelta(seconds=config.JOB_LEASE_SECONDS)
        sim.atualizada_em = _agora(); db.commit()
        res_lista = _executar_driver(db, sim, nome, driver, sol, ctx)
        db.refresh(sim)
        if sim.status != "processando" or sim.reserva_token != token:
            db.rollback(); return sim
        for res in res_lista:
            db.add(ResultadoORM(
                simulacao_id=sim.id, provedor=res.provedor, status=res.status,
                valor_parcela=res.valor_parcela, taxa_am=res.taxa_am,
                prazo_meses=res.prazo_meses, valor_financiado=res.valor_financiado, codigo_erro=res.codigo_erro))
        db.commit()
        resultados.extend(res_lista)
```

Import `DriverContext` de `app.motor.drivers`.

- [ ] **Step 5: Rodar e ver passar** → `tests/test_multiprazo.py` PASS; depois `pytest -q` **inteiro** verde (mock volta a funcionar via lista normalizada).

- [ ] **Step 6: Commit**

```bash
git add app/processamento.py tests/test_multiprazo.py
git commit -m "feat(motor): worker persiste multi-resultado por provedor (multi-prazo)"
```

---

### Task 6: Gating do driver real por credencial

**Files:**
- Modify: `app/motor/drivers.py` (`resolver_drivers`, `REAL_DRIVERS`)
- Test: `tests/test_gating_real.py`

**Interfaces:**
- Consumes: `credenciais.obter_segredo_para_uso(db, cliente_id, provedor)` (Task 11 existente).
- Produces: `REAL_DRIVERS: dict[str, callable]` (fábricas de driver real); `resolver_drivers(provedores, db=None, cliente_id=None)` — para um provedor com driver real **e** credencial habilitada, resolve o **real**; senão cai no mock (se existir) ou pula.

- [ ] **Step 1: Escrever o teste**

```python
# tests/test_gating_real.py
from app.motor import drivers as D


def test_provedor_real_so_resolve_com_credencial(monkeypatch):
    marcador = object()
    D.REAL_DRIVERS["santander"] = lambda: (lambda sol, ctx=None: marcador)

    # sem credencial -> não usa o real
    monkeypatch.setattr(D, "obter_segredo_para_uso", lambda db, c, p: None)
    pares = D.resolver_drivers(["santander"], db="X", cliente_id="c1")
    assert all(driver(None) is not marcador for _, driver in pares) or pares == []

    # com credencial -> usa o real
    monkeypatch.setattr(D, "obter_segredo_para_uso", lambda db, c, p: ("u", "s"))
    pares = D.resolver_drivers(["santander"], db="X", cliente_id="c1")
    assert any(driver(None) is marcador for _, driver in pares)
    D.REAL_DRIVERS.pop("santander", None)
```

- [ ] **Step 2: Rodar e ver falhar** → FAIL (`REAL_DRIVERS`/gating inexistentes).

- [ ] **Step 3: Implementar**

```python
# app/motor/drivers.py — adicionar
from app.credenciais import obter_segredo_para_uso  # import no topo

REAL_DRIVERS: dict[str, callable] = {}  # nome -> fábrica () -> Driver


def resolver_drivers(provedores, db=None, cliente_id=None):
    pedidos = provedores or ["mock"]
    pares, vistos = [], set()
    for p in pedidos:
        nomes = list(DRIVERS.keys()) if p == "mock" else [p]
        for nome in nomes:
            if nome in vistos:
                continue
            vistos.add(nome)
            usa_real = (
                nome in REAL_DRIVERS and db is not None and cliente_id is not None
                and obter_segredo_para_uso(db, cliente_id, nome) is not None
            )
            if usa_real:
                pares.append((nome, REAL_DRIVERS[nome]()))
            elif nome in DRIVERS:
                pares.append((nome, DRIVERS[nome]))
    return pares
```

Atualize a chamada em `processar_job`: `pares = drivers if drivers is not None else resolver_drivers(sol.provedores, db=db, cliente_id=sim.cliente_id)`.

- [ ] **Step 4: Rodar e ver passar** → PASS; `pytest -q` verde.

- [ ] **Step 5: Commit**

```bash
git add app/motor/drivers.py app/processamento.py tests/test_gating_real.py
git commit -m "feat(motor): resolve driver real so quando ha credencial do cliente"
```

---

### Task 7: Dependência Playwright + config

**Files:**
- Modify: `requirements.txt`, `Dockerfile`, `app/config.py`
- Test: `tests/test_config_browser.py`

**Interfaces:**
- Produces: `config.PRAZOS_PADRAO: list[int]`, `config.SCREENSHOT_DIR: str`, `config.STORAGE_STATE_DIR: str`, `config.BROWSER_TIMEOUT_MS: int`, `config.SANTANDER_LOGIN_URL: str`.

- [ ] **Step 1: Escrever o teste**

```python
# tests/test_config_browser.py
from app import config
def test_config_browser_defaults():
    assert isinstance(config.PRAZOS_PADRAO, list) and config.PRAZOS_PADRAO
    assert config.BROWSER_TIMEOUT_MS >= 1000
    assert config.SANTANDER_LOGIN_URL.startswith("https://")
```

- [ ] **Step 2: Rodar e ver falhar** → FAIL.

- [ ] **Step 3: Implementar config**

```python
# app/config.py — adicionar (seguindo o padrão os.getenv já usado no arquivo)
import os, json
PRAZOS_PADRAO = json.loads(os.getenv("MOTOR_PRAZOS_PADRAO", "[24,36,48,60]"))
SCREENSHOT_DIR = os.getenv("MOTOR_SCREENSHOT_DIR", "data/screenshots")
STORAGE_STATE_DIR = os.getenv("MOTOR_STORAGE_STATE_DIR", "data/browser_state")
BROWSER_TIMEOUT_MS = int(os.getenv("MOTOR_BROWSER_TIMEOUT_MS", "30000"))
SANTANDER_LOGIN_URL = os.getenv(
    "MOTOR_SANTANDER_LOGIN_URL", "https://financiamentos.santander.com.br/originacao-auto/login")
```

- [ ] **Step 4: Adicionar dependência e browser**

```text
# requirements.txt — adicionar
playwright==1.48.0
```

```dockerfile
# Dockerfile — após instalar requirements
RUN python -m playwright install --with-deps chromium
```

Instale local: `.\.venv\Scripts\python.exe -m pip install playwright==1.48.0` e
`.\.venv\Scripts\python.exe -m playwright install chromium`.

- [ ] **Step 5: Rodar e ver passar** → PASS; `pytest -q` verde.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt Dockerfile app/config.py tests/test_config_browser.py
git commit -m "chore(motor): playwright + config de browser/prazos/screenshots"
```

---

### Task 8: Base reutilizável `PlaywrightBankDriver`

**Files:**
- Create: `app/motor/playwright_base.py`, `tests/fixtures/banco_fake/login.html`, `tests/fixtures/banco_fake/passo1.html`
- Test: `tests/test_playwright_base.py`

**Interfaces:**
- Produces:
  - `class PlaywrightBankDriver` com: `provedor: str`; `__call__(sol, ctx) -> list[ResultadoDriver]`; métodos-gancho `login(page, usuario, senha)`, `preencher_e_ler(page, sol) -> list[ResultadoDriver]` (abstratos); helpers `preencher_por_rotulo(page, rotulo, valor)`, `_falha_campo(page, ctx, rotulo)` (screenshot + `IntervencaoNecessaria`).
  - Estratégia: abre browser (headless), carrega `storage_state` se existir, chama `login`, chama `preencher_e_ler`, salva `storage_state`. Exceções do Playwright viram `ErroTransitorio`; âncora ausente vira `IntervencaoNecessaria` com screenshot.

- [ ] **Step 1: Criar as fixtures HTML** (páginas locais que imitam um banco genérico, com os mesmos rótulos visíveis do padrão de âncora)

```html
<!-- tests/fixtures/banco_fake/login.html -->
<label>Usuário<input name="u" aria-label="Usuário"></label>
<label>Senha<input type="password" aria-label="Senha"></label>
<button>Entrar</button>
```

```html
<!-- tests/fixtures/banco_fake/passo1.html -->
<label>CPF ou CNPJ do cliente<input aria-label="CPF ou CNPJ do cliente"></label>
<div id="parcela" data-parcela="1320.00" data-taxa="1.90" data-prazo="48">48x de R$ 1.320,00</div>
```

- [ ] **Step 2: Escrever o teste (Playwright contra as fixtures via `file://`)**

```python
# tests/test_playwright_base.py
import pytest
from pathlib import Path
from app.motor.drivers import DriverContext, IntervencaoNecessaria
from app.motor.playwright_base import PlaywrightBankDriver

pytestmark = pytest.mark.playwright  # marcado; pulável se browser ausente
FIX = Path(__file__).parent / "fixtures" / "banco_fake"


class _FakeDriver(PlaywrightBankDriver):
    provedor = "banco_fake"
    def login(self, page, usuario, senha):
        page.goto((FIX / "login.html").as_uri())
        self.preencher_por_rotulo(page, "Usuário", usuario)
    def preencher_e_ler(self, page, sol):
        page.goto((FIX / "passo1.html").as_uri())
        el = page.locator("#parcela")
        from decimal import Decimal
        from app.motor.drivers import ResultadoDriver
        return [ResultadoDriver("banco_fake", "concluida",
                                valor_parcela=Decimal(el.get_attribute("data-parcela")),
                                taxa_am=Decimal(el.get_attribute("data-taxa")),
                                prazo_meses=int(el.get_attribute("data-prazo")))]


def test_base_loga_e_le_parcela(tmp_path):
    ctx = DriverContext(screenshot_dir=str(tmp_path))
    res = _FakeDriver(usuario="u", senha="s")(None, ctx)
    assert res[0].valor_parcela is not None and res[0].prazo_meses == 48


def test_campo_ausente_vira_intervencao_com_screenshot(tmp_path):
    class _Quebrado(_FakeDriver):
        def preencher_e_ler(self, page, sol):
            page.goto((FIX / "passo1.html").as_uri())
            self.preencher_por_rotulo(page, "Rótulo Inexistente", "x")  # deve falhar alto
    ctx = DriverContext(screenshot_dir=str(tmp_path))
    with pytest.raises(IntervencaoNecessaria):
        _Quebrado(usuario="u", senha="s")(None, ctx)
    assert any(tmp_path.iterdir())  # screenshot salvo
```

Registre o marker em `pytest.ini`: `markers = playwright: requer navegador Playwright`.

- [ ] **Step 3: Rodar e ver falhar** → FAIL (`playwright_base` inexistente).

- [ ] **Step 4: Implementar a base**

```python
# app/motor/playwright_base.py
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from app.motor.base import SolicitacaoSimulacao
from app.motor.drivers import (
    DriverContext, ErroTransitorio, IntervencaoNecessaria, ResultadoDriver)


class PlaywrightBankDriver:
    provedor: str = "base"

    def __init__(self, usuario: str = "", senha: str = "", timeout_ms: int = 30000):
        self.usuario, self.senha, self.timeout_ms = usuario, senha, timeout_ms

    # ganchos que cada banco implementa
    def login(self, page, usuario, senha): raise NotImplementedError
    def preencher_e_ler(self, page, sol) -> list[ResultadoDriver]: raise NotImplementedError

    def preencher_por_rotulo(self, page, rotulo, valor):
        loc = page.get_by_label(rotulo, exact=False)
        if loc.count() == 0:
            raise IntervencaoNecessaria("campo_nao_encontrado", f"rotulo ausente: {rotulo}")
        loc.first.fill(str(valor))

    def _screenshot(self, page, ctx, motivo):
        if ctx and ctx.screenshot_dir:
            Path(ctx.screenshot_dir).mkdir(parents=True, exist_ok=True)
            nome = f"{self.provedor}-{motivo}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}.png"
            page.screenshot(path=str(Path(ctx.screenshot_dir) / nome))

    def __call__(self, sol: SolicitacaoSimulacao, ctx: DriverContext | None = None):
        from playwright.sync_api import sync_playwright, Error as PWError
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                self.login(page, self.usuario, self.senha)
                return self.preencher_e_ler(page, sol)
            except IntervencaoNecessaria:
                self._screenshot(page, ctx, "intervencao"); raise
            except PWError as e:
                self._screenshot(page, ctx, "erro")
                raise ErroTransitorio("portal_indisponivel", str(e)[:200])
            finally:
                browser.close()
```

- [ ] **Step 5: Rodar e ver passar** → `pytest -m playwright tests/test_playwright_base.py -v` PASS. Suíte geral verde (testes playwright pulam se marker não coletado; garanta que `pytest -q` não quebra sem browser — ver Step 6).

- [ ] **Step 6: Skip gracioso sem browser** — em `tests/conftest.py`, adicione um hook que dá `skip` nos testes `@pytest.mark.playwright` se o Chromium não estiver instalado (tente `sync_playwright().start()` num try/except no início da sessão). Rode `pytest -q` e confirme verde.

- [ ] **Step 7: Commit**

```bash
git add app/motor/playwright_base.py tests/test_playwright_base.py tests/fixtures/banco_fake/ tests/conftest.py pytest.ini
git commit -m "feat(motor): PlaywrightBankDriver base (login/ancora/screenshot/mapeamento)"
```

---

### Task 9: `SantanderDriver` — Passo 1 contra fixture + esqueleto dos passos 2–5

**Files:**
- Create: `app/motor/santander.py`, `tests/fixtures/santander/passo1.html`
- Test: `tests/test_santander_driver.py`

**Interfaces:**
- Consumes: `PlaywrightBankDriver` (Task 8), contrato (Task 1), `config.SANTANDER_LOGIN_URL`/`PRAZOS_PADRAO`.
- Produces: `class SantanderDriver(PlaywrightBankDriver)` com `provedor = "santander"`; `login` (URL do config, rótulos "Usuário"/"Senha"); `preencher_e_ler` que preenche o Passo 1 (CPF, Data de nascimento, CNH, Placa, UF, Finalidade, aceite) e lê a(s) parcela(s).

> **Passos 2–5 (entrada/prazo/plano → oferta):** os seletores exatos **não são conhecíveis sem o portal**. Procedimento de mapeamento (parte da execução desta task):
> 1. Rodar `.\.venv\Scripts\python.exe -m playwright codegen https://financiamentos.santander.com.br/originacao-auto/login` e fazer uma simulação real à mão.
> 2. Salvar o HTML de cada passo em `tests/fixtures/santander/passoN.html`.
> 3. Implementar cada passo em `preencher_e_ler` **ancorando no texto visível** (rótulo/placeholder), nunca em classe/div.
> Esta task entrega o **Passo 1 testado contra fixture** (concreto abaixo) + os métodos `_passo2..5` chamando o mesmo helper `preencher_por_rotulo`, preenchidos com os rótulos capturados no codegen.

- [ ] **Step 1: Fixture do Passo 1** (rótulos reais do dump do portal)

```html
<!-- tests/fixtures/santander/passo1.html -->
<label>Digite o CPF ou CNPJ do cliente<input aria-label="CPF ou CNPJ do cliente"></label>
<label>Data de nascimento<input aria-label="Data de nascimento"></label>
<fieldset><legend>Cliente possui CNH?</legend>
  <button aria-label="CNH Sim">Sim</button><button aria-label="CNH Não">Não</button></fieldset>
<label>Placa<input aria-label="Placa"></label>
<label>Licenciamento<input aria-label="Licenciamento" value="SAO PAULO"></label>
<fieldset><legend>Finalidade</legend>
  <button aria-label="Comum">Comum</button><button aria-label="PCD">PCD</button></fieldset>
<button aria-label="Concordar e Continuar">Concordar e Continuar</button>
<div id="oferta" data-parcela="1320.00" data-taxa="1.90" data-prazo="48"></div>
```

- [ ] **Step 2: Escrever o teste do Passo 1**

```python
# tests/test_santander_driver.py
import pytest
from pathlib import Path
from decimal import Decimal
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import DriverContext
from app.motor.santander import SantanderDriver

pytestmark = pytest.mark.playwright
FIX = Path(__file__).parent / "fixtures" / "santander"


def _sol():
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-01-01", cnh=True),
        veiculo=Veiculo(placa="ABC1D23", uf_licenciamento="SP", finalidade="comum"),
        condicoes=Condicoes(entrada=1000, prazos_meses=[48]))


class _SantanderFixture(SantanderDriver):
    def login(self, page, usuario, senha):  # no teste, não bate no portal real
        page.goto((FIX / "passo1.html").as_uri())
    def _abrir_simulacao(self, page):  # já estamos na página de fixture
        pass


def test_santander_preenche_passo1_e_le_oferta(tmp_path):
    res = _SantanderFixture(usuario="u", senha="s")(_sol(), DriverContext(screenshot_dir=str(tmp_path)))
    assert res[0].provedor == "santander"
    assert res[0].valor_parcela == Decimal("1320.00")
    assert res[0].prazo_meses == 48
```

- [ ] **Step 3: Rodar e ver falhar** → FAIL (`santander` inexistente).

- [ ] **Step 4: Implementar o driver (Passo 1 concreto; ganchos 2–5)**

```python
# app/motor/santander.py
from decimal import Decimal
from app import config
from app.motor.drivers import ResultadoDriver
from app.motor.playwright_base import PlaywrightBankDriver


class SantanderDriver(PlaywrightBankDriver):
    provedor = "santander"

    def login(self, page, usuario, senha):
        page.goto(config.SANTANDER_LOGIN_URL)
        self.preencher_por_rotulo(page, "Usuário", usuario)
        self.preencher_por_rotulo(page, "Senha", senha)
        page.get_by_role("button", name="Entrar").click()

    def _abrir_simulacao(self, page):
        page.get_by_role("link", name="Simulação").click()

    def preencher_e_ler(self, page, sol):
        self._abrir_simulacao(page)
        self._passo1(page, sol)
        # _passo2..5 preenchidos com os rótulos do codegen (entrada/prazo/plano):
        # self._passo2(page, sol) ...
        return self._ler_ofertas(page, sol)

    def _passo1(self, page, sol):
        self.preencher_por_rotulo(page, "CPF ou CNPJ do cliente", sol.pessoa.cpf)
        self.preencher_por_rotulo(page, "Data de nascimento", sol.pessoa.nascimento)
        page.get_by_label("CNH Sim" if sol.pessoa.cnh else "CNH Não").click()
        self.preencher_por_rotulo(page, "Placa", sol.veiculo.placa or "")
        page.get_by_label("PCD" if sol.veiculo.finalidade == "pcd" else "Comum").click()
        page.get_by_role("button", name="Concordar e Continuar").click()

    def _ler_ofertas(self, page, sol) -> list[ResultadoDriver]:
        el = page.locator("#oferta")
        return [ResultadoDriver(
            "santander", "concluida",
            valor_parcela=Decimal(el.get_attribute("data-parcela")),
            taxa_am=Decimal(el.get_attribute("data-taxa")),
            prazo_meses=int(el.get_attribute("data-prazo")))]
```

> Na execução real, `_ler_ofertas` itera os prazos de `config.PRAZOS_PADRAO`/`sol.condicoes.prazos_meses` conforme o portal (uma tela com vários prazos → parse da tabela; um por vez → repetir o passo do prazo). Decisão registrada como questão aberta no spec; resolver com o HTML capturado.

- [ ] **Step 5: Rodar e ver passar** → `pytest -m playwright tests/test_santander_driver.py -v` PASS; `pytest -q` verde.

- [ ] **Step 6: Commit**

```bash
git add app/motor/santander.py tests/test_santander_driver.py tests/fixtures/santander/
git commit -m "feat(motor): SantanderDriver passo 1 (fixture) + esqueleto do wizard"
```

---

### Task 10: Registrar o Santander como driver real + saúde da credencial

**Files:**
- Modify: `app/motor/santander.py` (fábrica), `app/motor/drivers.py` (registro em `REAL_DRIVERS`), `app/processamento.py` (login success/fail → credenciais)
- Test: `tests/test_santander_integrado.py`

**Interfaces:**
- Consumes: `REAL_DRIVERS` (Task 6), `credenciais.registrar_sucesso_login/registrar_falha_login` (Task 11).
- Produces: `construir_santander(db, cliente_id) -> Driver` que injeta usuário/senha da credencial e chama `registrar_sucesso_login`/`registrar_falha_login` conforme o login; entrada em `REAL_DRIVERS["santander"]`.

- [ ] **Step 1: Escrever o teste** (usa o Santander de fixture + credencial real na base; monkeypatcha o browser para não bater no portal)

```python
# tests/test_santander_integrado.py — esboço concreto
# 1. cria cliente + credencial santander via credenciais.upsert_credencial
# 2. cria job provedores=["santander"], reserva
# 3. monkeypatcha REAL_DRIVERS["santander"] para uma fábrica que devolve um driver
#    de fixture que "loga com sucesso" e devolve 3 prazos
# 4. processa e assere: 3 ResultadoORM 'concluida' + cred.ultimo_sucesso_em preenchido
```

Escreva o teste completo seguindo esse roteiro, reutilizando as fixtures de db/cliente e
`credenciais.upsert_credencial`, e asserindo `db.get(CredencialProvedorORM,...).ultimo_sucesso_em is not None`.

- [ ] **Step 2: Rodar e ver falhar** → FAIL.

- [ ] **Step 3: Implementar a fábrica e o registro**

```python
# app/motor/santander.py — adicionar
from app import credenciais


def construir_santander(db, cliente_id):
    seg = credenciais.obter_segredo_para_uso(db, cliente_id, "santander")
    usuario, senha = seg if seg else ("", "")
    driver = SantanderDriver(usuario=usuario, senha=senha)

    def _com_saude(sol, ctx=None):
        try:
            res = driver(sol, ctx)
            credenciais.registrar_sucesso_login(db, cliente_id, "santander")
            return res
        except Exception as e:
            codigo = getattr(e, "codigo", type(e).__name__)
            credenciais.registrar_falha_login(db, cliente_id, "santander", codigo)
            raise
    return _com_saude
```

```python
# app/motor/drivers.py — no fim do módulo (evita import circular; importe dentro de função se preciso)
def _registrar_reais():
    from app.motor.santander import construir_santander
    REAL_DRIVERS["santander"] = lambda db, cliente_id: construir_santander(db, cliente_id)
```

> Ajuste `resolver_drivers` para chamar `REAL_DRIVERS[nome](db, cliente_id)` (fábrica recebe db+cliente_id). Atualize o teste da Task 6 conforme essa assinatura de fábrica. Garanta `_registrar_reais()` seja chamado na carga do app (ex.: em `main.py`/`worker.py` no startup).

- [ ] **Step 4: Rodar e ver passar** → PASS; `pytest -q` verde.

- [ ] **Step 5: Commit**

```bash
git add app/motor/santander.py app/motor/drivers.py app/processamento.py tests/test_santander_integrado.py
git commit -m "feat(motor): registra Santander como driver real + saude da credencial"
```

---

### Task 11: Smoke live (gated) + RUNBOOK

**Files:**
- Create: `tests/test_santander_live.py`, `deploy/motor-standalone/RUNBOOK.md` (append seção)
- Test: o próprio arquivo (gated por env)

**Interfaces:**
- Consumes: tudo acima + credencial real da loja (fora do git).

- [ ] **Step 1: Teste live gated**

```python
# tests/test_santander_live.py
import os
import pytest

pytestmark = [pytest.mark.playwright,
              pytest.mark.skipif(os.getenv("MOTOR_SANTANDER_LIVE") != "1",
                                 reason="smoke live off (defina MOTOR_SANTANDER_LIVE=1 e credenciais)")]


def test_login_e_simulacao_reais():
    from app.motor.santander import SantanderDriver
    from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
    from app.motor.drivers import DriverContext
    d = SantanderDriver(usuario=os.environ["SANTANDER_USER"], senha=os.environ["SANTANDER_PASS"])
    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf=os.environ["SANTANDER_CPF_TESTE"], nascimento=os.environ["SANTANDER_NASC_TESTE"], cnh=True),
        veiculo=Veiculo(placa=os.environ["SANTANDER_PLACA_TESTE"], uf_licenciamento="SP", finalidade="comum"),
        condicoes=Condicoes(entrada=0, prazos_meses=[48]))
    res = d(sol, DriverContext(screenshot_dir="data/screenshots"))
    assert res and res[0].valor_parcela is not None
```

- [ ] **Step 2: Rodar (fica skipped por padrão)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_santander_live.py -v` → SKIPPED.
(Rodar de verdade só manualmente, com `MOTOR_SANTANDER_LIVE=1` + envs, contra o portal real.)

- [ ] **Step 3: RUNBOOK** — em `deploy/motor-standalone/RUNBOOK.md`, seção "Driver real Santander": como cadastrar a credencial (endpoint `PUT /v1/provedores/santander/credenciais`, Task 11), como rodar o codegen para (re)mapear o wizard, como rodar o smoke live, e o aviso de ToS/fragilidade.

- [ ] **Step 4: Commit**

```bash
git add tests/test_santander_live.py deploy/motor-standalone/RUNBOOK.md
git commit -m "test(motor): smoke live gated do Santander + RUNBOOK do driver real"
```

---

## Self-Review (feita)

- **Cobertura do spec:** contrato estendido (T1), colunas/migration (T2), API/criação (T3), interface comum + DriverContext (T4), multi-prazo (T5), gating por credencial `real:true` (T6), Playwright+infra (T7), base reutilizável (T8), SantanderDriver + âncoras/screenshot (T9), registro real + saúde da credencial via Task 11 (T10), testes fixtures + smoke live + RUNBOOK (T11). Mapeamento de desfechos coberto em T4/T8. `ApiBankDriver` é fora desta fase (futuro) — documentado no spec.
- **Placeholders:** os passos 2–5 do wizard dependem de HTML privado do portal — tratados por procedimento de codegen explícito (T9), não por "TODO". Todo o resto tem código real.
- **Consistência de tipos:** `Driver` retorna único|lista, normalizado em `_executar_driver` (T4) e consumido como lista em `processar_job` (T5); `REAL_DRIVERS[nome]` é fábrica `(db, cliente_id) -> Driver` (T6/T10, alinhados); `DriverContext(db, cliente_id, screenshot_dir)` usado em T5/T8/T9/T10.

## Fora desta fase (próximos planos)

- **Fase 2 (coleta):** Chatbot (WhatsApp) e Portal coletam CNH/UF/finalidade e repassam ao Motor.
- **Fase 3 (hardening):** rename do mock para `BancoDemo …`; retenção/mascaramento de screenshots; métricas por banco.
- **Outros bancos:** cada um herda `PlaywrightBankDriver` (ou `ApiBankDriver` se houver API), plano próprio.

## Requisitos de produto (dono — 2026-07-13, em curso)

### Portal: ver simulações rodando ao vivo

- [ ] **Lista ao vivo** em `/app/simulacoes` (ou aba “Em andamento”): todos os jobs
  `recebida` / `processando` do cliente, não só o job da aba atual.
- [ ] Cada linha: id curto, placa/valor, bancos pedidos, status, tempo desde criação,
  link para `/app/simulacoes/job/{id}` (tela de progresso que já auto-atualiza).
- [ ] Quando multi-banco: progresso **por provedor** (Santander processando, Bradesco na fila…).
- [ ] Jobs terminais recentes (concluída/falhou/parcial) na mesma lista com filtro “hoje”.
- [ ] Fonte: `GET` Motor (lista de simulações do cliente) — se não existir endpoint de listagem,
  criar no #1A (`GET /v1/simulacoes?status=…`) e consumir no Portal BFF.

### Motor: um Playwright **por banco** (não um browser compartilhado)

- [x] Princípio documentado na base `PlaywrightBankDriver`: cada driver Playwright abre
  **seu próprio** `chromium.launch` + contexto (isolamento de sessão/cookie/storage).
- [ ] Em job multi-provedor (ex.: Santander + Bradesco RPA + …), o worker deve poder
  executar drivers Playwright **em paralelo** (thread/process pool limitado), **um browser
  por banco**, com teto de concorrência (ex.: max 2–3 Chromium no worker para não estourar RAM).
- [ ] Drivers `ApiBankDriver` não abrem browser; rodam em paralelo com os RPA sem contenda de sessão.
- [ ] Rate-limit **por provedor** (não martelar o mesmo portal com N abas no mesmo browser).
- [ ] Aceite: simulação com 2+ bancos RPA ⇒ N processos/browsers distintos; falha de um banco
  não derruba os outros (status `parcial`).

### Incidentes operacionais conhecidos

- **2026-07-13:** job Santander live retornou `portal_falhou` / screenshot **Access Denied**
  (Akamai EdgeSuite) com **headless_shell**. Credencial e Motor OK.
- **Mitigação aplicada (mesmo dia):** worker com **browser headed + Xvfb**
  (`MOTOR_BROWSER_HEADLESS=0`, `PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0`, entrypoint
  `scripts/worker-entrypoint.sh`), stealth (UA/CH/webdriver/plugins), digitação com delay,
  `shm_size=1gb`, volume de `storage_state`. Probe: login **Portal Auto** OK (sem Access Denied).
  Se ainda bloquear: IP/datacenter na denylist Akamai (proxy residencial / rodar worker no host).
