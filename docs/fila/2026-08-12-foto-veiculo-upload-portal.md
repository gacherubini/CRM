# Foto de veículo → upload no Portal — Implementation Plan

> **Status 2026-08-13:** alinhado ao spec dos dois modos. Vale nos **dois**: Modo 1 = atalho
> além do grupo; Modo 2 = **único** jeito de publicar. **Não** apagar o fluxo de foto pelo
> grupo (Modo 1). Eixo à parte — não misturar com o plano WhatsApp.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) ou superpowers:executing-plans para executar tarefa-a-tarefa. Steps usam checkbox (`- [ ]`).

**Goal:** Permitir que o vendedor suba a **foto do veículo por arquivo** (tirar/selecionar) na tela de estoque que **já existe** no Portal, reaproveitando o endpoint de upload que o `estoque-api` já expõe — substituindo o cadastro de foto por URL. Tira a *obrigatoriedade* do grupo para ter foto; o grupo do Modo 1 **permanece**.

**Architecture:** três peças no `portal-gestao`, backend do `estoque-api` já pronto e sem migração: (1) método `adicionar_foto` no `EstoqueClient` chamando `POST /v1/veiculos/{id}/fotos/upload`; (2) tratamento de `UploadFile` nas rotas `estoque_criar`/`estoque_editar` via helper `_anexar_foto_se_enviada`; (3) `enctype="multipart/form-data"` + `<input type="file">` no `estoque/form.html`, herdando o estilo dos inputs.

**Tech Stack:** FastAPI + Starlette forms (multipart; `python-multipart` já em `portal-gestao/requirements.txt`), `httpx`, Jinja2, design system Revy.

## Global Constraints

- **Não recriar a área de estoque.** O form legado `estoque/form.html` + rotas `/app/estoque*` permanecem; só se **adiciona** o upload. (`portal-gestao/app/web/loja_estoque.py:1-9` confirma que CRUD/fotos/publicar ficam no legado.)
- **Design da marca, sem CSS novo.** Usar classes existentes: `.form-grid`, `.wide`, `.button.secondary`/`.primary`, `.alert.error`. `<input type="file">` **já herda** o estilo global de input (`portal-gestao/app/static/css/app.css:1637`, foco `--brand` em `:1665`). Não editar `revy-tokens.css` (é cópia gerada por `shared/brand/sync_tokens.py`).
- **Contrato do estoque-api (já existe):** `POST /v1/veiculos/{veiculo_id}/fotos/upload?publicar=<bool>` — corpo = **bytes crus**, headers `Content-Type: <mime>` + `Idempotency-Key`; Bearer token de serviço; papel ≥ operador; 201 na criação. Mime jpeg/png/webp; ≤ 10 MB; mesma key + bytes diferentes → **409**; mesma key + mesmos bytes → no-op.
- **Idempotência:** derivar a key dos bytes: `portal-foto:{veiculo_id}:{sha256(conteudo)[:32]}`.
- Rodar testes **a partir de `portal-gestao/`** (senão importa o `app` errado). O dono usa **Mac e
  Windows**, então cada Run traz as duas formas:
  - macOS/Linux: `python -m pytest -q`
  - Windows: `.\.venv\Scripts\python.exe -m pytest -q`

---

### Task 1: `EstoqueClient.adicionar_foto`

**Files:**
- Modify: `portal-gestao/app/clients/estoque.py` (novo método na classe `EstoqueClient`, após `atualizar`, ~`:105`)
- Test: `portal-gestao/tests/test_estoque_client_foto.py`

**Interfaces:**
- Produces: `EstoqueClient.adicionar_foto(veiculo_id: str, conteudo: bytes, content_type: str, *, idempotency_key: str, publicar: bool = True) -> dict`
- Consumes: `EstoqueClient._request` já existente (`estoque.py:51`), que injeta `Authorization: Bearer`, faz retry idempotente e mapeia 404→`VeiculoNaoEncontrado` / 409→`ConflitoEstoque`.

- [ ] **Step 1: Escrever o teste que falha** (espelha o padrão `_client(handler)` de `test_estoque_client_atualizar.py`)

