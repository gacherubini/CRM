# Modo 2 / Card 5 — A metade do dono na Loja — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Fazer o rodízio aparecer na Loja: o vendedor recebe a oferta **também no sino**, com
botão Peguei que trava de verdade, e o dono passa a ver os leads que ninguém pegou.

**Architecture:** o `chatbot-api` ganha duas rotas que expõem o estado da oferta; o Portal lê por
`ChatbotClient` como já faz com canais e leads. O produtor de sinal entra no **worker que já
existe** (`copiloto_sinais_job`), que o plano B1 desacoplou da flag do Copiloto justamente para
receber tipos novos. Nenhuma direção nova de chamada, nenhum daemon novo.

**Tech Stack:** FastAPI, SQLAlchemy, httpx, Jinja2, pytest.

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §5.7 (Peguei no sino), §5.4 e §5.8 (faixa, filtro, card de 7 dias), §2 (canal do aviso é WhatsApp **e** sino).

## Por que este card existe

Os planos 1 a 4 do Modo 2 foram recortados **por produto**, e a interface entre eles ficou no vão:
o plano `wa-modo2-1` entregou a capacidade de endereçar um sinal a uma pessoa; o `wa-modo2-2`
entregou o estado da oferta no chatbot; e **nenhum dos dois entregou a ponte**. Hoje:

- `criar_sinal_direcionado` e `transferir_sinal` existem, testados, **sem nenhum chamador** — o
  sino não toca para o vendedor, ele só recebe a oferta pelo WhatsApp;
- o `chatbot-api` **não expõe rota nenhuma de oferta**: `oferta_lead` nunca sai do banco dele;
- **lead que ninguém pega some.** Vira `esgotou_fila` dentro do chatbot e ninguém é avisado — nem
  por tela, nem por WhatsApp. O dono escolheu a faixa na Loja **no lugar** do resumo das 19h
  (§15, decisão 4), então sem ela o fallback que ele escolheu não existe em forma nenhuma.

## Pré-requisitos

Planos `wa-modo2-1` a `wa-modo2-4` e o B1 executados — todos estão em
[`../referencia-viva/planos/`](../referencia-viva/planos/). Este card **usa** o que eles
entregaram e não os reimplementa.

## Global Constraints

- **Direção de chamada não muda:** Portal → Chatbot, sempre, com a credencial de serviço que já
  existe. O chatbot **não** chama o Portal.
- **Nunca telefone em claro no sinal.** `entidade_ref` guarda o id da oferta; o telefone do cliente
  só transita na resposta do `assumir`, e não é persistido em `copiloto_sinal`.
- **Sino 1:1 é 1:1.** Só o `oferecido_a` vê a oferta. Dono e gerente **não** veem — eles veem o que
  sobrou, na faixa.
- **Gate do Modo 2 vale aqui também:** loja em Modo 1 não ganha faixa, nem filtro, nem sinal de
  oferta. Nada disso pode vazar para o Modo 1.
- **Não criar worker novo.** O produtor entra no `copiloto_sinais_job`, que o B1 já fez rodar
  independente da flag do Copiloto — era exatamente para isto.
- Rodar testes a partir da pasta do produto: macOS `.venv/bin/python -m pytest -q`;
  Windows `.\.venv\Scripts\python.exe -m pytest -q`.

---

### Task 1: `GET /v1/ofertas` — o chatbot expõe o estado do rodízio

**Files:**
- Modify: `chatbot-api/app/main.py`
- Test: `chatbot-api/tests/test_ofertas_rotas.py`

**Interfaces:**
- Produces: `GET /v1/ofertas?estado=aberta|travada|esgotada` sob `get_contexto` (Bearer → loja) →
  `[{id, telefone_cliente, vendedor_id, vendedor_nome, estado, prazo_em, criado_em}]`.
  Sem `estado`, devolve as **não encerradas** (`aberta` + `esgotada`), que é o que a Loja desenha.

O `vendedor_nome` vem junto de propósito: sem ele o Portal teria que buscar a fila a cada render
só para escrever "oferecido a Ana".

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_ofertas_rotas.py
import pytest

from app.models_db import FilaVendedor, LojaOperacionalProjecao
from app.rodizio import abrir_oferta


