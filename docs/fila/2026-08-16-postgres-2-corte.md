# Postgres, leva 2 — o corte de Portal e Control para o banco `revy`

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para executar tarefa a tarefa.
> Os passos usam checkbox (`- [ ]`).

**Goal:** mover `portal.db` (564 KB) e `revy_trafego.db` (872 KB) para o Postgres que já
existe (`suite-pg`), num banco novo `revy` com schema por produto, **sem perder uma linha
e sem alterar um centavo** — e com um caminho de aborto que não muda nada em produção.

**Architecture:** três ferramentas pequenas e independentes do modelo — elas **refletem**
o schema em vez de importar `app.models`, porque o Portal e o Control têm ambos um pacote
chamado `app` e nenhum processo pode importar os dois. `verificar.py` roda **antes** e
recusa tudo que o Postgres vai recusar (órfão de FK, string maior que a coluna, NULL em
NOT NULL, booleano fora de 0/1, decimal com mais casas que a escala). `copiar.py` carrega
tabela a tabela em ordem topológica de FK, convertendo por **tipo de destino**.
`validar.py` compara os dois lados linha a linha, soma a soma, e é ele que libera ou
aborta o corte. As tabelas no destino são criadas pelo `alembic upgrade head` de cada
produto — nunca por `create_all`, nunca por DDL escrito à mão.

**Tech Stack:** SQLAlchemy 2 (reflection + Core), psycopg 3 (já em ambos os
`requirements.txt`), alembic 1.14, Postgres 18.1 no `suite-pg`, pytest.

**Spec:** `docs/referencia-viva/specs/2026-08-16-portal-control-para-postgres-design.md`
— leia §1 (estado medido), §2 (decisões D1–D4), §3 (os perigos) e §4 (o plano). §5 e §6
são sobre o que esta leva **não** resolve; leia por último.

## Global Constraints

- **Calibrado em `010e07a`.** As cadeias de migration estão lineares e com um head cada:
  Portal `0001_cria_usuarios` → **`0026_copiloto_sinal_destinatario`**; Control
  `0001_revy_trafego_baseline` → **`0020_loja_whatsapp_modo`**. O merge `5607c64` renumerou
  o card do sino (era `0024`, virou `0026`) — comando escrito antes disso aponta para
  revision que não existe mais. **Antes de começar, reconfira:** as duas cadeias ainda
  precisam ter head único.
- **Nenhuma senha de banco no repo, no log, no histórico de shell ou num arquivo dentro
  da árvore do projeto.** As URLs completas entram por `fly secrets import` lendo um
  arquivo escrito em editor, fora do repo, apagado depois. Nunca `echo "...senha..."`.
- **Não destruir app nem volume Fly.** Nada de `fly apps destroy`, `fly volumes destroy`,
  `git clean -fdX`. Os dois `.db` **ficam no volume** por 30 dias depois do corte.
- **`create_all` é proibido no destino.** As tabelas vêm de `alembic upgrade head`, senão
  o schema de produção passa a divergir da cadeia de migrations em silêncio.
- **O corte só é liberado pelo `validar.py` com saída zero.** Qualquer divergência aborta,
  e abortar é barato: até o passo do `fly secrets import`, produção continua nos `.db`.
- **Testes das ferramentas rodam da pasta `deploy/migracao-pg/`**, com o venv do Portal
  (as ferramentas não importam `app`, então não há conflito de pacote):
  - macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest -q`
  - Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`
- **Testes dos produtos rodam da pasta do produto.** Baseline em `010e07a`:
  **Portal 1282 passed**, **Control 514 passed** (Control usa o venv do Portal — ele não
  tem `.venv` próprio). Os números deste plano assumem que a **leva 1
  (`2026-08-16-postgres-1-concorrencia.md`) ainda não entrou**; se ela já tiver entrado,
  some **12** ao total do Portal. As duas levas são independentes e podem ir em qualquer
  ordem.
- `git status --short` antes de cada commit. **Tem outra pessoa mexendo no repo.**
- Deploy só por `deploy/fly/3vm/`. Os `fly.toml` dentro das pastas de produto apontam para
  apps monolíticos destruídos.

## O que já é verdade e não precisa ser resolvido

Levantado em `010e07a` — não gaste a janela redescobrindo:

| | |
|---|---|
| Driver | `psycopg[binary]==3.*` já está nos dois `requirements.txt`. **A URL tem que ser `postgresql+psycopg://`** — `postgresql://` pede psycopg2, que não está instalado |
| Colisão de `alembic_version` | **Já resolvida**: o Control usa `version_table = "alembic_version_revy_trafego"` (`revy-trafego/alembic/env.py:19`). O Portal usa o default |
| Índice parcial único | Todo `sqlite_where` do Control tem `postgresql_where` do lado — em `models.py` **e** nas migrations `0002`/`0003`/`0007`. Sem isto, um índice parcial viraria índice total no Postgres e recusaria linha legítima |
| Sequences | **Não existem.** Nenhuma PK é `Integer`; são todas `String(36)` de `uuid4()`. Não há `setval` para acertar |
| Tipos exóticos | Nenhum. `JSON` é guardado como `Text`. Sem `ARRAY`, sem `LargeBinary`. Superfície total: `String`, `Text`, `Integer`, `BigInteger`, `Boolean`, `Numeric`, `DateTime`, `Date` |
| SQL específico de engine | Dois `text()`, ambos `SELECT 1 FROM x LIMIT 1` de healthcheck (`portal/main.py:514`, `control/main.py:337`). `funil_eventos.py:189` já ramifica dialeto para `ON CONFLICT` |
| Fuso dos timestamps | **Todo timestamp gravado é UTC.** Os dois `agora()` são `datetime.now(timezone.utc)`; o único `datetime.now()` sem tz (`portal/main.py:451`) é comparação de tela e nunca chega a coluna. É isso que autoriza a regra "naive → UTC" da Task 3 |
| Região | `app2037` e `suite-pg` estão **os dois em `iad`**. Os ~120 ms de RTT do README são do `motor2037`, que fica em `gru` de propósito |
| `FOR UPDATE` do Control | Já escrito em `control/portfolio.py:94,257`, `control/stores.py:315`, `control/password_recovery.py:144`, hoje inerte. A migração liga sozinha |

## O perigo que mata, em uma frase

`run-portal.sh:3` e `run-revy-trafego.sh:4` hoje dizem
`${PORTAL_DATABASE_URL:-sqlite:////data/portal/portal.db}`. Depois do corte, um secret
apagado, renomeado ou com typo faz o app **criar um SQLite vazio e subir saudável, com
zero dado, sem um erro no log**. É por isso que a Task 2 vem antes de tudo que é
operacional.

---

## ENSAIO FEITO — 16/08/2026. Leia antes de executar as Tasks 8 a 10.

Tasks 1 a 7 estão **DONE** e mergeadas em `main`. O ensaio (Task 8) rodou inteiro
contra o Postgres de verdade, em banco descartável `revy_ensaio`, já derrubado.
Os dois portões terminaram em **"Sem divergencia. Corte liberado."**

### Números medidos (o que a janela precisava saber)

| | Portal | Control |
|---|---|---|
| tabelas | 26 | 31 |
| linhas | 172 | 243 |
| carga | **1s** | **2s** |
| pré-voo | 0 problemas | 0 problemas |

**Zero órfão de FK** nos dois — o achado que este plano dava como "quase certo"
não existe. Os bancos são muito menores do que o arquivo sugere (610 KB e 917 KB
são quase todo página livre e índice).

**O gargalo da janela não é a carga**: são segundos. É o `alembic upgrade head`
do zero e a conferência na tela. Latência de base, com o app ainda em SQLite:
`/healthz` ~0,25–0,42 s, `/trafego/health/ready` ~0,22–0,30 s. Repetir depois do
corte e comparar.

### Quatro correções que o ensaio forçou — o plano abaixo está desatualizado

1. **Pré-crie a tabela de versão do alembic.** Ela é `VARCHAR(32)` por padrão, e
   **9 revisions passam disso** (2 no Portal, 7 no Control, a maior com 45). O
   `upgrade head` morria no meio, com o DDL já aplicado. DDL em
   `deploy/migracao-pg/README.md`. Cuidado: o Control renomeia a tabela para
   `alembic_version_revy_trafego`.
2. **Migrations 0018/0019 do Control** derrubavam a PK de `modulos_revy` que uma
   FK referencia (`batch_alter_table(recreate="always")`). Corrigidas com ramo por
   dialeto — já em `main`.
3. **Falta um `TRUNCATE` entre o alembic e a carga.** A Task 9 Step 6 diz que as
   tabelas ficam "criadas e vazias": **é falso**. Migrations semeiam catálogo
   (`op.bulk_insert` em `0007`/`0018`/`0019`), então `control.modulos_revy` nasce
   com 4 linhas e o `copiar.py` recusa a carga. SQL no README.
4. **O portão tinha um falso positivo** que abortaria um corte bom: comparava
   máximo lexicográfico (SQLite sobre TEXT) contra cronológico (Postgres). A
   origem guarda datetime em dois formatos. Corrigido — já em `main`.

### Erros no texto deste plano, achados ao executá-lo

- `fly pg connect -a suite-pg -c "\l"` (Task 10 Step 2) **não faz o que parece**:
  o `-c` do `fly pg connect` é `--config`, não `--command`. Não existe flag de
  comando. O caminho que funciona é `fly ssh console -a suite-pg` e chamar
  `/usr/lib/postgresql/18/bin/psql -h localhost -p 5433 -U postgres` com
  `PGPASSWORD=$OPERATOR_PASSWORD` (o `SU_PASSWORD` **não** autentica `postgres`).
