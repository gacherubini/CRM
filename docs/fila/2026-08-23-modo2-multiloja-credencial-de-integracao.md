# Plano — Modo 2 multi-loja: credencial de integração

> **Status 2026-08-23: FILA / NÃO IMPLEMENTADO.**
> Descoberto durante o smoke do piloto Modo 2 no número de teste. Não altera o
> contrato do webhook nem o comportamento de loja única já em produção.
> Implementa o §6.2 da spec [`2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md).

**Goal:** fazer um único workflow `n8n-cloud` atender N lojas, resolvendo a loja pela
instância que já viaja no evento em vez do `loja_id` embutido no bearer token.

**Architecture:** hoje `CredencialServico` é "token → uma loja", e todas as rotas que o
n8n chama derivam `ctx.loja_id` do token. Acrescentamos um papel `integracao` cujo token
**não** aponta para loja nenhuma; as rotas do bot passam a resolver a loja pela `instance`
do corpo (o mesmo caminho que o webhook já usa, `servico.resolver_loja_e_canal_por_instancia`).
Credencial de loja continua funcionando exatamente como hoje — expand-only, sem quebrar
nada existente.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped[...]`), Alembic, pytest. Produto único:
`chatbot-api`. Nenhuma mudança cruza produto.

**Spec:** `docs/referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md` §6.2
("Um workflow `n8n-cloud` serve N lojas, e o Revy é **um** app na Meta").

## O sintoma que originou este card

Com a loja `teste` em Modo 2 e o número de teste apontado para ela:

1. a mensagem entra por `POST /webhook/cloud`, que resolve a loja por `phone_number_id`
   (`main.py:617`, `_loja_por_phone_number_id`) e grava na loja certa;
2. o n8n volta perguntando `POST /v1/conversas/{tel}/pode-responder`, autenticado com o
   único `__CHATBOT_TOKEN__` que o workflow carrega — de **outra** loja;
3. `servico.pode_responder_mensagem` (`servico.py:1364-1370`) consulta conversa e mensagem
   por `loja_id` **do token** e devolve `conversa_nao_encontrada`;
4. o agente para. **Nenhum erro em log** — só `200` e silêncio.

O caminho do webhook é multi-loja; o caminho da API não é. Nunca apareceu porque só existia
uma loja em produção.

## Adendo 2026-08-24 — o que envelheceu neste card

Conferido contra o repo antes de executar. O plano continua valendo; três detalhes
mudaram e travariam quem colasse os trechos como estao.

**1. As fixtures dos testes nao existem com esses nomes.** O card escreve `loja`,
`loja_com_canal` e `conversa_com_entrada`. O `tests/conftest.py` oferece `client`,
`db`, `loja_a`, `loja_b` e `loja_sem_projecao` — e as tres de loja devolvem um
**dict**, nao um objeto: `{"loja_id", "slug", "instance", "headers"}`. Use `loja_a`
e `loja_b`: sao exatamente as duas lojas que este bug precisa, entao o teste de
regressao e escrivivel **na suite**, sem depender de duas lojas em producao.
Conversa com mensagem de entrada nao tem fixture — semeie no proprio teste.

**2. Ha dois resolvedores de instancia, e eles nao sao iguais.** A Task 2 delega
para `resolver_loja_e_canal_por_instancia` (`app/servico.py:606`), que chama
`channels.resolve_canal_for_instance` (`app/channels.py:432`) e **faz backfill**:
cria o canal como efeito colateral quando o numero so existe em
`lojas.evolution_instance`. Desde 24/08 existe tambem
`cloud_canal.loja_id_do_phone_number_id` (`app/cloud_canal.py:93`), que faz as
**mesmas duas buscas** e e **so leitura**. Escolha consciente: a rota autenticada
pode aceitar o backfill (e o mesmo que o inbound ja faz), mas nao deixe as duas
divergirem sem alguem ter decidido. Ver
[[2026-08-24-outbound-por-loja-quer-loja-id]].

**3. Os numeros de linha do `main.py` andaram** (mexido em 24/08 no handoff e no
`_loja_por_phone_number_id`). Atuais:

| Simbolo | Linha |
|---|---|
| `PodeResponderInput` | 285 |
| `SimularInput` | 355 |
| `RespostaBotInput` | 430 |
| `HandoffHumanoInput` | 445 |
| `pode_responder` | 914 |
| `config_catalogo_bot` | 1231 |
| `buscar_estoque` | 1273 |
| `solicitar_simulacao` | 1419 |
| `solicitar_simulacao_humana` | 1771 |
| `responder_cliente` | 1810 |
| `acionar_handoff_humano` | 1857 |

