# Worker Playwright em PC local — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer os drivers Playwright dos bancos rodarem num PC de gabinete com IP residencial, com fallback automático para o Fly, sem mudar o contrato `/v1/simulacoes`.

**Architecture:** O PC roda a imagem de produção do Motor como worker (`MOTOR_WORKER_TIPOS=playwright`), alcança o Postgres do Fly por um túnel WireGuard sidecar e drena a fila por `SELECT ... FOR UPDATE SKIP LOCKED`. O Fly deixa de acordar Machine na criação da simulação e passa a acordar só após uma carência, virando fallback. Uma coluna nova de `executor` permite comparar captcha entre PC e Fly.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Playwright/Chromium sob Xvfb, Docker Compose, WireGuard, pytest.

**Spec:** [`../specs/2026-08-12-worker-playwright-pc-local-design.md`](../specs/2026-08-12-worker-playwright-pc-local-design.md)

## Global Constraints

- **O contrato `/v1/simulacoes` não muda.** Nem request, nem response, nem códigos de status. Quem chama nunca sabe se rodou no PC, no Fly ou no mock.
- **Teto de 2 browsers simultâneos.** `MOTOR_MAX_BROWSER_WORKERS=2` é decisão anti-ban de captcha/IP, não limite de hardware. Não subir, nem no PC.
- **O cliente nunca vê mensagem técnica nem página bancária.** Só `codigo_erro` estável por provedor.
- **Segredo bancário não sai do Motor.** Nenhuma tarefa deste plano loga senha, CPF, HTML de portal ou `MOTOR_ENCRYPTION_KEY`.
- **Defaults preservam o comportamento atual.** Toda variável nova default para o valor que mantém produção idêntica a hoje. O corte é ligado por configuração, nunca por deploy de código.
- **Rodar testes a partir de `motor-simulacao/`**, senão o pacote `app` importado é o errado: `cd motor-simulacao && python -m pytest -q`.
- **Migrations:** conferir `alembic heads` antes; head atual é `0014`.
- Finalizar cada tarefa com `git diff --check` e `git status --short`; preservar mudanças alheias no worktree.

## Pré-requisito: Fase 0 é gate

**Não comece a Task 1 antes da Fase 0 passar.** Rode no PC de gabinete, fora do Docker e sem VPN, contra os portais reais:

```bash
cd motor-simulacao
python -m playwright install chromium
python scripts/probe_bradesco.py
python scripts/probe_santander_login.py
python scripts/probe_fontecred.py
python scripts/probe_pan_portal.py
```

Registre para cada banco: disparou captcha, sim ou não. Se disparar em todos, a causa raiz não era o IP e **este plano inteiro deve ser abandonado** — o custo evitado é o ponto do gate. Se não disparar em pelo menos um, siga, e a ordem da Task 7 é a ordem dos bancos que passaram.

---

### Task 1: Configuração nova e coluna `executor`

Sem medir onde a tarefa rodou é impossível provar ou refutar a hipótese. Esta tarefa vem primeiro porque tudo depois dela é medido por ela.

**Files:**
- Modify: `motor-simulacao/app/config.py`
- Modify: `motor-simulacao/app/models_db.py:206-221`
- Modify: `motor-simulacao/app/processamento.py:208-226`
- Create: `motor-simulacao/alembic/versions/0015_tentativa_executor.py`
- Test: `motor-simulacao/tests/test_executor_origem.py`
- Test: `motor-simulacao/tests/test_migration_tentativa_executor.py`

**Interfaces:**
- Consumes: nada.
- Produces: `config.FALLBACK_GRACE_SECONDS: int`, `config.EXECUTOR_ID: str`, `config.WORKER_EXCLUIR_PROVEDORES: frozenset[str]`, coluna `SimulacaoTentativaORM.executor: str | None`.

- [ ] **Step 1: Escreva o teste que falha (gravação do executor)**

Crie `motor-simulacao/tests/test_executor_origem.py`:

```python
"""Origem da execução (PC local vs Fly) gravada por tentativa."""
from __future__ import annotations

from app import config, processamento, servico
from app.models_db import SimulacaoTentativaORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo


def _sol(provedores=None) -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24]),
        provedores=provedores or ["mock"],
    )


def test_tentativa_grava_executor_configurado(db, monkeypatch):
    monkeypatch.setattr(config, "EXECUTOR_ID", "local-pc")
    sim, _ = servico.criar_simulacao(db, _sol(["mock"]), "c1")

    processamento._registrar_tentativa(db, sim.id, "mock", 1, 42, "concluida", None)
    db.commit()

    linha = (
        db.query(SimulacaoTentativaORM)
        .filter_by(simulacao_id=sim.id, provedor="mock")
        .one()
    )
    assert linha.executor == "local-pc"


def test_executor_default_nao_quebra_quando_env_ausente(db, monkeypatch):
    monkeypatch.setattr(config, "EXECUTOR_ID", "desconhecido")
    sim, _ = servico.criar_simulacao(db, _sol(["mock"]), "c1")

    processamento._registrar_tentativa(db, sim.id, "mock", 1, 5, "erro", "timeout")
    db.commit()

    linha = db.query(SimulacaoTentativaORM).filter_by(simulacao_id=sim.id).one()
    assert linha.executor == "desconhecido"
    assert linha.codigo_erro == "timeout"
```

- [ ] **Step 2: Rode e confirme que falha**

```bash
cd motor-simulacao && python -m pytest tests/test_executor_origem.py -q
```

Esperado: FAIL com `AttributeError: module 'app.config' has no attribute 'EXECUTOR_ID'`.

