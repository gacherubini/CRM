# Catálogo conectado

Sobe somente o Catálogo e o conecta por HTTP a uma Estoque API existente. Portal, Chatbot e
Motor não são necessários.

1. Copie `.env.example` para `.env` e ajuste `ESTOQUE_PUBLIC_API_URL`.
2. Garanta que a loja exista e tenha veículos disponíveis publicados na Estoque API.
3. Suba o serviço:

```powershell
docker compose up -d --build
docker compose ps
```

A vitrine fica em `http://localhost:8200/l/<slug-da-loja>`. Eventos de clique ficam no volume
`catalogo_data`; preserve esse volume em backup. Para parar sem apagar eventos:

```powershell
docker compose down
```

Não use `docker compose down -v` se quiser preservar o histórico de interesses.

## Funil opcional Catálogo → Chatbot

Por padrão o funil vem **desligado**: os cliques ficam só no volume `catalogo_data`. Para entregar
cada `catalog.interest_clicked` na ingestão do Chatbot (e atribuir o lead quando o cliente mandar a
mensagem com a ref `CAT-*`), preencha no `.env`:

```dotenv
CATALOGO_EVENTS_URL=http://host.docker.internal:8001/v1/integracoes/catalogo/interesses
CATALOGO_EVENTS_TOKEN=<token de serviço da loja no Chatbot>
```

O `CATALOGO_EVENTS_TOKEN` é uma credencial de serviço da **mesma loja** cadastrada no Chatbot
(`CredencialServico`); a loja é derivada do token, então o `loja_slug` do evento precisa bater com o
slug dessa loja no Chatbot (senão a ingestão responde `403`). O outbox entrega com
`Authorization: Bearer <token>`, `Idempotency-Key = event_id` e `X-Event-Type`, com retry e backoff;
reentregas são idempotentes (o Chatbot devolve `duplicado: true`). Sem esses dois valores o worker do
outbox nem inicia.

O fluxo ponta a ponta (clique → outbox → ingestão → correlação da mensagem → lead atribuído) é
coberto pelo teste `chatbot-api/tests/test_e2e_outbox_delivery.py`.