@pytest.fixture(autouse=True)
def _modo2_on(db, loja_a, monkeypatch):
    monkeypatch.setattr("app.rodizio.config.MODO2_ENABLED", True)
    db.add(LojaOperacionalProjecao(
        loja_id=loja_a["loja_id"], aggregate="whatsapp_modo", version=1,
        state="2", event_id=f"e-{loja_a['loja_id'][:8]}",
    ))
    db.commit()


def _fila(db, loja_id):
    db.add(FilaVendedor(
        id=f"{loja_id[:8]}-f0", loja_id=loja_id, nome="Ana",
        telefone="5511999990000", ordem=0, ativo=True,
    ))
    db.commit()


def test_lista_oferta_aberta_com_nome_do_vendedor(client, db, loja_a):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    corpo = client.get("/v1/ofertas", headers=loja_a["headers"]).json()

    assert [o["id"] for o in corpo] == [oferta.id]
    assert corpo[0]["vendedor_nome"] == "Ana"
    assert corpo[0]["estado"] == "aberta"


def test_filtra_por_estado(client, db, loja_a):
    _fila(db, loja_a["loja_id"])
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    assert client.get(
        "/v1/ofertas", params={"estado": "travada"}, headers=loja_a["headers"]
    ).json() == []


def test_loja_so_ve_as_proprias_ofertas(client, db, loja_a, loja_b):
    _fila(db, loja_a["loja_id"])
    abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    assert client.get("/v1/ofertas", headers=loja_b["headers"]).json() == []


def test_sem_credencial_e_401(client):
    assert client.get("/v1/ofertas").status_code == 401
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_ofertas_rotas.py -q`
Esperado: 404 na rota.

- [ ] **Step 3: Implementar**

```python
ESTADOS_NAO_ENCERRADOS = ("aberta", "esgotada")


