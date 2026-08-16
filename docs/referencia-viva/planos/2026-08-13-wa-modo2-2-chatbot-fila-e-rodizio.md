# Modo 2 / Card 2 — Fila e rodízio no chatbot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Colocar no `chatbot-api` a fila de vendedores por loja e o motor de rodízio: ponteiro
rotativo, oferta com prazo de 10 min, trava idempotente no primeiro clique, e uma volta e para.

**Architecture:** duas tabelas novas (`fila_vendedor`, `oferta_lead`) mais um ponteiro por loja.
A decisão de "quem é o próximo" é uma **função pura** testável sem banco; o estado é um registro de
oferta com prazo. Um worker no padrão do `NotificacoesOutboxWorker` varre ofertas vencidas. O
Portal desenha a tela lendo por HTTP com a credencial de serviço que já existe.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, pytest. Auth de
serviço: `app/auth.py::get_contexto` (Bearer → `CredencialServico` → loja).

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §5.3 (rodízio), §5.7 (trava por clique), §6.3 (suspensão e flag).

## Escopo

**Dentro:** fila de vendedores (tabela + HTTP), ponteiro rotativo, abertura de oferta, trava
idempotente, expiração de 10 min, fim de volta, gate de suspensão e flag.

**Fora, vai para o card 2b (bot do Modo 2):** os três gatilhos de handoff (§5.2), download de mídia
no Graph e transcrição (§5.10), follow-up de silêncio (§5.9), envio do template/interativo. Este
card entrega o **mecanismo**; o 2b liga os eventos nele.

Também fora: `n8n-cloud` (card 3) e toggle no Control (card 4).

## Global Constraints

- **Flag `CHATBOT_WHATSAPP_MODO2_ENABLED` default OFF.** Invariante do projeto. A flag gateia a
  **operação, não a configuração**: com ela desligada, `abrir_oferta` devolve `None` e o worker não
  oferece nada — mas o CRUD de `/v1/fila-vendedores` **continua respondendo**, porque o lojista
  precisa cadastrar a fila **antes** do rollout. Gatear o cadastro tornaria o Modo 2 impossível de
  configurar.

  > Corrigido em 2026-08-14, depois da execução: a redação anterior dizia "nenhuma rota nova
  > responde", o que contradizia a própria Task 8. O gate que importa está em `abrir_oferta`.
- **Loja suspensa não opera** (§6.3): reusar `app/provisioning.py:28::allows_processing` — não
  reimplementar leitura de projeção. Vale para abrir oferta, expirar e travar. Um ponto só.
- **Um lead pendente por vendedor** (§5.3): vendedor com oferta aberta é pulado.
- **Trava idempotente:** o primeiro `assumir` ganha; clique seguinte devolve "já foi pego" sem
  alterar nada. Nunca duas travas para a mesma oferta.
- **Telefone de vendedor mora aqui**, normalizado com `app/operacao.py::normalizar_telefone`. A
  comparação usa `variantes_telefone` (9º dígito) — nunca `==` de string crua.
- **Sem import entre produtos.** O Portal chama por HTTP; nada de importar `app` do Portal.
- **O step "ver falhar" tem que falhar de verdade.** Teste que passa antes da implementação é
  cobertura falsa. Cuidado especial com default de coluna (só é aplicado no `commit`, antes disso o
  atributo é `None`) e com asserção que só confere o que o próprio teste acabou de passar por
  kwarg — isso testa o SQLAlchemy, não o nosso código.
- Rodar testes **a partir de `chatbot-api/`** (senão importa o `app` errado). O dono usa **Mac e
  Windows**: macOS `.venv/bin/python -m pytest -q`; Windows `.\.venv\Scripts\python.exe -m pytest -q`.

---

### Task 1: Tabela `fila_vendedor` + migration

**Files:**
- Modify: `chatbot-api/app/models_db.py` (classe nova depois de `WhatsAppCanal`, ~`:67`)
- Create: `chatbot-api/alembic/versions/0020_fila_vendedor.py`
- Test: `chatbot-api/tests/test_fila_vendedor.py`

**Interfaces:**
- Produces: `FilaVendedor` com `id`, `loja_id`, `nome`, `telefone`, `ordem`, `ativo`, `criado_em`.
  Unique `(loja_id, ordem)` entre ativos não é constraint de banco (reordenar ficaria impossível sem
  transação acrobática) — a ordenação é resolvida na leitura.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_fila_vendedor.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models_db import FilaVendedor


def test_vendedor_nasce_ativo(db, loja_a):
    """Precisa do commit: default de coluna só é aplicado no flush.

    Sem ele, ``v.ativo`` é ``None`` e o teste passaria mesmo se o default
    estivesse errado.
    """
    v = FilaVendedor(
        id="f1", loja_id=loja_a["loja_id"], nome="João",
        telefone="5511999998888", ordem=1,
    )
    db.add(v)
    db.commit()
    assert v.ativo is True


