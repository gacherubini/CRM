# Modo 2 / Card 3 — Webhook da Meta e `n8n-cloud` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Receber o inbound da Meta com segurança: assinatura conferida, verificação de domínio
respondida, reentrega deduplicada, e o payload da Cloud API traduzido para o modelo normalizado que
o `chatbot-api` já entende.

**Architecture:** o `n8n-cloud` é **transporte fino**: recebe o webhook público, encaminha o corpo
**cru** e o header de assinatura ao `chatbot-api`, e devolve o que o chatbot mandar responder. Toda
a decisão — assinatura, verify token, dedup, parse — é Python testável. Nenhum segredo da Meta entra
no JSON do workflow.

**Tech Stack:** FastAPI, `hmac`/`hashlib` da stdlib, SQLAlchemy, pytest. n8n: dois nós Webhook
(GET e POST) com `rawBody`.

**Spec:** [`../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`](../referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md) — §6.1 (verificação, assinatura, reentrega), §6.2 (credenciais), §5.6 (CTWA), §5.10 (mídia).

## Pré-requisito

**Cards 2 e 2b** feitos: este card chama `disparar_handoff`, `processar_clique` e o processador de
áudio, e não os reimplementa.

## Decisão tomada com o dono (2026-08-13)

**A assinatura é validada no `chatbot-api`, não no n8n.** O n8n encaminha corpo cru + header.
Motivos: o App Secret nunca entra no n8n; a validação vira teste de pytest com vetores fixos; e não
depende de `NODE_FUNCTION_ALLOW_BUILTIN` incluir `crypto` no container do n8n2037 — o que não dá
para confirmar sem abrir o container, já que nenhum nó do workflow atual usa `require()`.

Requisição forjada chega a atravessar o n8n antes de morrer — aceito: ela morre no chatbot, que
também exige o `X-Webhook-Token` que já existe.

## Consequência: o `n8n-cloud` ficou fino, e isso é de propósito

A §6 da spec dizia "inbound **e outbound** pelo `n8n-cloud`". O outbound já foi para o
`CloudWhatsAppOutbound` no card 2b — o chatbot fala com a Graph API direto, porque é ele que decide
envelope, template e conteúdo. Com a assinatura também no chatbot, sobra para o `n8n-cloud`:
responder a Meta rápido e encaminhar.

**Por que manter o n8n no caminho, então:** ele é a **superfície pública**. O `chatbot-api` não
precisa ficar exposto na internet para a Meta alcançar, e o n8n já é o que está exposto e tem TLS.
Trocar isso é decisão de deploy, não deste card.

## Global Constraints

- **Nenhum segredo no JSON do workflow.** O repo usa placeholders (`__CHATBOT_WEBHOOK_TOKEN__`) e
  `n8n/update_live_workflow.js` substitui na publicação. App Secret e verify token da Meta **não**
  entram nem como placeholder: moram no `chatbot-api`.
- **`n8n-baileys` intacto.** `workflow-ai-nao-salvos.json` não é tocado. Sem `if` de modo.
- **Responder 200 rápido.** A Meta reentrega se demorar. Processar depois de responder.
- **Dedup por `wamid`.** O replay >5 min do Modo 1 não cobre reentrega em segundos.
- **Ativar workflow é só pelo "Publish" na UI.** `active=1` no banco **não** registra o webhook.
- Rodar testes **a partir de `chatbot-api/`**. O dono usa **Mac e Windows**: macOS
  `.venv/bin/python -m pytest -q`; Windows `.\.venv\Scripts\python.exe -m pytest -q`.
  O validador do n8n roda **da raiz**: `python n8n/validate_workflow_cloud.py`.

---

### Task 1: `assinatura_valida` — HMAC sobre o corpo cru

**Files:**
- Create: `chatbot-api/app/meta_webhook.py`
- Modify: `chatbot-api/app/config.py`
- Test: `chatbot-api/tests/test_meta_assinatura.py`

**Interfaces:**
- Produces: `assinatura_valida(corpo_cru: bytes, header: str, *, app_secret: str) -> bool`.