@app.get("/v1/ofertas")
def listar_ofertas(
    estado: str | None = None,
    ctx=Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Estado do rodízio para a Loja desenhar (spec §5.8).

    Sem ``estado``, devolve o que ainda pede ação — aberta e esgotada. Travada
    não entra por padrão: quem travou já está no workspace de Atendimento.
    """
    consulta = (
        db.query(OfertaLead, FilaVendedor)
        .join(FilaVendedor, FilaVendedor.id == OfertaLead.vendedor_id)
        .filter(OfertaLead.loja_id == ctx.loja_id)
    )
    if estado:
        consulta = consulta.filter(OfertaLead.estado == estado)
    else:
        consulta = consulta.filter(OfertaLead.estado.in_(ESTADOS_NAO_ENCERRADOS))
    return [
        {
            "id": oferta.id,
            "telefone_cliente": oferta.telefone_cliente,
            "vendedor_id": oferta.vendedor_id,
            "vendedor_nome": vendedor.nome,
            "estado": oferta.estado,
            "prazo_em": oferta.prazo_em.isoformat() if oferta.prazo_em else None,
            "criado_em": oferta.criado_em.isoformat() if oferta.criado_em else None,
        }
        for oferta, vendedor in consulta.all()
    ]
```

- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(chatbot): expor estado das ofertas para a Loja`

---

### Task 2: `POST /v1/ofertas/{id}/assumir` — o Portal trava e recebe o contato

**Files:**
- Modify: `chatbot-api/app/main.py`
- Test: `chatbot-api/tests/test_ofertas_rotas.py` (acrescentar)

**Interfaces:**
- Produces: `POST /v1/ofertas/{oferta_id}/assumir` → `200 {"ganhou": bool, "telefone_cliente": str}`.
  `ganhou=false` = já foi pego; nesse caso **`telefone_cliente` vem vazio**.

O telefone só volta para quem ganhou — é a mesma regra do §5.7 aplicada ao sino: quem perdeu o
clique não recebe o contato.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em chatbot-api/tests/test_ofertas_rotas.py
def test_assumir_devolve_o_contato_para_quem_ganhou(client, db, loja_a):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    corpo = client.post(
        f"/v1/ofertas/{oferta.id}/assumir", headers=loja_a["headers"]
    ).json()

    assert corpo["ganhou"] is True
    assert corpo["telefone_cliente"] == "5511988887777"


def test_assumir_duas_vezes_nao_devolve_contato_na_segunda(client, db, loja_a):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")
    client.post(f"/v1/ofertas/{oferta.id}/assumir", headers=loja_a["headers"])

    corpo = client.post(
        f"/v1/ofertas/{oferta.id}/assumir", headers=loja_a["headers"]
    ).json()

    assert corpo["ganhou"] is False
    assert corpo["telefone_cliente"] == ""


def test_assumir_oferta_de_outra_loja_e_404(client, db, loja_a, loja_b):
    _fila(db, loja_a["loja_id"])
    oferta = abrir_oferta(db, loja_a["loja_id"], "5511988887777")

    assert client.post(
        f"/v1/ofertas/{oferta.id}/assumir", headers=loja_b["headers"]
    ).status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar** — 404 na rota.
- [ ] **Step 3: Implementar**, reusando `rodizio.assumir_oferta` (idempotente, primeiro vence):

```python
@app.post("/v1/ofertas/{oferta_id}/assumir")
def assumir_oferta_http(
    oferta_id: str,
    ctx=Depends(get_contexto),
    db: Session = Depends(get_db),
):
    """Peguei pelo sino da Loja — mesmo assumir do clique no WhatsApp (§5.7)."""
    oferta = db.get(OfertaLead, oferta_id)
    if oferta is None or oferta.loja_id != ctx.loja_id:
        raise HTTPException(status_code=404, detail="oferta não encontrada")

    ganhou, travada = rodizio.assumir_oferta(db, oferta_id)
    # Contato só para quem ganhou: quem perdeu o clique não fala com o cliente.
    return {
        "ganhou": ganhou,
        "telefone_cliente": travada.telefone_cliente if ganhou else "",
    }
```

- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5:** `cd chatbot-api && .venv/bin/python -m pytest -q` — suíte inteira verde.
- [ ] **Step 6: Commit** — `feat(chatbot): assumir oferta pelo Portal`

---

### Task 3: `ChatbotClient` fala das ofertas

**Files:**
- Modify: `portal-gestao/app/clients/chatbot.py`
- Test: `portal-gestao/tests/test_chatbot_client_ofertas.py`

**Interfaces:**
- Produces: `ChatbotClient.listar_ofertas(estado: str | None = None) -> list[dict]` e
  `ChatbotClient.assumir_oferta(oferta_id: str) -> dict`.

- [ ] **Step 1: Escrever o teste que falha** — espelhe o padrão de
      `tests/test_estoque_client_foto.py` (subclasse com `MockTransport`), verificando a URL, o
      query param `estado` e o corpo devolvido.
- [ ] **Step 2: Rodar e ver falhar** — `AttributeError: 'ChatbotClient' object has no attribute 'listar_ofertas'`.
- [ ] **Step 3: Implementar** com `self._request`, ao lado de `listar_canais_whatsapp`.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(portal): cliente das ofertas do rodizio`

---

### Task 4: O produtor do sinal, dentro do worker que já existe

**Files:**
- Modify: `portal-gestao/app/copiloto_sinais_job.py`
- Test: `portal-gestao/tests/test_sinal_oferta_sync.py`

**Interfaces:**
- Produces: `sincronizar_ofertas(db, loja_slug, chatbot) -> dict[str, int]` →
  `{"criados": n, "transferidos": n, "resolvidos": n}`, chamado de `run_once` ao lado da avaliação
  do Copiloto.

**Por que aqui e não num worker novo:** o plano B1, Task 4, fez o `copiloto_sinais_job` rodar
mesmo com a flag do Copiloto desligada, e a Task 1 dele criou `regras_elegiveis` como gancho para
tipos novos. Era exatamente para este momento. Criar um daemon novo duplicaria ciclo de vida,
gate e tratamento de erro.

A reconciliação é **idempotente por `entidade_ref`** (o id da oferta): rodar duas vezes não cria
sinal duplicado.

- [ ] **Step 1: Escrever o teste que falha**

```python
# portal-gestao/tests/test_sinal_oferta_sync.py
from app.copiloto_sinais_job import sincronizar_ofertas
from app.loja.copiloto.sinais_store import contar_sinais_novos


class _ChatbotFake:
    def __init__(self, ofertas):
        self._ofertas = ofertas

    def listar_ofertas(self, estado=None):
        return self._ofertas


def test_oferta_aberta_vira_sinal_so_do_vendedor(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])

    assert sincronizar_ofertas(db, "loja-a", chatbot)["criados"] == 1
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1
    assert contar_sinais_novos(db, "loja-a", "u-dono") == 0


def test_rodar_duas_vezes_nao_duplica(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    assert sincronizar_ofertas(db, "loja-a", chatbot)["criados"] == 0
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 1


def test_rodizio_avancou_transfere_o_sinal(db):
    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    chatbot._ofertas[0]["vendedor_id"] = "u-v2"
    chatbot._ofertas[0]["vendedor_nome"] = "Bruno"

    assert sincronizar_ofertas(db, "loja-a", chatbot)["transferidos"] == 1
    assert contar_sinais_novos(db, "loja-a", "u-v1") == 0
    assert contar_sinais_novos(db, "loja-a", "u-v2") == 1


def test_sinal_nunca_guarda_telefone_do_cliente(db):
    """Disciplina do model: sinal de lead é agregado, telefone não entra."""
    from app.models import CopilotoSinal

    chatbot = _ChatbotFake([{
        "id": "of-1", "vendedor_id": "u-v1", "vendedor_nome": "Ana",
        "telefone_cliente": "5511988887777", "estado": "aberta",
    }])
    sincronizar_ofertas(db, "loja-a", chatbot)

    sinal = db.query(CopilotoSinal).filter(CopilotoSinal.entidade_ref == "of-1").one()
    conteudo = f"{sinal.titulo}{sinal.detalhe}{sinal.dados_json or ''}"
    assert "5511988887777" not in conteudo
```

- [ ] **Step 2: Rodar e ver falhar** — `ImportError: cannot import name 'sincronizar_ofertas'`.
- [ ] **Step 3: Implementar.** Para cada oferta `aberta`: se não há sinal aberto com aquele
      `entidade_ref`, `criar_sinal_direcionado` com `regra="oferta_lead"`; se há, mas para outro
      destinatário, `transferir_sinal`. Oferta que sumiu da lista (travou) → resolver o sinal.
      Chamar de `run_once` **só para loja em Modo 2** — reuse o gate que a listagem de ofertas já
      implica (loja Modo 1 devolve lista vazia, então o sync vira no-op naturalmente).
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(portal): sincronizar ofertas do rodizio com o sino`

---

### Task 5: A rota do botão Peguei

**Files:**
- Modify: `portal-gestao/app/web/loja_copiloto.py`
- Test: `portal-gestao/tests/test_sino_peguei_rota.py`

**Interfaces:**
- Produces: `POST /app/loja/copiloto/notificacoes/{sinal_id}/peguei` →
  `{"ganhou": bool, "mensagem": str}`.

Fluxo: valida que o sinal é **do usuário logado** (`destinatario_usuario_id`), chama
`chatbot.assumir_oferta(entidade_ref)`, e **se ganhou** usa o telefone devolvido para o
`registrar_handoff_local` que já existe (`app/main.py:1255`). O telefone **transita** e não é
gravado no sinal.

- [ ] **Step 1: Escrever o teste que falha**, cobrindo: ganhou → handoff registrado e sinal
      resolvido; perdeu → mensagem "já foi pego" e nenhum handoff; **sinal de outra pessoa → 403**.
- [ ] **Step 2: Rodar e ver falhar** — 404 na rota.
- [ ] **Step 3: Implementar.** O 403 do sinal alheio não é detalhe: sem ele, qualquer pessoa com
      o `sinal_id` assumiria a oferta de outro vendedor.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(portal): rota do botao Peguei no sino`

---

### Task 6: O botão no painel do sino

**Files:**
- Modify: `portal-gestao/app/web/loja_copiloto.py` (`notificacoes.json`)
- Modify: o template/JS do painel do sino
- Test: `portal-gestao/tests/test_sino_peguei_rota.py` (acrescentar)

**Interfaces:**
- `notificacoes.json` passa a devolver `pode_pegar: bool` por item — `true` só quando
  `regra == "oferta_lead"` e o sinal é do usuário logado.

- [ ] **Step 1: Teste** — item de oferta do próprio usuário vem com `pode_pegar: true`; sinal do
      Copiloto vem `false`.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**, e no painel renderizar o botão **Peguei** só quando `pode_pegar`.
      Usar as classes existentes (`.button.primary`) — sem CSS novo, e sem editar
      `revy-tokens.css`, que é cópia gerada.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(portal): botao Peguei no painel do sino`

---

### Task 7: Faixa "N sem vendedor" e filtro Aguardando no Atendimento

**Files:**
- Modify: `portal-gestao/app/loja/routes.py` (`atendimento_lista:164`)
- Modify: `portal-gestao/app/templates/loja/` (lista de atendimento)
- Test: `portal-gestao/tests/test_atendimento_faixa_aguardando.py`

**Interfaces:**
- A rota já aceita `estado`. Entra o valor sintético **`aguardando_vendedor`**, alimentado por
  `chatbot.listar_ofertas(estado="esgotada")` — não é um `AttendanceState` novo, porque não é
  estado da conversa e sim da fila.
- Contexto novo: `sem_vendedor_total: int`. A faixa aparece com `> 0` e **só para dono/gerente**.

- [ ] **Step 1: Escrever o teste que falha**, cobrindo: dono vê a faixa com a contagem certa;
      **vendedor não vê a faixa**; clique aplica `estado=aguardando_vendedor`; loja em Modo 1 não
      mostra faixa nenhuma; e chatbot fora do ar **não derruba a página** (a faixa some, o resto
      renderiza — o mesmo tratamento que `erro_integracao` já dá).
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar**, reusando `pode_usar_atendimento` e o papel para o gate de
      dono/gerente. A contagem é "em aberto agora", sem recorte de data — some quando alguém assume.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(portal): faixa e filtro de lead sem vendedor`

---

### Task 8: Card de 7 dias no Agente

**Files:**
- Modify: `portal-gestao/app/loja/routes.py` (`/app/loja/agente:273`)
- Modify: o template do Agente
- Test: `portal-gestao/tests/test_agente_card_rodizio.py`

**Interfaces:**
- Card com quatro números dos **últimos 7 dias corridos**, com as definições da spec §5.4:
  **atendidos** (travados), **oferecidos** (oferta viva agora), **aguardando** (`esgotou_fila` sem
  dono), **perdidos** (morreu sem atendimento humano).

- [ ] **Step 1: Escrever o teste que falha**, incluindo um caso que prova que **aguardando ≠
      perdidos** — é a confusão que a própria spec teve que desfazer.
- [ ] **Step 2: Rodar e ver falhar**
- [ ] **Step 3: Implementar.** O card **não** substitui a barra agente × handoff do mês; é o
      recorte da fila, ao lado. Só aparece em loja Modo 2.
- [ ] **Step 4: Rodar e ver passar**
- [ ] **Step 5: Commit** — `feat(portal): card de 7 dias do rodizio no Agente`

---

### Task 9: Regressão — o Modo 1 não mudou

- [ ] **Step 1:** `cd portal-gestao && .venv/bin/python -m pytest -q` → tudo verde.
- [ ] **Step 2:** `cd chatbot-api && .venv/bin/python -m pytest -q` → tudo verde.
- [ ] **Step 3:** Conferir à mão, com uma loja **Modo 1** no contexto: sem faixa no Atendimento,
      sem card no Agente, sem sinal `oferta_lead` no sino. Se algum aparecer, o gate vazou.
- [ ] **Step 4:** `git diff --check` e `git status --short`.

---

## Self-Review

- §2 "canal do aviso é WhatsApp **e** sino": Tasks 4–6. **Coberto.**
- §5.7 Peguei no sino = mesmo assumir, primeiro clique vence: Tasks 2 e 5, reusando
  `assumir_oferta`, que já é idempotente. **Coberto.**
- §5.7 dono/gerente não veem a oferta: o filtro por destinatário já existe (plano `wa-modo2-1`);
  a Task 5 acrescenta o 403 na ação. **Coberto.**
- §5.4 faixa + filtro Aguardando, contagem em aberto agora: Task 7. **Coberto.**
- §5.4 card de 7 dias com as quatro definições: Task 8. **Coberto.**
- §5.3 sino muda de dono quando o rodízio avança: Task 4 (`transferir_sinal`). **Coberto.**
- **Fora deste card:** o pacote pós-clique completo com CPF (depende do intake montado) e o VAD
  antes da transcrição — os dois seguem declarados nos planos executados.
