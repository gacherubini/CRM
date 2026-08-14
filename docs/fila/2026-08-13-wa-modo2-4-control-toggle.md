# Modo 2 / Card 4 — Toggle `whatsapp_modo` no Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Tornar o modo de WhatsApp uma **escolha por loja no Revy Control** (1 XOR 2), propagada ao
`chatbot-api` pelo mesmo transporte que já leva status e módulos — e fechar o gate do Modo 2, que
hoje ainda não sabe qual é o modo da loja.

**Architecture:** `lojas` ganha a coluna `whatsapp_modo` (1 ou 2, default 1). O provisionamento
emite isso como **mais um aggregate** no snapshot (`aggregate="whatsapp_modo"`, `state="1"|"2"`),
reusando outbox e projeção existentes — zero encanamento novo. No chatbot, `loja_opera_modo2` passa
a exigir esse aggregate igual a `"2"`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, pytest. Control (`revy-trafego/`) e um ajuste no
`chatbot-api/`.

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §5.8 (Control escolhe, Loja opera), §2 (1 XOR 2), §6.3 (flag).

## Pré-requisito

**Card 2** feito: a Task 4 daqui altera `loja_opera_modo2`, criada lá.

## Correção que este card fecha

O `loja_opera_modo2` do card 2 checa **flag + loja ativa** — e mais nada. Com a flag ligada, uma
loja **Modo 1** entraria no rodízio. Isso não é bug do card 2: o conceito de modo só nasce aqui.
A Task 4 fecha o buraco, e é obrigatória antes de ligar a flag em qualquer ambiente com mais de
uma loja.

## Global Constraints

- **1 XOR 2, nunca os dois** (§2). A restrição é de banco (`CHECK`), não só de UI.
- **Trocar o modo não migra conversa antiga** (§5.8). Nada de backfill, nada de mexer em conversa.
- **O Control não opera QR nem fila** (§5.8). Aqui só se escolhe o modo; a fila é do chatbot
  (card 2) e a tela é da Loja.
- **Default é 1.** Toda loja existente continua no comportamento de hoje sem backfill semântico.
- **Migration aditiva.** O Control não faz downgrade: o padrão do repo é
  `raise RuntimeError(...)` no `downgrade`, com rollback por feature flag
  (`alembic/versions/0018_copiloto_modulo.py`).
- Rodar testes **a partir da pasta do produto**. O dono usa **Mac e Windows**: macOS
  `.venv/bin/python -m pytest -q`; Windows `.\.venv\Scripts\python.exe -m pytest -q`.

---

### Task 1: Coluna `whatsapp_modo` em `lojas`

**Files:**
- Modify: `revy-trafego/app/models.py` (classe `Loja:34`)
- Create: `revy-trafego/alembic/versions/0019_loja_whatsapp_modo.py`
- Test: `revy-trafego/tests/test_loja_whatsapp_modo.py`

**Interfaces:**
- Produces: `Loja.whatsapp_modo: int` — `1` (Baileys + grupo) ou `2` (central Cloud), default `1`,
  com `CheckConstraint("whatsapp_modo IN (1, 2)")`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# revy-trafego/tests/test_loja_whatsapp_modo.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Loja


def test_loja_nasce_no_modo_1(db):
    loja = Loja(slug="loja-modo", nome="Loja Modo", status="ativa", versao=1)
    db.add(loja)
    db.commit()
    assert loja.whatsapp_modo == 1


def test_modo_2_e_aceito(db):
    loja = Loja(
        slug="loja-cloud", nome="Loja Cloud", status="ativa", versao=1, whatsapp_modo=2
    )
    db.add(loja)
    db.commit()
    assert loja.whatsapp_modo == 2


def test_modo_invalido_e_rejeitado_pelo_banco(db):
    """1 XOR 2 é restrição de banco, não só de UI (spec §2)."""
    db.add(Loja(slug="loja-x", nome="X", status="ativa", versao=1, whatsapp_modo=3))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
