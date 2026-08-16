# Modo 2 / Card 1 — Sino por pessoa na Loja — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Dar ao sino da Loja a capacidade de endereçar uma notificação a **uma pessoa
específica** (o `oferecido_a` do rodízio), sem que dono/gerente vejam — hoje todo sinal é da loja
inteira.

**Architecture:** `copiloto_sinal` ganha uma coluna `destinatario_usuario_id` nullable. `NULL` =
comportamento de hoje (loja inteira); preenchido = só aquela pessoa vê e conta. A leitura
(`listar_sinais_abertos`, `contar_sinais_novos`) passa a filtrar por isso. Nenhum produtor de sinal
existente preenche a coluna, então as 7 regras do Copiloto não mudam de comportamento.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic (`batch_alter_table`,
o projeto roda SQLite em teste), pytest.

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §5.7 (sino 1:1 com Peguei) e §5.3 (rodízio troca o dono da oferta).

## Relação com o card B1 do sino

**Verificado em 2026-08-13: o B1 ainda NÃO foi executado.** `regras_elegiveis` e
`central_disponivel` não existem no `main`, `tests/test_central_elegibilidade.py` não existe,
`app/web/loja_shell.py:98` ainda usa `copiloto_secao_liberada` direto e
`app/copiloto_sinais_job.py:85` ainda filtra lojas por `_copiloto_permitido`.

**Este card não depende do B1 para rodar.** Nenhuma das 6 tasks aqui chama `regras_elegiveis` —
elas mexem em coluna, filtro de leitura e criação/transferência de sinal. Pode executar este card
antes, depois ou em paralelo ao B1.

**Mas a feature ponta-a-ponta depende.** Hoje o sino só existe quando a flag do Copiloto está
ligada, e `oferta_lead` não é uma das 7 regras do Copiloto — então, sem o B1, o sinal endereçado é
gravado corretamente e **não aparece para ninguém**. A ordem recomendada é B1 → este card, mas a
inversa também funciona: o que não pode é ligar o Modo 2 em produção sem os dois.

Card B1: [`2026-08-12-notificacao-central-simulacao-pronta.md`](2026-08-12-notificacao-central-simulacao-pronta.md).

## Escopo — o que este card NÃO faz

Fora daqui **de propósito**, porque depende de contrato que o `chatbot-api` ainda não expõe
(cards 2 e 3):

- **Botão Peguei** ligado ao `assumir` real. O `registrar_handoff_local` (`app/main.py:1255`)
  exige o **telefone** do cliente, e o sinal não pode guardar telefone em claro (disciplina do
  model). Quem resolve `oferta_id → telefone` é o chatbot. O botão sai no card da Loja pós-chatbot.
- **Cadastro da fila de vendedores.** O dado é do `chatbot-api`, não do Portal — mesmo padrão de
  `whatsapp_canais`, que o Portal só lê via `ChatbotClient`. Ver "Nota de arquitetura" no fim.
- Faixa "N sem vendedor", filtro Aguardando e card de 7 dias no Agente: dependem do estado do lead,
  que vem do chatbot.

Este card entrega **só a capacidade de endereçar** — que é a peça que ninguém tinha visto e que
bloqueia todo o resto.

## Global Constraints

- **`NULL` é o comportamento de hoje.** Sinal sem destinatário continua sendo da loja inteira. Se
  qualquer teste das 7 regras do Copiloto mudar de resultado, a implementação está errada.
- **Nunca gravar telefone em claro** em `copiloto_sinal` (nem em `dados_json`). A disciplina está
  no docstring do model e vale aqui: o sinal referencia a oferta, não o contato.
- **Não reimplementar checagem de gate.** Usar `regras_elegiveis` (card B1), `module_enabled`,
  papéis. Contrato em `app/web/loja_shell.py`.