- `fly ssh sftp put` **não sobrescreve** arquivo existente; apague antes.
- `time` não existe no container (`sh: 1: time: not found`); use `date +%s`.

### O que continua valendo e ainda é do dono

Task 9 (senhas, roles definitivas, `fly secrets import`) e Task 10 (a janela).
A janela derruba o `app2037` inteiro — Loja, Control **e o bot do WhatsApp** —
e o passo 1 continua sendo anunciar.

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `portal-gestao/app/db.py` · `revy-trafego/app/db.py` | falar Postgres: driver certo, pool que sobrevive ao Fly Proxy, `search_path` e `timezone` fixados na conexão |
| `deploy/fly/3vm/run-portal.sh` · `run-revy-trafego.sh` · `entrypoint-app.sh` | falhar alto em vez de inventar um SQLite vazio |
| `deploy/migracao-pg/tipos.py` | **novo.** Conversão de valor por tipo de destino. É aqui que dinheiro se corrompe se estiver errado |
| `deploy/migracao-pg/verificar.py` | **novo.** Pré-voo: tudo que o Postgres vai recusar, encontrado antes da janela |
| `deploy/migracao-pg/copiar.py` | **novo.** Carga em ordem topológica de FK |
| `deploy/migracao-pg/validar.py` | **novo.** O portão que libera ou aborta o corte |
| `deploy/migracao-pg/tests/` | **novo.** Suíte das três ferramentas, SQLite→SQLite, sem precisar de Postgres |
| `deploy/migracao-pg/README.md` | **novo.** Como rodar, na ordem |
| `deploy/fly/3vm/Dockerfile.app` | leva as ferramentas para dentro da imagem, para a janela não depender de sftp |

---

### Task 1: `db.py` fala Postgres nos dois produtos

Hoje os dois `db.py` são idênticos e só sabem tratar SQLite. Faltam quatro coisas, e as
quatro são silenciosas quando faltam:

1. **Driver.** O Fly emite URL curta `postgres://`; SQLAlchemy 2 resolve `postgresql://`
   para psycopg2, que não está instalado. Sem normalizar, o boot morre com
   `ModuleNotFoundError: psycopg2` — barulhento, mas só descoberto na janela.
2. **Pool que sobrevive ao Fly Proxy**, que encerra conexão ociosa. É por isso que
   `chatbot-api/app/db.py:22` usa `pool_pre_ping=True, pool_recycle=300`. Copie o padrão
   da casa.
3. **`search_path`.** O default é `"$user", public`. Com `public` vazio e sem permissão de
   criar (Task 9), um `search_path` errado falha alto — mas melhor não depender só disso:
   fixe na conexão.
4. **`timezone=UTC` na sessão.** Não muda o armazenamento (`timestamptz` é absoluto), mas
   é seguro barato: se algum caminho mandar um datetime *naive*, o Postgres o interpreta
   no fuso da sessão — e o container roda com `TZ=America/Sao_Paulo` (`fly.app.toml:87`).
   Sem isso, um naive que escapasse viraria um deslocamento de 3 horas, sem erro.

**Files:**
- Modify: `portal-gestao/app/db.py`
- Modify: `revy-trafego/app/db.py`
- Test: `portal-gestao/tests/test_db_engine.py` (novo)
- Test: `revy-trafego/tests/test_db_engine.py` (novo)

**Interfaces:**
- Produces, nos dois módulos:
  `normalizar_database_url(url: str) -> str` e
  `montar_kwargs(url: str, *, schema: str) -> dict`.
  O `schema` é literal por produto: `"portal"` num, `"control"` no outro.

- [ ] **Step 1: Escrever o teste que falha (Portal)**

Crie `portal-gestao/tests/test_db_engine.py`:

```python
from app.db import montar_kwargs, normalizar_database_url


def test_normaliza_url_curta_do_fly():
    assert normalizar_database_url("postgres://u:p@h:5432/revy") == (
        "postgresql+psycopg://u:p@h:5432/revy"
    )


def test_normaliza_postgresql_sem_driver():
    """`postgresql://` resolve para psycopg2, que NAO esta instalado."""
    assert normalizar_database_url("postgresql://u:p@h:5432/revy") == (
        "postgresql+psycopg://u:p@h:5432/revy"
    )


def test_nao_mexe_em_url_ja_com_driver():
    url = "postgresql+psycopg://u:p@h:5432/revy"
    assert normalizar_database_url(url) == url


def test_nao_mexe_em_sqlite():
    assert normalizar_database_url("sqlite:///./portal.db") == "sqlite:///./portal.db"


def test_kwargs_sqlite_em_memoria_usa_staticpool():
    from sqlalchemy.pool import StaticPool

    kwargs = montar_kwargs("sqlite+pysqlite:///:memory:", schema="portal")
    assert kwargs["connect_args"] == {"check_same_thread": False}
    assert kwargs["poolclass"] is StaticPool


def test_kwargs_postgres_fixa_schema_e_utc():
    kwargs = montar_kwargs(
        "postgresql+psycopg://u:p@h:5432/revy", schema="portal"
    )
    opcoes = kwargs["connect_args"]["options"]
    assert "-csearch_path=portal" in opcoes
    assert "-ctimezone=UTC" in opcoes


def test_kwargs_postgres_sobrevive_ao_fly_proxy():
    kwargs = montar_kwargs(
        "postgresql+psycopg://u:p@h:5432/revy", schema="portal"
    )
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 300
    # 1 GB de RAM no app2037, seis servicos no mesmo container: pool curto.
    assert kwargs["pool_size"] == 5
    assert kwargs["max_overflow"] == 5
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd portal-gestao && .venv/bin/python -m pytest tests/test_db_engine.py -q`
Windows: `cd portal-gestao; .\.venv\Scripts\python.exe -m pytest tests/test_db_engine.py -q`

Esperado: `ImportError: cannot import name 'montar_kwargs'`.

- [ ] **Step 3: Implementar no Portal**

Substitua `portal-gestao/app/db.py` por:

```python
"""Conexão do Portal. SQLite nos testes e no dev; Postgres (schema `portal`) em produção."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

SCHEMA = "portal"


def normalizar_database_url(url: str) -> str:
    """Aponta para o driver que está instalado.

    O Fly emite `postgres://`; SQLAlchemy 2 resolve tanto `postgres://` quanto
    `postgresql://` para psycopg2, e o que está no requirements é
    `psycopg[binary]==3.*`. Sem isto o boot morre com ModuleNotFoundError.
    """
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url.removeprefix(prefixo)
    return url


def montar_kwargs(url: str, *, schema: str) -> dict:
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return kwargs
    return {
        # search_path: o default é `"$user", public`. Com `public` vazio e sem
        # permissão de criar, errar aqui falha alto — mas não dependa só disso.
        # timezone=UTC: o container roda com TZ=America/Sao_Paulo; se algum
        # caminho mandar datetime naive, o Postgres o interpreta no fuso da
        # sessão e o valor desloca 3h sem erro nenhum.
        "connect_args": {"options": f"-csearch_path={schema} -ctimezone=UTC"},
        # O Fly Proxy encerra conexão ociosa (mesmo motivo de chatbot/app/db.py).
        "pool_pre_ping": True,
        "pool_recycle": 300,
        # 1 GB de RAM no app2037 com seis serviços no mesmo container, e o
        # suite-pg é shared-1x/512 MB. Pool curto de propósito.
        "pool_size": 5,
        "max_overflow": 5,
    }


DATABASE_URL = normalizar_database_url(settings.database_url)
engine = create_engine(
    DATABASE_URL, future=True, **montar_kwargs(DATABASE_URL, schema=SCHEMA)
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 7 passed.

- [ ] **Step 5: Repetir no Control**

Crie `revy-trafego/tests/test_db_engine.py` com os mesmos sete testes, trocando
`schema="portal"` por `schema="control"` e `-csearch_path=portal` por
`-csearch_path=control`. Depois aplique o mesmo `db.py` em `revy-trafego/app/db.py`, com
`SCHEMA = "control"` e a docstring ajustada.

Não fatore num módulo compartilhado: os produtos não importam código um do outro
(`AGENTS.md` §2), e os dois `db.py` já eram duplicados idênticos antes desta task.

- [ ] **Step 6: Rodar as duas suítes inteiras**

macOS:
```bash
cd portal-gestao && .venv/bin/python -m pytest -q
cd ../revy-trafego && ../portal-gestao/.venv/bin/python -m pytest -q
```
Windows:
```powershell
cd portal-gestao; .\.venv\Scripts\python.exe -m pytest -q
cd ..\revy-trafego; ..\portal-gestao\.venv\Scripts\python.exe -m pytest -q
```

Esperado: **Portal 1289 passed** (1282 + 7), **Control 521 passed** (514 + 7).

- [ ] **Step 7: Commit**

```bash
git add portal-gestao/app/db.py portal-gestao/tests/test_db_engine.py revy-trafego/app/db.py revy-trafego/tests/test_db_engine.py
git commit -m "feat(db): Portal e Control falam Postgres (driver, pool, search_path, UTC)"
```

---

### Task 2: O boot falha alto em vez de inventar um SQLite vazio

**A task mais importante do plano para "não perder dados".** Hoje, se
`PORTAL_DATABASE_URL` sumir depois do corte, o `:-` cria um arquivo novo em
`/data/portal/portal.db`, o alembic roda em cima dele, e o app sobe **saudável, com o
banco zerado, sem uma linha de erro**. O dono descobre pela tela vazia.

O padrão correto já existe na casa: `run-chatbot.sh:3` usa
`${CHATBOT_DATABASE_URL:?CHATBOT_DATABASE_URL required}`.

Nesta task **não** mexa em `fly.app.toml`. O `[env]` de lá continua fornecendo o valor
SQLite, então este deploy é seguro e pode ir a qualquer hora, antes da janela. O `[env]`
sai só depois do corte (Task 11).

**Files:**
- Modify: `deploy/fly/3vm/run-portal.sh:3`
- Modify: `deploy/fly/3vm/run-revy-trafego.sh:4-5`
- Modify: `deploy/fly/3vm/entrypoint-app.sh:27,34`
- Test: `deploy/migracao-pg/tests/test_scripts_de_boot.py` (novo)

**Interfaces:** nenhuma. É shell e um teste de regressão que lê os arquivos.

- [ ] **Step 1: Escrever o teste que falha**

Crie `deploy/migracao-pg/tests/test_scripts_de_boot.py`:

```python
"""Regressão: nenhum script de boot pode inventar um SQLite quando a URL some.