- [ ] **Step 3: Adicione as três variáveis em `app/config.py`**

Logo após a definição de `WORKER_TIPOS` (por volta da linha 114), acrescente:

```python
# --- Worker local em IP residencial ------------------------------------------
# Carência antes de o Fly assumir tarefa que o worker local não reservou.
# 0 = comportamento atual (acorda Machine imediatamente na criação).
FALLBACK_GRACE_SECONDS = max(0, int(os.getenv("MOTOR_FALLBACK_GRACE_SECONDS", "0")))

# Identifica ONDE a tentativa rodou. Base da comparação PC × Fly.
EXECUTOR_ID = ((os.getenv("MOTOR_EXECUTOR_ID") or "desconhecido").strip() or "desconhecido")[:40]

# Kill switch: provedores que ESTE worker não deve reservar (lista por vírgula).
_EXCLUIR_RAW = (os.getenv("MOTOR_WORKER_EXCLUIR_PROVEDORES") or "").strip().lower()
WORKER_EXCLUIR_PROVEDORES: frozenset[str] = frozenset(
    p.strip() for p in _EXCLUIR_RAW.split(",") if p.strip()
)
```

- [ ] **Step 4: Adicione a coluna no modelo**

Em `app/models_db.py`, dentro de `SimulacaoTentativaORM`, logo após o campo `codigo_erro`:

```python
    executor: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
```

- [ ] **Step 5: Preencha a coluna ao registrar a tentativa**

Em `app/processamento.py`, dentro de `_registrar_tentativa`, acrescente o campo ao `SimulacaoTentativaORM(...)`:

```python
            codigo_erro=codigo_erro,
            executor=config.EXECUTOR_ID,
```

- [ ] **Step 6: Rode o teste e confirme que passa**

```bash
cd motor-simulacao && python -m pytest tests/test_executor_origem.py -q
```

Esperado: 2 passed.

- [ ] **Step 7: Escreva a migration**

Confirme a head antes: `cd motor-simulacao && python -m alembic heads` deve imprimir `0014`.

Crie `motor-simulacao/alembic/versions/0015_tentativa_executor.py`:

```python
"""Origem da execução por tentativa (PC local vs Fly).

Revision ID: 0015
Revises: 0014
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulacao_tentativas",
        sa.Column("executor", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_simulacao_tentativas_executor", "simulacao_tentativas", ["executor"]
    )


def downgrade() -> None:
    op.drop_index("ix_simulacao_tentativas_executor", table_name="simulacao_tentativas")
    op.drop_column("simulacao_tentativas", "executor")
```

- [ ] **Step 8: Escreva o teste da migration**

Crie `motor-simulacao/tests/test_migration_tentativa_executor.py`:

```python
import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_adiciona_executor_e_reverte(tmp_path, monkeypatch):
    caminho = tmp_path / f"executor-{uuid.uuid4().hex}.db"
    url = f"sqlite:///{caminho.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")
    colunas = {
        c["name"]
        for c in inspect(create_engine(url)).get_columns("simulacao_tentativas")
    }
    assert "executor" in colunas

    command.downgrade(cfg, "0014")
    colunas_apos = {
        c["name"]
        for c in inspect(create_engine(url)).get_columns("simulacao_tentativas")
    }
    assert "executor" not in colunas_apos
```

- [ ] **Step 9: Rode a suíte inteira**

```bash
cd motor-simulacao && python -m pytest -q
```

Esperado: todos passando. A coluna é nullable, então nenhum teste antigo quebra.

- [ ] **Step 10: Commit**

```bash
git add motor-simulacao/app/config.py motor-simulacao/app/models_db.py \
        motor-simulacao/app/processamento.py \
        motor-simulacao/alembic/versions/0015_tentativa_executor.py \
        motor-simulacao/tests/test_executor_origem.py \
        motor-simulacao/tests/test_migration_tentativa_executor.py
git commit -m "feat(motor): registra executor por tentativa e config do worker local"
```

---

### Task 2: Kill switch por provedor (M4)

Precisa existir **antes** de o PC pegar tráfego, senão não há saída de emergência quando um driver quebrar lá.

**Files:**
- Modify: `motor-simulacao/app/processamento.py:643-662`
- Test: `motor-simulacao/tests/test_worker_kill_switch.py`

**Interfaces:**
- Consumes: `config.WORKER_EXCLUIR_PROVEDORES` (Task 1).
- Produces: `reservar_proxima_tarefa` passa a respeitar a exclusão. Assinatura inalterada.

- [ ] **Step 1: Escreva o teste que falha**

Crie `motor-simulacao/tests/test_worker_kill_switch.py`:

```python
"""Kill switch: worker local devolve um banco ao Fly sem parar os outros."""
from __future__ import annotations

from app import config, servico
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.processamento import reservar_proxima_tarefa


def _sol(provedores) -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24]),
        provedores=provedores,
    )


def test_provedor_excluido_nao_e_reservado(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "WORKER_EXCLUIR_PROVEDORES", frozenset({"bradesco"}))
    monkeypatch.setattr(config, "WORKER_PROVEDOR", None)
    servico.criar_simulacao(db, _sol(["bradesco"]), "c1")

    assert reservar_proxima_tarefa(db, tipos=frozenset({"playwright"})) is None


def test_exclusao_de_um_banco_nao_bloqueia_os_demais(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "WORKER_EXCLUIR_PROVEDORES", frozenset({"bradesco"}))
    monkeypatch.setattr(config, "WORKER_PROVEDOR", None)
    servico.criar_simulacao(db, _sol(["bradesco", "santander"]), "c1")

    tarefa = reservar_proxima_tarefa(db, tipos=frozenset({"playwright"}))
    assert tarefa is not None
    assert tarefa.provedor == "santander"


def test_exclusao_ignora_caixa_do_nome(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "WORKER_EXCLUIR_PROVEDORES", frozenset({"bradesco"}))
    monkeypatch.setattr(config, "WORKER_PROVEDOR", None)
    sim, _ = servico.criar_simulacao(db, _sol(["bradesco"]), "c1")
    tarefa_db = sim.tarefas_provedor[0]
    tarefa_db.provedor = "BRADESCO"
    db.commit()

    assert reservar_proxima_tarefa(db, tipos=frozenset({"playwright"})) is None


def test_sem_exclusao_reserva_normalmente(db, monkeypatch):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "WORKER_EXCLUIR_PROVEDORES", frozenset())
    monkeypatch.setattr(config, "WORKER_PROVEDOR", None)
    servico.criar_simulacao(db, _sol(["bradesco"]), "c1")

    tarefa = reservar_proxima_tarefa(db, tipos=frozenset({"playwright"}))
    assert tarefa is not None
    assert tarefa.provedor == "bradesco"
```

- [ ] **Step 2: Rode e confirme que falha**

```bash
cd motor-simulacao && python -m pytest tests/test_worker_kill_switch.py -q
```

Esperado: FAIL nos dois primeiros — a tarefa `bradesco` é reservada porque o filtro ainda não existe.

- [ ] **Step 3: Implemente o filtro**

Em `app/processamento.py`, adicione o import de `func` no bloco do SQLAlchemy:

```python
from sqlalchemy import func
from sqlalchemy.orm import Session
```

Em `reservar_proxima_tarefa`, logo depois do bloco `filtro_prov`:

```python
    filtro_prov = provedor or config.WORKER_PROVEDOR
    if filtro_prov:
        q = q.filter(SimulacaoProvedorORM.provedor == filtro_prov)
    if config.WORKER_EXCLUIR_PROVEDORES:
        q = q.filter(
            func.lower(SimulacaoProvedorORM.provedor).notin_(
                tuple(config.WORKER_EXCLUIR_PROVEDORES)
            )
        )
```

- [ ] **Step 4: Rode e confirme que passa**

```bash
cd motor-simulacao && python -m pytest tests/test_worker_kill_switch.py -q
```

Esperado: 4 passed.

- [ ] **Step 5: Rode a suíte inteira e commit**

```bash
cd motor-simulacao && python -m pytest -q
git add motor-simulacao/app/processamento.py motor-simulacao/tests/test_worker_kill_switch.py
git commit -m "feat(motor): kill switch por provedor no worker"
```

---

### Task 3: Carência antes do fallback do Fly (M1 + M2)

O sweeper de tarefa órfã **não precisa ser escrito**: `app/worker.py:73` já chama `acordar_workers` a cada ciclo no processo always-on do `app2037`. Com a carência aplicada dentro de `acordar_workers`, a chamada imediata de `app/servico.py:161` para de acordar o Fly, e a chamada periódica vira o sweeper. Esta tarefa é a carência mais o evento que torna o fallback visível.

**Files:**
- Modify: `motor-simulacao/app/orquestrador.py:16-30, 96-108`
- Test: `motor-simulacao/tests/test_fallback_carencia.py`

**Interfaces:**
- Consumes: `config.FALLBACK_GRACE_SECONDS` (Task 1).
- Produces: `acordar_workers` passa a devolver a chave `aguardando_carencia: int` no dicionário de contadores, além das existentes (`acordados`, `falhas`, `sem_slot`, `ignorados`, `aguardando`). Evento `fallback_fly_acionado` na timeline da simulação.

- [ ] **Step 1: Escreva o teste que falha**

Crie `motor-simulacao/tests/test_fallback_carencia.py`:

```python
"""Carência: o Fly só assume tarefa que o worker local não pegou a tempo."""
from __future__ import annotations

from datetime import timedelta

from app import config, servico
from app.lifecycle import FakeLifecycle
from app.models_db import SimulacaoEventoORM, SimulacaoProvedorORM
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.orquestrador import acordar_workers, upsert_slot


def _sol(provedores) -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24]),
        provedores=provedores,
    )


def _preparar(db, monkeypatch, carencia: int):
    monkeypatch.setattr(config, "FANOUT_ENABLED", True)
    monkeypatch.setattr(config, "FLY_AUTOSCALE_ENABLED", True)
    monkeypatch.setattr(config, "MAX_BROWSER_WORKERS", 2)
    monkeypatch.setattr(config, "FALLBACK_GRACE_SECONDS", carencia)
    upsert_slot(db, provedor="bradesco", fly_machine_id="m-bra", tipo_driver="playwright")


def _envelhecer(db, sim_id: str, segundos: int) -> None:
    tarefa = (
        db.query(SimulacaoProvedorORM).filter_by(simulacao_id=sim_id).one()
    )
    tarefa.criada_em = tarefa.criada_em - timedelta(seconds=segundos)
    db.commit()


def test_tarefa_nova_nao_acorda_o_fly(db, monkeypatch):
    """O PC precisa da janela para pegar o job antes do Fly."""
    _preparar(db, monkeypatch, carencia=180)
    sim, _ = servico.criar_simulacao(db, _sol(["bradesco"]), "c1")

    fake = FakeLifecycle()
    res = acordar_workers(db, simulacao_id=sim.id, lifecycle=fake)

    assert res["acordados"] == 0
    assert res["aguardando_carencia"] == 1
    assert fake.started == []


def test_tarefa_alem_da_carencia_acorda_o_fly(db, monkeypatch):
    """PC desligado: ninguém reservou, o Fly assume."""
    _preparar(db, monkeypatch, carencia=180)
    sim, _ = servico.criar_simulacao(db, _sol(["bradesco"]), "c1")
    _envelhecer(db, sim.id, 200)

    fake = FakeLifecycle()
    res = acordar_workers(db, lifecycle=fake)

    assert res["acordados"] == 1
    assert fake.started == ["m-bra"]


def test_fallback_registra_evento_para_alerta(db, monkeypatch):
    _preparar(db, monkeypatch, carencia=180)
    sim, _ = servico.criar_simulacao(db, _sol(["bradesco"]), "c1")
    _envelhecer(db, sim.id, 200)

    acordar_workers(db, lifecycle=FakeLifecycle())

    etapas = {
        e.etapa
        for e in db.query(SimulacaoEventoORM).filter_by(simulacao_id=sim.id).all()
    }
    assert "fallback_fly_acionado" in etapas


def test_carencia_zero_preserva_comportamento_atual(db, monkeypatch):
    """Default de produção hoje: acorda na hora, sem esperar."""
    _preparar(db, monkeypatch, carencia=0)
    sim, _ = servico.criar_simulacao(db, _sol(["bradesco"]), "c1")

    fake = FakeLifecycle()
    res = acordar_workers(db, simulacao_id=sim.id, lifecycle=fake)

    assert res["acordados"] == 1
    assert res["aguardando_carencia"] == 0
    assert fake.started == ["m-bra"]
```

