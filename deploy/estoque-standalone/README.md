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

## Usar (API privada — precisa do token)

```bash
TOKEN=cole-o-token-aqui

curl -s -X POST http://localhost:8100/v1/veiculos \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"tipo":"moto","marca":"Honda","modelo":"CG 160","ano_modelo":2023,"preco":16000,"custo":13000}'

# publicar (troque <id>)
curl -s -X POST http://localhost:8100/v1/veiculos/<id>/publicar -H "Authorization: Bearer $TOKEN"
```

## Vitrine pública (sem token, por slug)

```bash
curl -s http://localhost:8100/public/v1/lojas/moto-center/veiculos
# retorna só veículos disponíveis+publicados, sem custo/dados internos
```

## Operação

- **Backup:** `docker compose exec postgres pg_dump -U estoque estoque > backup.sql`
- **Logs:** `docker compose logs -f estoque-api`
- **Parar:** `docker compose down` (dados no volume `estoque_pg`)
