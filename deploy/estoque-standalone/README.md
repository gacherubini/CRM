# Estoque API — pacote standalone

Sobe **apenas** o Estoque (API privada + pública + Postgres). Não depende de Bot,
Portal, Catálogo ou Motor (Plano #4A).

## Subir

```bash
cd deploy/estoque-standalone
docker compose up -d --build
```

A API sobe em `http://localhost:8100`. O schema é migrado por Alembic no boot.

## Onboarding — criar a primeira loja

```bash
docker compose exec estoque-api python -m app.cli criar-loja \
  --nome "Moto Center" --slug moto-center --whatsapp 5511999999999
# imprime o TOKEN da loja (guarde: usado no header Authorization)
```

Para emitir uma credencial adicional sem revelar as existentes:

```bash
docker compose exec estoque-api python -m app.cli criar-credencial \
  --slug moto-center --papel operador
```

Papéis disponíveis:

- `dono` e `gerente`: operação completa, custo, auditoria e eventos;
- `operador`: gerencia veículos, mas não acessa custo;
- `leitor`: somente consulta privada.

## Usar (API privada — precisa do token)

```bash
TOKEN=cole-o-token-aqui

curl -s -X POST http://localhost:8100/v1/veiculos \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"tipo":"moto","marca":"Honda","modelo":"CG 160","ano_modelo":2023,"preco":16000,"custo":13000}'

# publicar (troque <id>)
curl -s -X POST http://localhost:8100/v1/veiculos/<id>/publicar -H "Authorization: Bearer $TOKEN"
```

Também estão disponíveis:

- `PUT /v1/veiculos/{id}/fotos` para fotos ordenadas, com capa, MIME e tamanho;
- `POST /v1/importacoes/csv/preview` para validar um CSV sem gravar;
- `POST /v1/importacoes/csv` para importar e atualizar por `codigo_interno`;
- `GET /v1/veiculos.csv` para exportar;
- `GET /v1/auditoria` e `GET /v1/eventos` para dono/gerente.

O CSV usa `,` ou `;` e exige `tipo`, `marca`, `modelo`, `ano_modelo` e `preco`.
O conteúdo é enviado como `text/csv` no corpo da requisição.

### Fotos para WhatsApp

Fotos ficam em object storage/CDN; o Estoque persiste somente URL pública e
metadados, nunca base64 ou paths locais. Configure, por exemplo:

```env
ESTOQUE_MEDIA_PUBLIC_BASE_URL=https://media.seudominio.com/veiculos
ESTOQUE_MEDIA_MAX_FOTOS=20
ESTOQUE_MEDIA_MAX_BYTES=10485760
ESTOQUE_MEDIA_ALLOWED_HOSTS=media.seudominio.com
```

O contrato recomendado aceita URL HTTPS pública ou `storage_key` relativa à base:

```json
{
  "fotos": [
    {
      "storage_key": "moto-center/veiculo-123/frente.webp",
      "content_type": "image/webp",
      "tamanho_bytes": 245000,
      "ordem": 0,
      "capa": true
    }
  ]
}
```

Tipos aceitos: JPEG, PNG e WebP. Exatamente uma foto deve ser capa. URLs com
base64, host local/privado, credenciais, fragmento ou query são recusadas. A forma
legada `{ "urls": ["https://..."] }` continua disponível para integração existente.
As respostas mantêm `foto_url`/`fotos` e acrescentam `midia_principal`/`midias`.

## Vitrine pública (sem token, por slug)

```bash
curl -s http://localhost:8100/public/v1/lojas/moto-center/veiculos
# retorna só veículos disponíveis+publicados, sem custo/dados internos
```

A listagem pública aceita `tipo`, `marca`, `preco_min`, `preco_max`, `limit` e
`offset`. As respostas incluem `ETag`, `Last-Modified` e rate limit configurável
por `ESTOQUE_PUBLIC_RATE_LIMIT`.

## Entrega de eventos (outbox → webhook)

Cada mutação de veículo gera um evento (`vehicle.created/updated/published/reserved/sold`).
O serviço **`estoque-outbox`** entrega esses eventos ao webhook da loja, com **assinatura
HMAC-SHA256** no header `X-Assinatura` (formato `sha256=<hex>`), `X-Evento-Id` (idempotência) e
`X-Entrega-Id` (rastreio por tentativa). Falhas reagendam com backoff exponencial; após 5
tentativas o evento é **descartado**.

```bash
# 1) gere a chave que cifra o segredo em repouso e ponha em .env (ESTOQUE_OUTBOX_KEY)
docker compose run --rm estoque-api python -m app.cli gerar-chave-outbox

# 2) configure o destino da loja (segredo HMAC >= 16 chars; fica cifrado no banco)
docker compose exec estoque-api python -m app.cli configurar-webhook \
  --slug moto-center --url https://seu-endpoint/webhook --segredo "um-segredo-bem-grande"
```

Pela API (dono/gerente): `PUT /v1/webhook` `{ "url", "segredo" }`, `GET /v1/webhook`
(nunca devolve o segredo) e `GET /v1/entregas` (histórico de tentativas). O receptor deve
validar a assinatura e deduplicar por `X-Evento-Id`.

O verificador do lado do receptor: `HMAC_SHA256(segredo, corpo_bruto)` deve bater com o header.

## Operação

- **Backup:** `docker compose exec postgres pg_dump -U estoque estoque > backup.sql`
- **Restore:** pare a API e aplique `psql -U estoque estoque < backup.sql` no Postgres.
- **Logs:** `docker compose logs -f estoque-api`
- **Parar:** `docker compose down` (dados no volume `estoque_pg`)