O erro que mata essa integração: calcular o HMAC sobre o JSON **re-serializado**. Ordem de chave e
escape de unicode mudam, e a assinatura nunca bate. Por isso a função recebe `bytes`, não `dict` —
o tipo impede o erro.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_meta_assinatura.py
import hashlib
import hmac
import json

from app.meta_webhook import assinatura_valida

SEGREDO = "app-secret-de-teste"
CORPO = b'{"entry":[{"id":"1","changes":[]}],"object":"whatsapp_business_account"}'


def _assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


def test_assinatura_correta_passa():
    assert assinatura_valida(CORPO, _assinar(CORPO), app_secret=SEGREDO) is True


def test_corpo_alterado_reprova():
    assert assinatura_valida(CORPO + b" ", _assinar(CORPO), app_secret=SEGREDO) is False


def test_segredo_errado_reprova():
    assert assinatura_valida(CORPO, _assinar(CORPO, "outro"), app_secret=SEGREDO) is False


def test_header_ausente_ou_torto_reprova():
    assert assinatura_valida(CORPO, "", app_secret=SEGREDO) is False
    assert assinatura_valida(CORPO, "abc123", app_secret=SEGREDO) is False
    assert assinatura_valida(CORPO, "sha1=abc", app_secret=SEGREDO) is False


def test_reserializar_o_json_quebra_a_assinatura():
    """Documenta a armadilha: reserializar muda os bytes e invalida o HMAC."""
    reserializado = json.dumps(json.loads(CORPO)).encode()
    assert reserializado != CORPO
    assert assinatura_valida(reserializado, _assinar(CORPO), app_secret=SEGREDO) is False


def test_sem_app_secret_configurado_reprova():
    """Fail-closed: sem segredo, não valida nada — não libera tudo."""
    assert assinatura_valida(CORPO, _assinar(CORPO), app_secret="") is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_meta_assinatura.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_meta_assinatura.py -q`
Esperado: `ModuleNotFoundError: No module named 'app.meta_webhook'`.

- [ ] **Step 3: Implementar**

Em `app/config.py`:

```python
# Webhook da Meta (Modo 2). App Secret assina o corpo; verify token fecha o GET.
META_APP_SECRET = os.getenv("CHATBOT_META_APP_SECRET", "")
META_VERIFY_TOKEN = os.getenv("CHATBOT_META_VERIFY_TOKEN", "")
```

```python
# chatbot-api/app/meta_webhook.py
"""Entrada do webhook da Cloud API (spec §6.1)."""
from __future__ import annotations

import hashlib
import hmac

_PREFIXO = "sha256="


def assinatura_valida(corpo_cru: bytes, header: str, *, app_secret: str) -> bool:
    """Confere ``X-Hub-Signature-256`` sobre o corpo **cru**.

    Recebe ``bytes`` de propósito: calcular o HMAC sobre o JSON re-serializado
    é o erro clássico dessa integração — ordem de chave e escape de unicode
    mudam os bytes e a assinatura nunca bate. O tipo impede o erro.

    Fail-closed: sem ``app_secret`` configurado, nada passa.
    """
    if not app_secret or not header.startswith(_PREFIXO):
        return False
    recebida = header[len(_PREFIXO):].strip()
    esperada = hmac.new(app_secret.encode("utf-8"), corpo_cru, hashlib.sha256).hexdigest()
    return hmac.compare_digest(recebida, esperada)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_meta_assinatura.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_meta_assinatura.py -q`
Esperado: PASS nos 6 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/meta_webhook.py chatbot-api/app/config.py chatbot-api/tests/test_meta_assinatura.py
git commit -m "feat(chatbot): validacao da assinatura do webhook da Meta"
```

---

### Task 2: Parse do inbound da Cloud API

**Files:**
- Modify: `chatbot-api/app/meta_webhook.py`
- Test: `chatbot-api/tests/test_meta_parse.py`

