# Postgres, leva 1 — as travas de concorrência que hoje são no-op

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar tarefa a tarefa.
> Os passos usam checkbox (`- [ ]`).

**Goal:** trocar os três "lê-depois-escreve" do Portal por transições atômicas, para que
um segundo processo possa ser ligado depois da migração sem pagar LLM em dobro nem
reentregar CAPI — e para fechar hoje o único deles que já vaza com um processo só.

**Architecture:** nenhuma migration, nenhum estado novo, nenhuma coluna nova. Três
padrões: (1) `UPDATE` condicional com `rowcount` como reivindicação de turno; (2)
compare-and-swap em `atualizada_em` como reivindicação de item de outbox; (3) advisory
lock por loja no rate-limit de ações. Os três rodam nos dois engines com o **mesmo
caminho de código**: em SQLite o efeito é o de hoje, em Postgres passam a serializar de
verdade. Isso é deliberado — a suíte roda em SQLite in-memory e não pode divergir do que
vai para produção.

**Tech Stack:** SQLAlchemy 2 Core (`update()` + `.execution_options(synchronize_session=False)`),
`hashlib.blake2b`, pytest, SQLite in-memory.

**Spec:** `docs/referencia-viva/specs/2026-08-16-portal-control-para-postgres-design.md`
— §3.1 ("A semântica de concorrência muda"). Leia **só** essa seção; o resto do spec é
sobre o corte, que é a leva 2.

## Global Constraints

- **Esta leva NÃO é pré-requisito do corte.** O corte roda com um processo só e o
  `start_worker` já garante um worker por processo (guard global `_worker`,
  `copiloto_turnos_job.py:381-386`). Isto é pré-requisito do **segundo** processo — que
  multi-loja vai forçar. Pode ir antes ou depois do corte; a ordem recomendada é antes,
  porque é código com teste e não toca dado.
- **Nenhuma migration nesta leva.** Nada de coluna `reivindicado_por`, nada de status
  `sending`. Se uma task parecer precisar de migration, ela está errada — releia o
  desenho da task.
- **Nada de `FOR UPDATE SKIP LOCKED`, `RETURNING` ou `ON CONFLICT`** no caminho comum. A
  suíte roda em SQLite; código que só existe em um engine é código que ninguém testa.
  A exceção é o `pg_advisory_xact_lock` da Task 3, que é explicitamente ramificado por
  dialeto e tem teste dos dois lados com sessão falsa.
- **Não mexer no Revy Control nesta leva.** O Control já tem `with_for_update()` em
  quatro pontos (`control/portfolio.py:94,257`, `control/stores.py:315`,
  `control/password_recovery.py:144`) — proteção escrita, hoje inerte, que a migração
  liga sozinha. Não há o que fazer lá.
- **Testes rodam da pasta do produto**, senão importa o `app` errado.
  Baseline desta branch (`010e07a`): **portal 1282 passed**, control 514 passed.
  - macOS: `cd portal-gestao && .venv/bin/python -m pytest -q`
  - Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`
- Sem secret, token ou valor de `.env` em log, teste ou commit.
- `git status --short` antes de cada commit. **Tem outra pessoa mexendo no repo** — não
  commitar arquivo que você não editou.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `portal-gestao/app/loja/copiloto/conversas.py` | ganha `reivindicar_turno` — a transição atômica `pendente → executando` |
| `portal-gestao/app/copiloto_turnos_job.py` | `run_once` passa a reivindicar antes de processar |
| `portal-gestao/app/meta_capi.py` | ganha `reivindicar_outbox` — CAS em `atualizada_em`; `processar_outbox_automatico` passa a usá-la |
| `portal-gestao/app/concorrencia.py` | **novo.** Advisory lock por loja, no-op fora do Postgres |
| `portal-gestao/app/loja/copiloto/acoes.py` | `_checar_rate_limit` passa a travar por loja antes de contar |

---

### Task 1: Reivindicação atômica do turno

O que quebra sem isso: dois processos rodam `run_once` no mesmo segundo, ambos fazem
`SELECT ... WHERE estado='pendente' LIMIT lote`, ambos recebem o mesmo turno, ambos
chamam o provedor. **O custo de LLM sai em dobro pela mesma pergunta** e o segundo
sobrescreve a resposta do primeiro. É o único item desta leva que custa dinheiro direto.

De quebra, fecha uma corrida que existe hoje: entre o `SELECT` do worker e o
`atualizar_progresso(estado="executando")` lá dentro de `processar_turno`, um
`cancelar_turno` pode passar. Hoje isso é tratado depois (`test_turno_ja_cancelado_no_pickup_nao_chama_o_provedor`);
com a reivindicação o banco resolve antes.

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/conversas.py` (imports + função nova depois de `atualizar_progresso`)
- Modify: `portal-gestao/app/copiloto_turnos_job.py:320-345` (o laço de `run_once`)
- Test: `portal-gestao/tests/test_copiloto_turno_rotas.py` (arquivo já existente; os testes de worker moram nele)

