# catalogo-publico · 8 rotas · 1 workers · 2 flags · 4 templates

Gerado de `1b61c0f`. NAO editar a mao — saida de `gerar_mapa.py`.
Migration head: `n/a`

## Rotas

- `GET /` — app/main.py:277
- `GET /health/live` — app/main.py:284
- `GET /health/ready` — app/main.py:289
- `GET /version` — app/main.py:297
- `POST /internal/v1/provisioning/state` — app/main.py:302
- `GET /l/{slug}` — app/main.py:348
- `GET /l/{slug}/veiculos/{vehicle_id}` — app/main.py:460
- `GET /l/{slug}/interesse/{vehicle_id}` — app/main.py:525

## Workers

- `OutboxWorker` — app/outbox.py:73

## Flags

- `REVY_TRAFEGO_PUBLIC_URL` — app/config.py:53
- `META_PIXEL_ENABLED (default: '')` — app/config.py:66

## Templates

- `app/templates/error.html` — app/main.py:195
- `app/templates/storefront.html` — app/main.py:439
- `app/templates/vehicle.html` — app/main.py:512
- `app/templates/base.html` — app/templates/base.html

## Testes

- macOS: `cd catalogo-publico && .venv/bin/python -m pytest -q`
- Windows: `cd catalogo-publico && .\.venv\Scripts\python.exe -m pytest -q`