```

> Confirme o nome da fixture de sessão em `revy-trafego/tests/conftest.py` e os campos
> obrigatórios de `Loja` (`slug`, `nome`, `status`, `versao`) — use o mesmo helper de criação de
> loja que os testes de `stores` já usam, se existir, em vez de montar o objeto à mão.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd revy-trafego && .venv/bin/python -m pytest tests/test_loja_whatsapp_modo.py -q`
— Windows: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_loja_whatsapp_modo.py -q`
Esperado: `TypeError: 'whatsapp_modo' is an invalid keyword argument`.

- [ ] **Step 3: Implementar no model**

Em `app/models.py`, na classe `Loja`, junto dos outros campos:

```python
    # 1 = Baileys + grupo (legado). 2 = central Cloud API. Nunca os dois:
    # a spec dos dois modos é explícita em 1 XOR 2 por loja. Default 1 para
    # que toda loja existente siga no comportamento de hoje sem backfill.
    whatsapp_modo: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
```

E em `__table_args__`, junto dos outros `CheckConstraint`:

```python
        CheckConstraint(
            "whatsapp_modo IN (1, 2)",
            name="ck_lojas_whatsapp_modo",
        ),
```

- [ ] **Step 4: Escrever a migration**

```python
# revy-trafego/alembic/versions/0019_loja_whatsapp_modo.py
"""Loja escolhe o modo de WhatsApp (1 Baileys+grupo, 2 central Cloud).

Revision ID: 0019_loja_whatsapp_modo
Revises: 0018_copiloto_modulo

Spec dos dois modos, §5.8: o tipo de atendimento e escolha do Control, por
loja, e 1 XOR 2 — nunca os dois. Server default 1 para que toda loja
existente continue no comportamento de hoje: o backfill e semanticamente
correto, nao um chute.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0019_loja_whatsapp_modo"
down_revision = "0018_copiloto_modulo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("lojas") as batch_op:
        batch_op.add_column(
            sa.Column(
                "whatsapp_modo",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.create_check_constraint(
            "ck_lojas_whatsapp_modo", "whatsapp_modo IN (1, 2)"
        )


def downgrade() -> None:
    raise RuntimeError(
        "Migration aditiva do Revy Control: use as feature flags para rollback."
    )
```

- [ ] **Step 5: Rodar migration e testes**

Run: `cd revy-trafego && .venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/test_loja_whatsapp_modo.py -q`
— Windows: `cd revy-trafego && alembic upgrade head && .\.venv\Scripts\python.exe -m pytest tests/test_loja_whatsapp_modo.py -q`
Esperado: PASS nos 3 testes.

- [ ] **Step 6: Commit**

```bash
git add revy-trafego/app/models.py revy-trafego/alembic/versions/0019_loja_whatsapp_modo.py revy-trafego/tests/test_loja_whatsapp_modo.py
git commit -m "feat(control): coluna whatsapp_modo por loja"
```

---

### Task 2: Emitir `whatsapp_modo` no snapshot de provisionamento

**Files:**
- Modify: `revy-trafego/app/control/provisioning.py` (`snapshot:58-100`)
- Test: `revy-trafego/tests/test_provisioning_whatsapp_modo.py`

**Interfaces:**
- Produces: mais um envelope em `snapshot(...).operational`, com
  `aggregate="whatsapp_modo"`, `state="1"` ou `"2"`, `version=store.versao`.

**Por que aggregate e não módulo:** módulo é ligado/desligado; modo é **1 XOR 2**. Modelar como dois
módulos mutuamente exclusivos criaria um estado inválido representável (ambos ligados, ambos
desligados). Como aggregate, o valor é único por construção — e a projeção
`LojaOperacionalProjecao` do chatbot já aceita qualquer aggregate, então **nenhum encanamento novo**
é preciso: outbox, versionamento e idempotência vêm de graça.

- [ ] **Step 1: Escrever o teste que falha**

```python
# revy-trafego/tests/test_provisioning_whatsapp_modo.py
def test_snapshot_traz_o_modo_como_aggregate(db, loja_ativa, provisioning_service):
    snapshot = provisioning_service.snapshot(loja_ativa.ref)
    modos = [e for e in snapshot.operational if e.aggregate == "whatsapp_modo"]
    assert len(modos) == 1
    assert modos[0].state == "1"


def test_modo_2_aparece_no_snapshot(db, loja_ativa, provisioning_service):
    loja_ativa.whatsapp_modo = 2
    db.commit()
    snapshot = provisioning_service.snapshot(loja_ativa.ref)
    modo = next(e for e in snapshot.operational if e.aggregate == "whatsapp_modo")
    assert modo.state == "2"


def test_aggregate_loja_continua_existindo(db, loja_ativa, provisioning_service):
    """Regressão: o envelope novo não pode substituir o de status da loja."""
    snapshot = provisioning_service.snapshot(loja_ativa.ref)
    assert any(e.aggregate == "loja" for e in snapshot.operational)
```

> As fixtures `loja_ativa` e `provisioning_service` podem não existir com esses nomes. Antes de
> escrever, abra `revy-trafego/tests/` e use as que os testes de provisionamento já usam para montar
> loja e serviço — não crie fixture nova nem instancie o serviço à mão.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd revy-trafego && .venv/bin/python -m pytest tests/test_provisioning_whatsapp_modo.py -q`
— Windows: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_provisioning_whatsapp_modo.py -q`
Esperado: FAIL — nenhum envelope com `aggregate == "whatsapp_modo"`.

- [ ] **Step 3: Implementar**

Em `provisioning.py`, dentro de `snapshot`, logo depois do envelope de `aggregate="loja"`:

```python
            operational.append(
                _envelope(
                    db,
                    loja_id=store.id,
                    # Aggregate e não módulo: modo é 1 XOR 2, não ligado/desligado.
                    # Dois módulos exclusivos deixariam "ambos" representável.
                    aggregate="whatsapp_modo",
                    version=store.versao,
                    state=str(store.whatsapp_modo),
                    effective_at=store.atualizada_em,
                    resource_type="loja",
                    resource_id=store.id,
                )
            )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd revy-trafego && .venv/bin/python -m pytest tests/test_provisioning_whatsapp_modo.py tests/ -k provisioning -q`
— Windows: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_provisioning_whatsapp_modo.py tests/ -k provisioning -q`
Esperado: PASS, e os testes de provisionamento existentes continuam verdes — inclusive os que
conferem o hash composto das versões (`provisioning_outbox.py:76-81`), que agora inclui um
aggregate a mais. **Se algum deles quebrar por causa do hash**, o teste é que precisa reconhecer o
aggregate novo, não o código.

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/control/provisioning.py revy-trafego/tests/test_provisioning_whatsapp_modo.py
git commit -m "feat(control): whatsapp_modo no snapshot de provisionamento"
```

---

### Task 3: Escolher o modo na ficha da loja

**Files:**
- Modify: `revy-trafego/app/control/stores.py` (ação nova)
- Modify: o template da ficha da loja (aba WhatsApp / prontidão)
- Modify: `revy-trafego/app/config.py` (flag)
- Test: `revy-trafego/tests/test_stores_whatsapp_modo.py`

**Interfaces:**
- Produces: `definir_whatsapp_modo(db, loja_id, modo, *, ator) -> Loja` — valida `modo in (1, 2)`,
  incrementa `Loja.versao` (senão a projeção do chatbot ignora o evento, que é monotônica por
  versão) e grava auditoria.
- Flag `REVY_CONTROL_WHATSAPP_MODO2_ENABLED` default OFF: com ela desligada, a opção "central
  Cloud" **não aparece** e a rota recusa `modo=2`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# revy-trafego/tests/test_stores_whatsapp_modo.py
import pytest

from app.control.stores import definir_whatsapp_modo


def test_troca_para_modo_2_incrementa_a_versao(db, loja_ativa, ator_admin, monkeypatch):
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", True)
    versao_antes = loja_ativa.versao

    loja = definir_whatsapp_modo(db, loja_ativa.id, 2, ator=ator_admin)

    assert loja.whatsapp_modo == 2
    # Sem bump, a projeção monotônica do chatbot descarta o evento.
    assert loja.versao > versao_antes


def test_flag_off_recusa_modo_2(db, loja_ativa, ator_admin, monkeypatch):
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", False)
    with pytest.raises(ValueError):
        definir_whatsapp_modo(db, loja_ativa.id, 2, ator=ator_admin)
    assert loja_ativa.whatsapp_modo == 1


def test_modo_invalido_e_recusado(db, loja_ativa, ator_admin, monkeypatch):
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", True)
    with pytest.raises(ValueError):
        definir_whatsapp_modo(db, loja_ativa.id, 3, ator=ator_admin)


def test_voltar_para_modo_1_bumpa_a_versao_de_novo(db, loja_ativa, ator_admin, monkeypatch):
    """Ida e volta. Cada troca é um evento novo para a projeção do chatbot.

    Sem o segundo bump, o chatbot ficaria no modo 2 para sempre: a projeção é
    monotônica e descartaria a volta com a mesma versão.
    """
    monkeypatch.setattr("app.control.stores.config.WHATSAPP_MODO2_ENABLED", True)
    versao_inicial = loja_ativa.versao

    definir_whatsapp_modo(db, loja_ativa.id, 2, ator=ator_admin)
    versao_no_modo_2 = loja_ativa.versao
    loja = definir_whatsapp_modo(db, loja_ativa.id, 1, ator=ator_admin)

    assert loja.whatsapp_modo == 1
    assert versao_no_modo_2 > versao_inicial
    assert loja.versao > versao_no_modo_2
```

> `ator_admin` e `loja_ativa` são as fixtures dos testes de `stores` — reuse as existentes. A
> auditoria usa o mesmo helper que as outras ações de loja em `app/control/audit.py`; confira o nome
> real antes de chamar.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd revy-trafego && .venv/bin/python -m pytest tests/test_stores_whatsapp_modo.py -q`
— Windows: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_stores_whatsapp_modo.py -q`
Esperado: `ImportError: cannot import name 'definir_whatsapp_modo'`.

- [ ] **Step 3: Implementar**

Em `app/config.py`:

```python
# Rollout do Modo 2 (central Cloud API). Default OFF: invariante do projeto.
WHATSAPP_MODO2_ENABLED = os.getenv("REVY_CONTROL_WHATSAPP_MODO2_ENABLED", "").lower() in {
    "1", "true", "yes",
}
```

Em `app/control/stores.py`:

```python
def definir_whatsapp_modo(db: Session, loja_id: str, modo: int, *, ator) -> Loja:
    """Escolhe o modo de WhatsApp da loja (spec §5.8).

    O Control **escolhe**; quem opera é a Loja e o chatbot. Aqui não se toca em
    QR, fila nem conversa: trocar o modo não migra conversa antiga.

    O bump de ``versao`` é obrigatório — a projeção do chatbot é monotônica por
    versão e descartaria um evento com a versão anterior, deixando a loja no
    modo velho sem erro nenhum aparecer.
    """
    if modo not in (1, 2):
        raise ValueError("modo de WhatsApp inválido: use 1 ou 2")
    if modo == 2 and not config.WHATSAPP_MODO2_ENABLED:
        raise ValueError("Modo 2 ainda não liberado neste ambiente")

    loja = db.get(Loja, loja_id)
    if loja is None:
        raise StoreNotFound("Loja não encontrada")

    loja.whatsapp_modo = modo
    loja.versao = loja.versao + 1
    db.commit()

    registrar_auditoria(
        db, ator=ator, acao="whatsapp_modo_definido",
        recurso="loja", recurso_id=loja.id, detalhe={"modo": modo},
    )
    return loja
```

Na ficha da loja (aba WhatsApp / prontidão), dois rádios — **Baileys + grupo** e **central Cloud
API** —, com o segundo só renderizado se `config.WHATSAPP_MODO2_ENABLED`. Ao lado, uma linha de
texto: *"Trocar o modo não migra conversas antigas."* Nada de QR e nada de fila nesta tela.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd revy-trafego && .venv/bin/python -m pytest tests/test_stores_whatsapp_modo.py -q`
— Windows: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest tests/test_stores_whatsapp_modo.py -q`
Esperado: PASS nos 4 testes.

- [ ] **Step 5: Commit**

```bash
git add revy-trafego/app/control/stores.py revy-trafego/app/config.py revy-trafego/tests/test_stores_whatsapp_modo.py
git commit -m "feat(control): escolher o modo de WhatsApp na ficha da loja"
```

---

### Task 4: Fechar o gate do chatbot — modo 2 de verdade

**Files:**
- Modify: `chatbot-api/app/rodizio.py` (`loja_opera_modo2`, card 2 Task 7)
- Test: `chatbot-api/tests/test_rodizio_gate.py` (acrescentar)

**Interfaces:**
- `loja_opera_modo2(db, loja_id)` passa a exigir **três** coisas: flag ligada, loja operacional, e
  projeção `whatsapp_modo == "2"`.

Sem isso, ligar a flag colocaria **toda** loja ativa no rodízio, inclusive as de Modo 1 — que não
têm central Cloud nenhuma e cujos vendedores nunca receberiam a oferta.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em chatbot-api/tests/test_rodizio_gate.py
from app.models_db import LojaOperacionalProjecao


def _projetar_modo(db, loja_id, modo: str):
    db.add(LojaOperacionalProjecao(
        loja_id=loja_id, aggregate="whatsapp_modo", version=1,
        state=modo, event_id=f"e-modo-{modo}",
    ))
    db.commit()


def test_loja_no_modo_1_nao_opera_o_rodizio(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo(db, loja_a["loja_id"], "1")
    assert loja_opera_modo2(db, loja_a["loja_id"]) is False


def test_loja_no_modo_2_opera(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _projetar_modo(db, loja_a["loja_id"], "2")
    assert loja_opera_modo2(db, loja_a["loja_id"]) is True


def test_sem_projecao_de_modo_nao_opera(db, loja_a, monkeypatch):
    """Fail-closed: sem o Control ter dito o modo, não entra no rodízio."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    assert loja_opera_modo2(db, loja_a["loja_id"]) is False