**Interfaces:**
- Produces: `parse_inbound(payload: dict) -> list[EventoCloud]`, com
  `EventoCloud` = dataclass `(phone_number_id, tipo, remetente, wamid, texto, media_id, mime, oferta_id, referral_ad_id, status)`.
- `tipo ∈ {"texto", "audio", "imagem", "clique", "status", "ignorado"}`.

Um POST da Meta pode trazer **vários** eventos (`entry[].changes[].value.messages[]`), e também
`statuses[]` — que não é mensagem e não pode virar lead.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_meta_parse.py
from app.meta_webhook import parse_inbound


def _envelope(value: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": value}]}],
    }


def test_texto_simples():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111", "display_phone_number": "5511..."},
        "messages": [{
            "from": "5511988887777", "id": "wamid.A", "type": "text",
            "text": {"body": "quero uma biz"},
        }],
    }))
    assert len(eventos) == 1
    e = eventos[0]
    assert (e.tipo, e.phone_number_id, e.remetente, e.wamid) == (
        "texto", "111", "5511988887777", "wamid.A"
    )
    assert e.texto == "quero uma biz"


def test_audio_traz_media_id_e_nao_binario():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511988887777", "id": "wamid.B", "type": "audio",
            "audio": {"id": "media-9", "mime_type": "audio/ogg; codecs=opus"},
        }],
    }))
    assert eventos[0].tipo == "audio"
    assert eventos[0].media_id == "media-9"
    assert eventos[0].mime == "audio/ogg"


def test_clique_de_template_vira_clique_com_oferta():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511999990000", "id": "wamid.C", "type": "button",
            "button": {"payload": "pego:of-7", "text": "Peguei"},
        }],
    }))
    assert eventos[0].tipo == "clique"
    assert eventos[0].oferta_id == "of-7"


def test_clique_de_interativa_vira_clique_com_oferta():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511999990000", "id": "wamid.D", "type": "interactive",
            "interactive": {"type": "button_reply",
                            "button_reply": {"id": "pego:of-8", "title": "Peguei"}},
        }],
    }))
    assert eventos[0].tipo == "clique"
    assert eventos[0].oferta_id == "of-8"


def test_referral_de_anuncio_e_extraido():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{
            "from": "5511988887777", "id": "wamid.E", "type": "text",
            "text": {"body": "vi o anuncio"},
            "referral": {"source_id": "ad-123", "source_type": "ad"},
        }],
    }))
    assert eventos[0].referral_ad_id == "ad-123"


def test_status_nao_vira_mensagem():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "statuses": [{"id": "wamid.F", "status": "failed", "recipient_id": "5511988887777"}],
    }))
    assert len(eventos) == 1
    assert eventos[0].tipo == "status"
    assert eventos[0].status == "failed"


def test_varios_eventos_no_mesmo_post():
    eventos = parse_inbound({
        "object": "whatsapp_business_account",
        "entry": [{"id": "w", "changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "111"},
            "messages": [
                {"from": "1", "id": "wamid.G", "type": "text", "text": {"body": "a"}},
                {"from": "2", "id": "wamid.H", "type": "text", "text": {"body": "b"}},
            ],
        }}]}],
    })
    assert [e.wamid for e in eventos] == ["wamid.G", "wamid.H"]


