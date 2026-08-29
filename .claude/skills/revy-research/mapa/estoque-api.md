# estoque-api · 41 rotas · 12 modelos · 1 workers · 10 migrations · 3 templates

Gerado de `a622345`. NAO editar a mao — saida de `gerar_mapa.py`.
Migration head: `0010`

## Rotas

- `GET /admin/login` — app/admin.py:36
- `POST /admin/login` — app/admin.py:43
- `POST /admin/logout` — app/admin.py:65
- `GET /admin` — app/admin.py:72
- `GET /admin/veiculos/novo` — app/admin.py:110
- `POST /admin/veiculos/novo` — app/admin.py:122
- `GET /admin/veiculos/{veiculo_id}` — app/admin.py:147
- `POST /admin/veiculos/{veiculo_id}` — app/admin.py:158
- `POST /admin/veiculos/{veiculo_id}/{acao}` — app/admin.py:183
- `POST /admin/importar` — app/admin.py:206
- `GET /health/live` — app/main.py:162
- `GET /health/ready` — app/main.py:167
- `GET /version` — app/main.py:173
- `POST /v1/internal/provisioning/state` — app/main.py:178
- `POST /v1/veiculos` — app/main.py:201
- `GET /v1/veiculos` — app/main.py:224
- `PUT /v1/veiculos/ordem-vitrine` — app/main.py:240
- `GET /v1/veiculos/por-placa/{placa}` — app/main.py:264
- `GET /v1/veiculos/{veiculo_id}` — app/main.py:274
- `PATCH /v1/veiculos/{veiculo_id}` — app/main.py:283
- `POST /v1/veiculos/{veiculo_id}/publicar` — app/main.py:300
- `POST /v1/veiculos/{veiculo_id}/despublicar` — app/main.py:312
- `POST /v1/veiculos/{veiculo_id}/reservar` — app/main.py:324
- `POST /v1/veiculos/{veiculo_id}/vender` — app/main.py:335
- `PUT /v1/veiculos/{veiculo_id}/fotos` — app/main.py:346
- `POST /v1/veiculos/{veiculo_id}/fotos/upload` — app/main.py:367
- `GET /v1/auditoria` — app/main.py:424
- `GET /v1/eventos` — app/main.py:447
- `GET /v1/webhook` — app/main.py:476
- `PUT /v1/webhook` — app/main.py:491
- `GET /v1/entregas` — app/main.py:505
- `POST /v1/importacoes/csv/preview` — app/main.py:529
- `POST /v1/importacoes/csv` — app/main.py:537
- `GET /v1/importacoes` — app/main.py:558
- `GET /v1/veiculos.csv` — app/main.py:587
- `GET /public/v1/media/{loja_id}/{veiculo_id}/{arquivo}` — app/main.py:602
- `GET /public/v1/lojas/{slug}` — app/main.py:673
- `GET /v1/loja` — app/main.py:691
- `PATCH /v1/loja` — app/main.py:701
- `GET /public/v1/lojas/{slug}/veiculos` — app/main.py:724
- `GET /public/v1/lojas/{slug}/veiculos/{veiculo_id}` — app/main.py:753

## Modelos

- `lojas` — app/models_db.py:18
- `loja_operacional_projecao` — app/models_db.py:32
- `credenciais_servico` — app/models_db.py:47
- `usuarios_estoque` — app/models_db.py:56
- `veiculos` — app/models_db.py:73
- `veiculo_fotos` — app/models_db.py:117
- `idempotencias_criacao_veiculo` — app/models_db.py:147
- `importacoes` — app/models_db.py:174
- `eventos_saida` — app/models_db.py:188
- `webhook_destinos` — app/models_db.py:207
- `entregas_evento` — app/models_db.py:222
- `auditoria` — app/models_db.py:238

## Workers

- `main` — app/worker.py:55

## Migrations

- `0001` — alembic/versions/0001_schema_inicial.py
- `0002` — alembic/versions/0002_operacao_estoque.py
- `0003` — alembic/versions/0003_usuarios_estoque.py
- `0004` — alembic/versions/0004_outbox_entrega.py
- `0005` — alembic/versions/0005_veiculo_placa.py
- `0006` — alembic/versions/0006_veiculo_fotos_midias.py
- `0007` — alembic/versions/0007_idempotencia_criacao_veiculo.py
- `0008` — alembic/versions/0008_loja_operacional_projecao.py
- `0009` — alembic/versions/0009_veiculo_ordem_vitrine.py
- `0010` — alembic/versions/0010_loja_catalogo_url.py

## Templates

- `app/templates/admin/login.html` — app/admin.py:40
- `app/templates/admin/painel.html` — app/admin.py:91
- `app/templates/admin/form.html` — app/admin.py:118

## Testes

- macOS: `cd estoque-api && .venv/bin/python -m pytest -q`
- Windows: `cd estoque-api && .\.venv\Scripts\python.exe -m pytest -q`