def test_nome_e_obrigatorio(db, loja_a):
    """O nome vai no aviso ao cliente (§5.1) — sem ele o handoff fica anônimo."""
    db.add(FilaVendedor(
        id="f2", loja_id=loja_a["loja_id"], nome=None,
        telefone="5511999998888", ordem=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_telefone_e_obrigatorio(db, loja_a):
    db.add(FilaVendedor(
        id="f3", loja_id=loja_a["loja_id"], nome="João", telefone=None, ordem=1,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_fila_vendedor.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_fila_vendedor.py -q`
Esperado: `ImportError: cannot import name 'FilaVendedor'`.

- [ ] **Step 3: Implementar o model**

```python
class FilaVendedor(Base):
    """Vendedor na fila de rodízio da loja (Modo 2).

    O telefone mora aqui, não no Portal: o chatbot já é dono de conversa e
    número (``Conversa.telefone``), e é ele que precisa casar o inbound do
    vendedor com o cadastro (spec §5.5). O Portal desenha a tela lendo por
    HTTP, mesmo padrão de ``whatsapp_canais``.

    ``nome`` é obrigatório porque vai no aviso ao cliente ("o João vai te
    chamar", spec §5.1) — sem ele o handoff fica anônimo.
    """

    __tablename__ = "fila_vendedor"
    __table_args__ = (
        Index("ix_fila_vendedor_loja_ordem", "loja_id", "ordem"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    # Só dígitos (DDI+DDD+número), normalizado por operacao.normalizar_telefone.
    telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
```

- [ ] **Step 4: Escrever a migration**

```python
# chatbot-api/alembic/versions/0020_fila_vendedor.py
"""fila_vendedor: vendedores do rodizio do Modo 2

Revision ID: 0020_fila_vendedor
Revises: 0019_canal_principal_estoque

Modo 2 (spec dos dois modos): a central distribui o lead por rodizio, e
precisa saber quem sao os vendedores, em que ordem, e com que numero. Mora
no chatbot porque e ele que roda o rodizio e que casa o inbound do
vendedor com o cadastro; o Portal so desenha a tela por HTTP.

Sem unique (loja_id, ordem): reordenar a fila trocaria duas linhas e
esbarraria na constraint no meio da transacao. A ordem e resolvida na
leitura, e empate desempata por criado_em.
"""

import sqlalchemy as sa
from alembic import op


revision = "0020_fila_vendedor"
down_revision = "0019_canal_principal_estoque"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fila_vendedor",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("telefone", sa.String(length=20), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fila_vendedor_loja_id", "fila_vendedor", ["loja_id"])
    op.create_index("ix_fila_vendedor_loja_ordem", "fila_vendedor", ["loja_id", "ordem"])


def downgrade() -> None:
    op.drop_index("ix_fila_vendedor_loja_ordem", table_name="fila_vendedor")
    op.drop_index("ix_fila_vendedor_loja_id", table_name="fila_vendedor")
    op.drop_table("fila_vendedor")
```

- [ ] **Step 5: Rodar migration e testes**

Run: `cd chatbot-api && .venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/test_fila_vendedor.py -q`
— Windows: `cd chatbot-api && alembic upgrade head && .\.venv\Scripts\python.exe -m pytest tests/test_fila_vendedor.py -q`
Esperado: PASS.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/models_db.py chatbot-api/alembic/versions/0020_fila_vendedor.py chatbot-api/tests/test_fila_vendedor.py
git commit -m "feat(chatbot): tabela fila_vendedor do rodizio"
```

---

### Task 2: Tabela `oferta_lead` + ponteiro + migration

**Files:**
- Modify: `chatbot-api/app/models_db.py`
- Create: `chatbot-api/alembic/versions/0021_oferta_lead.py`
- Test: `chatbot-api/tests/test_oferta_lead.py`

**Interfaces:**
- Produces: `OfertaLead` (`id`, `loja_id`, `telefone_cliente`, `vendedor_id`, `estado`,
  `posicao_inicial`, `prazo_em`, `criado_em`, `travada_em`) e `RodizioPonteiro`
  (`loja_id` PK, `posicao`).
- Estados: `aberta` | `travada` | `expirada` | `esgotada`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_oferta_lead.py
from app.models_db import FilaVendedor, OfertaLead, RodizioPonteiro


def test_oferta_nasce_aberta(db, loja_a):
    """Commit obrigatório: antes do flush o estado é ``None``, não o default."""
    db.add(FilaVendedor(
        id="f1", loja_id=loja_a["loja_id"], nome="V", telefone="5511999990000", ordem=0,
    ))
    db.commit()
    o = OfertaLead(
        id="o1", loja_id=loja_a["loja_id"], telefone_cliente="5511988887777",
        vendedor_id="f1", posicao_inicial=0,
    )
    db.add(o)
    db.commit()
    assert o.estado == "aberta"
    assert o.travada_em is None


def test_ponteiro_comeca_em_zero(db, loja_a):
    """Loja nova começa no topo da fila — o default é parte do contrato."""
    p = RodizioPonteiro(loja_id=loja_a["loja_id"])
    db.add(p)
    db.commit()
    assert p.posicao == 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_oferta_lead.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_oferta_lead.py -q`
Esperado: `ImportError: cannot import name 'OfertaLead'`.

- [ ] **Step 3: Implementar os models**

```python
class OfertaLead(Base):
    """Uma oferta de lead a um vendedor (spec §5.3).

    ``posicao_inicial`` guarda onde o ponteiro estava quando o lead entrou:
    e assim que se sabe que a volta fechou (voltou em quem comecou) sem
    contar quantas ofertas ja sairam.

    Oferta anterior continua ``aberta`` ate o lead travar — e o que faz
    "primeiro clique vence mesmo atrasado" funcionar.
    """

    __tablename__ = "oferta_lead"
    __table_args__ = (
        Index("ix_oferta_lead_loja_estado", "loja_id", "estado"),
        Index("ix_oferta_lead_prazo", "estado", "prazo_em"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), nullable=False, index=True)
    telefone_cliente: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    vendedor_id: Mapped[str] = mapped_column(ForeignKey("fila_vendedor.id"), nullable=False)
    # aberta | travada | expirada | esgotada
    estado: Mapped[str] = mapped_column(String(20), default="aberta", nullable=False)
    posicao_inicial: Mapped[int] = mapped_column(Integer, nullable=False)
    prazo_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_agora)
    travada_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RodizioPonteiro(Base):
    """Onde a proxima oferta da loja comeca (spec §5.3).

    Avanca a cada OFERTA emitida, nao a cada lead: dois leads simultaneos
    caem em vendedores diferentes em vez de empilharem no primeiro da lista.
    """

    __tablename__ = "rodizio_ponteiro"

    loja_id: Mapped[str] = mapped_column(ForeignKey("lojas.id"), primary_key=True)
    posicao: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

- [ ] **Step 4: Escrever a migration**

```python
# chatbot-api/alembic/versions/0021_oferta_lead.py
"""oferta_lead + rodizio_ponteiro: estado do rodizio do Modo 2

Revision ID: 0021_oferta_lead
Revises: 0020_fila_vendedor

O rodizio precisa de estado durável, nao de memoria de processo: o prazo
de 10 min tem que sobreviver a restart de VM, e o "primeiro clique vence"
tem que valer mesmo depois de o vendedor seguinte ja ter sido chamado.
"""

import sqlalchemy as sa
from alembic import op


revision = "0021_oferta_lead"
down_revision = "0020_fila_vendedor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oferta_lead",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("telefone_cliente", sa.String(length=20), nullable=False),
        sa.Column("vendedor_id", sa.String(length=36), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="aberta"),
        sa.Column("posicao_inicial", sa.Integer(), nullable=False),
        sa.Column("prazo_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("travada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.ForeignKeyConstraint(["vendedor_id"], ["fila_vendedor.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oferta_lead_loja_id", "oferta_lead", ["loja_id"])
    op.create_index("ix_oferta_lead_telefone", "oferta_lead", ["telefone_cliente"])
    op.create_index("ix_oferta_lead_loja_estado", "oferta_lead", ["loja_id", "estado"])
    op.create_index("ix_oferta_lead_prazo", "oferta_lead", ["estado", "prazo_em"])

    op.create_table(
        "rodizio_ponteiro",
        sa.Column("loja_id", sa.String(length=36), nullable=False),
        sa.Column("posicao", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["loja_id"], ["lojas.id"]),
        sa.PrimaryKeyConstraint("loja_id"),
    )


def downgrade() -> None:
    op.drop_table("rodizio_ponteiro")
    op.drop_index("ix_oferta_lead_prazo", table_name="oferta_lead")
    op.drop_index("ix_oferta_lead_loja_estado", table_name="oferta_lead")
    op.drop_index("ix_oferta_lead_telefone", table_name="oferta_lead")
    op.drop_index("ix_oferta_lead_loja_id", table_name="oferta_lead")
    op.drop_table("oferta_lead")
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/alembic upgrade head && .venv/bin/python -m pytest tests/test_oferta_lead.py -q`
— Windows: `cd chatbot-api && alembic upgrade head && .\.venv\Scripts\python.exe -m pytest tests/test_oferta_lead.py -q`
Esperado: PASS.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/models_db.py chatbot-api/alembic/versions/0021_oferta_lead.py chatbot-api/tests/test_oferta_lead.py
git commit -m "feat(chatbot): estado do rodizio (oferta_lead + ponteiro)"
```

---

### Task 3: `escolher_proximo` — a decisão do rodízio como função pura

**Files:**
- Create: `chatbot-api/app/rodizio.py`
- Test: `chatbot-api/tests/test_rodizio_escolha.py`

**Interfaces:**
- Produces:
  `escolher_proximo(ordem_ids: list[str], ponteiro: int, pendentes: set[str], ja_ofertados: set[str], posicao_inicial: int | None) -> tuple[str | None, int, bool]`
  → `(vendedor_id, nova_posicao, volta_fechou)`.
  `vendedor_id=None` com `volta_fechou=True` significa esgotou a fila; `None` com
  `volta_fechou=False` significa "todos ocupados, tenta de novo depois".

Esta é a peça que concentra a regra e é onde bug de rodízio nasce. Ficar sem banco torna cada caso
um teste de duas linhas.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_rodizio_escolha.py
from app.rodizio import escolher_proximo


def test_comeca_no_ponteiro_nao_no_topo():
    vend, pos, fechou = escolher_proximo(
        ["a", "b", "c"], ponteiro=1, pendentes=set(), ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert (vend, pos, fechou) == ("b", 2, False)


def test_pula_quem_ja_tem_oferta_aberta():
    vend, pos, fechou = escolher_proximo(
        ["a", "b", "c"], ponteiro=0, pendentes={"a"}, ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert vend == "b"


def test_todos_ocupados_devolve_none_sem_fechar_volta():
    vend, pos, fechou = escolher_proximo(
        ["a", "b"], ponteiro=0, pendentes={"a", "b"}, ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert vend is None
    assert fechou is False


def test_volta_fecha_quando_todos_ja_receberam():
    vend, pos, fechou = escolher_proximo(
        ["a", "b"], ponteiro=0, pendentes=set(), ja_ofertados={"a", "b"},
        posicao_inicial=0,
    )
    assert vend is None
    assert fechou is True


def test_fila_vazia_fecha_a_volta_na_hora():
    vend, pos, fechou = escolher_proximo(
        [], ponteiro=0, pendentes=set(), ja_ofertados=set(), posicao_inicial=None,
    )
    assert (vend, fechou) == (None, True)


def test_ponteiro_da_volta_circular():
    vend, pos, fechou = escolher_proximo(
        ["a", "b", "c"], ponteiro=2, pendentes=set(), ja_ofertados=set(),
        posicao_inicial=None,
    )
    assert (vend, pos) == ("c", 0)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_escolha.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_escolha.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.rodizio'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/rodizio.py
"""Decisão do rodízio (spec §5.3), sem banco.

Separado do store de propósito: é aqui que mora a regra que erra fácil
(ponteiro circular, pular ocupado, saber que a volta fechou), e sem I/O
cada caso vira um teste de duas linhas.
"""
from __future__ import annotations


def escolher_proximo(
    ordem_ids: list[str],
    *,
    ponteiro: int,
    pendentes: set[str],
    ja_ofertados: set[str],
    posicao_inicial: int | None,
) -> tuple[str | None, int, bool]:
    """Devolve ``(vendedor_id, nova_posicao, volta_fechou)``.

    - ``None`` + ``volta_fechou=True``: acabou (fila vazia ou todo mundo já
      recebeu). O lead vira ``aguardando``.
    - ``None`` + ``volta_fechou=False``: todos estão com oferta aberta agora.
      O lead espera uma vaga; não é fim de fila.
    """
    total = len(ordem_ids)
    if total == 0:
        return None, ponteiro, True

    if posicao_inicial is not None and len(ja_ofertados) >= total:
        return None, ponteiro, True

    inicio = ponteiro % total
    for salto in range(total):
        indice = (inicio + salto) % total
        candidato = ordem_ids[indice]
        if candidato in pendentes or candidato in ja_ofertados:
            continue
        return candidato, (indice + 1) % total, False

    # Ninguém elegível. Distinguir "todos ocupados agora" de "todos já
    # receberam" é o que separa esperar de encerrar.
    livres = [v for v in ordem_ids if v not in ja_ofertados]
    return None, ponteiro, not livres
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_escolha.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_escolha.py -q`
Esperado: PASS nos 6 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/rodizio.py chatbot-api/tests/test_rodizio_escolha.py
git commit -m "feat(chatbot): escolha do rodizio como funcao pura"
```

---

### Task 4: `abrir_oferta` — cria a oferta e avança o ponteiro

**Files:**
- Modify: `chatbot-api/app/rodizio.py`
- Test: `chatbot-api/tests/test_rodizio_store.py`

**Interfaces:**
- Consumes: `escolher_proximo` (Task 3), `FilaVendedor`/`OfertaLead`/`RodizioPonteiro` (Tasks 1–2).
- Produces: `abrir_oferta(db, loja_id, telefone_cliente, *, prazo_minutos=10) -> OfertaLead | None`.
  `None` = fila esgotou ou não há vendedor elegível — o chamador marca o lead como `aguardando`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_rodizio_store.py
from app.models_db import FilaVendedor, OfertaLead, RodizioPonteiro
from app.rodizio import abrir_oferta


def _fila(db, loja_id, quantos):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"f{i}", loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
    db.commit()


def test_primeira_oferta_vai_para_o_primeiro(db, loja_a):
    _fila(db, loja_a["loja_id"], 3)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assert oferta is not None
    assert oferta.vendedor_id == "f0"
    assert oferta.estado == "aberta"
    assert oferta.prazo_em is not None


def test_segundo_lead_vai_para_o_segundo(db, loja_a):
    _fila(db, loja_a["loja_id"], 3)
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    segunda = abrir_oferta(db, loja_a["loja_id"], "5511977776666")
    assert segunda.vendedor_id == "f1"


def test_fila_vazia_devolve_none(db, loja_a):
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is None


def test_vendedor_inativo_e_pulado(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    db.query(FilaVendedor).filter(FilaVendedor.id == "f0").update({"ativo": False})
    db.commit()
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assert oferta.vendedor_id == "f1"
```

> Fixtures de `chatbot-api/tests/conftest.py:99,108`: `db` é a sessão; `loja_a` é um **dict**
> (`{"loja_id", "slug", "instance", "headers"}`), já com credencial de serviço e projeção
> operacional ativa. Não crie fixture nova.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_store.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_store.py -q`
Esperado: `ImportError: cannot import name 'abrir_oferta'`.

- [ ] **Step 3: Implementar**

Acrescentar em `app/rodizio.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models_db import FilaVendedor, OfertaLead, RodizioPonteiro


def _fila_ordenada(db: Session, loja_id: str) -> list[FilaVendedor]:
    return (
        db.query(FilaVendedor)
        .filter(FilaVendedor.loja_id == loja_id, FilaVendedor.ativo.is_(True))
        .order_by(FilaVendedor.ordem, FilaVendedor.criado_em)
        .all()
    )


def abrir_oferta(
    db: Session,
    loja_id: str,
    telefone_cliente: str,
    *,
    prazo_minutos: int = 10,
) -> OfertaLead | None:
    """Oferece o lead ao vendedor da vez. ``None`` = ninguém para oferecer."""
    fila = _fila_ordenada(db, loja_id)
    ordem_ids = [v.id for v in fila]

    ponteiro = db.get(RodizioPonteiro, loja_id)
    if ponteiro is None:
        ponteiro = RodizioPonteiro(loja_id=loja_id, posicao=0)
        db.add(ponteiro)
        db.flush()

    abertas = (
        db.query(OfertaLead)
        .filter(OfertaLead.loja_id == loja_id, OfertaLead.estado == "aberta")
        .all()
    )
    pendentes = {o.vendedor_id for o in abertas}

    deste_lead = [o for o in abertas if o.telefone_cliente == telefone_cliente]
    ja_ofertados = {o.vendedor_id for o in db.query(OfertaLead).filter(
        OfertaLead.loja_id == loja_id,
        OfertaLead.telefone_cliente == telefone_cliente,
    ).all()}
    posicao_inicial = deste_lead[0].posicao_inicial if deste_lead else None

    vendedor_id, nova_posicao, _fechou = escolher_proximo(
        ordem_ids,
        ponteiro=ponteiro.posicao,
        pendentes=pendentes - ja_ofertados,
        ja_ofertados=ja_ofertados,
        posicao_inicial=posicao_inicial,
    )
    if vendedor_id is None:
        return None

    oferta = OfertaLead(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        telefone_cliente=telefone_cliente,
        vendedor_id=vendedor_id,
        estado="aberta",
        posicao_inicial=posicao_inicial if posicao_inicial is not None else ponteiro.posicao,
        prazo_em=datetime.now(timezone.utc) + timedelta(minutes=prazo_minutos),
    )
    ponteiro.posicao = nova_posicao
    db.add(oferta)
    db.commit()
    return oferta
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_store.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_store.py -q`
Esperado: PASS.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/rodizio.py chatbot-api/tests/test_rodizio_store.py
git commit -m "feat(chatbot): abrir oferta avancando o ponteiro"
```

---

### Task 5: `assumir_oferta` — trava idempotente, primeiro clique vence

**Files:**
- Modify: `chatbot-api/app/rodizio.py`
- Test: `chatbot-api/tests/test_rodizio_trava.py`

**Interfaces:**
- Produces: `assumir_oferta(db, oferta_id) -> tuple[bool, OfertaLead | None]` →
  `(ganhou, oferta_travada)`. `ganhou=False` com oferta preenchida = "já foi pego" (o chamador
  manda o recado ao perdedor); `(False, None)` = oferta inexistente.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_rodizio_trava.py
from app.models_db import FilaVendedor, OfertaLead
from app.rodizio import abrir_oferta, assumir_oferta


def _fila(db, loja_id, quantos):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"f{i}", loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
    db.commit()


def test_primeiro_clique_trava(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    ganhou, travada = assumir_oferta(db, oferta.id)
    assert ganhou is True
    assert travada.estado == "travada"
    assert travada.travada_em is not None


def test_segundo_clique_nao_muda_nada(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assumir_oferta(db, oferta.id)
    ganhou, travada = assumir_oferta(db, oferta.id)
    assert ganhou is False
    assert travada.vendedor_id == oferta.vendedor_id


def test_clique_atrasado_do_primeiro_vence_o_segundo(db, loja_a):
    """Spec §5.3: botão velho vale até o lead travar."""
    _fila(db, loja_a["loja_id"], 2)
    primeira = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    segunda = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    assert segunda.vendedor_id != primeira.vendedor_id

    ganhou_velho, _ = assumir_oferta(db, primeira.id)
    ganhou_novo, _ = assumir_oferta(db, segunda.id)

    assert ganhou_velho is True
    assert ganhou_novo is False


def test_oferta_inexistente(db):
    assert assumir_oferta(db, "nao-existe") == (False, None)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_trava.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_trava.py -q`
Esperado: `ImportError: cannot import name 'assumir_oferta'`.

- [ ] **Step 3: Implementar**

```python
def assumir_oferta(db: Session, oferta_id: str) -> tuple[bool, OfertaLead | None]:
    """Trava o lead no vendedor da oferta. Idempotente e exclusiva por lead.

    "Primeiro clique vence, mesmo atrasado" (spec §5.3): a oferta anterior
    continua ``aberta``, então o botão velho ainda resolve — o que decide é
    se JÁ EXISTE trava para aquele telefone, não qual oferta é mais nova.
    """
    oferta = db.get(OfertaLead, oferta_id)
    if oferta is None:
        return False, None

    ja_travada = (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == oferta.loja_id,
            OfertaLead.telefone_cliente == oferta.telefone_cliente,
            OfertaLead.estado == "travada",
        )
        .first()
    )
    if ja_travada is not None:
        return False, ja_travada

    agora = datetime.now(timezone.utc)
    oferta.estado = "travada"
    oferta.travada_em = agora

    # As demais ofertas deste lead morrem: o perdedor recebe "já foi pego".
    (
        db.query(OfertaLead)
        .filter(
            OfertaLead.loja_id == oferta.loja_id,
            OfertaLead.telefone_cliente == oferta.telefone_cliente,
            OfertaLead.id != oferta.id,
            OfertaLead.estado == "aberta",
        )
        .update({"estado": "expirada"}, synchronize_session=False)
    )
    db.commit()
    return True, oferta
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_trava.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_trava.py -q`
Esperado: PASS nos 4 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/rodizio.py chatbot-api/tests/test_rodizio_trava.py
git commit -m "feat(chatbot): trava idempotente do primeiro clique"
```

---

### Task 6: Worker de expiração — 10 min, próximo, uma volta e para

**Files:**
- Create: `chatbot-api/app/rodizio_job.py`
- Test: `chatbot-api/tests/test_rodizio_job.py`

**Interfaces:**
- Consumes: `abrir_oferta` (Task 4).
- Produces: `RodizioWorker` com `run_once(db) -> dict[str, int]` devolvendo
  `{"expiradas": n, "reofertadas": n, "esgotadas": n}`. Mesmo formato e ciclo de vida do
  `NotificacoesOutboxWorker` (`app/notificacoes_outbox_job.py:28-103`).

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_rodizio_job.py
from datetime import datetime, timedelta, timezone

from app.models_db import FilaVendedor, OfertaLead
from app.rodizio import abrir_oferta
from app.rodizio_job import RodizioWorker


def _fila(db, loja_id, quantos):
    for i in range(quantos):
        db.add(FilaVendedor(
            id=f"f{i}", loja_id=loja_id, nome=f"V{i}",
            telefone=f"551199999000{i}", ordem=i, ativo=True,
        ))
    db.commit()


def _vencer(db, oferta):
    oferta.prazo_em = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()


def test_oferta_vencida_passa_para_o_proximo(db, loja_a):
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db)

    assert resultado["expiradas"] == 1
    assert resultado["reofertadas"] == 1
    nova = db.query(OfertaLead).filter(OfertaLead.estado == "aberta").one()
    assert nova.vendedor_id != oferta.vendedor_id


def test_volta_completa_esgota(db, loja_a):
    _fila(db, loja_a["loja_id"], 1)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db)

    assert resultado["esgotadas"] == 1
    assert db.query(OfertaLead).filter(OfertaLead.estado == "aberta").count() == 0


def test_oferta_travada_nao_expira(db, loja_a):
    """Pegou e não ligou: fica travado, não volta para a fila (spec §5.3)."""
    _fila(db, loja_a["loja_id"], 2)
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    oferta.estado = "travada"
    _vencer(db, oferta)

    resultado = RodizioWorker().run_once(db)

    assert resultado["expiradas"] == 0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_job.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_job.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.rodizio_job'`.

- [ ] **Step 3: Implementar**

```python
# chatbot-api/app/rodizio_job.py
"""Worker do prazo do rodízio (spec §5.3): o timer é nosso, não Wait do n8n."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models_db import OfertaLead
from app.rodizio import abrir_oferta


class RodizioWorker:
    def run_once(self, db: Session) -> dict[str, int]:
        agora = datetime.now(timezone.utc)
        vencidas = (
            db.query(OfertaLead)
            .filter(
                OfertaLead.estado == "aberta",
                OfertaLead.prazo_em.isnot(None),
                OfertaLead.prazo_em <= agora,
            )
            .all()
        )

        contagem = {"expiradas": 0, "reofertadas": 0, "esgotadas": 0}
        for oferta in vencidas:
            oferta.estado = "expirada"
            contagem["expiradas"] += 1
            db.commit()

            nova = abrir_oferta(db, oferta.loja_id, oferta.telefone_cliente)
            if nova is None:
                contagem["esgotadas"] += 1
            else:
                contagem["reofertadas"] += 1
        return contagem
```

> A expiração marca `expirada` **antes** de reofertar de propósito: se `abrir_oferta` levantar, a
> oferta vencida não fica viva com prazo no passado, sendo reprocessada a cada ciclo.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_job.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_job.py -q`
Esperado: PASS nos 3 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/rodizio_job.py chatbot-api/tests/test_rodizio_job.py
git commit -m "feat(chatbot): worker de expiracao do rodizio"
```

---

### Task 7: Gate de suspensão e flag

**Files:**
- Modify: `chatbot-api/app/config.py`
- Modify: `chatbot-api/app/rodizio.py`
- Test: `chatbot-api/tests/test_rodizio_gate.py`

**Interfaces:**
- Produces: `MODO2_ENABLED` em `config.py` e
  `loja_opera_modo2(db, loja_id) -> bool` em `rodizio.py`. `abrir_oferta` devolve `None` quando o
  gate reprova — um ponto só, como manda a §6.3.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_rodizio_gate.py
from app.models_db import FilaVendedor, LojaOperacionalProjecao
from app.rodizio import abrir_oferta, loja_opera_modo2


def _fila(db, loja_id):
    db.add(FilaVendedor(
        id="f0", loja_id=loja_id, nome="V0",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()


def test_flag_off_nao_oferece(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", False)
    _fila(db, loja_a["loja_id"])
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is None


def test_loja_suspensa_nao_opera(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    projecao = db.get(LojaOperacionalProjecao, (loja_a["loja_id"], "loja"))
    projecao.state = "suspensa"
    db.commit()
    _fila(db, loja_a["loja_id"])

    assert loja_opera_modo2(db, loja_a["loja_id"]) is False
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is None


def test_loja_sem_projecao_nao_opera(db, loja_sem_projecao, monkeypatch):
    """Fail-closed: sem projeção do Control, não opera (allows_processing)."""
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_sem_projecao["loja_id"])
    assert loja_opera_modo2(db, loja_sem_projecao["loja_id"]) is False


def test_loja_ativa_com_flag_on_opera(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    _fila(db, loja_a["loja_id"])
    assert loja_opera_modo2(db, loja_a["loja_id"]) is True
    assert abrir_oferta(db, loja_a["loja_id"], "5511988887777") is not None
```

> Verificado: `provisioning.allows_processing` exige `state == "ativa"` — qualquer outro valor,
> **e a ausência de projeção**, bloqueiam. Por isso o teste só precisa tirar a loja de `"ativa"`,
> sem depender de qual é o rótulo de suspensão do Control.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_gate.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_gate.py -q`
Esperado: `ImportError: cannot import name 'loja_opera_modo2'`.

- [ ] **Step 3: Implementar**

Em `app/config.py`, junto das outras flags:

```python
# Rollout do Modo 2 (central Cloud API). Default OFF: invariante do projeto.
MODO2_ENABLED = os.getenv("CHATBOT_WHATSAPP_MODO2_ENABLED", "").lower() in {"1", "true", "yes"}
```

Em `app/rodizio.py`:

```python
from app import config
from app.provisioning import allows_processing


def loja_opera_modo2(db: Session, loja_id: str) -> bool:
    """Gate único do Modo 2 (spec §6.3).

    Suspensão é gate de backend, não item de menu: com a loja suspensa, a
    central não oferece, não expira e não trava — some tudo, não só o botão.

    Reusa ``provisioning.allows_processing`` (``app/provisioning.py:28``) em vez
    de reler a projeção: ele já é **fail-closed** (loja sem projeção também não
    opera) e já é o gate que o resto do chatbot usa. Reimplementar aqui criaria
    duas definições de "loja ativa" que divergem no primeiro estado novo que o
    Control inventar.
    """
    if not config.MODO2_ENABLED:
        return False
    return allows_processing(db, loja_id)
```

> **Este gate ainda não está completo.** Falta a terceira condição — a loja estar de fato no
> **modo 2** —, e ela só pode existir depois que o Control souber o que é modo. O
> [card 4](2026-08-13-wa-modo2-4-control-toggle.md), Task 4, acrescenta essa cláusula. **Não ligue a
> flag num ambiente com mais de uma loja antes do card 4**: com só estas duas condições, toda loja
> ativa entra no rodízio, inclusive as de Modo 1.

E no começo de `abrir_oferta`, antes de qualquer consulta:

```python
    if not loja_opera_modo2(db, loja_id):
        return None
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_rodizio_gate.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_rodizio_gate.py -q`
Esperado: PASS.

> Os testes das Tasks 4–6 vão passar a precisar de `MODO2_ENABLED=True`. Adicione o
> `monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)` nos testes daquelas tasks —
> é a prova de que o default OFF está valendo de verdade.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/config.py chatbot-api/app/rodizio.py chatbot-api/tests/test_rodizio_gate.py chatbot-api/tests/test_rodizio_store.py chatbot-api/tests/test_rodizio_trava.py chatbot-api/tests/test_rodizio_job.py
git commit -m "feat(chatbot): gate de suspensao e flag do Modo 2"
```

---

### Task 8: HTTP da fila — o Portal desenha a tela

**Files:**
- Modify: `chatbot-api/app/main.py` (rotas novas junto das de canal, ~`:242`)
- Test: `chatbot-api/tests/test_fila_rotas.py`

**Interfaces:**
- Produces, todas sob `get_contexto` (Bearer → loja):
  - `GET /v1/fila-vendedores` → `[{id, nome, telefone, ordem, ativo}]`, ordenado.
  - `POST /v1/fila-vendedores` `{nome, telefone, ordem}` → 201 com o item.
  - `PATCH /v1/fila-vendedores/{id}` `{nome?, telefone?, ordem?, ativo?}` → item.
  - `DELETE /v1/fila-vendedores/{id}` → 204, inativação lógica (`ativo=False`), nunca `DELETE` de
    linha: oferta antiga referencia o vendedor por FK.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_fila_rotas.py
def test_criar_e_listar_vendedor(client, loja_a):
    resposta = client.post(
        "/v1/fila-vendedores",
        json={"nome": "João", "telefone": "(11) 99999-8888", "ordem": 0},
        headers=loja_a["headers"],
    )
    assert resposta.status_code == 201
    criado = resposta.json()
    assert criado["nome"] == "João"
    # Normalizado na entrada: o lojista digita como quiser.
    assert criado["telefone"] == "11999998888"

    listagem = client.get("/v1/fila-vendedores", headers=loja_a["headers"])
    assert [v["nome"] for v in listagem.json()] == ["João"]


def test_sem_credencial_e_401(client):
    assert client.get("/v1/fila-vendedores").status_code == 401


def test_apagar_e_inativacao_logica(client, loja_a):
    criado = client.post(
        "/v1/fila-vendedores",
        json={"nome": "João", "telefone": "11999998888", "ordem": 0},
        headers=loja_a["headers"],
    ).json()

    assert client.delete(
        f"/v1/fila-vendedores/{criado['id']}", headers=loja_a["headers"]
    ).status_code == 204

    assert client.get("/v1/fila-vendedores", headers=loja_a["headers"]).json() == []
```

> `client` (`conftest.py:94`) é o `TestClient`; o Bearer sai de `loja_a["headers"]`. Não existe
> fixture `headers_servico` — não invente uma.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_fila_rotas.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_fila_rotas.py -q`
Esperado: 404 nas rotas.

- [ ] **Step 3: Implementar**

Em `app/main.py`, junto das rotas de canal:

```python
class FilaVendedorInput(BaseModel):
    nome: str
    telefone: str
    ordem: int = 0


class FilaVendedorPatch(BaseModel):
    nome: str | None = None
    telefone: str | None = None
    ordem: int | None = None
    ativo: bool | None = None


def _fila_dict(v: FilaVendedor) -> dict:
    return {
        "id": v.id, "nome": v.nome, "telefone": v.telefone,
        "ordem": v.ordem, "ativo": v.ativo,
    }


@app.get("/v1/fila-vendedores")
def listar_fila_vendedores(ctx=Depends(get_contexto), db: Session = Depends(get_db)):
    from app.rodizio import _fila_ordenada
    return [_fila_dict(v) for v in _fila_ordenada(db, ctx.loja_id)]


@app.post("/v1/fila-vendedores", status_code=201)
def criar_fila_vendedor(
    entrada: FilaVendedorInput,
    ctx=Depends(get_contexto),
    db: Session = Depends(get_db),
):
    telefone = normalizar_telefone(entrada.telefone)
    if not telefone:
        raise HTTPException(status_code=422, detail="telefone inválido")
    vendedor = FilaVendedor(
        id=str(uuid.uuid4()), loja_id=ctx.loja_id, nome=entrada.nome.strip(),
        telefone=telefone, ordem=entrada.ordem, ativo=True,
    )
    db.add(vendedor)
    db.commit()
    return _fila_dict(vendedor)


@app.patch("/v1/fila-vendedores/{vendedor_id}")
def atualizar_fila_vendedor(
    vendedor_id: str,
    entrada: FilaVendedorPatch,
    ctx=Depends(get_contexto),
    db: Session = Depends(get_db),
):
    vendedor = (
        db.query(FilaVendedor)
        .filter(FilaVendedor.id == vendedor_id, FilaVendedor.loja_id == ctx.loja_id)
        .first()
    )
    if vendedor is None:
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    if entrada.nome is not None:
        vendedor.nome = entrada.nome.strip()
    if entrada.telefone is not None:
        telefone = normalizar_telefone(entrada.telefone)
        if not telefone:
            raise HTTPException(status_code=422, detail="telefone inválido")
        vendedor.telefone = telefone
    if entrada.ordem is not None:
        vendedor.ordem = entrada.ordem
    if entrada.ativo is not None:
        vendedor.ativo = entrada.ativo
    db.commit()
    return _fila_dict(vendedor)


@app.delete("/v1/fila-vendedores/{vendedor_id}", status_code=204)
def remover_fila_vendedor(
    vendedor_id: str,
    ctx=Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Inativação lógica: oferta antiga referencia o vendedor por FK."""
    vendedor = (
        db.query(FilaVendedor)
        .filter(FilaVendedor.id == vendedor_id, FilaVendedor.loja_id == ctx.loja_id)
        .first()
    )
    if vendedor is None:
        raise HTTPException(status_code=404, detail="vendedor não encontrado")
    vendedor.ativo = False
    db.commit()
```

Importar no topo o que faltar: `FilaVendedor` de `app.models_db`, `normalizar_telefone` de
`app.operacao`, `uuid`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_fila_rotas.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_fila_rotas.py -q`
Esperado: PASS.

- [ ] **Step 5: Suíte inteira**

Run: `cd chatbot-api && .venv/bin/python -m pytest -q && git diff --check && git status --short`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
Esperado: tudo verde; nada de arquivo alheio no diff.

- [ ] **Step 6: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_fila_rotas.py
git commit -m "feat(chatbot): HTTP da fila de vendedores"
```

---

## Self-Review

- §5.3 ponteiro rotativo avançando por oferta: Tasks 3–4. **Coberto.**
- §5.3 um lead pendente por vendedor: `pendentes` em `escolher_proximo`, Task 3. **Coberto.**
- §5.3 fila vazia / vendedor inativo: Tasks 3–4. **Coberto.**
- §5.3 10 min e uma volta e para: Task 6. **Coberto.**
- §5.3 pegou e não ligou fica travado: Task 6, `test_oferta_travada_nao_expira`. **Coberto.**
- §5.7 primeiro clique vence mesmo atrasado + idempotência: Task 5. **Coberto.**
- §6.3 suspensão e flag OFF: Task 7. **Coberto.**
- §5.3 fila cadastrada pelo lojista: Task 8 expõe o contrato; a **tela** é do card da Loja.
- Envio do template/interativo ao vendedor, gatilhos, mídia e follow-up: **card 2b**, como declarado
  no Escopo. Este card não manda mensagem nenhuma — só decide e registra.