def test_tipo_desconhecido_vira_ignorado_sem_estourar():
    eventos = parse_inbound(_envelope({
        "metadata": {"phone_number_id": "111"},
        "messages": [{"from": "1", "id": "wamid.I", "type": "sticker", "sticker": {}}],
    }))
    assert eventos[0].tipo == "ignorado"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_meta_parse.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_meta_parse.py -q`
Esperado: `ImportError: cannot import name 'parse_inbound'`.

- [ ] **Step 3: Implementar**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EventoCloud:
    phone_number_id: str
    tipo: str  # texto | audio | imagem | clique | status | ignorado
    remetente: str = ""
    wamid: str = ""
    texto: str | None = None
    media_id: str | None = None
    mime: str | None = None
    oferta_id: str | None = None
    referral_ad_id: str | None = None
    status: str | None = None


def _oferta_do_clique(mensagem: dict) -> str | None:
    bruto = str(
        (mensagem.get("button") or {}).get("payload")
        or ((mensagem.get("interactive") or {}).get("button_reply") or {}).get("id")
        or ""
    )
    return bruto[len("pego:"):] or None if bruto.startswith("pego:") else None


def parse_inbound(payload: dict) -> list[EventoCloud]:
    """Traduz o envelope da Cloud API para eventos.

    Um POST pode trazer vários eventos, e ``statuses`` (entregue/lido/falhou)
    vem no mesmo lugar que ``messages`` — tratar status como mensagem criaria
    lead fantasma a cada confirmação de entrega.
    """
    eventos: list[EventoCloud] = []
    for entrada in payload.get("entry") or []:
        for mudanca in entrada.get("changes") or []:
            valor = mudanca.get("value") or {}
            phone_number_id = str((valor.get("metadata") or {}).get("phone_number_id") or "")

            for status in valor.get("statuses") or []:
                eventos.append(EventoCloud(
                    phone_number_id=phone_number_id,
                    tipo="status",
                    remetente=str(status.get("recipient_id") or ""),
                    wamid=str(status.get("id") or ""),
                    status=str(status.get("status") or ""),
                ))

            for mensagem in valor.get("messages") or []:
                tipo_meta = str(mensagem.get("type") or "")
                comum = {
                    "phone_number_id": phone_number_id,
                    "remetente": str(mensagem.get("from") or ""),
                    "wamid": str(mensagem.get("id") or ""),
                    "referral_ad_id": (
                        str((mensagem.get("referral") or {}).get("source_id"))
                        if (mensagem.get("referral") or {}).get("source_id")
                        else None
                    ),
                }
                if tipo_meta == "text":
                    eventos.append(EventoCloud(
                        tipo="texto", texto=(mensagem.get("text") or {}).get("body"), **comum
                    ))
                elif tipo_meta in ("audio", "voice"):
                    midia = mensagem.get(tipo_meta) or {}
                    eventos.append(EventoCloud(
                        tipo="audio",
                        media_id=str(midia.get("id") or "") or None,
                        mime=str(midia.get("mime_type") or "").split(";", 1)[0].strip() or None,
                        **comum,
                    ))
                elif tipo_meta == "image":
                    midia = mensagem.get("image") or {}
                    eventos.append(EventoCloud(
                        tipo="imagem",
                        media_id=str(midia.get("id") or "") or None,
                        mime=str(midia.get("mime_type") or "").split(";", 1)[0].strip() or None,
                        **comum,
                    ))
                elif tipo_meta in ("button", "interactive"):
                    eventos.append(EventoCloud(
                        tipo="clique", oferta_id=_oferta_do_clique(mensagem), **comum
                    ))
                else:
                    eventos.append(EventoCloud(tipo="ignorado", **comum))
    return eventos
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_meta_parse.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_meta_parse.py -q`
Esperado: PASS nos 8 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/meta_webhook.py chatbot-api/tests/test_meta_parse.py
git commit -m "feat(chatbot): parse do inbound da Cloud API"
```

---

### Task 3: Rotas `/webhook/cloud` — GET de verificação e POST assinado

**Files:**
- Modify: `chatbot-api/app/main.py`
- Test: `chatbot-api/tests/test_webhook_cloud_rotas.py`

**Interfaces:**
- Produces:
  - `GET /webhook/cloud` — responde `hub.challenge` **em texto puro** quando
    `hub.verify_token` bate; 403 quando não bate.
  - `POST /webhook/cloud` — 401 se a assinatura não bate; **200 sempre** quando bate, mesmo se o
    processamento falhar, para a Meta não reentregar em loop.

- [ ] **Step 1: Escrever o teste que falha**

```python
# chatbot-api/tests/test_webhook_cloud_rotas.py
import hashlib
import hmac

SEGREDO = "app-secret-de-teste"
VERIFY = "verify-de-teste"


