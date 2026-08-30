# Embedded Signup — Card 2: estado do canal, retomada e segredos

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar task a task. Os passos usam
> checkbox (`- [ ]`).

**Goal:** o canal Cloud passa a guardar até onde o onboarding chegou e os segredos da loja
cifrados, e a projeção `whatsapp_modo=2` vinda do Control passa a ativar o canal pendente.

**Architecture:** só `chatbot-api`. Migration expand-only no `whatsapp_canais`, um módulo
novo de cifra, e um gancho no ponto onde a projeção do Control já é aplicada. **Nenhuma
chamada à Meta neste card** — por isso ele não depende do Card 1 e pode ser feito agora.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest, `cryptography` (dependência nova).

**Spec:** [`../referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`](../specs/2026-08-29-embedded-signup-tech-provider-design.md)

## Global Constraints

- **Testes a partir de `chatbot-api/`**, senão importa o `app` errado. Cada produto tem seu
  próprio `.venv`: `.venv/bin/python -m pytest -q` (macOS) e
  `.\.venv\Scripts\python.exe -m pytest -q` (Windows).
- **Migration expand-only**, colunas nullable, sem backfill — mesmo padrão da
  `0025_canal_cloud_por_loja`. **Nunca `batch_alter_table`**: Portal e Chatbot estão em
  Postgres desde 23/08 e ele estoura lá.
- **Não renomear `evolution_instance`.** Ela guarda o `phone_number_id` no Modo 2, é a chave
  de roteamento do inbound e é `UNIQUE` de propósito (`models_db.py:60-67`).
- **Não criar coluna de estado nova.** `WhatsAppCanal.estado` já existe e o vocabulário do
  Modo 2 já está em `whatsapp_provider.ESTADOS_VALIDOS`: `cloud_pendente`, `cloud_ativo`,
  `cloud_restrito`, `cloud_banido`.
- Segredo não vai para log, para git nem para rota de leitura.
- Ao terminar: `git diff --check`, `git status --short`, e regerar o mapa
  (`cd .claude/skills/revy-research && python gerar_mapa.py`) porque este card mexe em
  modelo e migration.

---

### Task 1: colunas de retomada no canal

**Files:**
- Create: `chatbot-api/alembic/versions/0028_canal_onboarding.py`
- Modify: `chatbot-api/app/models_db.py` (classe `WhatsAppCanal`, depois de `template_oferta`)
- Test: `chatbot-api/tests/test_canal_onboarding_campos.py`

**Interfaces:**
- Produces: `WhatsAppCanal.business_id: str | None`,
  `WhatsAppCanal.onboarding_elo: int | None`, `WhatsAppCanal.onboarding_erro: str | None`,
  `WhatsAppCanal.token_cifrado: str | None`, `WhatsAppCanal.pin_cifrado: str | None`,
  `WhatsAppCanal.registro_tentativas: int` (default `0`, nunca nulo).
  O Card 3 grava `onboarding_elo` a cada elo concluído e retoma a partir dele, e incrementa
  `registro_tentativas` **antes** de cada chamada ao elo 3.

- [x] **Passo 1: escrever o teste que falha**

```python
# chatbot-api/tests/test_canal_onboarding_campos.py
"""Campos de retomada do onboarding Cloud (spec §5).

Canal antigo nao ganha valor nenhum: a migration e expand-only e sem backfill,
entao tudo nasce None e o Modo 1 nao muda.

A loja vem da fixture `loja_a` do conftest — `Loja.evolution_instance` e
obrigatoria e UNIQUE, entao construir Loja a mao no teste quebra na segunda.
"""
import uuid

from app.models_db import WhatsAppCanal


def _canal(loja_id, instance, **campos):
    """WhatsAppCanal minimo. `id` nao tem default e `e164_or_label` e NOT NULL."""
    return WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label="linha-cloud",
        evolution_instance=instance,
        **campos,
    )


def test_campos_de_onboarding_nascem_nulos(db, loja_a):
    canal = _canal(loja_a["loja_id"], "1227059273831581")
    db.add(canal)
    db.commit()
    db.refresh(canal)

    assert canal.business_id is None
    assert canal.onboarding_elo is None
    assert canal.onboarding_erro is None
    assert canal.token_cifrado is None
    assert canal.pin_cifrado is None
    # Contador do teto de 10/72h do elo 3: nasce 0, nunca None.
    assert canal.registro_tentativas == 0


def test_campos_de_onboarding_guardam_valor(db, loja_a):
    canal = _canal(
        loja_a["loja_id"],
        "1227059273831582",
        waba_id="waba-1",
        business_id="biz-1",
        onboarding_elo=3,
        onboarding_erro="numero ainda ativo no aplicativo",
    )
    db.add(canal)
    db.commit()
    db.refresh(canal)

    assert canal.business_id == "biz-1"
    assert canal.onboarding_elo == 3
    assert canal.onboarding_erro == "numero ainda ativo no aplicativo"
```