- [ ] **Step 2: Rode e confirme que falha**

```bash
cd motor-simulacao && python -m pytest tests/test_fallback_carencia.py -q
```

Esperado: FAIL com `KeyError: 'aguardando_carencia'`.

- [ ] **Step 3: Implemente a carência**

Em `app/orquestrador.py`, adicione o helper logo após `_rewake_stale` (por volta da linha 62):

```python
def _com_tz(momento: datetime) -> datetime:
    """SQLite devolve datetime naive; normaliza para UTC antes de comparar."""
    return momento.replace(tzinfo=timezone.utc) if momento.tzinfo is None else momento


def _passou_carencia(tarefa: SimulacaoProvedorORM, agora: datetime) -> bool:
    """False enquanto o worker local ainda tem janela para reservar a tarefa.

    Carência 0 = comportamento anterior (Fly acorda imediatamente).
    """
    if config.FALLBACK_GRACE_SECONDS <= 0:
        return True
    if tarefa.criada_em is None:
        return True
    idade = (agora - _com_tz(tarefa.criada_em)).total_seconds()
    return idade >= config.FALLBACK_GRACE_SECONDS
```

Em `acordar_workers`, acrescente a chave nova ao dicionário `resultado`:

```python
    resultado = {
        "acordados": 0,
        "falhas": 0,
        "sem_slot": 0,
        "ignorados": 0,
        # Tarefas já acordadas há pouco, aguardando o worker reservar (não re-acorda).
        "aguardando": 0,
        # Tarefas ainda dentro da janela do worker local (IP residencial).
        "aguardando_carencia": 0,
    }
```

E, logo depois de `tarefas = q.order_by(...).all()` e do `if not tarefas: return resultado`, filtre:

```python
    agora = _agora()
    maduras = []
    for t in tarefas:
        if _passou_carencia(t, agora):
            maduras.append(t)
        else:
            resultado["aguardando_carencia"] += 1
    if not maduras:
        return resultado
    for t in maduras:
        _registrar_evento_sim(
            db,
            t.simulacao_id,
            "fallback_fly_acionado",
            f"Worker local não reservou {t.provedor} na carência; Fly assume.",
            "aviso",
            provedor=t.provedor,
        )
    db.commit()
    tarefas = maduras
```

O evento só é registrado quando a carência está ligada; com `FALLBACK_GRACE_SECONDS=0` toda tarefa é madura desde o nascimento e o evento vira ruído. Guarde o bloco:

```python
    if config.FALLBACK_GRACE_SECONDS > 0:
        for t in maduras:
            _registrar_evento_sim(...)
        db.commit()
```

- [ ] **Step 4: Rode e confirme que passa**

```bash
cd motor-simulacao && python -m pytest tests/test_fallback_carencia.py -q
```

Esperado: 4 passed.

- [ ] **Step 5: Rode a suíte de workers, que é a mais exposta a esta mudança**

```bash
cd motor-simulacao && python -m pytest tests/test_workers_ondemand.py tests/test_fanout.py -q
```

Esperado: todos passando. Se algum falhar, é porque assume wake imediato — confirme que o teste roda com `FALLBACK_GRACE_SECONDS=0` (default) antes de alterar o teste.

- [ ] **Step 6: Suíte inteira e commit**

```bash
cd motor-simulacao && python -m pytest -q
git add motor-simulacao/app/orquestrador.py motor-simulacao/tests/test_fallback_carencia.py
git commit -m "feat(motor): carencia antes do fallback do Fly e evento de acionamento"
```

---

### Task 4: Retry com taxonomia (M3)

**Files:**
- Modify: `motor-simulacao/app/processamento.py:40, 293-359`
- Modify: `motor-simulacao/app/config.py:18`
- Test: `motor-simulacao/tests/test_retry_taxonomia.py`

**Interfaces:**
- Consumes: nada das tarefas anteriores.
- Produces: `MAX_TENTATIVAS_DRIVER = 3`; `CODIGOS_NUNCA_REPETIR: frozenset[str]` exportado de `app/processamento.py`.