def _assinar(corpo: bytes) -> dict:
    mac = hmac.new(SEGREDO.encode(), corpo, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={mac}", "Content-Type": "application/json"}


def test_get_devolve_o_challenge_em_texto_puro(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_VERIFY_TOKEN", VERIFY)
    resposta = client.get("/webhook/cloud", params={
        "hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345",
    })
    assert resposta.status_code == 200
    # Texto puro: a Meta compara o corpo inteiro. Aspas de JSON reprovam.
    assert resposta.text == "12345"


def test_get_com_token_errado_e_403(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_VERIFY_TOKEN", VERIFY)
    resposta = client.get("/webhook/cloud", params={
        "hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "12345",
    })
    assert resposta.status_code == 403


def test_post_sem_assinatura_e_401(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    assert client.post("/webhook/cloud", content=b"{}").status_code == 401


def test_post_com_assinatura_valida_e_200(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    corpo = b'{"object":"whatsapp_business_account","entry":[]}'
    resposta = client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))
    assert resposta.status_code == 200


def test_numero_desconhecido_nao_estoura_e_responde_200(client, monkeypatch):
    """Meta reentrega em erro. Número que não é de loja nenhuma: descarta e loga."""
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    corpo = (
        b'{"object":"whatsapp_business_account","entry":[{"id":"w","changes":'
        b'[{"field":"messages","value":{"metadata":{"phone_number_id":"nao-existe"},'
        b'"messages":[{"from":"1","id":"wamid.X","type":"text","text":{"body":"oi"}}]}}]}]}'
    )
    resposta = client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))
    assert resposta.status_code == 200


def test_reentrega_do_mesmo_wamid_nao_processa_duas_vezes(client, monkeypatch):
    monkeypatch.setattr("app.main.config.META_APP_SECRET", SEGREDO)
    processados = []
    monkeypatch.setattr("app.main.processar_evento_cloud", lambda *a, **k: processados.append(1))

    corpo = (
        b'{"object":"whatsapp_business_account","entry":[{"id":"w","changes":'
        b'[{"field":"messages","value":{"metadata":{"phone_number_id":"111"},'
        b'"messages":[{"from":"1","id":"wamid.DUP","type":"text","text":{"body":"oi"}}]}}]}]}'
    )
    client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))
    client.post("/webhook/cloud", content=corpo, headers=_assinar(corpo))

    assert len(processados) == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_webhook_cloud_rotas.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_webhook_cloud_rotas.py -q`
Esperado: 404 nas rotas.

- [ ] **Step 3: Implementar**

Em `app/main.py`:

```python
from fastapi.responses import PlainTextResponse

from app.meta_webhook import assinatura_valida, parse_inbound


@app.get("/webhook/cloud", response_class=PlainTextResponse)
def webhook_cloud_verificacao(request: Request):
    """Handshake de domínio da Meta (spec §6.1).

    Responde o challenge em **texto puro**: a Meta compara o corpo inteiro, e
    as aspas que o JSON acrescentaria reprovam a verificação.
    """
    parametros = request.query_params
    if parametros.get("hub.mode") != "subscribe":
        raise HTTPException(status_code=403, detail="modo inválido")
    if not config.META_VERIFY_TOKEN or not secrets.compare_digest(
        parametros.get("hub.verify_token", ""), config.META_VERIFY_TOKEN
    ):
        raise HTTPException(status_code=403, detail="verify token inválido")
    return parametros.get("hub.challenge", "")


@app.post("/webhook/cloud")
async def webhook_cloud(request: Request, db: Session = Depends(get_db)):
    """Inbound da Cloud API. Responde 200 rápido; a Meta reentrega se demorar."""
    corpo_cru = await request.body()
    if not assinatura_valida(
        corpo_cru,
        request.headers.get("X-Hub-Signature-256", ""),
        app_secret=config.META_APP_SECRET,
    ):
        raise HTTPException(status_code=401, detail="assinatura inválida")

    try:
        payload = json.loads(corpo_cru)
    except ValueError:
        # Assinatura bate mas o corpo não é JSON: não é reentrega útil.
        return {"ok": True, "ignorado": "corpo inválido"}

    for evento in parse_inbound(payload):
        if evento.wamid and _wamid_ja_visto(db, evento.wamid):
            continue
        try:
            processar_evento_cloud(db, evento)
        except Exception:  # noqa: BLE001
            # Erro nosso não pode virar reentrega infinita da Meta.
            logger.exception("falha ao processar evento cloud wamid=%s", evento.wamid)
    return {"ok": True}