- **Contagem por pessoa** (`CopilotoSinalVisto`) e cache TTL 45s (`app/loja/copiloto/notificacoes.py:36`) permanecem.
- **Migration com `batch_alter_table`** — o projeto testa em SQLite, que não faz `ALTER COLUMN`.
- **O step "ver falhar" tem que falhar de verdade.** Teste que passa antes da implementação é
  cobertura falsa. Cuidado especial com default de coluna (só é aplicado no `commit`, antes disso o
  atributo é `None`) e com asserção que só confere o que o próprio teste acabou de passar por
  kwarg — isso testa o SQLAlchemy, não o nosso código.
- Rodar testes **a partir de `portal-gestao/`** (senão importa o `app` errado). O dono usa **Mac e
  Windows**: macOS `.venv/bin/python -m pytest -q`; Windows `.\.venv\Scripts\python.exe -m pytest -q`.

---

### Task 1: Coluna `destinatario_usuario_id` no model + migration

**Files:**
- Modify: `portal-gestao/app/models.py` (classe `CopilotoSinal`, ~`:532-590`)
- Create: `portal-gestao/alembic/versions/0024_copiloto_sinal_destinatario.py`
- Test: `portal-gestao/tests/test_copiloto_sinal_destinatario.py`

**Interfaces:**
- Produces: `CopilotoSinal.destinatario_usuario_id: Optional[str]` — `None` = sinal da loja;
  preenchido = sinal de uma pessoa só. Índice
  `ix_copiloto_sinal_destinatario` sobre `(loja_slug, destinatario_usuario_id, estado)`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# portal-gestao/tests/test_copiloto_sinal_destinatario.py
from app.models import CopilotoSinal


def test_sinal_nasce_sem_destinatario():
    """NULL é o default: sinal continua sendo da loja inteira."""
    sinal = CopilotoSinal(
        loja_slug="loja-teste",
        regra="estoque_parado",
        severidade="info",
        titulo="t",
        detalhe="d",
    )
    assert sinal.destinatario_usuario_id is None


def test_sinal_aceita_destinatario():
    sinal = CopilotoSinal(
        loja_slug="loja-teste",
        regra="oferta_lead",
        severidade="atencao",
        titulo="t",
        detalhe="d",
        destinatario_usuario_id="u-vendedor-1",
    )
    assert sinal.destinatario_usuario_id == "u-vendedor-1"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: `TypeError: 'destinatario_usuario_id' is an invalid keyword argument`.

- [ ] **Step 3: Implementar no model**

Em `app/models.py`, dentro de `CopilotoSinal`, logo abaixo de `entidade_ref`:

```python
    # Destinatário único do sinal. None = sinal da loja inteira (todas as 7
    # regras do Copiloto). Preenchido = SÓ esta pessoa vê e conta — é o que
    # a oferta 1:1 do rodízio (spec §5.7) precisa: dono e gerente não podem
    # ver a oferta de um vendedor. Guarda o id do usuário, nunca telefone.
    destinatario_usuario_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
```

E acrescentar o índice em `__table_args__`, junto dos outros `Index(...)`:

```python
        Index(
            "ix_copiloto_sinal_destinatario",
            "loja_slug",
            "destinatario_usuario_id",
            "estado",
        ),
```

- [ ] **Step 4: Escrever a migration**