```python
# portal-gestao/tests/test_estoque_client_foto.py
import httpx
import pytest

from app.clients.estoque import ConflitoEstoque, EstoqueClient, VeiculoNaoEncontrado


def _client(handler):
    class ClientComTransporte(EstoqueClient):
        def _request(self, method, path, erro_404=None, erro_409=None, **kwargs):
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                transport=httpx.MockTransport(handler),
            ) as c:
                resposta = c.request(method, path, **kwargs)
            if resposta.status_code == 404 and erro_404 is not None:
                raise erro_404("veículo não encontrado")
            if resposta.status_code == 409 and erro_409 is not None:
                raise erro_409("veículo em estado incompatível")
            resposta.raise_for_status()
            return resposta.json()

    return ClientComTransporte("http://estoque.test", "token")


def test_adicionar_foto_faz_post_com_bytes_e_headers():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["url"] = str(request.url)
        capturado["content"] = request.content
        capturado["content_type"] = request.headers.get("content-type")
        capturado["idem"] = request.headers.get("idempotency-key")
        return httpx.Response(201, json={"id": "v1", "publicado": True})

    client = _client(handler)
    out = client.adicionar_foto(
        "v1", b"\xff\xd8jpegbytes", "image/jpeg", idempotency_key="portal-foto:v1:abc"
    )
    assert out["id"] == "v1"
    assert "/v1/veiculos/v1/fotos/upload" in capturado["url"]
    assert "publicar=true" in capturado["url"]
    assert capturado["content"] == b"\xff\xd8jpegbytes"
    assert capturado["content_type"] == "image/jpeg"
    assert capturado["idem"] == "portal-foto:v1:abc"


def test_adicionar_foto_404_vira_veiculo_nao_encontrado():
    client = _client(lambda r: httpx.Response(404, json={"detail": "x"}))
    with pytest.raises(VeiculoNaoEncontrado):
        client.adicionar_foto("v1", b"x", "image/jpeg", idempotency_key="k")


def test_adicionar_foto_409_vira_conflito():
    client = _client(lambda r: httpx.Response(409, json={"detail": "x"}))
    with pytest.raises(ConflitoEstoque):
        client.adicionar_foto("v1", b"x", "image/jpeg", idempotency_key="k")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd portal-gestao && python -m pytest tests/test_estoque_client_foto.py -q` — Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_estoque_client_foto.py -q`
Expected: FAIL — `AttributeError: 'EstoqueClient' object has no attribute 'adicionar_foto'`.

- [ ] **Step 3: Implementar o método** (em `portal-gestao/app/clients/estoque.py`, logo após `atualizar`)

```python
    def adicionar_foto(
        self,
        veiculo_id: str,
        conteudo: bytes,
        content_type: str,
        *,
        idempotency_key: str,
        publicar: bool = True,
    ) -> dict:
        """Sobe uma foto (bytes) para um veículo existente via estoque-api.

        A Idempotency-Key torna o reenvio seguro: mesma key + mesmos bytes = no-op;
        mesma key + bytes diferentes = 409 (ConflitoEstoque). O upload define a capa.
        """
        return self._request(
            "POST",
            f"/v1/veiculos/{veiculo_id}/fotos/upload",
            params={"publicar": str(publicar).lower()},
            content=conteudo,
            headers={"Content-Type": content_type, "Idempotency-Key": idempotency_key},
            erro_404=VeiculoNaoEncontrado,
            erro_409=ConflitoEstoque,
        )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd portal-gestao && python -m pytest tests/test_estoque_client_foto.py -q` — Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_estoque_client_foto.py -q`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add portal-gestao/app/clients/estoque.py portal-gestao/tests/test_estoque_client_foto.py
git commit -m "feat(portal): EstoqueClient.adicionar_foto (upload de foto por bytes)"
```

---

### Task 2: rota — helper `_anexar_foto_se_enviada` + integração no criar/editar

**Files:**
- Modify: `portal-gestao/app/main.py` (novo helper perto de `dados_veiculo:823`; chamadas em `estoque_criar:944-967` e `estoque_editar:1001-1025`; garantir `import hashlib` no topo)
- Test: `portal-gestao/tests/test_estoque_foto_upload.py`
- Modify (spy no fake): `portal-gestao/tests/conftest.py` — adicionar `adicionar_foto` ao `estoque_fake` para registrar a chamada.

**Interfaces:**
- Consumes: `EstoqueClient.adicionar_foto` (Task 1); `estoque.criar` devolve o veículo criado com `id`.
- Produces: helper `async def _anexar_foto_se_enviada(estoque, veiculo_id: str | None, form) -> None` (levanta `ValueError` para foto inválida → reaproveita o `except (..., ValueError)` das rotas, que já re-renderiza o `form.html` com `erro=` e 422).

- [ ] **Step 1: Escrever o teste que falha**

```python
# portal-gestao/tests/test_estoque_foto_upload.py
from conftest import csrf_da_resposta, login