- [ ] **Step 1: Escreva o teste que falha**

Crie `motor-simulacao/tests/test_retry_taxonomia.py`:

```python
"""O que repete 3x e o que morre na primeira.

Repetir rejeição de negócio é gastar tempo pela mesma resposta; repetir captcha
manda o caso difícil para o ambiente mais fraco; repetir credencial inválida
BLOQUEIA A CONTA BANCÁRIA da loja.
"""
from __future__ import annotations

import pytest

from app import processamento, servico
from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
from app.motor.drivers import (
    ErroTransitorio,
    IntervencaoNecessaria,
    RejeicaoNegocio,
)


def _sol() -> SolicitacaoSimulacao:
    return SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24]),
        provedores=["mock"],
    )


class _DriverContador:
    """Driver falso que conta invocações e levanta a exceção pedida."""

    def __init__(self, excecao):
        self.chamadas = 0
        self._excecao = excecao

    def simular(self, solicitacao, contexto=None):
        self.chamadas += 1
        raise self._excecao


def _rodar(db, driver):
    sim, _ = servico.criar_simulacao(db, _sol(), "c1")
    return processamento._executar_driver_com_retry(db, sim, "mock", driver, _sol())


def test_erro_transitorio_repete_tres_vezes(db):
    driver = _DriverContador(ErroTransitorio("indisponivel_temporario"))
    resultados = _rodar(db, driver)
    assert driver.chamadas == 3
    assert resultados[0].status == "erro"


def test_rejeicao_negocio_nao_repete(db):
    driver = _DriverContador(RejeicaoNegocio("score_insuficiente"))
    resultados = _rodar(db, driver)
    assert driver.chamadas == 1
    assert resultados[0].status == "rejeitada"
    assert resultados[0].codigo_erro == "score_insuficiente"


def test_captcha_nao_repete(db):
    """Mandar captcha para o datacenter é levar o caso difícil ao IP pior."""
    driver = _DriverContador(IntervencaoNecessaria("captcha_login"))
    resultados = _rodar(db, driver)
    assert driver.chamadas == 1
    assert resultados[0].status == "aguardando_intervencao"


def test_credencial_invalida_nao_repete_mesmo_sendo_transitoria(db):
    """3 logins errados bloqueiam a conta da loja em todos os bancos."""
    driver = _DriverContador(ErroTransitorio("credencial_invalida"))
    resultados = _rodar(db, driver)
    assert driver.chamadas == 1
    assert resultados[0].status == "erro"
    assert resultados[0].codigo_erro == "credencial_invalida"


def test_erro_inesperado_repete_tres_vezes(db):
    driver = _DriverContador(RuntimeError("browser sumiu"))
    resultados = _rodar(db, driver)
    assert driver.chamadas == 3
    assert resultados[0].codigo_erro == "erro_inesperado"


def test_timeout_de_driver_default_caiu_para_240(monkeypatch):
    """3 × 420s eram 21 minutos de espera para um lead no WhatsApp."""
    monkeypatch.delenv("MOTOR_DRIVER_TIMEOUT_SECONDS", raising=False)
    import importlib

    from app import config as config_mod

    recarregado = importlib.reload(config_mod)
    assert recarregado.DRIVER_TIMEOUT_SECONDS == 240
    importlib.reload(config_mod)
```

- [ ] **Step 2: Rode e confirme que falha**

```bash
cd motor-simulacao && python -m pytest tests/test_retry_taxonomia.py -q
```

Esperado: FAIL — `chamadas == 2` onde se espera 3, e credencial inválida repetindo.

- [ ] **Step 3: Suba o teto de tentativas e declare os códigos terminais**

Em `app/processamento.py`, substitua a linha 40:

```python
MAX_TENTATIVAS_DRIVER = 3

# Códigos que NUNCA repetem, mesmo vindo como ErroTransitorio: repetir login
# errado bloqueia a conta bancária da loja e derruba todos os bancos de uma vez.
CODIGOS_NUNCA_REPETIR = frozenset(
    {"credencial_invalida", "login_invalido", "sem_driver_ou_credencial"}
)
```

- [ ] **Step 4: Curto-circuito no ramo de erro transitório**

Em `_executar_driver_com_retry`, no `except (ErroTransitorio, TimeoutError)`, troque o corpo por:

```python
        except (ErroTransitorio, TimeoutError) as e:
            dur = int((time.perf_counter() - inicio) * 1000)
            codigo = getattr(e, "codigo", "timeout")
            _registrar_tentativa(db, sim.id, nome, tentativa, dur, "erro_transitorio", codigo)
            if codigo in CODIGOS_NUNCA_REPETIR:
                return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro=codigo)]
            if tentativa >= MAX_TENTATIVAS_DRIVER:
                return [ResultadoDriver(nome, "erro", prazo_meses=prazo, codigo_erro=codigo)]
```

`RejeicaoNegocio` e `IntervencaoNecessaria` já retornam na primeira iteração — não precisam de mudança. `DriverDeadlineExceeded` também já retorna direto, e isso é intencional: o driver queimou o orçamento inteiro de 240s, repetir custa mais 8 minutos com chance baixa.

- [ ] **Step 5: Baixe o timeout default**

Em `app/config.py:18`:

```python
DRIVER_TIMEOUT_SECONDS = int(os.getenv("MOTOR_DRIVER_TIMEOUT_SECONDS", "240"))
```

Leia o comentário da linha 34 (`Folga sob o deadline do driver`) e ajuste os valores derivados se ele fixar números que assumiam 420s.

- [ ] **Step 6: Rode e confirme que passa**