```

E a dedup, ao lado das outras funções de `main.py`:

```python
def _wamid_ja_visto(db: Session, wamid: str) -> bool:
    """Dedup de reentrega (spec §6.1).

    O replay >5 min do Modo 1 não cobre isto: a Meta reentrega em segundos
    quando não recebe 200 rápido, e o mesmo ``wamid`` chegaria duas vezes
    dentro da janela.
    """
    existe = (
        db.query(Mensagem.id)
        .filter(Mensagem.provider_message_id == wamid)
        .first()
        is not None
    )
    return existe
```

> `processar_evento_cloud(db, evento)` é o despacho por `evento.tipo`: `texto` segue o fluxo do bot,
> `audio`/`imagem` chamam o processador do card 2b Task 1–2, `clique` chama `processar_clique`
> (card 2b Task 5), `status` só loga o `failed`, `ignorado` não faz nada. Escreva-o como função
> nova em `main.py` chamando o que os cards 2 e 2b já entregaram — não reimplemente nada.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd chatbot-api && .venv/bin/python -m pytest tests/test_webhook_cloud_rotas.py -q`
— Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest tests/test_webhook_cloud_rotas.py -q`
Esperado: PASS nos 6 testes.

- [ ] **Step 5: Commit**

```bash
git add chatbot-api/app/main.py chatbot-api/tests/test_webhook_cloud_rotas.py
git commit -m "feat(chatbot): rotas do webhook da Cloud API"
```

---

### Task 4: Workflow `n8n-cloud` — transporte fino

**Files:**
- Create: `n8n/workflow-cloud.json`
- Test: manual, via `curl` (o validador é a Task 5)

**Interfaces:**
- Dois nós Webhook no mesmo path `whatsapp-cloud`:
  - **GET** → `responseMode: lastNode`, encaminha os `hub.*` ao chatbot e devolve o challenge.
  - **POST** → `options.rawBody: true`, `responseMode: onReceived` (200 imediato), encaminha corpo
    cru + `X-Hub-Signature-256`.
- Um nó HTTP Request por caminho, apontando para `http://chatbot-api:8000/webhook/cloud`.

**Por que dois nós:** o nó Webhook do n8n aceita **um** `httpMethod`. GET e POST precisam de nós
separados — e ainda bem, porque os dois têm `responseMode` diferente: o GET precisa devolver o
challenge (`lastNode`), o POST precisa responder na hora (`onReceived`).

**Por que `rawBody`:** sem isso o n8n faz `JSON.parse` e o corpo re-serializado invalida a
assinatura (a Task 1 tem um teste que documenta exatamente esse fracasso).

- [ ] **Step 1: Criar o workflow**