- [x] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canal_onboarding_campos.py -q`
Esperado: FAIL com `TypeError: 'business_id' is an invalid keyword argument`.

- [x] **Passo 3: acrescentar as colunas ao modelo**

Em `app/models_db.py`, na classe `WhatsAppCanal`, logo depois de `template_oferta`:

```python
    # Portfólio empresarial do cliente, devolvido pelo embedded signup. Só
    # identificador, não é segredo.
    business_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Até qual elo da cadeia do onboarding chegou (spec §7). Nulo = canal que
    # não nasceu pelo embedded signup — todo canal Modo 1 e a loja piloto.
    onboarding_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Motivo da parada, em texto para a tela. Nunca guarda corpo de resposta da
    # Meta: resposta de erro pode carregar identificador de token.
    onboarding_erro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Token de negócio da loja e PIN de duas etapas, CIFRADOS (ver
    # app/segredo_canal.py). Nunca saem em rota de leitura nem em log.
    token_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    pin_cifrado: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Quantas vezes o elo 3 (POST /{phone_number_id}/register) foi chamado.
    # A Meta permite 10 por número em 72h móveis; estourar devolve 133016 e
    # TRAVA o número por três dias. O Card 3 para bem antes de 10 — por isso o
    # contador é coluna, não métrica.
    registro_tentativas: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
```

Confirme que `Integer` e `Text` estão no import de `sqlalchemy` no topo do arquivo;
acrescente o que faltar.

- [x] **Passo 4: escrever a migration**

```python
# chatbot-api/alembic/versions/0028_canal_onboarding.py
"""whatsapp_canais: campos de retomada e segredos do embedded signup

Revision ID: 0028_canal_onboarding
Revises: 0027_agente_config

Expand-only, todas nullable e sem backfill: canal que nao nasceu pelo embedded
signup (todo Modo 1 e a loja piloto) continua com None e nada muda para ele.

Sem batch_alter_table: o chatbot esta em Postgres desde 23/08 e ele estoura la.

Nao ha coluna de estado nova de proposito — `estado` ja existe e o vocabulario
do Modo 2 mora em whatsapp_provider.ESTADOS_VALIDOS.
"""
import sqlalchemy as sa
from alembic import op


revision = "0028_canal_onboarding"
down_revision = "0027_agente_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "whatsapp_canais",
        sa.Column("business_id", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("onboarding_elo", sa.Integer(), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("onboarding_erro", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("token_cifrado", sa.Text(), nullable=True),
    )
    op.add_column(
        "whatsapp_canais",
        sa.Column("pin_cifrado", sa.String(length=255), nullable=True),
    )
    # NOT NULL com server_default: canal antigo nasce com 0 sem backfill, e o
    # contador nunca e None no codigo que decide se ainda pode tentar.
    op.add_column(
        "whatsapp_canais",
        sa.Column(
            "registro_tentativas",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_canais", "registro_tentativas")
    op.drop_column("whatsapp_canais", "pin_cifrado")
    op.drop_column("whatsapp_canais", "token_cifrado")
    op.drop_column("whatsapp_canais", "onboarding_erro")
    op.drop_column("whatsapp_canais", "onboarding_elo")
    op.drop_column("whatsapp_canais", "business_id")
```

- [x] **Passo 5: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canal_onboarding_campos.py -q`
Esperado: 2 passed.

- [x] **Passo 6: rodar a suíte inteira**

Rode: `.\.venv\Scripts\python.exe -m pytest -q`
Esperado: verde. Se `test_cloud_canal_por_loja.py` quebrar, é sinal de que uma coluna
ganhou default não-nulo por engano — todas nascem `None`.

- [x] **Passo 7: commitar**

```bash
git add chatbot-api/app/models_db.py chatbot-api/alembic/versions/0028_canal_onboarding.py chatbot-api/tests/test_canal_onboarding_campos.py
git commit -m "feat(canal): o canal guarda ate onde o onboarding chegou"
```

---

### Task 2: cifra dos segredos da loja

**Files:**
- Create: `chatbot-api/app/segredo_canal.py`
- Modify: `chatbot-api/app/config.py`, `chatbot-api/requirements.txt`
- Test: `chatbot-api/tests/test_segredo_canal.py`

**Interfaces:**
- Produces: `cifrar(valor: str) -> str` e `decifrar(cifrado: str) -> str`, e a exceção
  `SegredoIndisponivel`. O Card 3 chama `cifrar` antes de gravar o token do elo 1 e o PIN
  do elo 3.

- [x] **Passo 1: escrever o teste que falha**

```python
# chatbot-api/tests/test_segredo_canal.py
"""Cifra dos segredos por loja (spec §8).

Fail-closed de proposito: sem chave configurada nao ha degradacao para texto
puro. Guardar token de cliente em claro por causa de um secret esquecido e
pior do que a rota falhar.
"""
import pytest

from app import segredo_canal


CHAVE = "LvALLRsc3ZykD4ZrrFrm25elgLGhYThKQ7Z2ili9KYw="


def test_cifrado_nao_e_o_texto(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)
    cifrado = segredo_canal.cifrar("EAAG-token-de-negocio")
    assert cifrado != "EAAG-token-de-negocio"
    assert "EAAG" not in cifrado


def test_ida_e_volta(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)
    assert segredo_canal.decifrar(segredo_canal.cifrar("123456")) == "123456"


def test_duas_cifras_do_mesmo_valor_diferem(monkeypatch):
    """Fernet poe nonce: valor igual nao vira cifra igual.

    Importa porque a coluna e indexavel por engano — cifra deterministica
    deixaria comparar tokens sem decifrar.
    """
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", CHAVE)
    assert segredo_canal.cifrar("igual") != segredo_canal.cifrar("igual")


def test_sem_chave_falha_fechado(monkeypatch):
    monkeypatch.setattr(segredo_canal.config, "CANAL_SECRET_KEY", "")
    with pytest.raises(segredo_canal.SegredoIndisponivel):
        segredo_canal.cifrar("qualquer")
```

- [x] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_segredo_canal.py -q`
Esperado: FAIL com `ModuleNotFoundError: No module named 'app.segredo_canal'`.

- [x] **Passo 3: acrescentar a dependência**

Em `chatbot-api/requirements.txt`, depois de `psycopg[binary]==3.*`:

```
cryptography==43.*
```

Instale: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

- [x] **Passo 4: acrescentar a chave ao config**

Em `chatbot-api/app/config.py`, junto das outras leituras de ambiente:

```python
# Chave Fernet (urlsafe base64, 32 bytes) da cifra dos segredos por loja.
# É secret no app2037, nunca [env]: ela abre o token de WhatsApp de todo cliente.
CANAL_SECRET_KEY = os.getenv("CHATBOT_CANAL_SECRET_KEY", "")
```

- [x] **Passo 5: escrever o módulo**

```python
# chatbot-api/app/segredo_canal.py
"""Cifra em repouso dos segredos que pertencem a cada loja (spec §8).

Token de negócio e PIN de duas etapas chegam pelo embedded signup e são da
loja, não do Revy — o que é do Revy (App Secret, verify token) continua em
variável de ambiente e nunca encosta aqui.

Fail-closed: sem ``CHATBOT_CANAL_SECRET_KEY`` a operação levanta em vez de
guardar em claro. Secret esquecido vira erro visível, não vazamento calado.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app import config


class SegredoIndisponivel(RuntimeError):
    """Chave de cifra ausente ou inválida."""


def _fernet() -> Fernet:
    chave = (config.CANAL_SECRET_KEY or "").strip()
    if not chave:
        raise SegredoIndisponivel("CHATBOT_CANAL_SECRET_KEY não configurada")
    try:
        return Fernet(chave.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SegredoIndisponivel("CHATBOT_CANAL_SECRET_KEY inválida") from exc


def cifrar(valor: str) -> str:
    return _fernet().encrypt(valor.encode("utf-8")).decode("utf-8")


def decifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SegredoIndisponivel("valor cifrado não abre com esta chave") from exc
```

- [x] **Passo 6: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_segredo_canal.py -q`
Esperado: 4 passed.

- [x] **Passo 7: commitar**

```bash
git add chatbot-api/app/segredo_canal.py chatbot-api/app/config.py chatbot-api/requirements.txt chatbot-api/tests/test_segredo_canal.py
git commit -m "feat(canal): segredo de loja e cifrado em repouso, e falha fechado sem chave"
```

---

### Task 3: o segredo não sai em rota de leitura

**Files:**
- Test: `chatbot-api/tests/test_canal_nao_vaza_segredo.py`
- Modify: `chatbot-api/app/channels.py` (só se o teste reprovar)

**Interfaces:**
- Consumes: as colunas da Task 1.

- [x] **Passo 1: escrever o teste que falha (ou não)**

```python
# chatbot-api/tests/test_canal_nao_vaza_segredo.py
"""GET /v1/whatsapp/canais nao pode devolver segredo (spec §8).

A tela de numeros da Loja lista canais. Uma chave a mais no serializer
mandaria o token de WhatsApp do cliente para o navegador.
"""
import uuid

from app.models_db import WhatsAppCanal

PROIBIDOS = {"token_cifrado", "pin_cifrado", "token", "pin", "access_token"}


def test_listagem_nao_traz_campo_de_segredo(client, db, loja_a):
    db.add(
        WhatsAppCanal(
            id=str(uuid.uuid4()),
            loja_id=loja_a["loja_id"],
            e164_or_label="linha-cloud",
            evolution_instance="1227059273831583",
            waba_id="waba-1",
            token_cifrado="gAAAAA-cifrado",
            pin_cifrado="gAAAAA-cifrado",
        )
    )
    db.commit()

    resposta = client.get("/v1/whatsapp/canais", headers=loja_a["headers"])
    assert resposta.status_code == 200

    canais = resposta.json()["canais"]
    assert canais, "a loja precisa ter canal, senao o teste passa sem olhar nada"
    for canal in canais:
        assert PROIBIDOS.isdisjoint(canal.keys()), canal.keys()
    assert "gAAAAA-cifrado" not in resposta.text
```

As fixtures `client`, `db` e `loja_a` são as do `tests/conftest.py`; `loja_a["headers"]`
já traz o `Authorization: Bearer`. Não crie fixture nova.

- [x] **Passo 2: rodar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canal_nao_vaza_segredo.py -q`
Esperado: PASS, porque o serializer de canais (`app/channels.py:27`, `_canal_dict`) é
explícito campo a campo. **Se falhar**,
o serializer está devolvendo o modelo inteiro — conserte listando os campos, nunca com um
`exclude`, que volta a vazar na próxima coluna.

- [x] **Passo 3: commitar**

```bash
git add chatbot-api/tests/test_canal_nao_vaza_segredo.py
git commit -m "test(canal): a listagem de canais nao pode devolver segredo"
```

---

### Task 4: a projeção do Control ativa o canal pendente

**Files:**
- Modify: `chatbot-api/app/provisioning.py` (função `_apply_envelope`, linha 71)
- Test: `chatbot-api/tests/test_canal_ativa_pela_projecao.py`

**Interfaces:**
- Consumes: `_apply_envelope(db, loja_id, envelope, aggregate) -> str`, que já devolve
  `"applied"`, `"stale"` ou `"idempotent"`.
- Produces: nenhuma assinatura nova. O efeito é o canal `cloud_pendente` da loja virar
  `cloud_ativo` quando a projeção `whatsapp_modo=2` é aplicada.

**Por que aqui:** é o portão da §9 do spec. O Control não ganha rota nova — ele já projeta
`whatsapp_modo` com versionamento, e "liberar a loja" continua sendo só isso.

- [x] **Passo 1: escrever o teste que falha**

```python
# chatbot-api/tests/test_canal_ativa_pela_projecao.py
"""O portao do Control (spec §9).

Liberar a loja e projetar whatsapp_modo=2. O canal Cloud que nasceu pendente
vira ativo junto — uma decisao, um lugar, sem segunda rota de escrita.
"""
import uuid

from app import provisioning
from app.models_db import WhatsAppCanal


def _canal_pendente(db, loja_id, instance):
    canal = WhatsAppCanal(
        id=str(uuid.uuid4()),
        loja_id=loja_id,
        e164_or_label="linha-cloud",
        evolution_instance=instance,
        waba_id="waba-1",
        estado="cloud_pendente",
    )
    db.add(canal)
    db.commit()
    return canal


def test_projecao_modo_2_ativa_o_canal_pendente(db, loja_a):
    canal = _canal_pendente(db, loja_a["loja_id"], "1227059273831584")

    resultado = provisioning._apply_envelope(
        db,
        loja_a["loja_id"],
        {"version": 99, "state": "2", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert resultado == "applied"
    assert canal.estado == "cloud_ativo"


def test_projecao_modo_1_nao_mexe_no_canal(db, loja_a):
    """Modo 1 nao desativa: quem barra o Modo 2 e loja_opera_modo2, que ja le a
    projecao. Mexer no canal aqui seria um segundo gate dizendo a mesma coisa."""
    canal = _canal_pendente(db, loja_a["loja_id"], "1227059273831585")

    provisioning._apply_envelope(
        db,
        loja_a["loja_id"],
        {"version": 99, "state": "1", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert canal.estado == "cloud_pendente"


def test_envelope_velho_nao_ativa(db, loja_b):
    """Stale nao aplica projecao, entao nao pode ativar canal tambem."""
    canal = _canal_pendente(db, loja_b["loja_id"], "1227059273831586")
    provisioning._apply_envelope(
        db,
        loja_b["loja_id"],
        {"version": 99, "state": "1", "event_id": "e1"},
        "whatsapp_modo",
    )
    db.commit()

    resultado = provisioning._apply_envelope(
        db,
        loja_b["loja_id"],
        {"version": 2, "state": "2", "event_id": "e0"},
        "whatsapp_modo",
    )
    db.commit()
    db.refresh(canal)

    assert resultado == "stale"
    assert canal.estado == "cloud_pendente"


def test_loja_sem_canal_nao_estoura(db, loja_sem_projecao):
    resultado = provisioning._apply_envelope(
        db,
        loja_sem_projecao["loja_id"],
        {"version": 99, "state": "2", "event_id": "e1"},
        "whatsapp_modo",
    )

    assert resultado == "applied"
```

**`version=99` não é enfeite:** as fixtures do conftest já semeiam projeção operacional
para a loja, e `_apply_envelope` é monotônico — envelope com versão menor volta `"stale"` e
o teste passaria sem exercitar nada.

- [x] **Passo 2: rodar e ver falhar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canal_ativa_pela_projecao.py -q`
Esperado: FAIL no primeiro teste — `assert 'cloud_pendente' == 'cloud_ativo'`.

- [x] **Passo 3: escrever a ativação**

Em `app/provisioning.py`, acrescente o import do modelo no topo:

```python
from app.models_db import LojaOperacionalProjecao, WhatsAppCanal, _agora
```

E a função, acima de `_apply_envelope`:

```python
def _liberar_canal_cloud(db: Session, loja_id: str) -> None:
    """Portão do Control (spec §9): liberar a loja ativa o canal que esperava.

    Só sobe de ``cloud_pendente``. Canal restrito ou banido pela Meta não volta
    por decisão nossa, e canal já ativo não é tocado.
    """
    canais = (
        db.query(WhatsAppCanal)
        .filter(
            WhatsAppCanal.loja_id == loja_id,
            WhatsAppCanal.waba_id.isnot(None),
            WhatsAppCanal.estado == "cloud_pendente",
        )
        .all()
    )
    for canal in canais:
        canal.estado = "cloud_ativo"
```

E, no fim de `_apply_envelope`, nos **dois** pontos que devolvem `"applied"`, chame a
liberação antes do `return`:

```python
        existing.atualizado_em = _agora()
        if aggregate == "whatsapp_modo" and state == "2":
            _liberar_canal_cloud(db, loja_id)
        return "applied"
```

```python
    )
    if aggregate == "whatsapp_modo" and state == "2":
        _liberar_canal_cloud(db, loja_id)
    return "applied"
```

São dois pontos porque a projeção tem caminho de update e caminho de insert. Esquecer o
segundo faz a **primeira** liberação de cada loja não ativar nada — que é justamente o
caso real, já que a loja nova nunca teve projeção antes.

- [x] **Passo 4: rodar e ver passar**

Rode: `.\.venv\Scripts\python.exe -m pytest tests/test_canal_ativa_pela_projecao.py -q`
Esperado: 4 passed.

- [x] **Passo 5: rodar a suíte inteira**

Rode: `.\.venv\Scripts\python.exe -m pytest -q`
Esperado: verde, incluindo `test_provisioning*` e `test_rodizio*`.

- [x] **Passo 6: commitar**

```bash
git add chatbot-api/app/provisioning.py chatbot-api/tests/test_canal_ativa_pela_projecao.py
git commit -m "feat(canal): liberar a loja no Control ativa o canal Cloud que esperava"
```

---

### Task 5: fechamento

- [x] **Passo 1:** `alembic upgrade head` no `chatbot-api`, com `CHATBOT_DATABASE_URL`
      apontando para o banco certo. Sem a variável o alembic responde SQLite e **mente**.
- [x] **Passo 2:** Gerar a chave Fernet e pô-la como **secret** (nunca `[env]`):
      `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
      e `fly secrets set CHATBOT_CANAL_SECRET_KEY=... -a app2037`. Agrupe com outros
      secrets se houver — `fly secrets set` reinicia a máquina.
- [x] **Passo 3:** `git diff --check` e `git status --short`.
- [x] **Passo 4:** Regerar o mapa e commitar junto:
      `cd .claude/skills/revy-research && python gerar_mapa.py`.

## Como saber que acabou

`.\.venv\Scripts\python.exe -m pytest -q` verde a partir de `chatbot-api/`, `alembic
current` mostrando `0028_canal_onboarding`, e um canal `cloud_pendente` virando
`cloud_ativo` quando o Control projeta `whatsapp_modo=2`.

---

## Executado em 29/08/2026 — o que o card errou

Quatro commits: `dadb6be`, `96533e5`, `ff82264`, `ffc51e7`. Suíte do chatbot-api
em **633 passed**. Três coisas escritas aqui não sobreviveram ao contato com o
código, e já estão corrigidas acima:

1. **A chave Fernet de exemplo era inválida.** Tinha 48 caracteres base64 → 35
   bytes; `Fernet()` exige 32 e teria levantado no primeiro teste. Trocada por
   uma gerada de verdade. Chave de teste não se escreve à mão.
2. **O serializer de canais não mora em `app/main.py`.** A rota
   `GET /v1/whatsapp/canais` (`main.py:1772`) delega para
   `channels.list_channels`, e quem monta o dicionário é `_canal_dict`
   (`app/channels.py:27`). O card mandava consertar no arquivo errado.
3. **Os quatro testes da Task 4 passavam com o gancho do caminho de update
   apagado.** O `conftest` só semeia projeção de `loja`, `vendas` e `estoque`,
   nunca `whatsapp_modo` — então todo primeiro envelope desse aggregate cai no
   *insert*, e o `return "applied"` do update ficava sem rede. Acrescentado
   `test_loja_ja_projetada_ativa_ao_virar_modo_2`, que é o caso real da loja já
   no Modo 1 sendo promovida. Verificado comentando o gancho: só o teste novo
   quebra. Virou learning
   (`2026-08-29-o-conftest-do-chatbot-nao-semeia-todo-aggregate.md`).

A migration foi exercitada sozinha contra um SQLite descartável stampado em
`0027`: as seis colunas entram e um canal Modo 1 pré-existente fica com tudo
`None` e `registro_tentativas = 0`. **O Postgres não foi exercitado** — a cadeia
completa não roda em SQLite (uma migration antiga altera constraint), e aplicar
em produção é o `alembic upgrade head` do boot do bundle, no deploy.

## Task 5 — o que falta, e é do dono

- [ ] `CHATBOT_CANAL_SECRET_KEY` como **secret** no `app2037`. Gerar com
      `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
      `fly secrets set` reinicia a máquina — agrupe com outros secrets se houver.
      **Sem esta chave o Card 3 falha fechado**, que é o comportamento desejado,
      mas o onboarding não anda.
- [ ] Deploy do `app2037` (roda a `0028` no boot, fail-fast). Nada aqui muda
      comportamento de loja nenhuma antes do Card 3 — a única mudança visível é
      o canal `cloud_pendente` passando a `cloud_ativo` quando o Control projeta
      `whatsapp_modo=2`, e hoje não existe canal nesse estado.