```

> Os testes das Tasks 4–6 do card 2, que hoje só ligam a flag, vão passar a precisar de
> `_projetar_modo(db, loja_a["loja_id"], "2")`. Acrescente a chamada neles — é a prova de que o
> gate ficou de verdade fail-closed.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_gate.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_gate.py -q`
Esperado: FAIL em `test_loja_no_modo_1_nao_opera_o_rodizio` e em
`test_sem_projecao_de_modo_nao_opera` — hoje o gate devolve `True` para os dois.

- [ ] **Step 3: Implementar**

```python
def loja_opera_modo2(db: Session, loja_id: str) -> bool:
    """Gate único do Modo 2 (spec §6.3 e §5.8).

    Três condições, todas fail-closed:

    1. flag de rollout ligada (invariante do projeto: default OFF);
    2. loja operacional — ``allows_processing`` já cobre suspensa e sem projeção;
    3. o Control projetou ``whatsapp_modo == "2"`` para esta loja.

    A terceira é o que impede uma loja Modo 1 de cair no rodízio quando a flag
    é ligada no ambiente: sem central Cloud, os vendedores dela nunca receberiam
    a oferta e o lead ficaria preso em ``aguardando``.
    """
    if not config.MODO2_ENABLED:
        return False
    if not allows_processing(db, loja_id):
        return False
    modo = db.get(LojaOperacionalProjecao, (loja_id, "whatsapp_modo"))
    return modo is not None and modo.state == "2"
```