```json
{
  "name": "whatsapp-cloud",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "GET",
        "path": "whatsapp-cloud",
        "responseMode": "lastNode",
        "options": {}
      },
      "id": "webhook-get",
      "name": "Meta verificacao",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 0],
      "webhookId": "whatsapp-cloud"
    },
    {
      "parameters": {
        "method": "GET",
        "url": "http://chatbot-api:8000/webhook/cloud",
        "sendQuery": true,
        "specifyQuery": "keypair",
        "queryParameters": {
          "parameters": [
            {"name": "hub.mode", "value": "={{ $json.query['hub.mode'] }}"},
            {"name": "hub.verify_token", "value": "={{ $json.query['hub.verify_token'] }}"},
            {"name": "hub.challenge", "value": "={{ $json.query['hub.challenge'] }}"}
          ]
        },
        "options": {"response": {"response": {"neverError": true, "responseFormat": "text"}}}
      },
      "id": "http-get",
      "name": "Repassar verificacao",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [220, 0]
    },
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "whatsapp-cloud",
        "responseMode": "onReceived",
        "responseCode": 200,
        "options": {"rawBody": true}
      },
      "id": "webhook-post",
      "name": "Meta inbound",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [0, 200],
      "webhookId": "whatsapp-cloud"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://chatbot-api:8000/webhook/cloud",
        "sendHeaders": true,
        "specifyHeaders": "keypair",
        "headerParameters": {
          "parameters": [
            {"name": "X-Hub-Signature-256", "value": "={{ $json.headers['x-hub-signature-256'] }}"},
            {"name": "X-Webhook-Token", "value": "__CHATBOT_WEBHOOK_TOKEN__"},
            {"name": "Content-Type", "value": "application/json"}
          ]
        },
        "sendBody": true,
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": "={{ $json.body }}",
        "options": {"response": {"response": {"neverError": true}}}
      },
      "id": "http-post",
      "name": "Repassar inbound",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.2,
      "position": [220, 200]
    }
  ],
  "connections": {
    "Meta verificacao": {"main": [[{"node": "Repassar verificacao", "type": "main", "index": 0}]]},
    "Meta inbound": {"main": [[{"node": "Repassar inbound", "type": "main", "index": 0}]]}
  },
  "settings": {},
  "active": false
}
```

- [ ] **Step 2: Conferir o corpo cru ponta a ponta**

Este é o passo que não dá para pular: se o n8n reserializar o corpo, **toda** requisição da Meta vai
dar 401 e o sintoma vai parecer "assinatura errada".

Com o workflow publicado e o chatbot no ar, mande um POST assinado à mão:

```bash
CORPO='{"object":"whatsapp_business_account","entry":[]}'
SEG='<o mesmo CHATBOT_META_APP_SECRET>'
ASSIN="sha256=$(printf '%s' "$CORPO" | openssl dgst -sha256 -hmac "$SEG" | sed 's/^.* //')"
curl -i -X POST "https://<host-n8n>/webhook/whatsapp-cloud" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $ASSIN" \
  --data "$CORPO"
```

Esperado: `200`. Se vier `401`, o corpo chegou alterado ao chatbot — revise `rawBody` no nó Webhook
e `contentType: raw` no HTTP Request antes de mexer em qualquer outra coisa.

- [ ] **Step 3: Publicar e ativar**

Publicar pelo `n8n/update_live_workflow.js` (mesmo caminho do `n8n-baileys`) e **ativar pelo botão
"Publish" na UI**. `active: true` no JSON ou `active=1` no banco **não registra o webhook** — o
workflow fica listado como ativo e a URL responde 404.

- [ ] **Step 4: Commit**

```bash
git add n8n/workflow-cloud.json
git commit -m "feat(n8n): workflow cloud como transporte do webhook da Meta"
```

---

### Task 5: Validador do workflow cloud

**Files:**
- Create: `n8n/validate_workflow_cloud.py`
- Test: o próprio script (roda no CI e antes de publicar)

**Interfaces:**
- Produces: `python n8n/validate_workflow_cloud.py` da raiz, saindo `0` quando o workflow está
  íntegro. Mesmo espírito de `validate_workflow.py`: as invariantes que, se quebradas, só aparecem
  em produção.

- [ ] **Step 1: Escrever o validador**