```bash
cd motor-simulacao && python -m pytest tests/test_retry_taxonomia.py -q
```

Esperado: 6 passed.

- [ ] **Step 7: Suíte inteira e commit**

```bash
cd motor-simulacao && python -m pytest -q
git add motor-simulacao/app/processamento.py motor-simulacao/app/config.py \
        motor-simulacao/tests/test_retry_taxonomia.py
git commit -m "feat(motor): retry 3x so para erro tecnico e timeout de 240s"
```

---

### Task 5: Observabilidade por executor

**Files:**
- Modify: `motor-simulacao/app/observabilidade.py:81-108`
- Test: `motor-simulacao/tests/test_observabilidade.py`

**Interfaces:**
- Consumes: coluna `SimulacaoTentativaORM.executor` (Task 1).
- Produces: chave `por_executor` no dicionário de métricas, no formato `{executor: {provedor: {status: contagem}}}`.

- [ ] **Step 1: Escreva o teste que falha**

Acrescente ao fim de `motor-simulacao/tests/test_observabilidade.py`:

```python
def test_metricas_separam_captcha_por_executor(db):
    """Sem separar por origem é impossível comparar PC e Fly."""
    from app import observabilidade
    from app.models_db import SimulacaoTentativaORM
    from app.motor.base import Condicoes, Pessoa, SolicitacaoSimulacao, Veiculo
    from app import servico

    sol = SolicitacaoSimulacao(
        pessoa=Pessoa(cpf="52998224725", nascimento="1990-05-20"),
        veiculo=Veiculo(categoria="moto", valor=20000),
        condicoes=Condicoes(entrada=2000, prazos_meses=[24]),
        provedores=["mock"],
    )
    sim, _ = servico.criar_simulacao(db, sol, "c1")
    db.add_all(
        [
            SimulacaoTentativaORM(
                simulacao_id=sim.id, provedor="bradesco", tentativa=1,
                duracao_ms=10, status="aguardando_intervencao",
                codigo_erro="captcha_login", executor="fly-motor2037",
            ),
            SimulacaoTentativaORM(
                simulacao_id=sim.id, provedor="bradesco", tentativa=1,
                duracao_ms=10, status="concluida", codigo_erro=None,
                executor="local-pc",
            ),
        ]
    )
    db.commit()

    metricas = observabilidade.metricas(db)

    assert metricas["por_executor"]["fly-motor2037"]["bradesco"]["aguardando_intervencao"] == 1
    assert metricas["por_executor"]["local-pc"]["bradesco"]["concluida"] == 1
```

Antes de rodar, abra `app/observabilidade.py` e confirme o nome real da função de entrada (o teste acima assume `metricas(db)`); se o nome for outro, use o nome real no teste e mantenha o resto igual.

- [ ] **Step 2: Rode e confirme que falha**

```bash
cd motor-simulacao && python -m pytest tests/test_observabilidade.py -q
```

Esperado: FAIL com `KeyError: 'por_executor'`.

- [ ] **Step 3: Implemente a agregação**

Em `app/observabilidade.py`, ao lado da consulta que já agrupa tentativas (linha ~81), adicione:

```python
    por_executor: dict[str, dict[str, dict[str, int]]] = {}
    linhas_executor = (
        db.query(
            SimulacaoTentativaORM.executor,
            SimulacaoTentativaORM.provedor,
            SimulacaoTentativaORM.status,
            func.count(),
        )
        .group_by(
            SimulacaoTentativaORM.executor,
            SimulacaoTentativaORM.provedor,
            SimulacaoTentativaORM.status,
        )
        .all()
    )
    for executor, provedor, status, quantidade in linhas_executor:
        chave = executor or "desconhecido"
        por_executor.setdefault(chave, {}).setdefault(provedor, {})[status] = int(quantidade)
```

E inclua `"por_executor": por_executor` no dicionário devolvido.

- [ ] **Step 4: Rode e confirme que passa**

```bash
cd motor-simulacao && python -m pytest tests/test_observabilidade.py -q
```

Esperado: todos passando.

- [ ] **Step 5: Suíte inteira e commit**

```bash
cd motor-simulacao && python -m pytest -q
git add motor-simulacao/app/observabilidade.py motor-simulacao/tests/test_observabilidade.py
git commit -m "feat(motor): metricas de tentativa separadas por executor"
```

---

### Task 6: Stack do PC — Compose com WireGuard sidecar

Esta tarefa é infraestrutura, não TDD: a verificação é o smoke, não o pytest. Só comece depois da Fase 0 ter passado.

**Files:**
- Create: `deploy/worker-local/docker-compose.yml`
- Create: `deploy/worker-local/.env.example`
- Create: `deploy/worker-local/README.md`
- Modify: `.gitignore` (garantir `deploy/worker-local/.env`)

**Interfaces:**
- Consumes: variáveis da Task 1 e o kill switch da Task 2.
- Produces: stack executável no PC. Nenhum código Python.

- [ ] **Step 1: Gere o peer WireGuard**

Na máquina que já tem o `fly` CLI autenticado:

```bash
fly wireguard create pessoal gru pc-gabinete ./wg-pc-gabinete.conf
```

Guarde o `.conf` — ele contém chave privada. Nunca versionar.

- [ ] **Step 2: Descubra o host interno do Postgres**

```bash
fly status -a suite-pg
```

O `DATABASE_URL` do worker usará o host `.internal` da rede privada. Confirme o valor exato no secret já existente do `app2037`:

```bash
fly secrets list -a app2037
```

Não imprima o valor do secret em log nem cole em documento.

- [ ] **Step 3: Escreva o `.env.example`**

Crie `deploy/worker-local/.env.example`:

```bash
# Preencha e salve como .env (NUNCA versionar este arquivo preenchido).
# Postgres do Fly, alcançado pelo túnel WireGuard.
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@suite-pg.internal:5432/motor

# OBRIGATÓRIO idêntico ao do app2037, senão as credenciais não abrem.
MOTOR_ENCRYPTION_KEY=

# Identifica esta máquina na medição PC x Fly.
MOTOR_EXECUTOR_ID=local-pc

# Só drivers de browser. Driver de API (Credere, Pan, BV) fica no Fly.
MOTOR_WORKER_TIPOS=playwright

# OBRIGATÓRIO 0: sem isso o worker sai exit 0 e ninguém o reinicia.
MOTOR_WORKER_IDLE_STOP_SECONDS=0

# Vazio de propósito: o PC pega TODOS os provedores playwright (decisão D2).
# Definir aqui ligaria WORKER_ON_DEMAND e o PC passaria a acordar Machines do Fly.
MOTOR_WORKER_PROVEDOR=

# Kill switch: bancos que voltam ao Fly. Vazio = nenhum.
MOTOR_WORKER_EXCLUIR_PROVEDORES=

# Teto anti-ban de captcha/IP. NÃO SUBIR.
MOTOR_MAX_BROWSER_WORKERS=2

# Headed sob Xvfb: Akamai bloqueia headless_shell.
MOTOR_BROWSER_HEADLESS=0
PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL=0
MOTOR_DRIVER_TIMEOUT_SECONDS=240
MOTOR_ENV=production
```

- [ ] **Step 4: Escreva o Compose**

Crie `deploy/worker-local/docker-compose.yml`:

```yaml
# Worker Playwright em IP residencial. Sem Postgres e sem API locais:
# o banco é o suite-pg do Fly, alcançado pelo sidecar WireGuard.
services:
  wireguard:
    image: lscr.io/linuxserver/wireguard:latest
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    sysctls:
      - net.ipv4.conf.all.src_valid_mark=1
      - net.ipv6.conf.all.disable_ipv6=0
    volumes:
      - ./wg-pc-gabinete.conf:/config/wg_confs/wg0.conf:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wg show wg0 >/dev/null 2>&1"]
      interval: 10s
      timeout: 5s
      retries: 6

  motor-worker:
    build: ../../motor-simulacao
    command: ["/srv/scripts/worker-entrypoint.sh"]
    # Compartilha a pilha de rede do túnel: resolve o IPv6 do 6PN sem depender
    # do NAT do WSL2, que não roteia IPv6 de forma confiável.
    network_mode: "service:wireguard"
    env_file: .env
    environment:
      - MOTOR_SCREENSHOT_DIR=/srv/data/screenshots
      - MOTOR_STORAGE_STATE_DIR=/srv/data/storage_state
      - DISPLAY=:99
    volumes:
      - motor_browser_data:/srv/data
    depends_on:
      wireguard:
        condition: service_healthy
    restart: unless-stopped
    # Chromium consome RAM; evita OOM silenciosa.
    shm_size: "1gb"

volumes:
  motor_browser_data:
```

`MOTOR_STORAGE_STATE_DIR` em volume nomeado é o que faz a sessão quente sobreviver a restart — sem ele o score do reCAPTCHA v3 nunca sobe e metade do ganho do IP residencial se perde.

- [ ] **Step 5: Garanta que o `.env` e o `.conf` não vão para o git**

Acrescente ao `.gitignore` da raiz:

```
deploy/worker-local/.env
deploy/worker-local/*.conf
```

Verifique:

```bash
cd /Users/gabrielabreucherubini/Documents/codigo/CRM
git check-ignore -v deploy/worker-local/.env deploy/worker-local/wg-pc-gabinete.conf
```

Esperado: ambas as linhas casando com uma regra. Se qualquer uma sair vazia, **pare** — está prestes a versionar segredo.

- [ ] **Step 6: Prepare o Windows**

Em PowerShell como administrador, no PC de gabinete:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 5
powercfg /hibernate off
powercfg /h off
```

Desative o Fast Startup em Painel de Controle → Opções de Energia → "Escolher a função dos botões de energia" → desmarcar "Ligar inicialização rápida".

Desative o gerenciamento de energia da placa de rede: Gerenciador de Dispositivos → adaptador de rede → Propriedades → Gerenciamento de Energia → desmarcar "O computador pode desligar este dispositivo".

Configure login automático via `netplwiz` (desmarcar "Os usuários devem digitar um nome de usuário e senha") e marque no Docker Desktop a opção "Start Docker Desktop when you log in".

Ligue o BitLocker no disco que hospeda o `.env`.

- [ ] **Step 7: Suba a stack e verifique o túnel**

```bash
cd deploy/worker-local
docker compose up -d
docker compose exec wireguard wg show
```

Esperado: interface `wg0` com um peer e handshake recente.

- [ ] **Step 8: Verifique que o worker alcança o banco**

```bash
docker compose logs motor-worker --tail 50
```

Esperado: linha `iniciado (intervalo=2s on_demand=False provedor=* ...)` e nenhuma exceção de conexão. `on_demand=False` é o esperado — se aparecer `True`, `MOTOR_WORKER_PROVEDOR` foi preenchido por engano e o PC vai acordar Machines do Fly contra si mesmo.

- [ ] **Step 9: Smoke com `mock`, sem gastar login de banco**

Crie uma simulação `mock` pela API do Fly e confirme que o resultado sai. Depois verifique a origem:

```sql
SELECT executor, provedor, status, count(*)
FROM simulacao_tentativas
WHERE criada_em > now() - interval '10 minutes'
GROUP BY 1,2,3;
```

Esperado: pelo menos uma linha com `executor = 'local-pc'`. Se vier só `fly-motor2037`, o PC não está reservando — confira `MOTOR_WORKER_TIPOS` e o kill switch.

- [ ] **Step 10: Escreva o README da stack e commit**

Crie `deploy/worker-local/README.md` com: o diagrama de rede do spec, a tabela de variáveis, os quatro comandos de energia do Windows, o procedimento de rotação da `MOTOR_ENCRYPTION_KEY`, e a armadilha do `MOTOR_WORKER_IDLE_STOP_SECONDS=0`. Aponte para o spec para o resto.

```bash
git add deploy/worker-local/docker-compose.yml deploy/worker-local/.env.example \
        deploy/worker-local/README.md .gitignore