Importar `LojaOperacionalProjecao` de `app.models_db`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
Esperado: suíte inteira verde, com os testes dos cards 2 e 2b ajustados para projetar o modo.

- [ ] **Step 5: Rodar a suíte do Control também**

Run: `cd revy-trafego && .venv/bin/python -m pytest -q && git diff --check && git status --short`
— Windows: `cd revy-trafego && .\.venv\Scripts\python.exe -m pytest -q`
Esperado: verde; nada de arquivo alheio no diff.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/rodizio.py chatbot-api/tests/test_rodizio_gate.py chatbot-api/tests/test_rodizio_store.py chatbot-api/tests/test_rodizio_trava.py chatbot-api/tests/test_rodizio_job.py
git commit -m "feat(chatbot): gate do Modo 2 exige o modo projetado pelo Control"
```

---

## Self-Review

- §5.8 modo mora só no Control, escolhido na ficha da loja: Tasks 1 e 3. **Coberto.**
- §2 1 XOR 2 garantido no banco: Task 1 (`CheckConstraint`). **Coberto.**
- §5.8 trocar o modo não migra conversa: Task 3 — a função só muda o campo e a versão; teste
  explícito de ida e volta. **Coberto.**
- §6.3 flag default OFF, nos dois produtos: Task 3 (Control) e card 2 Task 7 (chatbot).
  **Coberto.**
- §5.8 Control não opera QR nem fila: nada disso entra nesta tela — dito na Task 3.
- **Buraco fechado:** `loja_opera_modo2` agora exige o modo projetado (Task 4). Sem esta task,
  ligar a flag colocaria toda loja ativa no rodízio.
- **Fora deste card:** a projeção de saúde da central Cloud na ficha do Control (§5.8, coluna
  "Saúde da central Cloud. Sem QR"). É leitura de estado da Meta e não bloqueia o piloto —
  merece card próprio quando houver o que mostrar.