```python
#!/usr/bin/env python3
"""Valida invariantes do workflow Cloud (Modo 2). Roda da raiz do repo."""

from __future__ import annotations

import json
from pathlib import Path

WORKFLOW = Path(__file__).with_name("workflow-cloud.json")
DESTINO = "http://chatbot-api:8000/webhook/cloud"


def main() -> None:
    dados = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    serializado = json.dumps(dados, ensure_ascii=False)
    nos = dados.get("nodes", [])

    # Segredo da Meta nunca entra no workflow: mora no chatbot (decisão do
    # card 3). Placeholder do webhook token é o único aceito.
    for proibido in ("META_APP_SECRET", "META_VERIFY_TOKEN", "GRAPH_TOKEN", "EAA"):
        assert proibido not in serializado, f"workflow contém segredo da Meta: {proibido}"

    webhooks = [n for n in nos if n.get("type") == "n8n-nodes-base.webhook"]
    metodos = {n["parameters"].get("httpMethod") for n in webhooks}
    assert metodos == {"GET", "POST"}, "faltam os dois webhooks (GET verificação, POST inbound)"

    post = next(n for n in webhooks if n["parameters"].get("httpMethod") == "POST")
    assert post["parameters"].get("options", {}).get("rawBody") is True, (
        "webhook POST sem rawBody: o corpo reserializado invalida a assinatura da Meta"
    )
    assert post["parameters"].get("responseMode") == "onReceived", (
        "webhook POST tem que responder 200 na hora, senão a Meta reentrega"
    )

    get = next(n for n in webhooks if n["parameters"].get("httpMethod") == "GET")
    assert get["parameters"].get("responseMode") == "lastNode", (
        "webhook GET precisa devolver o challenge do chatbot"
    )

    http = [n for n in nos if n.get("type") == "n8n-nodes-base.httpRequest"]
    assert http, "nenhum HTTP Request: o workflow não encaminha nada"
    assert all(n["parameters"].get("url") == DESTINO for n in http), (
        f"todo encaminhamento tem que ir para {DESTINO}"
    )

    encaminhador = next(n for n in http if n["parameters"].get("method") == "POST")
    cabecalhos = {
        p["name"]
        for p in encaminhador["parameters"]["headerParameters"]["parameters"]
    }
    assert "X-Hub-Signature-256" in cabecalhos, (
        "assinatura não é repassada: o chatbot não tem como validar"
    )
    assert "__CHATBOT_WEBHOOK_TOKEN__" in serializado, (
        "webhook token tem que ser placeholder, substituído na publicação"
    )
    assert dados.get("active") is not True, (
        "workflow versionado não nasce ativo; ativar é pelo Publish na UI"
    )

    print("workflow-cloud.json OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar**

Run: `python n8n/validate_workflow_cloud.py`
Esperado: `workflow-cloud.json OK`.

- [ ] **Step 3: Rodar também o validador do Modo 1, que não pode ter mudado**

Run: `python n8n/validate_workflow.py`
Esperado: passa igual — o `n8n-baileys` não foi tocado.

- [ ] **Step 4: Commit**

```bash
git add n8n/validate_workflow_cloud.py
git commit -m "test(n8n): validador do workflow cloud"
```

---

## Self-Review

- §6.1 verificação com `hub.challenge` em texto puro: Task 3. **Coberto.**
- §6.1 assinatura sobre corpo cru: Tasks 1, 3, 4 (e o validador na 5 impede o `rawBody` sumir).
  **Coberto.**
- §6.1 responder 200 rápido e deduplicar por `wamid`: Task 3. **Coberto.**
- §6.1 `statuses` com `failed` logado: Task 2 devolve o evento; o log entra no despacho da Task 3.
  **Coberto.**
- §5.6 `referral`/`ad_id`: Task 2. **Coberto.**
- §5.10 `media_id` repassado sem baixar no n8n: Task 2. **Coberto.**
- §6.2 roteamento por `phone_number_id` e descarte de número desconhecido: Task 3
  (`test_numero_desconhecido_nao_estoura_e_responde_200`). **Coberto.**
- **Divergência registrada:** a §6 previa outbound pelo `n8n-cloud`; ele mora no
  `CloudWhatsAppOutbound` (card 2b). O `n8n-cloud` ficou só de entrada. Ver "Consequência" no topo.
- **Não coberto de propósito:** `processar_evento_cloud` é despacho para o que os cards 2 e 2b já
  entregam; está descrito na Task 3, sem código, porque escrevê-lo aqui duplicaria aqueles cards.