Confirme com `rg` antes de editar; nao confie nesta tabela depois da primeira task.

Baseline confirmado: `criar_credencial_integracao` e `resolver_loja_id` **nao
existem** ainda, `CredencialServico.loja_id` segue `nullable=False`
(`models_db.py:163`), `Contexto.loja_id` segue `str` (`auth.py:19-22`) e a ultima
migration e mesmo `0025_canal_cloud_por_loja` — o `down_revision` do Step 4 esta
certo.

## Global Constraints

- **Expand-only.** Token de loja existente continua autenticando e resolvendo igual. Nenhuma
  rota muda de comportamento para credencial de loja.
- **Fail-closed.** Credencial de integração **sem** `instance` no pedido é `400`, nunca um
  fallback para "alguma" loja.
- **Isolamento.** Credencial de integração resolve só lojas que possuem a instância pedida;
  `resolve_canal_for_instance` já rejeita instância desconhecida (`servico.py:616`).
- **Sem segredo em log, git ou doc.** O token da credencial de integração é impresso uma vez
  pelo CLI e nunca persistido no repo.
- **Postgres.** `batch_alter_table` estoura no PG (ver learning `engine-do-produto-se-confere-no-db-py`);
  use `op.alter_column` direto.
- **Flag de rollout nasce OFF** — mas aqui não há flag: a mudança é inerte enquanto ninguém
  criar uma credencial de integração.
- Testes rodam **a partir de `chatbot-api/`**: `.venv/bin/python -m pytest -q` (macOS) ou
  `.\.venv\Scripts\python.exe -m pytest -q` (Windows).

## Baseline existente — não reinventar

- `chatbot-api/app/auth.py:15` — `hash_token` (sha256) e `get_contexto` (linha 25).
- `chatbot-api/app/auth.py:19` — `Contexto(loja_id, papel)`.
- `chatbot-api/app/models_db.py:159` — `CredencialServico(token_hash PK, loja_id FK, papel, criada_em)`.
- `chatbot-api/app/servico.py:606` — `resolver_loja_e_canal_por_instancia(db, instancia) -> (Loja, WhatsAppCanal)`,
  que já faz backfill de canal legado e recusa instância desconhecida.
- `chatbot-api/app/servico.py:573` — `criar_loja`, único lugar que hoje cria credencial.
- `chatbot-api/app/cli.py` — `criar-loja` e `autorizar-numero`.
- Última migration: `chatbot-api/alembic/versions/0025_canal_cloud_por_loja.py`.

### Quem já manda `instance`, e quem não manda

Levantado no `n8n/workflow-cloud.json` e nos modelos de `main.py`:

| Rota chamada pelo workflow | `instance` hoje |
|---|---|
| `POST /v1/conversas/{tel}/pode-responder` | **obrigatório** (`PodeResponderInput`, `main.py:290`) |
| `POST /v1/operacao/solicitacoes-simulacao-humana` | opcional (`main.py:408`) |
| `POST /v1/operacao/moto-escolhida` | opcional (`main.py:466`) |
| `POST /v1/operacao/responder` | **não tem** (`RespostaBotInput`, `main.py:430`) |
| `POST /v1/operacao/handoff-humano` | **não tem** (`HandoffHumanoInput`, `main.py:445`) |
| `POST /v1/simulacoes/solicitar` | **não tem** (`SimularInput`, `main.py:355`) |
| `GET /v1/estoque/buscar` | **não tem** (query, `main.py:1281`) |
| `GET /v1/config/catalogo-bot` | **não tem** (query, `main.py:1239`) |

---

### Task 1: Credencial sem loja (modelo, migration, CLI)

**Files:**
- Modify: `chatbot-api/app/models_db.py:159-166`
- Create: `chatbot-api/alembic/versions/0026_credencial_integracao.py`
- Modify: `chatbot-api/app/servico.py` (nova função `criar_credencial_integracao`)
- Modify: `chatbot-api/app/cli.py:17-40`
- Test: `chatbot-api/tests/test_credencial_integracao.py`

**Interfaces:**
- Produces: `servico.criar_credencial_integracao(db) -> str` (devolve o token em claro, uma vez).
- Produces: `CredencialServico.loja_id` passa a aceitar `None`; `papel == "integracao"` marca o caso.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_credencial_integracao.py
from app import servico
from app.auth import hash_token
from app.models_db import CredencialServico