git commit -m "feat(deploy): stack do worker Playwright local com WireGuard sidecar"
```

---

### Task 7: Corte do primeiro banco e medição

**Files:**
- Modify: secrets do `app2037` (não versionado)
- Modify: `deploy/worker-local/.env` (não versionado)
- Create: `docs/historico/2026-XX-XX-resultado-worker-ip-residencial.md`

**Interfaces:**
- Consumes: tudo das Tasks 1–6.
- Produces: a decisão de seguir para os demais bancos, ou de reverter.

- [ ] **Step 1: Registre o baseline ANTES de mexer em qualquer coisa**

```sql
SELECT provedor, codigo_erro, count(*)
FROM simulacao_tentativas
WHERE criada_em > now() - interval '30 days'
  AND codigo_erro IN ('captcha_login', 'portal_bloqueado')
GROUP BY 1,2 ORDER BY 3 DESC;
```

Salve o resultado. Sem baseline não existe comparação e a Fase 3 não conclui nada.

- [ ] **Step 2: Marque o executor do Fly**

```bash
fly secrets set MOTOR_EXECUTOR_ID=fly-motor2037 -a motor2037
fly secrets set MOTOR_EXECUTOR_ID=fly-app2037 -a app2037
```

- [ ] **Step 3: Ligue a carência no `app2037`**

```bash
fly secrets set MOTOR_FALLBACK_GRACE_SECONDS=180 -a app2037
```

Este é o momento do corte: a partir daqui o Fly espera 3 minutos antes de assumir. Confirme que o `app2037` reiniciou limpo e que `/health` responde.

- [ ] **Step 4: Deixe só o Bradesco no PC**

No `.env` do PC, exclua todos os outros bancos que ainda devem rodar no Fly:

```bash
MOTOR_WORKER_EXCLUIR_PROVEDORES=santander,fontecred,pan_portal
```

```bash
cd deploy/worker-local && docker compose up -d
```

- [ ] **Step 5: Rode uma simulação real de Bradesco e colete evidência**

Confirme, sem imprimir segredo: `/health` do Motor, os eventos do job na timeline, e as últimas 30 linhas de `docker compose logs motor-worker`.

- [ ] **Step 6: Deixe rodando alguns dias e compare**

```sql
SELECT executor, provedor, codigo_erro, count(*)
FROM simulacao_tentativas
WHERE criada_em > now() - interval '7 days'
  AND provedor = 'bradesco'
GROUP BY 1,2,3 ORDER BY 4 DESC;
```

**Critério de sucesso:** `captcha_login` de `local-pc` perto de zero, enquanto o baseline do Fly permanece. **Critério de falha:** taxa igual ou pior — nesse caso reverta `MOTOR_FALLBACK_GRACE_SECONDS=0`, desligue a stack do PC, e não faça a Fase 4.

- [ ] **Step 7: Registre o resultado e atualize o README do Motor**

Escreva o resultado medido em `docs/historico/`, e atualize a seção "Worker em IP residencial" de `motor-simulacao/README.md` de **PLANEJADO** para o estado real, movendo a narrativa para o histórico e deixando no README só as invariantes (é o corte que o CLAUDE.md exige: invariante fica, história sai).

```bash
git add motor-simulacao/README.md docs/historico/
git commit -m "docs(motor): resultado medido do worker em IP residencial"
```

---

## Self-Review

**Cobertura do spec:** M1 e M2 → Task 3 (colapsadas, porque `app/worker.py:73` já é o sweeper periódico). M3 → Task 4. M4 → Task 2. M5 → Task 1. Medição → Tasks 5 e 7. Máquina Windows, WireGuard, energia, autostart, segurança → Task 6. Fase 0 → seção de pré-requisito, como gate. Fase 4 (demais bancos) → sai por configuração na Task 7 (esvaziar `MOTOR_WORKER_EXCLUIR_PROVEDORES`), sem código novo, que é exatamente o ganho da decisão D2.

**Nomes consistentes:** `FALLBACK_GRACE_SECONDS`, `EXECUTOR_ID`, `WORKER_EXCLUIR_PROVEDORES`, `CODIGOS_NUNCA_REPETIR`, `_passou_carencia`, `aguardando_carencia`, `por_executor` — usados com a mesma grafia em todas as tarefas.

**Dois pontos que o implementador precisa confirmar no código antes de seguir**, sinalizados no próprio passo: o nome real da função de entrada de `app/observabilidade.py` (Task 5, Step 1) e se o comentário de folga em `app/config.py:34` fixa números derivados de 420s (Task 4, Step 5).

**Ordem:** Tasks 1 e 2 podem ir em paralelo com 3 e 4 depois da 1. A Task 6 só depende da 1 e da 2 para ser útil, mas o corte real (Task 7) exige todas.