_CAMPOS = {
    "tipo": "moto", "marca": "Honda", "modelo": "CG 160", "versao": "Fan",
    "ano_modelo": "2022", "cor": "Preta", "km": "10000", "preco": "15900",
    "custo": "12000", "codigo_interno": "H01", "foto_url": "", "placa": "ABC1D23",
}


def test_upload_de_foto_no_cadastro_chama_estoque(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={"csrf": csrf_da_resposta(pagina), **_CAMPOS},
        files={"foto": ("moto.jpg", b"\xff\xd8fakejpeg", "image/jpeg")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303  # sucesso → redirect
    assert estoque_fake.fotos, "adicionar_foto deveria ter sido chamado"
    chamada = estoque_fake.fotos[-1]
    assert chamada["content_type"] == "image/jpeg"
    assert chamada["conteudo"] == b"\xff\xd8fakejpeg"
    assert chamada["idempotency_key"].startswith("portal-foto:")


def test_upload_de_mime_invalido_mostra_erro(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={"csrf": csrf_da_resposta(pagina), **_CAMPOS},
        files={"foto": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
        follow_redirects=False,
    )
    assert resposta.status_code == 422
    assert "Formato de foto inválido" in resposta.text


def test_cadastro_sem_arquivo_nao_chama_upload(client, estoque_fake):
    login(client)
    pagina = client.get("/app/estoque/novo")
    resposta = client.post(
        "/app/estoque/novo",
        data={"csrf": csrf_da_resposta(pagina), **_CAMPOS},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert not estoque_fake.fotos
```

- [ ] **Step 2: Adicionar o spy ao `estoque_fake`** (em `portal-gestao/tests/conftest.py`, na classe fake que já expõe `criar`/`atualizar`)

```python
    def __init__(self, ...):
        ...
        self.fotos = []

    def adicionar_foto(self, veiculo_id, conteudo, content_type, *, idempotency_key, publicar=True):
        self.fotos.append({
            "veiculo_id": veiculo_id, "conteudo": conteudo,
            "content_type": content_type, "idempotency_key": idempotency_key,
            "publicar": publicar,
        })
        return {"id": veiculo_id, "publicado": publicar}
```

E garantir que `criar` do fake devolva um `id` (ex.: `return {"id": "v-novo", ...}`) para o helper ter o alvo do upload.

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd portal-gestao && python -m pytest tests/test_estoque_foto_upload.py -q` — Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_estoque_foto_upload.py -q`
Expected: FAIL — upload não é chamado (helper ainda não existe).

- [ ] **Step 4: Implementar o helper e ligar nas rotas** (em `portal-gestao/app/main.py`)

No topo do arquivo, garantir `import hashlib`.

Adicionar após `dados_veiculo` (`:839`):

```python
_FOTO_MIMES = {"image/jpeg", "image/png", "image/webp"}
_FOTO_MAX_BYTES = 10 * 1024 * 1024


async def _anexar_foto_se_enviada(estoque, veiculo_id: str | None, form) -> None:
    """Se o form trouxe um arquivo de foto, sobe para o estoque-api.

    Levanta ValueError (capturado pelas rotas → re-render com erro/422) para
    arquivo inválido. Sem arquivo = no-op.
    """
    foto = form.get("foto")
    if foto is None or not hasattr(foto, "read") or not getattr(foto, "filename", ""):
        return
    conteudo = await foto.read()
    if not conteudo:
        return
    if len(conteudo) > _FOTO_MAX_BYTES:
        raise ValueError("A foto excede o limite de 10 MB.")
    content_type = (getattr(foto, "content_type", "") or "").lower()
    if content_type not in _FOTO_MIMES:
        raise ValueError("Formato de foto inválido (use JPG, PNG ou WEBP).")
    if not veiculo_id:
        raise ValueError("Não foi possível associar a foto ao veículo.")
    chave = f"portal-foto:{veiculo_id}:{hashlib.sha256(conteudo).hexdigest()[:32]}"
    estoque.adicionar_foto(
        veiculo_id, conteudo, content_type, idempotency_key=chave, publicar=True
    )
```

Em `estoque_criar` (`:959-960`), trocar o corpo do `try` por:

```python
    try:
        criado = estoque.criar(dados_veiculo(form, pode_ver_custo(usuario)))
        await _anexar_foto_se_enviada(estoque, (criado or {}).get("id"), form)
    except (EstoqueIndisponivel, ConflitoEstoque, ValueError) as exc:
```
(adicionar `ConflitoEstoque` ao `except` e ao import de `app.clients.estoque`.)

Em `estoque_editar` (`:1017-1018`), dentro do `try`:

```python
    try:
        estoque.atualizar(veiculo_id, dados_veiculo(form, pode_ver_custo(usuario)))
        await _anexar_foto_se_enviada(estoque, veiculo_id, form)
    except (ConflitoEstoque, EstoqueIndisponivel, VeiculoNaoEncontrado, ValueError) as exc:
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd portal-gestao && python -m pytest tests/test_estoque_foto_upload.py -q` — Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_estoque_foto_upload.py -q`
Expected: PASS (3 testes). Rodar a suíte de estoque para não regredir: `... -m pytest tests/ -q -k estoque`.

- [ ] **Step 6: Commit**

```bash
git add portal-gestao/app/main.py portal-gestao/tests/test_estoque_foto_upload.py portal-gestao/tests/conftest.py
git commit -m "feat(portal): aceita upload de foto de veiculo no cadastro/edicao"
```

---

### Task 3: template — `enctype` + input de arquivo (design da marca)

**Files:**
- Modify: `portal-gestao/app/templates/estoque/form.html` (`:9` e `:30`)

**Interfaces:**
- Consumes: rota da Task 2 (lê `form.get("foto")`).

- [ ] **Step 1: Adicionar `enctype` ao form** (`form.html:9`)

De:
```html
<form method="post" class="form-layout">
```
Para:
```html
<form method="post" class="form-layout" enctype="multipart/form-data">
```

- [ ] **Step 2: Adicionar o input de arquivo** ao lado do campo URL, na seção "Comercial" (`form.html:30`, dentro do mesmo `.form-grid`, espelhando `campanhas/gastos_lote.html:64-66`)

Logo após o `<label class="wide">URL da foto ...</label>`:
```html
<label class="wide">Foto do veículo
  <input type="file" name="foto" accept="image/jpeg,image/png,image/webp">
  <small>Tire ou selecione a foto (JPG, PNG ou WEBP, até 10 MB). Vira a capa. Ou informe a URL acima.</small>
</label>
```
Não precisa de CSS: o `<input type="file">` herda o estilo global de input (`app.css:1637`, foco `--brand`), e `<small>` já é estilizado como apoio (`app.css:981-987`). O botão "Salvar veículo" existente (`.button.primary`, `form.html:33`) envia tudo.

- [ ] **Step 3: Verificar render** — teste rápido de presença

```python
# adicionar em tests/test_estoque_foto_upload.py
def test_form_tem_input_de_arquivo(client):
    login(client)
    pagina = client.get("/app/estoque/novo")
    assert 'enctype="multipart/form-data"' in pagina.text
    assert 'type="file"' in pagina.text and 'name="foto"' in pagina.text
```

Run: `cd portal-gestao && python -m pytest tests/test_estoque_foto_upload.py::test_form_tem_input_de_arquivo -q` — Windows: `cd portal-gestao && .\.venv\Scripts\python.exe -m pytest tests/test_estoque_foto_upload.py::test_form_tem_input_de_arquivo -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add portal-gestao/app/templates/estoque/form.html portal-gestao/tests/test_estoque_foto_upload.py
git commit -m "feat(portal): input de upload de foto no form de estoque (design Revy)"
```

---

## Self-Review (cobertura vs §6.1 do design)

- §6.1 "foto de veículo → upload no Portal": Tasks 1-3 entregam o caminho completo (cliente → rota → UI) reusando o endpoint existente do estoque-api. **Coberto.**
- Sem placeholder: código real do método, do helper, do template e dos testes; classes/tokens citados por arquivo:linha.
- Consistência de tipos: `adicionar_foto` tem a mesma assinatura no cliente (Task 1), no spy do fake (Task 2) e nas chamadas do helper (Task 2). `criar` do fake devolve `id` consumido pelo helper.
- **Fora de escopo (não faz parte):** galeria de múltiplas fotos, reordenação, remoção de foto — o `VeiculoFoto`/`MEDIA_MAX_FOTOS=20` já suportam, mas ficam para depois. Este plano entrega **capa única por upload**, substituindo o fluxo do grupo.