def test_credencial_integracao_nasce_sem_loja(db):
    token = servico.criar_credencial_integracao(db)

    cred = db.get(CredencialServico, hash_token(token))
    assert cred is not None
    assert cred.loja_id is None
    assert cred.papel == "integracao"
```

- [ ] **Step 2: Rodar e ver falhar**

Windows: `.\.venv\Scripts\python.exe -m pytest tests/test_credencial_integracao.py -q`
macOS: `.venv/bin/python -m pytest tests/test_credencial_integracao.py -q`
Esperado: FAIL — `module 'app.servico' has no attribute 'criar_credencial_integracao'`.

- [ ] **Step 3: Tornar `loja_id` opcional no modelo**

```python
# models_db.py, dentro de CredencialServico
    loja_id: Mapped[str | None] = mapped_column(
        ForeignKey("lojas.id"), index=True, nullable=True
    )
    # Nulo = credencial de integração (papel "integracao"): não é de loja nenhuma,
    # e a loja de cada pedido vem da instância (spec §6.2).
    papel: Mapped[str] = mapped_column(String, default="dono")
```

- [ ] **Step 4: Migration**

```python
# chatbot-api/alembic/versions/0026_credencial_integracao.py
"""credencial de integracao: loja_id passa a aceitar NULL"""
from alembic import op
import sqlalchemy as sa