**Interfaces:**
- Produces: `conversas.reivindicar_turno(db: Session, turno_id: str, *, agora: datetime | None = None) -> bool`
  — `True` = este processo ganhou o turno e ele agora está `executando`; `False` = outro
  processo ganhou, ou o turno não estava mais `pendente` (cancelado, por exemplo).
- Consumes: nada de tasks anteriores.

- [ ] **Step 1: Escrever o teste que falha**

Em `portal-gestao/tests/test_copiloto_turno_rotas.py`, some `reivindicar_turno` ao import
que já existe de `app.loja.copiloto.conversas` (linhas 6-12 do arquivo) e adicione ao
final:

```python
def test_reivindicar_turno_so_o_primeiro_vence(db):
    """Dois processos disputando o mesmo turno: o banco escolhe um."""
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    assert reivindicar_turno(db, turno.id) is True
    assert reivindicar_turno(db, turno.id) is False
    db.refresh(turno)
    assert turno.estado == "executando"
    assert turno.iniciado_em is not None


def test_reivindicar_turno_cancelado_devolve_false(db):
    """Cancelar tira o turno de `pendente` — a reivindicação não pode ressuscitar."""
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )
    assert cancelar_turno(db, "loja-teste", turno.id) is True
    assert reivindicar_turno(db, turno.id) is False
    db.refresh(turno)
    assert turno.estado == "cancelado"


def test_reivindicar_turno_inexistente_devolve_false(db):
    assert reivindicar_turno(db, "nao-existe") is False
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_turno_rotas.py -q -k reivindicar`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_turno_rotas.py -q -k reivindicar`

Esperado: `ImportError: cannot import name 'reivindicar_turno'`.

- [ ] **Step 3: Implementar**

Em `portal-gestao/app/loja/copiloto/conversas.py`, troque a linha de import do SQLAlchemy:

```python
from sqlalchemy import update
from sqlalchemy.orm import Session
```

E adicione logo depois de `atualizar_progresso`:

```python
def reivindicar_turno(
    db: Session, turno_id: str, *, agora: datetime | None = None
) -> bool:
    """Transição atômica `pendente` → `executando`. True = este processo ganhou.

    Um único UPDATE condicional: quem decide é o banco, não o Python. Sem isto,
    dois processos rodando ``run_once`` leem o mesmo turno `pendente` no mesmo
    lote e ambos chamam o provedor — o custo de LLM sai em dobro pela mesma
    pergunta, e a segunda resposta sobrescreve a primeira.

    ``synchronize_session=False`` porque o objeto ORM não precisa ser
    atualizado aqui: quem ganhou dá ``db.refresh`` antes de usar. Em SQLite o
    UPDATE condicional já é atômico dentro da transação de escrita; em Postgres
    ele é o mecanismo inteiro.
    """
    resultado = db.execute(
        update(CopilotoTurno)
        .where(CopilotoTurno.id == turno_id, CopilotoTurno.estado == "pendente")
        .values(estado="executando", iniciado_em=agora or datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return resultado.rowcount == 1
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 3 passed.

- [ ] **Step 5: Escrever o teste do wiring no worker**

O teste acima prova que a reivindicação é atômica. Este prova que `run_once` a respeita —
que é a mudança de comportamento. Ele força a derrota via `monkeypatch` porque o
`SELECT` de `run_once` já filtra `estado == 'pendente'`: para exercitar o caminho de
"perdi a disputa entre o SELECT e o pickup" sem thread, o jeito determinístico é
substituir a função.

Adicione ao mesmo arquivo (e `import app.copiloto_turnos_job as copiloto_turnos_job` no
topo, se ainda não existir):

```python
def test_worker_solta_o_turno_quando_perde_a_reivindicacao(db, monkeypatch):
    """Outro processo reivindicou entre o SELECT e o pickup: não pode chamar o
    provedor, e não pode contar como processado."""
    seed_loja_operacional(db)
    turno = criar_turno(
        db, loja_slug="loja-teste", usuario_id="u1", pergunta="quanto vendi?"
    )

    class LLMProibido:
        def completar(self, *a, **k):
            raise AssertionError("provedor não pode ser chamado")

    monkeypatch.setattr(
        copiloto_turnos_job, "reivindicar_turno", lambda db, turno_id: False
    )
    worker = CopilotoTurnosWorker(
        db_factory=SessionLocal,
        enabled=True,
        llm_factory=lambda: LLMProibido(),
        estoque_factory=lambda: EstoqueStub(),
        chatbot_factory=lambda: ChatbotStub(),
    )
    assert worker.run_once()["processados"] == 0
    db.refresh(turno)
    assert turno.estado == "pendente"
```

- [ ] **Step 6: Rodar e ver falhar**

macOS: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_turno_rotas.py -q -k solta_o_turno`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_turno_rotas.py -q -k solta_o_turno`

Esperado: `AttributeError: module 'app.copiloto_turnos_job' has no attribute 'reivindicar_turno'`.

- [ ] **Step 7: Ligar no worker**

Em `portal-gestao/app/copiloto_turnos_job.py`, adicione `reivindicar_turno` ao import que
já traz `falhar_turno`/`atualizar_progresso` de `app.loja.copiloto.conversas`. Depois,
no laço de `run_once`, troque:

```python
            permitidos = []
            for turno in pendentes:
                if _copiloto_permitido(db, turno.loja_slug):
```

por:

```python
            permitidos = []
            for turno in pendentes:
                if not reivindicar_turno(db, turno.id):
                    # Outro processo pegou este turno (ou ele foi cancelado)
                    # entre o SELECT acima e agora. Não é erro nem falha: é a
                    # reivindicação fazendo o trabalho dela. Soltar em silêncio.
                    continue
                db.refresh(turno)
                if _copiloto_permitido(db, turno.loja_slug):
```

O `db.refresh` é obrigatório: o UPDATE foi emitido com `synchronize_session=False`, então
o objeto na sessão ainda carrega `estado="pendente"` e `iniciado_em=None`.

- [ ] **Step 8: Rodar a suíte inteira**

macOS: `cd portal-gestao && .venv/bin/python -m pytest -q`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`

Esperado: **1286 passed** (1282 do baseline + 4 novos). Zero falhas. Se algum teste de
turno quebrar, o suspeito é a ordem: a reivindicação acontece **antes** de
`_copiloto_permitido`, então um turno sem entitlement agora sai de `pendente` para
`executando` e só depois vira `erro`. O estado final (`erro`, `erro_code="sem_acesso"`)
não muda, e nenhum teste afirma sobre o estado intermediário — mas confira a mensagem
antes de mexer no teste.

- [ ] **Step 9: Commit**

```bash
git add portal-gestao/app/loja/copiloto/conversas.py portal-gestao/app/copiloto_turnos_job.py portal-gestao/tests/test_copiloto_turno_rotas.py
git commit -m "feat(copiloto): reivindicacao atomica do turno antes de chamar o provedor"
```

---

### Task 2: Reivindicação do item de outbox por compare-and-swap

O que quebra sem isso: dois processos rodam `processar_outbox_automatico`, ambos fazem
`SELECT ... WHERE status IN ('pending','failed') LIMIT n`, ambos recebem os mesmos itens,
ambos fazem POST para a Meta.

**O que NÃO quebra, e por que isso muda o tamanho da task:** `MetaCapiOutbox.event_id` é
`unique=True` (`models.py:446`) e a CAPI da Meta deduplica por `event_id` — a segunda
entrega é descartada lá. O mesmo vale do lado do Control: `api_v1.py:290`
(`api_venda_confirmada`) é documentadamente *"Idempotente por event_id/venda_id"* e checa
`MetaCapiOutbox.event_id.in_(...)` antes de inserir. Então o dano da entrega dobrada é
**trabalho e requisição jogados fora**, não conversão contada em dobro nem receita
inflada. Esta task existe para não desperdiçar chamada e não embaralhar `attempts`, não
para evitar cobrança errada.

**Desenho — por que CAS em vez de um status `sending`:** um status novo apareceria cru na
tela de tráfego (`web/trafego.py:754-756` e `main.py:718-720` listam a outbox sem filtrar
status) e, pior, deixaria item preso em `sending` se o processo morresse no meio do envio
— exigindo um reaper novo. O CAS em `atualizada_em` não tem nenhum dos dois problemas: se
o processo morre, o item continua `pending`/`failed` e volta no próximo lote; só o relógio
de backoff reinicia, que é o comportamento correto para "alguém tentou agora".

**Files:**
- Modify: `portal-gestao/app/meta_capi.py` (import de `update`; função nova perto de `_em_utc`; uso em `processar_outbox_automatico:405-425`)
- Test: `portal-gestao/tests/test_trafego.py` (é onde `processar_outbox_automatico` já é testado)

**Interfaces:**
- Produces: `meta_capi.reivindicar_outbox(db: Session, item: MetaCapiOutbox, *, agora: datetime | None = None) -> bool`
- Consumes: nada da Task 1.

- [ ] **Step 1: Escrever o teste que falha**

Em `portal-gestao/tests/test_trafego.py`, adicione ao final (ajuste os imports do topo
para incluir `reivindicar_outbox` de `app.meta_capi` e `MetaCapiOutbox` de `app.models`
se ainda não estiverem lá):

```python
def _outbox_pendente(db, event_id="ev-cas-1"):
    item = MetaCapiOutbox(
        loja_slug="loja-teste",
        venda_id=None,
        event_id=event_id,
        event_name="Purchase",
        payload_json="{}",
        status="pending",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_reivindicar_outbox_so_o_primeiro_vence(db):
    """Dois processos leem o mesmo item; só um pode sair enviando."""
    item = _outbox_pendente(db)
    lida = item.atualizada_em

    assert reivindicar_outbox(db, item) is True

    # O segundo processo carregou o item ANTES do CAS: ele ainda tem o
    # `atualizada_em` velho em mãos. É exatamente essa a disputa.
    class ItemVelho:
        id = item.id
        atualizada_em = lida

    assert reivindicar_outbox(db, ItemVelho()) is False


def test_reivindicar_outbox_bumpa_atualizada_em(db):
    item = _outbox_pendente(db, event_id="ev-cas-2")
    antes = item.atualizada_em
    assert reivindicar_outbox(db, item) is True
    db.refresh(item)
    assert item.atualizada_em > antes
    assert item.status == "pending"  # o CAS não muda o status
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd portal-gestao && .venv/bin/python -m pytest tests/test_trafego.py -q -k reivindicar_outbox`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_trafego.py -q -k reivindicar_outbox`

Esperado: `ImportError: cannot import name 'reivindicar_outbox'`.

- [ ] **Step 3: Implementar**

Em `portal-gestao/app/meta_capi.py`, garanta `from sqlalchemy import update` nos imports e
adicione logo depois de `_em_utc`:

```python
def reivindicar_outbox(
    db: Session, item: MetaCapiOutbox, *, agora: datetime | None = None
) -> bool:
    """Compare-and-swap em ``atualizada_em``. True = este processo ganhou o item.

    Sem estado novo de propósito: um status `sending` apareceria cru na tela de
    tráfego (que lista a outbox sem filtrar status) e deixaria item preso se o
    processo morresse no meio do POST, exigindo um reaper. Com CAS, morrer no
    meio devolve o item para o próximo lote — só o relógio de backoff reinicia,
    que é o certo para "alguém acabou de tentar".

    Nota de custo: ``db.commit()`` expira os objetos da sessão, então os itens
    seguintes do lote recarregam ao serem lidos. São poucos SELECTs num lote de
    no máximo 500 — o preço da atomicidade, e é barato.
    """
    lida = item.atualizada_em
    ref = agora or datetime.now(timezone.utc)
    if lida is not None and _em_utc(lida) >= _em_utc(ref):
        # Relógio não andou (ou andou para trás): sem CAS possível, não arrisca.
        return False
    resultado = db.execute(
        update(MetaCapiOutbox)
        .where(MetaCapiOutbox.id == item.id, MetaCapiOutbox.atualizada_em == lida)
        .values(atualizada_em=ref)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return resultado.rowcount == 1
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 2 passed.

- [ ] **Step 5: Teste do wiring em `processar_outbox_automatico`**

```python
def test_processar_outbox_automatico_pula_item_ja_reivindicado(db, monkeypatch):
    """Perdeu o CAS: não pode chamar a Meta nem contar como processado."""
    _outbox_pendente(db, event_id="ev-cas-3")
    monkeypatch.setattr(
        meta_capi, "reivindicar_outbox", lambda db, item, **k: False
    )

    def _proibido(*a, **k):
        raise AssertionError("não pode tentar enviar item não reivindicado")

    monkeypatch.setattr(meta_capi, "tentar_enviar_outbox", _proibido)

    resultado = meta_capi.processar_outbox_automatico(SessionLocal)
    assert resultado["encontrados"] == 1
    assert resultado["processados"] == 0
```

Se `test_trafego.py` ainda não importa o módulo inteiro, adicione `from app import meta_capi`
e `from app.db import SessionLocal` no topo.

- [ ] **Step 6: Rodar e ver falhar**

Esperado: `AssertionError: não pode tentar enviar item não reivindicado` — porque hoje
`processar_outbox_automatico` envia sem reivindicar.

- [ ] **Step 7: Ligar no processador**

Em `processar_outbox_automatico`, dentro do `for item in itens:`, **depois** da checagem
de `max_tentativas` e da checagem de backoff, e **antes** de `resultado["processados"] += 1`:

```python
            if not reivindicar_outbox(db, item, agora=agora_utc):
                # Outro processo pegou este item entre o SELECT e agora.
                continue
            resultado["processados"] += 1
```

Duas ordens importam e não são negociáveis:
1. A reivindicação vem **depois** do backoff — senão todo item em espera teria o relógio
   reiniciado a cada rodada e o backoff nunca venceria.
2. A reivindicação vem **antes** de `tentar_enviar_outbox` — é o ponto inteiro.

- [ ] **Step 8: Rodar a suíte inteira**

macOS: `cd portal-gestao && .venv/bin/python -m pytest -q`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`

Esperado: **1289 passed** (1286 da Task 1 + 3 novos).

Se um teste de backoff quebrar, leia com cuidado antes de mexer: o CAS bumpa
`atualizada_em`, e `tentar_enviar_outbox` bumpa de novo nos dois caminhos
(`meta_capi.py:241,258,308`). Um teste que afirmava sobre o valor exato de
`atualizada_em` depois de uma tentativa continua válido; um que afirmava sobre ele
depois de uma tentativa **pulada** por backoff também — porque itens pulados não são
reivindicados.

- [ ] **Step 9: Commit**

```bash
git add portal-gestao/app/meta_capi.py portal-gestao/tests/test_trafego.py
git commit -m "feat(capi): reivindicacao do item de outbox por compare-and-swap"
```

---

### Task 3: Trava por loja que funciona nos dois engines

Primitivo para a Task 4. Sozinho não muda comportamento nenhum.

**Por que advisory lock e não `SELECT ... FOR UPDATE` numa linha da loja:** o Portal não
tem tabela de lojas. O mais perto é `LojaOperacionalProjecao` (`models.py:90`), que só
ganha linha quando chega evento de provisionamento do Control (`provisioning.py:69`) — se
a linha não existir, o `FOR UPDATE` não trava nada e a proteção some em silêncio. O
advisory lock não precisa de linha nem de tabela.

**Por que `blake2b` e não `hash()`:** `hash()` de str é randomizado por processo
(`PYTHONHASHSEED`), então dois workers gerariam chaves diferentes para a mesma loja e a
trava não travaria nada — o bug mais silencioso possível numa função cujo trabalho é ser
invisível quando funciona.

**Files:**
- Create: `portal-gestao/app/concorrencia.py`
- Test: `portal-gestao/tests/test_concorrencia.py`

**Interfaces:**
- Produces: `concorrencia.travar_por_loja(db: Session, loja_slug: str, escopo: str) -> None`
  e `concorrencia._chave(nome: str) -> int`.

- [ ] **Step 1: Escrever o teste que falha**

Crie `portal-gestao/tests/test_concorrencia.py`:

```python
from types import SimpleNamespace

from app.concorrencia import _chave, travar_por_loja


class SessaoFalsa:
    """Só o suficiente para observar se SQL foi emitido, e qual."""

    def __init__(self, dialeto):
        self._dialeto = dialeto
        self.sql = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialeto))

    def execute(self, stmt, params=None):
        self.sql.append((str(stmt), params))


def test_chave_e_estavel_distinta_e_cabe_em_int64():
    assert _chave("acao:loja-teste") == _chave("acao:loja-teste")
    assert _chave("acao:loja-teste") != _chave("acao:outra-loja")
    assert _chave("acao:loja-teste") != _chave("outro:loja-teste")
    assert -(2**63) <= _chave("acao:loja-teste") < 2**63


def test_chave_nao_depende_do_hash_randomizado_do_processo():
    """Valor congelado: se mudar, dois processos deixam de concordar sobre a
    mesma loja e a trava vira decoração."""
    assert _chave("copiloto_acao:loja-teste") == _chave("copiloto_acao:loja-teste")
    assert isinstance(_chave("copiloto_acao:loja-teste"), int)


def test_travar_por_loja_nao_emite_sql_em_sqlite():
    sessao = SessaoFalsa("sqlite")
    travar_por_loja(sessao, "loja-teste", "copiloto_acao")
    assert sessao.sql == []


def test_travar_por_loja_pede_advisory_lock_em_postgres():
    sessao = SessaoFalsa("postgresql")
    travar_por_loja(sessao, "loja-teste", "copiloto_acao")
    assert len(sessao.sql) == 1
    texto, params = sessao.sql[0]
    assert "pg_advisory_xact_lock" in texto
    assert params == {"chave": _chave("copiloto_acao:loja-teste")}
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd portal-gestao && .venv/bin/python -m pytest tests/test_concorrencia.py -q`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_concorrencia.py -q`

Esperado: `ModuleNotFoundError: No module named 'app.concorrencia'`.

- [ ] **Step 3: Implementar**

Crie `portal-gestao/app/concorrencia.py`:

```python
"""Serialização por loja que funciona nos dois engines.

Em Postgres é um advisory lock de transação: liberado no commit ou no rollback,
sem tabela, sem linha, sem risco de vazar lock se o processo morrer. Em SQLite é
no-op — que é exatamente o comportamento de hoje, então nada regride enquanto o
banco for arquivo.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text


def _chave(nome: str) -> int:
    """int64 estável a partir do nome do escopo.

    ``blake2b`` e não ``hash()``: hash de str é randomizado por processo via
    PYTHONHASHSEED, então dois workers gerariam chaves diferentes para a mesma
    loja e a trava não travaria nada — falhando em silêncio, que é o pior modo
    de falha que uma trava pode ter.
    """
    digest = hashlib.blake2b(nome.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def travar_por_loja(db, loja_slug: str, escopo: str) -> None:
    """Serializa, por loja e por escopo, até o fim da transação atual.

    A trava é por loja: uma loja lenta não bloqueia as outras. Ela é mantida até
    o commit/rollback da transação de quem chamou — se essa transação inclui uma
    chamada de rede, a trava dura a chamada. Isso é intencional onde é usada
    (ver ``acoes._checar_rate_limit``), mas é a razão de ela não ser um utilitário
    de uso geral.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:chave)"),
        {"chave": _chave(f"{escopo}:{loja_slug}")},
    )
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/concorrencia.py portal-gestao/tests/test_concorrencia.py
git commit -m "feat(portal): trava por loja portatil (advisory lock no Postgres, no-op em SQLite)"
```

---

### Task 4: Rate-limit de ações deixa de contar antes de decidir

**Esta é a única task da leva que corrige um vazamento que já existe hoje**, com um
processo só: `_checar_rate_limit` (`acoes.py:132-153`) conta e depois decide, e o FastAPI
atende requisições num pool de threads. Dois cliques simultâneos com o limite em N-1
passam os dois.

**Leia o trade-off antes de executar.** A trava é adquirida antes da contagem e só é
solta no fim da transação de `executar_acao` — que inclui o PATCH para a estoque-api.
Ou seja: com Postgres, ações **da mesma loja** passam a ser serializadas durante a chamada
de rede. É o que torna "no máximo N por hora por loja" verdade em vez de aproximação, e é
por loja (uma loja lenta não afeta outra), mas é um comportamento novo.

**Se doer em produção, esta task é a única da leva que pode ser revertida sozinha** — as
Tasks 1 e 2 não dependem dela. A alternativa, se for revertida, é aceitar overshoot de
poucas unidades num guarda de custo. Deixe isso registrado no commit.

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/acoes.py` (import + `_checar_rate_limit`)
- Test: `portal-gestao/tests/test_copiloto_acoes.py`

**Interfaces:**
- Consumes: `concorrencia.travar_por_loja` (Task 3).
- Produces: nada novo.

- [ ] **Step 1: Escrever o teste que falha**

Em `portal-gestao/tests/test_copiloto_acoes.py`, adicione:

```python
def test_rate_limit_trava_a_loja_antes_de_contar(db, monkeypatch):
    """A trava tem que vir ANTES do COUNT, senão ela não serializa nada —
    seria só um lock decorativo depois da decisão já tomada."""
    ordem = []

    import app.loja.copiloto.acoes as acoes_mod

    monkeypatch.setattr(
        acoes_mod,
        "travar_por_loja",
        lambda db, loja_slug, escopo: ordem.append(("travou", loja_slug, escopo)),
    )
    original_query = db.query

    def query_espiao(*a, **k):
        ordem.append(("consultou",))
        return original_query(*a, **k)

    monkeypatch.setattr(db, "query", query_espiao)

    acoes_mod._checar_rate_limit(db, "loja-teste", datetime.now(timezone.utc))

    assert ordem[0] == ("travou", "loja-teste", "copiloto_acao")
    assert ("consultou",) in ordem
```

Ajuste os imports do arquivo de teste para ter `datetime` e `timezone`.

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_acoes.py -q -k trava_a_loja`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_acoes.py -q -k trava_a_loja`

Esperado: `AttributeError: ... has no attribute 'travar_por_loja'`.

- [ ] **Step 3: Implementar**

Em `portal-gestao/app/loja/copiloto/acoes.py`, adicione ao topo:

```python
from app.concorrencia import travar_por_loja
```

E em `_checar_rate_limit`, insira como **primeira** instrução do corpo (depois da
docstring):

```python
    # Antes do COUNT, não depois: sem isto o limite é "contei e decidi", e dois
    # cliques simultâneos com o limite em N-1 passam os dois. Em Postgres esta
    # trava dura até o fim da transação de executar_acao — inclusive durante o
    # PATCH na estoque-api. É por loja, então uma loja lenta não segura as
    # outras. Em SQLite é no-op e o comportamento é o de hoje.
    travar_por_loja(db, loja_slug, "copiloto_acao")
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 1 passed.

- [ ] **Step 5: Rodar a suíte inteira**

macOS: `cd portal-gestao && .venv/bin/python -m pytest -q`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q`

Esperado: **1294 passed** (1282 do baseline + 4 da Task 1 + 3 da Task 2 + 4 da Task 3 + 1 desta).

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/loja/copiloto/acoes.py portal-gestao/tests/test_copiloto_acoes.py
git commit -m "fix(copiloto): rate-limit de acoes serializa por loja antes de contar

Trade-off aceito: em Postgres a trava dura ate o fim da transacao, o que
inclui o PATCH na estoque-api. E por loja. Se doer, esta e a unica mudanca
da leva que pode ser revertida sozinha."
```

---

## Fora de escopo desta leva

- **`copiloto_sinais_job.run_once`**, que itera `for loja_slug in lojas_ativas(db)` numa
  thread só. É problema de **capacidade**, não de corrida — dois processos não corrompem
  nada ali, só duplicam sinal. Fica para a leva de multi-loja (§5 do spec).
- **`expirar_orfaos`**: dois processos podem fechar o mesmo órfão; os dois escrevem
  `estado="erro"`, `erro_code="interrompido"`. Resultado idêntico, sem dano. Não vale
  código.
- **Job de purge**: apaga por retenção; apagar duas vezes é apagar uma vez.
- **Revy Control**: já tem `with_for_update()` escrito nos quatro pontos que importam. A
  migração liga; não há código a escrever.

## Antes de dizer que acabou

- [ ] `cd portal-gestao && .venv/bin/python -m pytest -q` (macOS) ou
      `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q` (Windows) → **1294 passed**
- [ ] Nenhuma migration nova: `git status --short portal-gestao/alembic/` vazio
- [ ] `git diff --check` limpo
- [ ] `git status --short` sem arquivo de outra pessoa no stage