Depois do corte, um secret apagado ou com typo faria o app criar um banco vazio
e subir saudável, com zero dado e sem erro no log. Este teste existe para que
alguém que reintroduza o `:-sqlite:` seja parado pelo CI, não pelo dono olhando
uma tela vazia.
"""
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
SCRIPTS = RAIZ / "deploy" / "fly" / "3vm"

VARIAVEIS = {
    "run-portal.sh": ["PORTAL_DATABASE_URL"],
    "run-revy-trafego.sh": ["REVY_TRAFEGO_DATABASE_URL"],
    "entrypoint-app.sh": ["PORTAL_DATABASE_URL", "REVY_TRAFEGO_DATABASE_URL"],
}


@pytest.mark.parametrize("arquivo", sorted(VARIAVEIS))
def test_nenhum_script_cai_para_sqlite(arquivo):
    texto = (SCRIPTS / arquivo).read_text(encoding="utf-8")
    for variavel in VARIAVEIS[arquivo]:
        assert f"{variavel}:-sqlite" not in texto, (
            f"{arquivo} ainda cai para SQLite se {variavel} sumir"
        )
        assert f"${{{variavel}:?" in texto, (
            f"{arquivo} precisa exigir {variavel} com ${{VAR:?mensagem}}"
        )


def test_revy_trafego_nao_exporta_a_url_do_portal():
    """`PORTAL_DATABASE_URL` não é lida por nenhum arquivo de revy-trafego/app.
    O export era morto — e depois do corte vira arma carregada: bastaria alguém
    passar a ler a variável para existir um segundo escritor no banco do Portal.
    """
    texto = (SCRIPTS / "run-revy-trafego.sh").read_text(encoding="utf-8")
    assert "PORTAL_DATABASE_URL" not in texto
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest -q`
Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`

Esperado: 4 failed (`ainda cai para SQLite se ... sumir`).

- [ ] **Step 3: Corrigir os três scripts**

`deploy/fly/3vm/run-portal.sh`, linha 3:
```sh
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:?PORTAL_DATABASE_URL obrigatorio}"
```

`deploy/fly/3vm/run-revy-trafego.sh`, linha 4 — e **apague a linha 5 inteira**
(`export PORTAL_DATABASE_URL=...`), que é export morto:
```sh
export REVY_TRAFEGO_DATABASE_URL="${REVY_TRAFEGO_DATABASE_URL:?REVY_TRAFEGO_DATABASE_URL obrigatorio}"
```

`deploy/fly/3vm/entrypoint-app.sh`, linhas 27 e 34:
```sh
export PORTAL_DATABASE_URL="${PORTAL_DATABASE_URL:?PORTAL_DATABASE_URL obrigatorio}"
...
export REVY_TRAFEGO_DATABASE_URL="${REVY_TRAFEGO_DATABASE_URL:?REVY_TRAFEGO_DATABASE_URL obrigatorio}"
```

O `entrypoint-app.sh` roda com `set -euo pipefail`, então `${VAR:?msg}` sai com código 1
e a mensagem no log. É exatamente o comportamento desejado: boot que morre em vez de boot
que mente.

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 4 passed.

- [ ] **Step 5: Conferir que o `[env]` ainda fornece o valor**

```bash
grep -n "PORTAL_DATABASE_URL\|REVY_TRAFEGO_DATABASE_URL" deploy/fly/3vm/fly.app.toml
```
Tem que continuar mostrando as duas linhas com `sqlite:////data/...`. Se não mostrar, o
deploy vai quebrar o boot — **pare e reponha** antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add deploy/fly/3vm/run-portal.sh deploy/fly/3vm/run-revy-trafego.sh deploy/fly/3vm/entrypoint-app.sh deploy/migracao-pg/tests/test_scripts_de_boot.py
git commit -m "fix(deploy): boot exige a URL do banco em vez de criar SQLite vazio"
```

---

### Task 3: `tipos.py` — a conversão onde dinheiro se corrompe

Quatro regras. A terceira é a que importa mais.

1. **`DateTime` naive → UTC.** O SQLite guarda `DateTime(timezone=True)` como texto sem
   offset e devolve naive. Todo escritor usa `agora() = datetime.now(timezone.utc)`, e o
   único `datetime.now()` sem tz do código (`portal/main.py:451`) é comparação de tela e
   nunca chega a coluna — então o valor guardado **é** UTC e anexar `timezone.utc` é
   restaurar a informação, não inventá-la.
2. **`Boolean`** aceita só `0`, `1`, `True`, `False`. Qualquer outra coisa é erro, não
   coerção — o SQLite aceita `2` numa coluna booleana e ninguém percebe.
3. **`Numeric` via `str`, nunca via `float`.** `Decimal(0.1)` é
   `0.1000000000000000055511151231257827…`; `Decimal(str(0.1))` é `0.1`. São 11 colunas de
   dinheiro (8 no Portal, 3 no Control) e é aqui que elas sobrevivem ou não.
4. Todo o resto passa direto.

**Files:**
- Create: `deploy/migracao-pg/tipos.py`
- Test: `deploy/migracao-pg/tests/test_tipos.py`

**Interfaces:**
- Produces: `tipos.ValorInconvertivel(Exception)` e
  `tipos.converter(valor, tipo: TypeEngine) -> object`.

- [ ] **Step 1: Escrever o teste que falha**

Crie `deploy/migracao-pg/tests/test_tipos.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String

from tipos import ValorInconvertivel, converter


def test_none_atravessa_qualquer_tipo():
    assert converter(None, Numeric(12, 2)) is None
    assert converter(None, DateTime(timezone=True)) is None


def test_datetime_naive_ganha_utc():
    naive = datetime(2026, 8, 16, 10, 0, 0)
    convertido = converter(naive, DateTime(timezone=True))
    assert convertido.tzinfo is timezone.utc
    assert convertido.hour == 10  # NAO desloca: o valor guardado ja era UTC


def test_datetime_aware_nao_e_tocado():
    aware = datetime(2026, 8, 16, 10, 0, 0, tzinfo=timezone.utc)
    assert converter(aware, DateTime(timezone=True)) == aware


def test_datetime_em_texto_e_lido_como_iso():
    convertido = converter("2026-08-16 10:00:00.000000", DateTime(timezone=True))
    assert convertido == datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)


def test_date_atravessa():
    assert converter(date(2026, 8, 16), Date()) == date(2026, 8, 16)


def test_numeric_de_float_passa_por_str():
    """Decimal(0.1) e 0.1000000000000000055511151231257827...; Decimal(str(0.1)) e 0.1."""
    assert converter(0.1, Numeric(12, 6)) == Decimal("0.1")
    assert converter(118900.0, Numeric(12, 2)) == Decimal("118900.0")


def test_numeric_de_decimal_e_preservado():
    assert converter(Decimal("1234.56"), Numeric(12, 2)) == Decimal("1234.56")


def test_numeric_de_texto_e_preservado():
    assert converter("1234.56", Numeric(12, 2)) == Decimal("1234.56")


def test_boolean_aceita_zero_e_um():
    assert converter(0, Boolean()) is False
    assert converter(1, Boolean()) is True
    assert converter(True, Boolean()) is True


def test_boolean_recusa_valor_fora_de_zero_e_um():
    """SQLite aceita 2 numa coluna booleana. O Postgres nao — e coercao
    silenciosa aqui esconderia um dado ja corrompido."""
    with pytest.raises(ValorInconvertivel):
        converter(2, Boolean())


def test_string_e_integer_atravessam():
    assert converter("abc", String(10)) == "abc"
    assert converter(7, Integer()) == 7
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest tests/test_tipos.py -q`
Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest tests/test_tipos.py -q`

Esperado: `ModuleNotFoundError: No module named 'tipos'`.

- [ ] **Step 3: Implementar**

Crie `deploy/migracao-pg/tipos.py`:

```python
"""Conversão de valor lido do SQLite para o tipo declarado no Postgres.

A conversão é dirigida pelo **tipo de destino**, refletido do banco que o
alembic acabou de criar. Não há import de `app.models` em lugar nenhum desta
pasta: Portal e Control têm ambos um pacote chamado `app` e nenhum processo
pode importar os dois.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import types as sqltypes


class ValorInconvertivel(Exception):
    """Valor que o Postgres não aceitaria e que não pode ser coagido em silêncio."""