revision = "0026_credencial_integracao"
down_revision = "0025_canal_cloud_por_loja"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table estoura no Postgres; alter_column direto serve nos dois.
    op.alter_column(
        "credenciais_servico",
        "loja_id",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("DELETE FROM credenciais_servico WHERE loja_id IS NULL")
    op.alter_column(
        "credenciais_servico",
        "loja_id",
        existing_type=sa.String(),
        nullable=False,
    )
```

- [ ] **Step 5: Implementar a criação**

```python
# servico.py, ao lado de criar_loja
def criar_credencial_integracao(db: Session) -> str:
    """Credencial da plataforma: sem loja. A loja de cada pedido vem da instância.

    Devolve o token em claro **uma vez**; o banco guarda só o hash.
    """
    token = secrets.token_urlsafe(24)
    db.add(
        CredencialServico(
            token_hash=hash_token(token), loja_id=None, papel="integracao"
        )
    )
    db.commit()
    return token
```

- [ ] **Step 6: Subcomando no CLI**

```python
# cli.py, dentro de main(), junto dos outros add_parser
    sub.add_parser(
        "criar-credencial-integracao",
        help="cria credencial da plataforma (sem loja) para o n8n",
    )

# e no despacho:
    elif args.comando == "criar-credencial-integracao":
        db = SessionLocal()
        try:
            token = servico.criar_credencial_integracao(db)
        finally:
            db.close()
        print("Credencial de integração criada (papel=integracao, sem loja).")
        print(f"TOKEN (guarde agora, não será mostrado de novo): {token}")
```

- [ ] **Step 7: Rodar e ver passar**

`... -m pytest tests/test_credencial_integracao.py -q` → PASS.

- [ ] **Step 8: Suíte inteira + migration**

`... -m pytest -q` e `... -m alembic upgrade head` no `chatbot-api`.

- [ ] **Step 9: Commit**

```bash
git add chatbot-api/app/models_db.py chatbot-api/app/servico.py chatbot-api/app/cli.py \
        chatbot-api/alembic/versions/0026_credencial_integracao.py \
        chatbot-api/tests/test_credencial_integracao.py
git commit -m "feat(chatbot): credencial de integracao sem loja (spec 6.2)"
```

---

### Task 2: O resolvedor de loja do contexto

**Files:**
- Modify: `chatbot-api/app/auth.py:19-34`
- Test: `chatbot-api/tests/test_resolver_loja_do_contexto.py`

**Interfaces:**
- Consumes: `CredencialServico.loja_id` opcional (Task 1).
- Produces: `Contexto.loja_id: str | None` e
  `auth.resolver_loja_id(db, ctx, instance: str | None) -> str`. Toda rota do bot passa a
  chamar essa função em vez de ler `ctx.loja_id` direto.

- [ ] **Step 1: Escrever os testes que falham**

```python
# chatbot-api/tests/test_resolver_loja_do_contexto.py
import pytest
from fastapi import HTTPException

from app import auth
from app.auth import Contexto


def test_credencial_de_loja_ignora_instance(db, loja):
    ctx = Contexto(loja_id=loja.id, papel="dono")
    assert auth.resolver_loja_id(db, ctx, None) == loja.id


def test_integracao_resolve_pela_instance(db, loja_com_canal):
    loja, canal = loja_com_canal
    ctx = Contexto(loja_id=None, papel="integracao")
    assert auth.resolver_loja_id(db, ctx, canal.evolution_instance) == loja.id


def test_integracao_sem_instance_e_400(db):
    ctx = Contexto(loja_id=None, papel="integracao")
    with pytest.raises(HTTPException) as e:
        auth.resolver_loja_id(db, ctx, None)
    assert e.value.status_code == 400


def test_integracao_com_instance_desconhecida_e_404(db):
    ctx = Contexto(loja_id=None, papel="integracao")
    with pytest.raises(HTTPException) as e:
        auth.resolver_loja_id(db, ctx, "instancia-que-nao-existe")
    assert e.value.status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar**

`... -m pytest tests/test_resolver_loja_do_contexto.py -q` → FAIL, `resolver_loja_id` não existe.

- [ ] **Step 3: Implementar**

```python
# auth.py
@dataclass
class Contexto:
    loja_id: str | None
    papel: str


def resolver_loja_id(db: Session, ctx: Contexto, instance: str | None) -> str:
    """Loja deste pedido. Credencial de loja manda; integração resolve pela instância.

    Fail-closed de propósito (spec §6.2): integração sem instância é 400, nunca um
    fallback para "alguma" loja — isso mandaria a mensagem de uma loja pela outra.
    """
    if ctx.loja_id:
        return ctx.loja_id
    if not instance:
        raise HTTPException(
            status_code=400, detail="instance é obrigatório para credencial de integração"
        )
    from app.servico import resolver_loja_e_canal_por_instancia

    loja, _canal = resolver_loja_e_canal_por_instancia(db, instance)
    return loja.id
```

- [ ] **Step 4: Rodar e ver passar**

`... -m pytest tests/test_resolver_loja_do_contexto.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/auth.py chatbot-api/tests/test_resolver_loja_do_contexto.py
git commit -m "feat(chatbot): resolver_loja_id resolve loja por instancia na integracao"
```

---

### Task 3: `pode-responder` na credencial de integração

Primeira rota migrada, e a que prova o caminho inteiro: é a que quebrou no smoke, e já
recebe `instance` obrigatório.

**Files:**
- Modify: `chatbot-api/app/main.py:921-935`
- Test: `chatbot-api/tests/test_pode_responder_integracao.py`

**Interfaces:**
- Consumes: `auth.resolver_loja_id` (Task 2).

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_pode_responder_integracao.py
def test_integracao_acha_conversa_da_loja_da_instance(client, db, loja_com_canal, conversa_com_entrada):
    """O bug do smoke: token de integração + instance da loja B acha a conversa da loja B."""
    loja, canal = loja_com_canal
    token = servico.criar_credencial_integracao(db)

    r = client.post(
        f"/v1/conversas/{conversa_com_entrada.telefone}/pode-responder",
        json={
            "provider_message_id": conversa_com_entrada.ultimo_provider_message_id,
            "instance": canal.evolution_instance,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert r.status_code == 200
    assert r.json()["pode_responder"] is True
```

- [ ] **Step 2: Rodar e ver falhar**

Esperado: FAIL com `{"pode_responder": False, "motivo": "conversa_nao_encontrada"}` — que é
exatamente o sintoma de produção, agora capturado em teste.

- [ ] **Step 3: Implementar**

```python
# main.py, dentro de pode_responder
    loja_id = auth.resolver_loja_id(db, ctx, dados.instance)
    return servico.pode_responder_mensagem(
        db,
        loja_id,
        telefone,
        dados.provider_message_id,
        instance=dados.instance,
    )
```

- [ ] **Step 4: Rodar e ver passar**

`... -m pytest tests/test_pode_responder_integracao.py -q` → PASS. E a suíte inteira, para
provar que credencial de loja não regrediu.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_pode_responder_integracao.py
git commit -m "feat(chatbot): pode-responder resolve loja por instance"
```

---

### Task 4: `responder` e `handoff-humano` ganham `instance`

As duas rotas que hoje **não** carregam instância — e sem elas o bot nem responde nem
entrega o lead.

**Files:**
- Modify: `chatbot-api/app/main.py:430-443` (`RespostaBotInput`), `445-458` (`HandoffHumanoInput`),
  `1818-1830` e `1866-1878` (as rotas)
- Test: `chatbot-api/tests/test_responder_handoff_integracao.py`

**Interfaces:**
- Produces: `RespostaBotInput.instance: str | None` e `HandoffHumanoInput.instance: str | None`,
  ambos opcionais — credencial de loja segue mandando o corpo de hoje, sem `instance`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_responder_com_integracao_usa_a_loja_da_instance(client, db, loja_com_canal, conversa_com_entrada):
    loja, canal = loja_com_canal
    token = servico.criar_credencial_integracao(db)

    r = client.post(
        "/v1/operacao/responder",
        json={
            "telefone": conversa_com_entrada.telefone,
            "texto": "oi",
            "instance": canal.evolution_instance,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_responder_com_integracao_sem_instance_e_400(client, db):
    token = servico.criar_credencial_integracao(db)
    r = client.post(
        "/v1/operacao/responder",
        json={"telefone": "5511999999999", "texto": "oi"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Rodar e ver falhar**

Esperado: FAIL — o primeiro por `instance` não existir no modelo (422), o segundo por não
haver validação de 400.

- [ ] **Step 3: Implementar**

```python
# main.py, em RespostaBotInput e em HandoffHumanoInput
    instance: Optional[str] = Field(default=None, max_length=120)

# nas duas rotas, trocando ctx.loja_id pelo resolvedor:
    loja_id = auth.resolver_loja_id(db, ctx, dados.instance)
```

- [ ] **Step 4: Rodar e ver passar**

`... -m pytest tests/test_responder_handoff_integracao.py -q` → PASS. Suíte inteira também.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_responder_handoff_integracao.py
git commit -m "feat(chatbot): responder e handoff-humano aceitam instance"
```

---

### Task 5: As rotas restantes do bot

`solicitacoes-simulacao-humana` e `moto-escolhida` já têm `instance` opcional; falta trocar
o uso de `ctx.loja_id`. `simulacoes/solicitar` precisa do campo. `estoque/buscar` e
`config/catalogo-bot` são GET e recebem `instance` como query.

**Files:**
- Modify: `chatbot-api/app/main.py:355-370` (`SimularInput`), `1239-1246`, `1281-1292`,
  `1427-1440`, `1779-1790`, `1907-1918`
- Test: `chatbot-api/tests/test_rotas_bot_integracao.py`

**Interfaces:**
- Produces: `SimularInput.instance: str | None`; `GET /v1/estoque/buscar` e
  `GET /v1/config/catalogo-bot` passam a aceitar `instance: str | None = None` na query.

- [ ] **Step 1: Escrever o teste que falha**

```python
import pytest

ROTAS_POST = [
    ("/v1/operacao/solicitacoes-simulacao-humana", {"telefone": "5511999999999"}),
    ("/v1/operacao/moto-escolhida", {"telefone": "5511999999999", "placa": "ABC1D23"}),
    ("/v1/simulacoes/solicitar", {"telefone": "5511999999999", "placa": "ABC1D23"}),
]


@pytest.mark.parametrize("rota,corpo", ROTAS_POST)
def test_post_com_integracao_sem_instance_e_400(client, db, rota, corpo):
    token = servico.criar_credencial_integracao(db)
    r = client.post(rota, json=corpo, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


@pytest.mark.parametrize("rota", ["/v1/estoque/buscar", "/v1/config/catalogo-bot"])
def test_get_com_integracao_resolve_pela_query(client, db, loja_com_canal, rota):
    loja, canal = loja_com_canal
    token = servico.criar_credencial_integracao(db)
    r = client.get(
        rota,
        params={"instance": canal.evolution_instance},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
```

- [ ] **Step 2: Rodar e ver falhar**

`... -m pytest tests/test_rotas_bot_integracao.py -q` → FAIL.

- [ ] **Step 3: Implementar**

```python
# SimularInput ganha o campo:
    instance: Optional[str] = Field(default=None, max_length=120)

# nas rotas GET, novo parâmetro de query e uso do resolvedor:
def buscar_estoque(
    termo: Optional[str] = None,
    instance: Optional[str] = None,
    ctx: Contexto = Depends(get_contexto),
    db: Session = Depends(get_db),
    provider: InventoryProvider = Depends(get_inventory_provider),
):
    loja = db.get(models_db.Loja, auth.resolver_loja_id(db, ctx, instance))

# nas rotas POST, mesma troca:
    loja_id = auth.resolver_loja_id(db, ctx, dados.instance)
```

`config_catalogo_bot` não recebe `db` hoje — acrescente `db: Session = Depends(get_db)` à
assinatura junto do parâmetro `instance`.

- [ ] **Step 4: Rodar e ver passar**

`... -m pytest -q` (suíte inteira, `chatbot-api`).

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_rotas_bot_integracao.py
git commit -m "feat(chatbot): rotas do bot resolvem loja por instance"
```

---

### Task 6: O workflow passa a mandar `instance` em tudo

**Files:**
- Modify: `n8n/fork_cloud_workflow.py`
- Modify: `n8n/validate_workflow_cloud.py`
- Regenerate: `n8n/workflow-cloud.json`
- Test: `chatbot-api/` não entra aqui; a verificação é o validador do n8n.

**Interfaces:**
- Consumes: os campos `instance` das Tasks 4 e 5.

- [ ] **Step 1: Fazer o validador exigir `instance`**

```python
# n8n/validate_workflow_cloud.py
ROTAS_QUE_EXIGEM_INSTANCE = (
    "/v1/operacao/responder",
    "/v1/operacao/handoff-humano",
    "/v1/simulacoes/solicitar",
    "/v1/estoque/buscar",
    "/v1/config/catalogo-bot",
)


def conferir_instance(workflow: dict) -> list[str]:
    """Toda chamada ao chatbot precisa dizer de qual loja fala (spec §6.2).

    Sem isso o workflow volta a servir uma loja só — e o sintoma é silêncio,
    não erro: o chatbot procura a conversa na loja errada e o agente para.
    """
    faltando = []
    for no in workflow.get("nodes", []):
        url = str(((no.get("parameters") or {}).get("url")) or "")
        if not any(r in url for r in ROTAS_QUE_EXIGEM_INSTANCE):
            continue
        if "instance" not in json.dumps(no.get("parameters") or {}):
            faltando.append(no.get("name", "?"))
    return faltando
```

- [ ] **Step 2: Rodar o validador e ver falhar**

`python n8n/validate_workflow_cloud.py` na raiz → sai `1`, listando os nós sem `instance`.

- [ ] **Step 3: Fazer o gerador acrescentar `instance` ao corpo**

No `fork_cloud_workflow.py`, ao reescrever cada nó HTTP do fork, injetar no corpo
`instance` com o `phone_number_id` do evento — o mesmo valor que o webhook já usa para
resolver a loja. Regerar: `python n8n/fork_cloud_workflow.py`.

- [ ] **Step 4: Rodar os dois validadores e ver passar**

```bash
python n8n/validate_workflow.py
python n8n/validate_workflow_cloud.py
```

- [ ] **Step 5: Commit**

```bash
git add n8n/fork_cloud_workflow.py n8n/validate_workflow_cloud.py n8n/workflow-cloud.json
git commit -m "feat(n8n): workflow cloud manda instance em toda chamada ao chatbot"
```

---

## Publicação (depois das seis tasks)

1. `python -m app.cli criar-credencial-integracao` no `app2037` (uma vez, guardar o token).
2. Pôr esse token como `CHATBOT_API_TOKEN` do build **cloud** — hoje o
   `deploy/fly/3vm/prepare-workflow.ps1` lê uma chave só para os dois modos; **acrescente
   `CHATBOT_API_TOKEN_CLOUD`** ao `.secrets.local` e use-a quando `-Mode cloud`, senão
   publicar o cloud sobrescreve o token do Modo 1 (foi o que aconteceu em 23/08 e exigiu
   backup e restore à mão).
3. `prepare-workflow.ps1 -Mode cloud`, `import:workflow`, `update:workflow --active=true`,
   `fly apps restart n8n2037` — na ordem do learning `import-do-n8n-desativa-o-workflow`.
4. Conferir com duas lojas em Modo 2 ao mesmo tempo. **É o único teste que prova o card**:
   uma loja só passa mesmo com o bug.

## Fora de escopo

- **Um workflow por loja.** Serve de muleta para 2–3 lojas e multiplica o que o
  `fork_cloud_workflow.py` existe para não deixar divergir.
- **Rotação do token de integração.** Continua em aberto (§16.7): um token alcança N WABAs
  e, revogado, derruba todas as lojas juntas. Card próprio.
- **Trocar a autenticação por mTLS ou JWT.** Não há motivo hoje; bearer + hash resolve.