```python
# portal-gestao/alembic/versions/0024_copiloto_sinal_destinatario.py
"""copiloto_sinal: destinatario opcional (sino 1:1 do Modo 2)

Revision ID: 0024_copiloto_sinal_destinatario
Revises: 0023_copiloto_sinal_visto

O sino sempre foi da loja: quem tem acesso ve o sinal, e "visto" e por
pessoa (0023). A oferta 1:1 do rodizio (spec dos dois modos, §5.7) precisa
do oposto — SO o vendedor da vez pode ver, dono e gerente nao. Coluna
nullable porque NULL tem que continuar significando "da loja inteira":
os 7 sinais do Copiloto nao mudam de comportamento nem precisam backfill.

Guarda id de usuario, nunca telefone — mesma disciplina do model.
"""

import sqlalchemy as sa
from alembic import op


revision = "0024_copiloto_sinal_destinatario"
down_revision = "0023_copiloto_sinal_visto"
branch_labels = None
depends_on = None

_TABELA = "copiloto_sinal"
_INDICE = "ix_copiloto_sinal_destinatario"


def upgrade() -> None:
    with op.batch_alter_table(_TABELA) as batch:
        batch.add_column(
            sa.Column("destinatario_usuario_id", sa.String(length=36), nullable=True)
        )
    op.create_index(
        _INDICE,
        _TABELA,
        ["loja_slug", "destinatario_usuario_id", "estado"],
    )


def downgrade() -> None:
    # Sem perda de dado da loja: toda linha legada tem NULL aqui. Só some o
    # endereçamento 1:1 gravado depois do upgrade — e no modelo antigo não
    # existe onde guardá-lo.
    op.drop_index(_INDICE, table_name=_TABELA)
    with op.batch_alter_table(_TABELA) as batch:
        batch.drop_column("destinatario_usuario_id")
```

- [ ] **Step 5: Rodar a migration e os testes**

Run: `cd portal-gestao && .venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && alembic upgrade head && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: PASS nos dois testes.

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/models.py portal-gestao/alembic/versions/0024_copiloto_sinal_destinatario.py portal-gestao/tests/test_copiloto_sinal_destinatario.py
git commit -m "feat(portal): copiloto_sinal aceita destinatario por pessoa"
```

---

### Task 2: `contar_sinais_novos` respeita o destinatário

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py` (`contar_sinais_novos:168`)
- Test: `portal-gestao/tests/test_copiloto_sinal_destinatario.py` (acrescentar)

**Interfaces:**
- Consumes: `CopilotoSinal.destinatario_usuario_id` (Task 1).
- Produces: `contar_sinais_novos(db, loja_slug, usuario_id)` — assinatura **não muda**. A regra
  nova é interna: conta sinal com `destinatario_usuario_id IS NULL` **ou** `== usuario_id`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em portal-gestao/tests/test_copiloto_sinal_destinatario.py
from app.loja.copiloto.sinais_store import contar_sinais_novos
from app.models import CopilotoSinal


def _sinal(db, loja, *, regra="estoque_parado", destinatario=None):
    sinal = CopilotoSinal(
        loja_slug=loja,
        regra=regra,
        severidade="info",
        titulo="t",
        detalhe="d",
        estado="novo",
        destinatario_usuario_id=destinatario,
    )
    db.add(sinal)
    db.commit()
    return sinal


def test_sinal_da_loja_conta_para_todo_mundo(db):
    _sinal(db, "loja-a")
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 1
    assert contar_sinais_novos(db, "loja-a", "u-vendedor") == 1


def test_sinal_direcionado_conta_so_para_o_dono_dele(db):
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")
    assert contar_sinais_novos(db, "loja-a", "u-vendedor") == 1
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 0


def test_direcionado_e_da_loja_somam_para_o_destinatario(db):
    _sinal(db, "loja-a")
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")
    assert contar_sinais_novos(db, "loja-a", "u-vendedor") == 2
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 1
```

> A fixture `db` é a de `portal-gestao/tests/conftest.py:873` (`SessionLocal()` por teste). Não crie
> fixture nova.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: FAIL em `test_sinal_direcionado_conta_so_para_o_dono_dele` — conta 1 para o dono, porque
o filtro ainda não existe.

- [ ] **Step 3: Implementar**

Em `sinais_store.py`, dentro de `contar_sinais_novos`, acrescentar o filtro e estender o docstring:

```python
    return (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == loja_slug,
            CopilotoSinal.estado == "novo",
            CopilotoSinal.id.notin_(vistos_pelo_usuario),
            # Sinal endereçado só conta para o destinatário. NULL continua
            # sendo da loja inteira — é o caso das 7 regras do Copiloto.
            or_(
                CopilotoSinal.destinatario_usuario_id.is_(None),
                CopilotoSinal.destinatario_usuario_id == usuario_id,
            ),
        )
        .count()
    )
```