def converter(valor, tipo):
    if valor is None:
        return None

    if isinstance(tipo, sqltypes.DateTime):
        if isinstance(valor, str):
            valor = datetime.fromisoformat(valor)
        if valor.tzinfo is None:
            # O SQLite guarda DateTime(timezone=True) sem offset e devolve
            # naive. Todo escritor do Portal e do Control usa
            # agora() = datetime.now(timezone.utc), então o que está guardado
            # É UTC: anexar tzinfo restaura a informação, não a inventa.
            valor = valor.replace(tzinfo=timezone.utc)
        return valor

    if isinstance(tipo, sqltypes.Boolean):
        if valor in (0, 1, False, True):
            return bool(valor)
        raise ValorInconvertivel(f"booleano fora de 0/1: {valor!r}")

    if isinstance(tipo, sqltypes.Numeric) and not isinstance(tipo, sqltypes.Float):
        if isinstance(valor, Decimal):
            return valor
        # str() e nunca float(): Decimal(0.1) é
        # 0.1000000000000000055511151231257827…, Decimal(str(0.1)) é 0.1.
        return Decimal(str(valor))

    return valor
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add deploy/migracao-pg/tipos.py deploy/migracao-pg/tests/test_tipos.py
git commit -m "feat(migracao-pg): conversao de tipos dirigida pelo tipo de destino"
```

---

### Task 4: `verificar.py` — o pré-voo

Cinco coisas que o SQLite deixou passar e o Postgres vai recusar. A primeira é a que quase
certamente vai achar algo:

1. **Órfão de FK.** São **43 FKs** (8 no Portal, 35 no Control) e **nenhuma é verificada
   hoje** — nenhum `db.py` liga `PRAGMA foreign_keys=ON`, e o default do SQLite é OFF.
   Toda linha filha apontando para uma mãe apagada existe hoje e vai fazer o `INSERT`
   estourar na janela.
2. **String maior que a coluna.** O SQLite ignora `String(120)`; o Postgres recusa.
3. **NULL em `NOT NULL`.**
4. **Booleano fora de 0/1.**
5. **Decimal com mais casas que a escala.** Não impede a carga — o Postgres arredonda —
   mas faz a soma do `validar.py` divergir. Melhor saber antes do que no portão.

Roda contra a **cópia** do SQLite e contra o Postgres **já migrado e vazio** (é de lá que
vêm os tipos e as FKs de verdade).

**Files:**
- Create: `deploy/migracao-pg/verificar.py`
- Test: `deploy/migracao-pg/tests/test_verificar.py`

**Interfaces:**
- Consumes: nada. O pré-voo só lê e conta — não converte valor nenhum, então não depende
  de `tipos.py`.
- Produces: `verificar.verificar(origem_url: str, destino_url: str, schema: str | None) -> list[str]`
  — lista de problemas em texto; vazia = liberado. CLI: `python verificar.py --origem ... --destino ... --schema ...`, sai 1 se a lista não estiver vazia.

- [ ] **Step 1: Escrever o teste que falha**

Crie `deploy/migracao-pg/tests/test_verificar.py`. Os testes usam **dois SQLite**: um como
"origem suja" e outro como "destino" com as restrições declaradas — o mesmo par que o
Postgres formaria, sem precisar de Postgres.

```python
from pathlib import Path

import pytest
from sqlalchemy import (
    Boolean, Column, ForeignKey, MetaData, String, Table, create_engine, insert,
)

from verificar import verificar


def _monta(tmp_path: Path, nome: str):
    url = f"sqlite:///{tmp_path / nome}"
    engine = create_engine(url)
    md = MetaData()
    Table("mae", md, Column("id", String(36), primary_key=True))
    Table(
        "filha",
        md,
        Column("id", String(36), primary_key=True),
        Column("mae_id", String(36), ForeignKey("mae.id")),
        Column("rotulo", String(5), nullable=False),
        Column("ativo", Boolean()),
    )
    md.create_all(engine)
    return url, engine, md


