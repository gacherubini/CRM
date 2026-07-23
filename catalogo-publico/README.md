# Catálogo Público

Vitrine FastAPI/Jinja independente. Consome somente o contrato HTTP público da Estoque API e
mantém apenas seus eventos de interesse em SQLite próprio.

## Desenvolvimento

```powershell
cd catalogo-publico
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
$env:ESTOQUE_PUBLIC_API_URL="http://localhost:8100"
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8200
```

Abra `http://localhost:8200/l/<slug-da-loja>`. O veículo precisa estar disponível e publicado
na Estoque API.

Configurações:

- `ESTOQUE_PUBLIC_API_URL`: URL-base da Estoque API;
- `ESTOQUE_PUBLIC_API_TOKEN`: Bearer opcional, mantido apenas no servidor;
- `CATALOGO_DATABASE_PATH`: arquivo SQLite de eventos;
- `CATALOGO_PAGE_SIZE`: tamanho padrão da página;
- `CATALOGO_PUBLIC_BASE_URL`: URL pública da instalação;
- `CATALOGO_SECURE_COOKIE=1`: cookie anônimo somente por HTTPS.
- `CATALOGO_EVENTS_URL`: endpoint server-side do Chatbot para eventos do catálogo;
- `CATALOGO_EVENTS_TOKEN`: Bearer tenant-scoped do Chatbot (nunca enviado ao navegador);
- `CATALOGO_EVENTS_TIMEOUT`, `CATALOGO_EVENTS_MAX_ATTEMPTS` e
  `CATALOGO_EVENTS_WORKER_INTERVAL`: entrega persistente da outbox;
- `PORTAL_PUBLIC_URL`: URL do Portal (ex.: `http://127.0.0.1:9000` no bundle 3-VM). O catálogo consulta `GET /public/v1/lojas/{slug}/pixel` e usa o Pixel ID que o dono salvou em Tráfego;
- `META_PIXEL_ID`: fallback opcional se o Portal estiver offline/indisponível;
- `META_PIXEL_ENABLED`: `1`/`0` (default: ativo quando há Pixel). **Nunca** coloque o token CAPI aqui;
- `CATALOGO_PORTAL_PIXEL_CACHE_TTL`: cache em segundos do Pixel por loja (default 60).

Quando URL e token estão configurados, o processo entrega `catalog.interest_clicked` em background.
Cada tentativa mantém o mesmo `event_id`/`Idempotency-Key`; o clique e sua outbox são gravados na
mesma transação. O payload não contém telefone nem o identificador anônimo local do visitante.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
