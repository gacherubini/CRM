# motor-simulacao · 16 rotas · 12 modelos · 1 workers · 14 migrations

Gerado de `e5836cf`. NAO editar a mao — saida de `gerar_mapa.py`.
Migration head: `0014`

## Rotas

- `GET /health/live` — app/main.py:28
- `GET /health/ready` — app/main.py:33
- `GET /version` — app/main.py:38
- `GET /metrics` — app/main.py:43
- `GET /v1/provedores` — app/main.py:66
- `GET /v1/provedores/credenciais` — app/main.py:83
- `GET /v1/provedores/{nome}/credenciais` — app/main.py:95
- `PUT /v1/provedores/{nome}/credenciais` — app/main.py:112
- `POST /v1/provedores/{nome}/testar-login` — app/main.py:127
- `POST /v1/internal/provisioning/state` — app/main.py:159
- `POST /v1/simulacoes` — app/main.py:181
- `GET /v1/simulacoes` — app/main.py:215
- `GET /v1/simulacoes/{sim_id}` — app/main.py:254
- `GET /v1/simulacoes/{sim_id}/eventos` — app/main.py:271
- `GET /v1/simulacoes/{sim_id}/eventos/{evento_id}/print` — app/main.py:292
- `POST /v1/simulacoes/{sim_id}/cancelar` — app/main.py:345

## Modelos

- `clientes_api` — app/models_db.py:33
- `cliente_operacional_projecao` — app/models_db.py:48
- `credenciais_api` — app/models_db.py:63
- `credenciais_provedor` — app/models_db.py:84
- `auditoria` — app/models_db.py:117
- `simulacoes` — app/models_db.py:130
- `simulacao_resultados` — app/models_db.py:188
- `simulacao_tentativas` — app/models_db.py:209
- `simulacao_eventos` — app/models_db.py:226
- `simulacao_provedores` — app/models_db.py:247
- `worker_slots` — app/models_db.py:290
- `idempotencia` — app/models_db.py:316

## Workers

- `main` — app/worker.py:93

## Migrations

- `0001` — alembic/versions/0001_schema_inicial.py
- `0002` — alembic/versions/0002_payload_cifrado.py
- `0003` — alembic/versions/0003_job_async.py
- `0004` — alembic/versions/0004_auth_tenancy.py
- `0005` — alembic/versions/0005_job_lease.py
- `0006` — alembic/versions/0006_credenciais_provedor.py
- `0007` — alembic/versions/0007_simulacao_campos_reais.py
- `0008` — alembic/versions/0008_resultado_entrada.py
- `0009` — alembic/versions/0009_simulacao_solicitado_por.py
- `0010` — alembic/versions/0010_pan_api.py
- `0011` — alembic/versions/0011_simulacao_eventos.py
- `0012` — alembic/versions/0012_simulacao_provedores_fanout.py
- `0013` — alembic/versions/0013_evento_screenshot_blob.py
- `0014` — alembic/versions/0014_cliente_operacional_projecao.py

## Testes

- macOS: `cd motor-simulacao && .venv/bin/python -m pytest -q`
- Windows: `cd motor-simulacao && .\.venv\Scripts\python.exe -m pytest -q`