Importar `or_` no topo do arquivo: `from sqlalchemy import or_`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py tests/test_copiloto_sinais_store.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py tests/test_copiloto_sinais_store.py -q`
Esperado: PASS, **e** os testes antigos do store continuam verdes (é a prova de que NULL não mudou).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/sinais_store.py portal-gestao/tests/test_copiloto_sinal_destinatario.py
git commit -m "feat(portal): contagem do sino respeita destinatario"
```

---

### Task 3: `listar_sinais_abertos` respeita o destinatário

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py` (`listar_sinais_abertos:147`)
- Modify: `portal-gestao/app/web/loja_copiloto.py` (chamada em `notificacoes.json`, `:345`)
- Test: `portal-gestao/tests/test_copiloto_sinal_destinatario.py` (acrescentar)

**Interfaces:**
- Produces: `listar_sinais_abertos(db, loja_slug, *, limite=20, usuario_id: str | None = None)`.
  `usuario_id=None` mantém o comportamento atual (devolve tudo) para não quebrar chamador
  existente; passando `usuario_id`, esconde o que é de outra pessoa.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em portal-gestao/tests/test_copiloto_sinal_destinatario.py
from app.loja.copiloto.sinais_store import listar_sinais_abertos


def test_listagem_esconde_oferta_de_outro_vendedor(db):
    _sinal(db, "loja-a")
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")

    do_vendedor = listar_sinais_abertos(db, "loja-a", usuario_id="u-vendedor")
    do_dono = listar_sinais_abertos(db, "loja-a", usuario_id="u-dono")

    assert {s.regra for s in do_vendedor} == {"estoque_parado", "oferta_lead"}
    assert {s.regra for s in do_dono} == {"estoque_parado"}


def test_listagem_sem_usuario_devolve_tudo(db):
    """Compat: chamador que ainda não passa usuario_id não muda de resultado."""
    _sinal(db, "loja-a")
    _sinal(db, "loja-a", regra="oferta_lead", destinatario="u-vendedor")
    assert len(listar_sinais_abertos(db, "loja-a")) == 2
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: `TypeError: listar_sinais_abertos() got an unexpected keyword argument 'usuario_id'`.

- [ ] **Step 3: Implementar**

```python
def listar_sinais_abertos(
    db: Session,
    loja_slug: str,
    *,
    limite: int = 20,
    usuario_id: str | None = None,
) -> list[CopilotoSinal]:
    """Sinais abertos da loja.

    ``usuario_id`` filtra o endereçamento 1:1 (spec §5.7): com ele, sinal de
    outra pessoa não aparece. Sem ele, devolve tudo — é o comportamento
    legado, mantido para não mudar chamador que ainda não conhece
    destinatário.
    """
    ordem = {"critico": 0, "atencao": 1, "info": 2}
    consulta = db.query(CopilotoSinal).filter(
        CopilotoSinal.loja_slug == loja_slug,
        CopilotoSinal.estado.in_(ESTADOS_ABERTOS),
    )
    if usuario_id is not None:
        consulta = consulta.filter(
            or_(
                CopilotoSinal.destinatario_usuario_id.is_(None),
                CopilotoSinal.destinatario_usuario_id == usuario_id,
            )
        )
    linhas = consulta.all()
    linhas.sort(
        key=lambda s: (
            ordem.get(s.severidade, 9),
            -(_aware(s.criado_em) or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
        )
    )
    return linhas[: max(1, limite)]
```

- [ ] **Step 4: Ligar a rota do painel**

Em `app/web/loja_copiloto.py`, na rota `notificacoes.json` (`:345`), passar o usuário logado — o
painel do sino é pessoal, então o filtro tem que valer ali:

```python
    sinais = listar_sinais_abertos(db, store.loja_slug, usuario_id=getattr(usuario, "id", None))
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py tests/test_copiloto_notificacoes_rotas.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py tests/test_copiloto_notificacoes_rotas.py -q`
Esperado: PASS.

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/loja/copiloto/sinais_store.py portal-gestao/app/web/loja_copiloto.py portal-gestao/tests/test_copiloto_sinal_destinatario.py
git commit -m "feat(portal): painel do sino esconde oferta de outro vendedor"
```

---

### Task 4: Criar e transferir sinal endereçado

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py` (funções novas no fim)
- Test: `portal-gestao/tests/test_copiloto_sinal_destinatario.py` (acrescentar)

**Interfaces:**
- Produces:
  - `criar_sinal_direcionado(db, loja_slug, *, regra, destinatario_usuario_id, entidade_ref, titulo, detalhe, severidade="atencao", dados_json=None) -> CopilotoSinal`
  - `transferir_sinal(db, loja_slug, *, entidade_ref, de_usuario_id, para_usuario_id) -> bool` —
    resolve o sinal do dono anterior e cria um novo para o próximo. É o que o rodízio chama quando
    os 10 min estouram (spec §5.3). Devolve `False` se não achou sinal aberto daquele
    `entidade_ref` para `de_usuario_id`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em portal-gestao/tests/test_copiloto_sinal_destinatario.py
from app.loja.copiloto.sinais_store import criar_sinal_direcionado, transferir_sinal


def test_criar_direcionado_so_aparece_para_o_destinatario(db):
    criar_sinal_direcionado(
        db,
        "loja-a",
        regra="oferta_lead",
        destinatario_usuario_id="u-v1",
        entidade_ref="oferta-123",
        titulo="Lead novo",
        detalhe="Cliente quer uma Biz 125",
    )
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 0


def test_transferir_passa_a_oferta_para_o_proximo(db):
    criar_sinal_direcionado(
        db,
        "loja-a",
        regra="oferta_lead",
        destinatario_usuario_id="u-v1",
        entidade_ref="oferta-123",
        titulo="Lead novo",
        detalhe="Cliente quer uma Biz 125",
    )

    assert transferir_sinal(
        db, "loja-a", entidade_ref="oferta-123",
        de_usuario_id="u-v1", para_usuario_id="u-v2",
    ) is True

    assert contar_sinais_novos(db, "loja-a", "u-v1") == 0
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 1


def test_transferir_sem_sinal_aberto_devolve_false(db):
    assert transferir_sinal(
        db, "loja-a", entidade_ref="oferta-inexistente",
        de_usuario_id="u-v1", para_usuario_id="u-v2",
    ) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: `ImportError: cannot import name 'criar_sinal_direcionado'`.

- [ ] **Step 3: Implementar**

No fim de `sinais_store.py`:

```python
def criar_sinal_direcionado(
    db: Session,
    loja_slug: str,
    *,
    regra: str,
    destinatario_usuario_id: str,
    entidade_ref: str,
    titulo: str,
    detalhe: str,
    severidade: str = "atencao",
    dados_json: str | None = None,
) -> CopilotoSinal:
    """Cria sinal de UMA pessoa (oferta 1:1 do rodízio, spec §5.7).

    Não passa por ``sincronizar_sinais``: aquilo é para regra determinística
    que roda em lote sobre a loja. Aqui o produtor é um evento único, e o
    destinatário é obrigatório — um sinal de oferta sem dono seria
    exatamente o "sino da loja inteira" que o dono recusou.

    ``entidade_ref`` guarda o id da oferta, nunca o telefone do cliente.
    """
    sinal = CopilotoSinal(
        loja_slug=loja_slug,
        regra=regra,
        entidade_ref=entidade_ref,
        severidade=severidade,
        titulo=titulo,
        detalhe=detalhe,
        dados_json=dados_json,
        estado="novo",
        destinatario_usuario_id=destinatario_usuario_id,
    )
    db.add(sinal)
    db.commit()
    return sinal


def transferir_sinal(
    db: Session,
    loja_slug: str,
    *,
    entidade_ref: str,
    de_usuario_id: str,
    para_usuario_id: str,
) -> bool:
    """Passa a oferta ao próximo do rodízio: resolve a do anterior, cria a nova.

    Não é um UPDATE do destinatário: o sinal antigo precisa sair do contador
    do vendedor que perdeu a vez, e ``CopilotoSinalVisto`` é por sinal — reusar
    a linha carregaria o "visto" do anterior para o próximo.
    """
    anterior = (
        db.query(CopilotoSinal)
        .filter(
            CopilotoSinal.loja_slug == loja_slug,
            CopilotoSinal.entidade_ref == entidade_ref,
            CopilotoSinal.destinatario_usuario_id == de_usuario_id,
            CopilotoSinal.estado.in_(ESTADOS_ABERTOS),
        )
        .first()
    )
    if anterior is None:
        return False

    agora_utc = datetime.now(timezone.utc)
    anterior.estado = "resolvido"
    anterior.resolvido_em = agora_utc
    anterior.atualizado_em = agora_utc

    db.add(
        CopilotoSinal(
            loja_slug=loja_slug,
            regra=anterior.regra,
            entidade_ref=entidade_ref,
            severidade=anterior.severidade,
            titulo=anterior.titulo,
            detalhe=anterior.detalhe,
            dados_json=anterior.dados_json,
            estado="novo",
            destinatario_usuario_id=para_usuario_id,
        )
    )
    db.commit()
    return True
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: PASS.

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/sinais_store.py portal-gestao/tests/test_copiloto_sinal_destinatario.py
git commit -m "feat(portal): criar e transferir sinal enderecado do rodizio"
```

---

### Task 5: Invalidar o cache dos dois lados da transferência

**Files:**
- Modify: `portal-gestao/app/loja/copiloto/sinais_store.py` (`criar_sinal_direcionado`, `transferir_sinal`)
- Test: `portal-gestao/tests/test_copiloto_sinal_destinatario.py` (acrescentar)

**Interfaces:**
- Consumes: `invalidar_contagem(loja_slug, usuario_id=None)` de
  `app/loja/copiloto/notificacoes.py:56`.

O contador do sino tem cache de 45s por pessoa. Sem invalidar, o vendedor novo espera até 45s para
ver a oferta — e o rodízio dá 10 min. Pior: o que perdeu a vez continua vendo por 45s.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em portal-gestao/tests/test_copiloto_sinal_destinatario.py
from app.loja.copiloto import notificacoes


def test_transferir_invalida_cache_dos_dois(db, monkeypatch):
    invalidados = []
    monkeypatch.setattr(
        "app.loja.copiloto.sinais_store.invalidar_contagem",
        lambda loja, usuario_id=None: invalidados.append((loja, usuario_id)),
    )

    criar_sinal_direcionado(
        db, "loja-a", regra="oferta_lead",
        destinatario_usuario_id="u-v1", entidade_ref="oferta-9",
        titulo="t", detalhe="d",
    )
    transferir_sinal(
        db, "loja-a", entidade_ref="oferta-9",
        de_usuario_id="u-v1", para_usuario_id="u-v2",
    )

    assert ("loja-a", "u-v1") in invalidados
    assert ("loja-a", "u-v2") in invalidados
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py::test_transferir_invalida_cache_dos_dois -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py::test_transferir_invalida_cache_dos_dois -q`
Esperado: FAIL — `invalidados` vazio.

- [ ] **Step 3: Implementar**

No topo de `sinais_store.py`: `from app.loja.copiloto.notificacoes import invalidar_contagem`.
Se isso criar import circular, importe dentro das funções (o projeto já usa esse recurso em
`app/main.py:1263`).

Em `criar_sinal_direcionado`, depois do `db.commit()`:

```python
    invalidar_contagem(loja_slug, destinatario_usuario_id)
```

Em `transferir_sinal`, depois do `db.commit()`:

```python
    # Os dois: quem perdeu a vez precisa parar de ver agora, não em 45s.
    invalidar_contagem(loja_slug, de_usuario_id)
    invalidar_contagem(loja_slug, para_usuario_id)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd portal-gestao && .venv/bin/python -m pytest tests/test_copiloto_sinal_destinatario.py -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_copiloto_sinal_destinatario.py -q`
Esperado: PASS.

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/loja/copiloto/sinais_store.py portal-gestao/tests/test_copiloto_sinal_destinatario.py
git commit -m "feat(portal): invalidar contagem nos dois lados da transferencia"
```

---

### Task 6: Regressão — o Copiloto não mudou

**Files:**
- Test: roda a suíte inteira, não escreve teste novo.

Esta task existe porque o risco real deste card não é o código novo: é ter mudado, sem querer, o
que dono e gerente veem hoje.

- [ ] **Step 1: Rodar a suíte inteira**

Run: `cd portal-gestao && .venv/bin/python -m pytest -q`
— Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest -q`
Esperado: **tudo verde**, incluindo a property test de 48 combinações em
`tests/test_copiloto_notificacoes_shell.py`.

- [ ] **Step 2: Se algo do Copiloto quebrou, é bug deste card**

Um sinal com `destinatario_usuario_id IS NULL` tem que se comportar exatamente como antes. Falha
nesses testes significa que um dos filtros `or_(...)` está errado — provavelmente trocou `is_(None)`
por `== None` dentro de um `and_`, ou esqueceu o ramo NULL. Corrija o filtro, não o teste.

- [ ] **Step 3: `git diff --check` e `git status --short`**

Run: `git diff --check && git status --short`
Esperado: sem espaço em branco solto, sem arquivo alheio no diff.

---

## Nota de arquitetura — onde mora a fila de vendedores

Ao ler o código para escrever este card, apareceu uma divergência com a spec que **não** dá para
resolver dentro deste card e que muda o card 2:

A spec §5.3 diz *"Fila por loja: nome + número + ordem, cadastrados no Portal pelo lojista. O Portal
é a fonte da verdade."* Mas o Portal **não expõe** nenhum endpoint de serviço hoje — a direção é
sempre Portal → Chatbot (`app/clients/chatbot.py`, Bearer). E o precedente mais próximo é
`whatsapp_canais`, cujo docstring diz explicitamente: *"o Chatbot é dono de whatsapp_canais"*; o
Portal só desenha a tela lendo pelo `ChatbotClient`.

Guardar a fila no banco do Portal obrigaria a inventar autenticação de serviço **de entrada** no
Portal, só para o chatbot ler a fila a cada rodízio. Guardar no chatbot mantém a direção existente,
e é onde o rodízio roda de qualquer jeito.

**Assunção adotada para o card 2:** a fila mora no `chatbot-api` e o Portal desenha a tela via
`ChatbotClient`, igual a `whatsapp_canais`. "Cadastrados no Portal pelo lojista" continua verdade —
é a UI. Se o dono discordar, o card 2 muda e este card 1 **não** é afetado.

## Self-Review

- Spec §5.7 "sino só para o `oferecido_a`, dono/gerente não veem": Tasks 1–3. **Coberto.**
- Spec §5.3 "sino muda de dono quando o rodízio avança": Task 4 (`transferir_sinal`). **Coberto.**
- Botão **Peguei** ligado ao `assumir`: **fora deste card** — precisa resolver `oferta_id → telefone`
  no chatbot (ver Escopo).
- "Nunca telefone em claro no sinal": `entidade_ref` guarda id da oferta; reforçado no docstring de
  `criar_sinal_direcionado`.
- Risco de regressão nas 7 regras do Copiloto: Task 6, e o ramo NULL testado explicitamente em
  Tasks 2 e 3.