def test_banco_limpo_nao_reporta_nada(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
        conn.execute(
            insert(md.tables["filha"]),
            [{"id": "f1", "mae_id": "m1", "rotulo": "ok", "ativo": 1}],
        )
    assert verificar(origem_url, destino_url, schema=None) == []


def test_acha_orfao_de_fk(tmp_path):
    """O SQLite nao verifica FK por default: a linha existe hoje."""
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(
            insert(md.tables["filha"]),
            [{"id": "f1", "mae_id": "sumida", "rotulo": "ok", "ativo": 1}],
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.mae_id" in p and "orfa" in p for p in problemas)


def test_acha_string_maior_que_a_coluna(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
        conn.execute(
            insert(md.tables["filha"]),
            [{"id": "f1", "mae_id": "m1", "rotulo": "cabe-nao", "ativo": 1}],
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.rotulo" in p and "5" in p for p in problemas)


def test_acha_null_em_not_null(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO filha (id, mae_id, rotulo, ativo) VALUES ('f1', NULL, NULL, 1)"
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.rotulo" in p and "NULL" in p for p in problemas)


def test_acha_booleano_fora_de_zero_e_um(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, _, _ = _monta(tmp_path, "destino.db")
    with engine.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
        conn.exec_driver_sql(
            "INSERT INTO filha (id, mae_id, rotulo, ativo) "
            "VALUES ('f1', 'm1', 'ok', 2)"
        )
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("filha.ativo" in p for p in problemas)


def test_acha_tabela_que_falta_no_destino(tmp_path):
    origem_url, engine, md = _monta(tmp_path, "origem.db")
    destino_url, destino_engine, _ = _monta(tmp_path, "destino.db")
    md_extra = MetaData()
    Table("sobrando", md_extra, Column("id", String(36), primary_key=True))
    md_extra.create_all(engine)
    problemas = verificar(origem_url, destino_url, schema=None)
    assert any("sobrando" in p for p in problemas)
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest tests/test_verificar.py -q`
Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest tests/test_verificar.py -q`

Esperado: `ModuleNotFoundError: No module named 'verificar'`.

- [ ] **Step 3: Implementar**

Crie `deploy/migracao-pg/verificar.py`:

```python
"""Pré-voo: encontra, antes da janela, tudo que o Postgres vai recusar.

Roda contra a CÓPIA do SQLite e contra o Postgres já migrado e vazio — os tipos,
as FKs e os NOT NULL de verdade vêm de lá, não de um modelo importado.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy import types as sqltypes


def _tabelas(md: MetaData) -> dict:
    return {t.name: t for t in md.tables.values()}


def verificar(origem_url: str, destino_url: str, schema: str | None) -> list[str]:
    origem_engine = create_engine(origem_url)
    destino_engine = create_engine(destino_url)

    md_origem = MetaData()
    md_origem.reflect(bind=origem_engine)
    md_destino = MetaData()
    md_destino.reflect(bind=destino_engine, schema=schema)

    origem = _tabelas(md_origem)
    destino = _tabelas(md_destino)
    problemas: list[str] = []

    ignoradas = {"alembic_version", "alembic_version_revy_trafego"}

    for nome in sorted(set(origem) - set(destino) - ignoradas):
        problemas.append(f"tabela `{nome}` existe na origem e nao no destino")
    for nome in sorted(set(destino) - set(origem) - ignoradas):
        problemas.append(f"tabela `{nome}` existe no destino e nao na origem")

    with origem_engine.connect() as conn:
        for nome in sorted(set(origem) & set(destino) - ignoradas):
            t_org = origem[nome]
            t_dst = destino[nome]

            for col_dst in t_dst.columns:
                col_org = t_org.columns.get(col_dst.name)
                if col_org is None:
                    problemas.append(
                        f"coluna `{nome}.{col_dst.name}` existe no destino e nao na origem"
                    )
                    continue

                if not col_dst.nullable:
                    nulos = conn.execute(
                        select(func.count()).select_from(t_org).where(col_org.is_(None))
                    ).scalar_one()
                    if nulos:
                        problemas.append(
                            f"`{nome}.{col_dst.name}` e NOT NULL no destino e tem "
                            f"{nulos} linha(s) NULL na origem"
                        )

                tipo = col_dst.type
                if isinstance(tipo, sqltypes.String) and tipo.length:
                    longos = conn.execute(
                        select(func.count())
                        .select_from(t_org)
                        .where(func.length(col_org) > tipo.length)
                    ).scalar_one()
                    if longos:
                        problemas.append(
                            f"`{nome}.{col_dst.name}` e VARCHAR({tipo.length}) e tem "
                            f"{longos} valor(es) maior(es) na origem"
                        )

                if isinstance(tipo, sqltypes.Boolean):
                    for (valor,) in conn.execute(
                        select(col_org).distinct().where(col_org.isnot(None))
                    ):
                        if valor not in (0, 1, False, True):
                            problemas.append(
                                f"`{nome}.{col_dst.name}` e booleano e tem o valor "
                                f"{valor!r} na origem"
                            )

                if isinstance(tipo, sqltypes.Numeric) and not isinstance(
                    tipo, sqltypes.Float
                ):
                    escala = tipo.scale
                    if escala is not None:
                        demais = 0
                        for (valor,) in conn.execute(
                            select(col_org).where(col_org.isnot(None))
                        ):
                            try:
                                exp = Decimal(str(valor)).as_tuple().exponent
                            except InvalidOperation:
                                problemas.append(
                                    f"`{nome}.{col_dst.name}` tem valor nao numerico "
                                    f"{valor!r} na origem"
                                )
                                continue
                            if isinstance(exp, int) and exp < -escala:
                                demais += 1
                        if demais:
                            problemas.append(
                                f"`{nome}.{col_dst.name}` e NUMERIC(escala={escala}) e "
                                f"tem {demais} valor(es) com mais casas — o Postgres vai "
                                f"arredondar e a soma da validacao vai divergir"
                            )

            for fk in t_dst.foreign_keys:
                col_filha = t_org.columns.get(fk.parent.name)
                mae_nome = fk.column.table.name
                t_mae = origem.get(mae_nome)
                if col_filha is None or t_mae is None:
                    continue
                col_mae = t_mae.columns.get(fk.column.name)
                if col_mae is None:
                    continue
                orfas = conn.execute(
                    select(func.count())
                    .select_from(t_org)
                    .where(
                        col_filha.isnot(None),
                        col_filha.notin_(select(col_mae)),
                    )
                ).scalar_one()
                if orfas:
                    problemas.append(
                        f"`{nome}.{fk.parent.name}` tem {orfas} linha(s) orfa(s) "
                        f"apontando para `{mae_nome}.{fk.column.name}` — o SQLite nao "
                        f"verifica FK, o Postgres verifica"
                    )

    return problemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    problemas = verificar(args.origem, args.destino, args.schema)
    for p in problemas:
        print(f"PROBLEMA: {p}")
    print(f"\n{len(problemas)} problema(s).")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add deploy/migracao-pg/verificar.py deploy/migracao-pg/tests/test_verificar.py
git commit -m "feat(migracao-pg): pre-voo do que o Postgres vai recusar"
```

---

### Task 5: `copiar.py` — a carga

Ordem topológica de FK (`md.sorted_tables`), lotes de 500, conversão por tipo de destino,
e uma contagem por tabela na saída. Não cria tabela, não apaga tabela, e **recusa
carregar** se a tabela de destino já tiver linha — carregar duas vezes é o erro que
duplica tudo.

**Files:**
- Create: `deploy/migracao-pg/copiar.py`
- Test: `deploy/migracao-pg/tests/test_copiar.py`

**Interfaces:**
- Consumes: `tipos.converter` (Task 3).
- Produces: `copiar.copiar(origem_url: str, destino_url: str, schema: str | None, lote: int = 500) -> dict[str, int]`
  — mapa `tabela → linhas copiadas`. CLI análogo ao do `verificar.py`.

- [ ] **Step 1: Escrever o teste que falha**

Crie `deploy/migracao-pg/tests/test_copiar.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, MetaData, Numeric, String, Table,
    create_engine, insert, select,
)

from copiar import CargaRecusada, copiar


def _esquema():
    md = MetaData()
    Table("mae", md, Column("id", String(36), primary_key=True))
    Table(
        "filha",
        md,
        Column("id", String(36), primary_key=True),
        Column("mae_id", String(36), ForeignKey("mae.id")),
        Column("valor", Numeric(12, 2)),
        Column("quando", DateTime(timezone=True)),
        Column("ativo", Boolean()),
    )
    return md


def _banco(tmp_path: Path, nome: str):
    url = f"sqlite:///{tmp_path / nome}"
    engine = create_engine(url)
    md = _esquema()
    md.create_all(engine)
    return url, engine, md


def test_copia_respeitando_a_ordem_de_fk(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}, {"id": "m2"}])
        conn.execute(
            insert(md.tables["filha"]),
            [
                {"id": "f1", "mae_id": "m1", "valor": 118900.0,
                 "quando": datetime(2026, 8, 16, 10, 0), "ativo": 1},
                {"id": "f2", "mae_id": "m2", "valor": 0.1,
                 "quando": datetime(2026, 8, 16, 11, 0), "ativo": 0},
            ],
        )

    contagem = copiar(origem_url, destino_url, schema=None)
    assert contagem == {"mae": 2, "filha": 2}

    with destino.connect() as conn:
        linhas = conn.execute(
            select(md.tables["filha"]).order_by(md.tables["filha"].c.id)
        ).mappings().all()
    assert linhas[0]["valor"] == Decimal("118900.00")
    assert linhas[1]["valor"] == Decimal("0.10")
    assert linhas[0]["ativo"] is True
    assert linhas[1]["ativo"] is False


def test_recusa_carregar_por_cima_de_tabela_com_linha(tmp_path):
    """Rodar duas vezes duplicaria tudo. Tem que parar antes de escrever."""
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "m1"}])
    with destino.begin() as conn:
        conn.execute(insert(md.tables["mae"]), [{"id": "ja-estava"}])

    with pytest.raises(CargaRecusada):
        copiar(origem_url, destino_url, schema=None)


def test_tabela_vazia_na_origem_nao_quebra(tmp_path):
    origem_url, _, _ = _banco(tmp_path, "origem.db")
    destino_url, _, _ = _banco(tmp_path, "destino.db")
    assert copiar(origem_url, destino_url, schema=None) == {"mae": 0, "filha": 0}


def test_lote_menor_que_o_total_copia_tudo(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["mae"]), [{"id": f"m{i}"} for i in range(25)]
        )
    assert copiar(origem_url, destino_url, schema=None, lote=7)["mae"] == 25
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest tests/test_copiar.py -q`
Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest tests/test_copiar.py -q`

Esperado: `ModuleNotFoundError: No module named 'copiar'`.

- [ ] **Step 3: Implementar**

Crie `deploy/migracao-pg/copiar.py`:

```python
"""Carga SQLite → Postgres, tabela a tabela, em ordem topológica de FK."""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import MetaData, create_engine, func, insert, select

from tipos import converter

IGNORADAS = {"alembic_version", "alembic_version_revy_trafego"}


class CargaRecusada(Exception):
    """O destino não estava vazio. Carregar duas vezes duplicaria tudo."""


def copiar(
    origem_url: str, destino_url: str, schema: str | None, lote: int = 500
) -> dict[str, int]:
    origem_engine = create_engine(origem_url)
    destino_engine = create_engine(destino_url)

    md_origem = MetaData()
    md_origem.reflect(bind=origem_engine)
    md_destino = MetaData()
    md_destino.reflect(bind=destino_engine, schema=schema)

    por_nome = {t.name: t for t in md_origem.tables.values()}
    alvos = [t for t in md_destino.sorted_tables if t.name not in IGNORADAS]

    # Recusa ANTES de escrever qualquer coisa: uma segunda carga por cima é
    # indistinguível de dado legítimo depois do fato.
    with destino_engine.connect() as conn:
        for t_dst in alvos:
            existentes = conn.execute(
                select(func.count()).select_from(t_dst)
            ).scalar_one()
            if existentes:
                raise CargaRecusada(
                    f"`{t_dst.name}` ja tem {existentes} linha(s) no destino"
                )

    contagem: dict[str, int] = {}
    with origem_engine.connect() as org, destino_engine.begin() as dst:
        for t_dst in alvos:
            t_org = por_nome.get(t_dst.name)
            if t_org is None:
                contagem[t_dst.name] = 0
                continue

            colunas = [c for c in t_dst.columns if c.name in t_org.columns]
            resultado = org.execute(select(*[t_org.c[c.name] for c in colunas]))
            total = 0
            while True:
                bloco = resultado.fetchmany(lote)
                if not bloco:
                    break
                dst.execute(
                    insert(t_dst),
                    [
                        {
                            c.name: converter(valor, c.type)
                            for c, valor in zip(colunas, linha)
                        }
                        for linha in bloco
                    ],
                )
                total += len(bloco)
            contagem[t_dst.name] = total

    return contagem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--schema", default=None)
    parser.add_argument("--lote", type=int, default=500)
    args = parser.parse_args()
    contagem = copiar(args.origem, args.destino, args.schema, lote=args.lote)
    for nome in sorted(contagem):
        print(f"{nome}: {contagem[nome]}")
    print(f"\n{len(contagem)} tabela(s), {sum(contagem.values())} linha(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add deploy/migracao-pg/copiar.py deploy/migracao-pg/tests/test_copiar.py
git commit -m "feat(migracao-pg): carga em ordem topologica de FK, recusando destino sujo"
```

---

### Task 6: `validar.py` — o portão que libera ou aborta

Quatro comparações. Enquanto elas não passarem, produção continua nos `.db` e nada foi
perdido.

**Files:**
- Create: `deploy/migracao-pg/validar.py`
- Test: `deploy/migracao-pg/tests/test_validar.py`

**Interfaces:**
- Produces: `validar.validar(origem_url: str, destino_url: str, schema: str | None) -> list[str]`
  — divergências em texto; vazia = liberado. CLI sai 1 se houver qualquer uma.

- [ ] **Step 1: Escrever o teste que falha**

Crie `deploy/migracao-pg/tests/test_validar.py`:

```python
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Column, DateTime, MetaData, Numeric, String, Table, create_engine, insert,
)

from copiar import copiar
from validar import validar


def _banco(tmp_path: Path, nome: str):
    url = f"sqlite:///{tmp_path / nome}"
    engine = create_engine(url)
    md = MetaData()
    Table(
        "vendas",
        md,
        Column("id", String(36), primary_key=True),
        Column("valor", Numeric(12, 2)),
        Column("criado_em", DateTime(timezone=True)),
    )
    md.create_all(engine)
    return url, engine, md


def test_carga_correta_nao_reporta_divergencia(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, _, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [
                {"id": "v1", "valor": 1000.50,
                 "criado_em": datetime(2026, 8, 16, 10, 0)},
                {"id": "v2", "valor": 250.25,
                 "criado_em": datetime(2026, 8, 16, 11, 0)},
            ],
        )
    copiar(origem_url, destino_url, schema=None)
    assert validar(origem_url, destino_url, schema=None) == []


def test_acha_linha_faltando(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 10.0, "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    divergencias = validar(origem_url, destino_url, schema=None)
    assert any("vendas" in d and "linha" in d for d in divergencias)


def test_acha_centavo_perdido(tmp_path):
    origem_url, origem, md = _banco(tmp_path, "origem.db")
    destino_url, destino, _ = _banco(tmp_path, "destino.db")
    with origem.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 1000.50,
              "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    with destino.begin() as conn:
        conn.execute(
            insert(md.tables["vendas"]),
            [{"id": "v1", "valor": 1000.49,
              "criado_em": datetime(2026, 8, 16, 10, 0)}],
        )
    divergencias = validar(origem_url, destino_url, schema=None)
    assert any("vendas.valor" in d for d in divergencias)
```

- [ ] **Step 2: Rodar e ver falhar**

macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest tests/test_validar.py -q`
Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest tests/test_validar.py -q`

Esperado: `ModuleNotFoundError: No module named 'validar'`.

- [ ] **Step 3: Implementar**

Crie `deploy/migracao-pg/validar.py`:

```python
"""O portão do corte: compara os dois lados e devolve toda divergência.

Enquanto esta lista não estiver vazia, produção continua nos `.db` e nada foi
perdido. Qualquer item aqui aborta o corte.
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy import types as sqltypes

IGNORADAS = {"alembic_version", "alembic_version_revy_trafego"}


def _decimal(valor) -> Decimal:
    return Decimal("0") if valor is None else Decimal(str(valor))


def _utc_naive(valor):
    """Compara instantes sem depender de tzinfo: o SQLite devolve naive (UTC) e
    o Postgres devolve aware (UTC)."""
    if valor is None:
        return None
    return valor.replace(tzinfo=None) if valor.tzinfo else valor


def validar(origem_url: str, destino_url: str, schema: str | None) -> list[str]:
    origem_engine = create_engine(origem_url)
    destino_engine = create_engine(destino_url)

    md_origem = MetaData()
    md_origem.reflect(bind=origem_engine)
    md_destino = MetaData()
    md_destino.reflect(bind=destino_engine, schema=schema)

    por_nome_org = {t.name: t for t in md_origem.tables.values()}
    divergencias: list[str] = []

    with origem_engine.connect() as org, destino_engine.connect() as dst:
        for t_dst in md_destino.sorted_tables:
            if t_dst.name in IGNORADAS:
                continue
            t_org = por_nome_org.get(t_dst.name)
            if t_org is None:
                divergencias.append(f"`{t_dst.name}` nao existe na origem")
                continue

            n_org = org.execute(select(func.count()).select_from(t_org)).scalar_one()
            n_dst = dst.execute(select(func.count()).select_from(t_dst)).scalar_one()
            if n_org != n_dst:
                divergencias.append(
                    f"`{t_dst.name}`: {n_org} linha(s) na origem, {n_dst} no destino"
                )

            for col in t_dst.columns:
                col_org = t_org.columns.get(col.name)
                if col_org is None:
                    continue

                if isinstance(col.type, sqltypes.Numeric) and not isinstance(
                    col.type, sqltypes.Float
                ):
                    s_org = _decimal(
                        org.execute(select(func.sum(col_org))).scalar_one()
                    )
                    s_dst = _decimal(
                        dst.execute(select(func.sum(col))).scalar_one()
                    )
                    if s_org != s_dst:
                        divergencias.append(
                            f"`{t_dst.name}.{col.name}`: soma {s_org} na origem, "
                            f"{s_dst} no destino (diferenca {s_dst - s_org})"
                        )

                if isinstance(col.type, sqltypes.DateTime):
                    m_org = _utc_naive(
                        org.execute(select(func.max(col_org))).scalar_one()
                    )
                    m_dst = _utc_naive(
                        dst.execute(select(func.max(col))).scalar_one()
                    )
                    if m_org != m_dst:
                        divergencias.append(
                            f"`{t_dst.name}.{col.name}`: max {m_org} na origem, "
                            f"{m_dst} no destino"
                        )

    return divergencias


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--schema", default=None)
    args = parser.parse_args()
    divergencias = validar(args.origem, args.destino, args.schema)
    for d in divergencias:
        print(f"DIVERGENCIA: {d}")
    if divergencias:
        print(f"\n{len(divergencias)} divergencia(s). NAO LIBERAR O CORTE.")
        return 1
    print("\nSem divergencia. Corte liberado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Nota sobre o `func.max` de `DateTime` no SQLite: o comparador do SQLite é lexicográfico
sobre o texto ISO, o que dá o mesmo resultado que o comparador temporal para o formato que
o SQLAlchemy grava (`YYYY-MM-DD HH:MM:SS.ffffff`, zero-padded). É por isso que a
comparação funciona sem converter tudo.

- [ ] **Step 4: Rodar e ver passar**

Mesmo comando do Step 2. Esperado: 3 passed.

- [ ] **Step 5: Rodar a suíte inteira das ferramentas**

macOS: `cd deploy/migracao-pg && ../../portal-gestao/.venv/bin/python -m pytest -q`
Windows: `cd deploy/migracao-pg; ..\..\portal-gestao\.venv\Scripts\python.exe -m pytest -q`

Esperado: **28 passed** (4 boot + 11 tipos + 6 verificar + 4 copiar + 3 validar).

- [ ] **Step 6: Commit**

```bash
git add deploy/migracao-pg/validar.py deploy/migracao-pg/tests/test_validar.py
git commit -m "feat(migracao-pg): portao de validacao (linhas, somas, maximos)"
```

---

### Task 7: Ferramenta dentro da imagem + README

A janela não pode depender de `sftp put` de quatro arquivos sob pressão. A ferramenta vai
na imagem num deploy normal, dias antes.

Ela roda **de dentro do `app2037`**, e é o desenho certo: o `suite-pg` está em flycast
(rede privada), o `.db` está no volume, e a imagem já tem `sqlalchemy`, `psycopg` e
`alembic`. Nenhum dado sai do Fly, nenhum túnel é aberto.

**Files:**
- Modify: `deploy/fly/3vm/Dockerfile.app` (depois da linha 47)
- Create: `deploy/migracao-pg/README.md`

- [ ] **Step 1: Levar a pasta para a imagem**

Em `deploy/fly/3vm/Dockerfile.app`, depois de `COPY motor-simulacao/alembic.ini …`:

```dockerfile
COPY deploy/migracao-pg /srv/migracao-pg
```

- [ ] **Step 2: Escrever o README**

Crie `deploy/migracao-pg/README.md` com: a ordem obrigatória
(`verificar` → `alembic upgrade head` → `copiar` → `validar`), os comandos de teste local
das duas plataformas, e a regra de que **nenhuma senha entra em comando** — as URLs vêm
das variáveis `REVY_PG_PORTAL_URL` e `REVY_PG_CONTROL_URL`, definidas como secret do Fly
(Task 9) e nunca escritas na linha de comando.

- [ ] **Step 3: Deploy**

```bash
fly deploy . -a app2037 -c deploy/fly/3vm/fly.app.toml --ha=false
```

⚠️ O deploy usa a **árvore local**, não o que está no GitHub. Commite antes.

- [ ] **Step 4: Conferir que chegou e que o app subiu igual**

```bash
fly ssh console -a app2037 -C "ls /srv/migracao-pg"
curl -sS -o /dev/null -w "%{http_code}\n" https://app2037.fly.dev/healthz
```
Esperado: os quatro `.py` listados, e `200` no healthz.

- [ ] **Step 5: Commit**

```bash
git add deploy/fly/3vm/Dockerfile.app deploy/migracao-pg/README.md
git commit -m "chore(deploy): ferramenta de migracao na imagem do app2037"
```

---

### Task 8: O ensaio

Dias antes da janela, contra **cópia**, em banco descartável. É o ensaio que transforma
"30–60 min" em número, e é onde os problemas do pré-voo aparecem com tempo de conserto.

Nada nesta task toca produção.

- [ ] **Step 1: Reconferir que as cadeias de migration têm head único**

```bash
cd portal-gestao && alembic heads
cd ../revy-trafego && alembic heads
```
Esperado: exatamente uma linha em cada, `0026_copiloto_sinal_destinatario` e
`0020_loja_whatsapp_modo`. **Duas linhas = pare e resolva o branch antes de qualquer
coisa** — o `upgrade head` do corte falharia com o app parado.

- [ ] **Step 2: Tirar cópia consistente dos dois `.db`, com o app rodando**

```bash
fly ssh console -a app2037 -C "mkdir -p /data/migracao"
fly ssh console -a app2037 -C "python - <<'PY'
import sqlite3
for origem, destino in (
    ('/data/portal/portal.db', '/data/migracao/portal-ensaio.db'),
    ('/data/revy-trafego/revy_trafego.db', '/data/migracao/control-ensaio.db'),
):
    o = sqlite3.connect(origem); d = sqlite3.connect(destino)
    o.backup(d); d.close(); o.close()
    print(destino, 'ok')
PY"
```

`sqlite3.backup` dá uma cópia consistente **com o app escrevendo** — é para isso que ele
existe. Não use `cp`.

- [ ] **Step 3: Guardar uma cópia fora do Fly**

```bash
fly ssh sftp get /data/migracao/portal-ensaio.db  -a app2037
fly ssh sftp get /data/migracao/control-ensaio.db -a app2037
```
Guarde fora da árvore do repo. Esta é a rede de segurança que não depende de nada do Fly.

- [ ] **Step 4: Criar o banco descartável do ensaio**

```bash
fly pg connect -a suite-pg
```
```sql
CREATE DATABASE revy_ensaio;
\c revy_ensaio
CREATE SCHEMA portal;
CREATE SCHEMA control;
```

- [ ] **Step 5: Rodar o alembic dos dois produtos contra o ensaio, do zero**

Dentro do `app2037` (`fly ssh console -a app2037`), com a URL do ensaio numa variável —
sem senha em comando:

```sh
export DATABASE_URL="$REVY_PG_ENSAIO_PORTAL_URL"
export PORTAL_DATABASE_URL="$DATABASE_URL"
cd /srv/portal && alembic upgrade head && alembic current
```
```sh
export DATABASE_URL="$REVY_PG_ENSAIO_CONTROL_URL"
export REVY_TRAFEGO_DATABASE_URL="$DATABASE_URL"
cd /srv/revy-trafego && alembic upgrade head && alembic current
```

Esperado: `alembic current` mostrando `0026_…` e `0020_…`.

**Este passo é meio ponto do ensaio.** É aqui que aparece qualquer migration que só
funcionava em SQLite. Se falhar, o conserto é uma migration nova — não um hack na janela.

- [ ] **Step 6: Pré-voo**

```sh
cd /srv/migracao-pg
python verificar.py --origem sqlite:////data/migracao/portal-ensaio.db \
                    --destino "$REVY_PG_ENSAIO_PORTAL_URL" --schema portal
python verificar.py --origem sqlite:////data/migracao/control-ensaio.db \
                    --destino "$REVY_PG_ENSAIO_CONTROL_URL" --schema control
```

Saída zero libera. **Órfão de FK é o achado mais provável** — são 43 FKs nunca
verificadas. Cada órfão exige decisão do dono: apagar a linha filha ou recriar a mãe.
Registre a decisão e trate na origem **antes** do corte, com o app parado, não durante.

- [ ] **Step 7: Carga, cronometrada**

```sh
time python copiar.py --origem sqlite:////data/migracao/portal-ensaio.db \
                      --destino "$REVY_PG_ENSAIO_PORTAL_URL" --schema portal
time python copiar.py --origem sqlite:////data/migracao/control-ensaio.db \
                      --destino "$REVY_PG_ENSAIO_CONTROL_URL" --schema control
```

Anote os dois tempos. **26 tabelas no Portal, 31 no Control, 57 no total.**

- [ ] **Step 8: Validação**

```sh
python validar.py --origem sqlite:////data/migracao/portal-ensaio.db \
                  --destino "$REVY_PG_ENSAIO_PORTAL_URL" --schema portal
python validar.py --origem sqlite:////data/migracao/control-ensaio.db \
                  --destino "$REVY_PG_ENSAIO_CONTROL_URL" --schema control
```

Esperado: `Sem divergencia. Corte liberado.` nos dois.

- [ ] **Step 9: Medir a latência de página, que é o efeito que ninguém vê no teste**

O SQLite é arquivo local: consulta em microssegundos. O Postgres pelo flycast é
milissegundos — mesma região (`iad`), mas ainda assim mil vezes mais. Uma página com 50
consultas passa de imperceptível para perceptível.

Com o `app2037` ainda apontando para os `.db`, meça a linha de base:

```bash
for _ in 1 2 3; do
  curl -sS -o /dev/null -w "%{time_total}\n" https://app2037.fly.dev/healthz
done
```

Anote. Depois do corte, repita e compare. **Isto não bloqueia o corte** — é o número que
diz se a próxima leva precisa atacar N+1, e sem a medição de antes ele não existe.

- [ ] **Step 10: Derrubar o ensaio**

```sql
DROP DATABASE revy_ensaio;
```
```sh
rm -f /data/migracao/*-ensaio.db
```

- [ ] **Step 11: Registrar o resultado**

Anote no card: tempo de carga de cada produto, problemas do pré-voo e como foram
resolvidos, latência de base. **Sem o número do ensaio, a janela é chute.**

---

### Task 9: Banco, schemas e roles definitivos

```
banco  revy
├── schema portal    role portal_app    USAGE + CREATE só em portal
└── schema control   role control_app   USAGE + CREATE só em control
```

Nenhuma das duas roles enxerga o schema da outra. É a primeira vez que a separação entre
produtos é um mecanismo em vez de uma frase no `AGENTS.md`.

- [ ] **Step 1: Gerar duas senhas fortes, fora do repo**

```bash
openssl rand -base64 24
openssl rand -base64 24
```
Guarde no gerenciador de senhas. **Não** cole em arquivo dentro da árvore do projeto.

- [ ] **Step 2: Criar banco, schemas e roles**

```bash
fly pg connect -a suite-pg
```
```sql
CREATE DATABASE revy;
\c revy

CREATE SCHEMA portal;
CREATE SCHEMA control;

CREATE ROLE portal_app  LOGIN PASSWORD 'SENHA_1';
CREATE ROLE control_app LOGIN PASSWORD 'SENHA_2';

-- `public` fica inútil de propósito: assim um search_path errado falha alto
-- em vez de criar tabela fantasma que ninguém encontra depois.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE revy FROM PUBLIC;
GRANT CONNECT ON DATABASE revy TO portal_app, control_app;

ALTER SCHEMA portal  OWNER TO portal_app;
ALTER SCHEMA control OWNER TO control_app;
GRANT USAGE, CREATE ON SCHEMA portal  TO portal_app;
GRANT USAGE, CREATE ON SCHEMA control TO control_app;

-- Vale para TODA conexão da role, inclusive a que o alembic abre por conta
-- própria em env.py (engine_from_config) e que NAO passa pelo connect_args do
-- app/db.py. Sem isto, `alembic upgrade head` tentaria criar em `public`.
ALTER ROLE portal_app  SET search_path = portal;
ALTER ROLE control_app SET search_path = control;
ALTER ROLE portal_app  SET timezone = 'UTC';
ALTER ROLE control_app SET timezone = 'UTC';
```

- [ ] **Step 3: Provar que o isolamento é real, não convenção**

```sql
\c revy portal_app
SHOW search_path;                 -- portal
CREATE TABLE control.invasao(id int);   -- tem que dar ERRO de permissao
CREATE TABLE public.invasao(id int);    -- tem que dar ERRO de permissao
```

Se qualquer um dos dois **funcionar**, pare: as roles não estão isolando e o principal
ganho estrutural do desenho não existe.

- [ ] **Step 4: Guardar as URLs como secret do Fly, sem passar por comando**

Escreva num editor, num arquivo **fora da árvore do repo** (ex.: `~/revy-pg.env`):

```
REVY_PG_PORTAL_URL=postgresql+psycopg://portal_app:SENHA_1@suite-pg.flycast:5432/revy
REVY_PG_CONTROL_URL=postgresql+psycopg://control_app:SENHA_2@suite-pg.flycast:5432/revy
```

```bash
fly secrets import -a app2037 < ~/revy-pg.env
rm -f ~/revy-pg.env
```

Estes dois nomes **não são lidos por nenhum código** — são só o cofre de onde os comandos
da janela vão puxar a URL. Setá-los reinicia a máquina, o que é um restart normal e
inofensivo; faça isso fora do horário de pico, dias antes.

- [ ] **Step 5: Conferir pelo nome, nunca pelo valor**

```bash
fly secrets list -a app2037 | grep REVY_PG
```

- [ ] **Step 6: Rodar o alembic de verdade contra `revy`**

Ainda **sem** tocar em produção: as tabelas ficam criadas e vazias, esperando a carga.

```sh
fly ssh console -a app2037
export DATABASE_URL="$REVY_PG_PORTAL_URL"; export PORTAL_DATABASE_URL="$DATABASE_URL"
cd /srv/portal && alembic upgrade head && alembic current
export DATABASE_URL="$REVY_PG_CONTROL_URL"; export REVY_TRAFEGO_DATABASE_URL="$DATABASE_URL"
cd /srv/revy-trafego && alembic upgrade head && alembic current
```

- [ ] **Step 7: Conferir onde as tabelas de versão foram parar**

```sql
\c revy
SELECT table_schema, table_name FROM information_schema.tables
WHERE table_name LIKE 'alembic_version%';
```
Esperado: `portal | alembic_version` e `control | alembic_version_revy_trafego`. Se
qualquer uma aparecer em `public`, o `search_path` da role está errado — **conserte antes
da janela**.

---

### Task 10: O corte

**Janela de 30–60 min, anunciada.** Durante ela o `app2037` inteiro fica indisponível —
Loja, Control **e o bot do WhatsApp**, porque os seis serviços moram no mesmo container e
o `/healthz` exige 2xx dos quatro. Mensagem que chegar na janela pode se perder: o n8n
recebe erro do chatbot e a Evolution cancela o retry no 404. **Escolha hora de baixo
movimento.**

Os passos 1 a 8 **não mudam nada em produção**. O ponto de virada é o passo 9.

- [ ] **Step 1: Anunciar a janela**

- [ ] **Step 2: Backup, os dois tipos**

```bash
fly volumes list -a app2037
fly volumes snapshots create <volume_id> -a app2037
fly pg connect -a suite-pg -c "\l"   # confirma que suite-pg responde
```
Snapshot diário automático já existe com retenção de 5 dias nos dois volumes; este é o
snapshot **sob demanda**, imediatamente antes.

- [ ] **Step 3: Preparar o comando de rollback ANTES de precisar dele**

Deixe este arquivo pronto num editor aberto, fora do repo. Não tem senha, então pode ser
colado direto:

```bash
fly secrets import -a app2037 <<'EOF'
PORTAL_DATABASE_URL=sqlite:////data/portal/portal.db
REVY_TRAFEGO_DATABASE_URL=sqlite:////data/revy-trafego/revy_trafego.db
EOF
```

- [ ] **Step 4: Parar quem escreve nos dois arquivos**

```bash
fly ssh console -a app2037
supervisorctl stop portal revy-trafego
supervisorctl status
```
Esperado: `portal STOPPED` e `revy-trafego STOPPED`.

São os **únicos** escritores: `PORTAL_DATABASE_URL` não é lida por nenhum arquivo de
`revy-trafego/app/` (o export do `run-revy-trafego.sh` era morto e foi apagado na Task 2),
e nenhum outro serviço do bundle abre esses arquivos.

A partir daqui o `/healthz` responde 5xx — é esperado.

- [ ] **Step 5: Tirar o snapshot que vai ser a fonte da carga**

```sh
mkdir -p /data/migracao
python - <<'PY'
import sqlite3
for origem, destino in (
    ('/data/portal/portal.db', '/data/migracao/portal-corte.db'),
    ('/data/revy-trafego/revy_trafego.db', '/data/migracao/control-corte.db'),
):
    o = sqlite3.connect(origem); d = sqlite3.connect(destino)
    o.backup(d); d.close(); o.close()
    print(destino, 'ok')
PY
```

**Toda a carga lê deste snapshot, nunca do arquivo vivo.** Assim, mesmo que o Fly reinicie
a máquina por causa do healthcheck falhando e o supervisord religue o Portal no meio, a
fonte da carga não muda debaixo dos pés.

- [ ] **Step 6: Cópia off-Fly do snapshot**

```bash
fly ssh sftp get /data/migracao/portal-corte.db  -a app2037
fly ssh sftp get /data/migracao/control-corte.db -a app2037
```
Guarde fora da árvore do repo. É a rede de segurança final.

- [ ] **Step 7: Pré-voo no snapshot real**

```sh
cd /srv/migracao-pg
python verificar.py --origem sqlite:////data/migracao/portal-corte.db \
                    --destino "$REVY_PG_PORTAL_URL" --schema portal
python verificar.py --origem sqlite:////data/migracao/control-corte.db \
                    --destino "$REVY_PG_CONTROL_URL" --schema control
```

Saída diferente de zero **aborta**: vá para o passo 11. Se o ensaio foi feito, aqui não
deve aparecer nada novo — se aparecer, é dado que nasceu entre o ensaio e agora, e a
decisão sobre ele é do dono, não do executor.

- [ ] **Step 8: Carga**

```sh
python copiar.py --origem sqlite:////data/migracao/portal-corte.db \
                 --destino "$REVY_PG_PORTAL_URL" --schema portal
python copiar.py --origem sqlite:////data/migracao/control-corte.db \
                 --destino "$REVY_PG_CONTROL_URL" --schema control
```

Se o `copiar.py` recusar com `CargaRecusada`, é porque `revy` **já tem linha** — provável
resto de uma tentativa anterior. Não force: `TRUNCATE` o schema inteiro ou recrie o banco
e refaça o `alembic upgrade head` (Task 9, step 6).

- [ ] **Step 9: O portão**

```sh
python validar.py --origem sqlite:////data/migracao/portal-corte.db \
                  --destino "$REVY_PG_PORTAL_URL" --schema portal
python validar.py --origem sqlite:////data/migracao/control-corte.db \
                  --destino "$REVY_PG_CONTROL_URL" --schema control
```

**Qualquer divergência aborta.** Vá para o passo 11.

E, antes de virar: confirme que ninguém escreveu no arquivo vivo depois do snapshot —

```sh
python validar.py --origem sqlite:////data/portal/portal.db \
                  --destino "$REVY_PG_PORTAL_URL" --schema portal
python validar.py --origem sqlite:////data/revy-trafego/revy_trafego.db \
                  --destino "$REVY_PG_CONTROL_URL" --schema control
```

Divergência aqui significa que a máquina reiniciou e o app voltou a escrever. Não é
catástrofe: `supervisorctl stop portal revy-trafego` de novo, apague o schema, refaça do
passo 5. É catástrofe **só** se você virar sem essa conferência.

- [ ] **Step 10: A virada**

Escreva num editor, fora do repo (`~/revy-cutover.env`) — usando as mesmas duas URLs da
Task 9:

```
PORTAL_DATABASE_URL=postgresql+psycopg://portal_app:SENHA_1@suite-pg.flycast:5432/revy
REVY_TRAFEGO_DATABASE_URL=postgresql+psycopg://control_app:SENHA_2@suite-pg.flycast:5432/revy
```

```bash
fly secrets import -a app2037 < ~/revy-cutover.env
rm -f ~/revy-cutover.env
```

Secret vence `[env]` do toml, então as duas linhas SQLite do `fly.app.toml` deixam de
valer neste instante. O `fly secrets import` reinicia a máquina; o `entrypoint-app.sh`
roda `alembic upgrade head` contra `revy` (já em head, no-op) e sobe tudo.

- [ ] **Step 11: Conferir — ou reverter**

```bash
fly logs -a app2037 | tail -50
curl -sS -o /dev/null -w "%{http_code}\n" https://app2037.fly.dev/healthz
curl -sS -o /dev/null -w "%{http_code}\n" https://app2037.fly.dev/trafego/health/ready
```

E na tela, como dono: abrir a Loja, ver vendas e metas; abrir o Control, ver as lojas.

**Se algo estiver errado**, cole o comando de rollback do Step 3. Os dois `.db` não foram
tocados — continuam exatamente como no passo 4.

- [ ] **Step 12: Liberar o acesso e avisar**

---

### Task 11: Depois do corte

- [ ] **Step 1: Tirar as linhas SQLite do `fly.app.toml`**

Apague de `deploy/fly/3vm/fly.app.toml` as duas linhas do bloco `[env]`:
```
PORTAL_DATABASE_URL = "sqlite:////data/portal/portal.db"
REVY_TRAFEGO_DATABASE_URL = "sqlite:////data/revy-trafego/revy_trafego.db"
```

Não coloque a URL Postgres no lugar — ela tem senha e o toml está no git. Depois desta
mudança o secret é a **única** fonte, e o `${VAR:?}` da Task 2 garante que um secret
perdido derruba o boot com mensagem em vez de subir um banco vazio.

Deploy e conferir `/healthz` = 200.

- [ ] **Step 2: `pg_dump` do `revy` entra na rotina**

Snapshot de volume é crash-consistent do cluster inteiro; não é backup lógico por banco.
São dois objetos diferentes e você quer os dois.

```bash
fly pg connect -a suite-pg -c "\l" | grep revy
```

- [ ] **Step 3: Medir por alguns dias**

```sql
SELECT count(*), state FROM pg_stat_activity WHERE datname = 'revy' GROUP BY state;
```
E a RAM do `suite-pg`: é **shared-1x com 512 MB**, e já houve OOM nessa máquina em
20/07 quando tinha 256 MB. Agora ela atende cinco bancos em vez de quatro.

E repita a medição de latência do ensaio (Task 8, Step 9) para comparar com a linha de
base.

- [ ] **Step 4: Os `.db` ficam 30 dias**

Não apague `/data/portal/portal.db` nem `/data/revy-trafego/revy_trafego.db`. Anote a data
de expurgo. Apague `/data/migracao/*-corte.db` só depois de confirmar que a cópia off-Fly
está guardada.

- [ ] **Step 5: Atualizar a documentação que agora está mentindo**

- `deploy/fly/3vm/README.md:118` — a tabela ainda diz `REVY_TRAFEGO_DATABASE_URL |
  sqlite:////data/revy-trafego/revy_trafego.db`
- `docs/referencia-viva/contexto-compacto.md` — o estado passa a ser "5 bancos, 1 engine"
- A memória `topologia-bancos-5-bancos-2-engines` fica **errada** no dia do corte

- [ ] **Step 6: Reabrir a Parte B da Fase 5**

`docs/fila/2026-08-12-copiloto-fase5-log-de-perguntas-e-isolamento.md` projeta RLS, que
não existe em SQLite — o card foi escrito com premissa errada sobre a própria infra.
Depois do corte, ele passa a ser implementável. **Não é escopo desta leva**; só deixe
registrado que destravou.

---

## O que este plano deliberadamente não faz

- **Não junta as tabelas duplicadas.** `portal.campanhas` e `control.campanhas` passam a
  coexistir, cada uma no seu schema, sem colidir. Reconciliar o fork é uma decisão de
  produto, não de migração, e agora fica possível — o que hoje não é.
- **Não muda nenhuma consulta.** O ganho de poder fazer join entre schemas fica
  disponível; usá-lo é outra leva.
- **Não move `chatbot`, `estoque`, `motor` nem `evolution`.** Eles continuam como bancos
  próprios no mesmo cluster.
- **Não liga um segundo processo.** Isso é a leva 1
  (`2026-08-16-postgres-1-concorrencia.md`) mais o trabalho de capacidade da §5 do spec.
- **Não implementa RLS.** Só destrava.

## Antes de dizer que acabou

- [ ] `cd deploy/migracao-pg && … -m pytest -q` → 28 passed
- [ ] `cd portal-gestao && … -m pytest -q` → 1289 passed
- [ ] `cd revy-trafego && … -m pytest -q` → 521 passed
- [ ] `python n8n/validate_workflow.py` na raiz (o corte não toca n8n, mas o gate é o gate)
- [ ] `/healthz` = 200 e `/trafego/health/ready` = 200
- [ ] `alembic current` dos dois produtos em head, **no schema certo**
- [ ] Os dois `.db` intactos no volume, com data de expurgo anotada
- [ ] `git diff --check` e `git status --short` limpos, sem mudança alheia
