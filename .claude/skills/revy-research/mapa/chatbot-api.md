# chatbot-api · 56 rotas · 17 modelos · 10 workers · 4 flags · 25 migrations

Gerado de `7899099`. NAO editar a mao — saida de `gerar_mapa.py`.
Migration head: `0025_canal_cloud_por_loja`

## Rotas

- `GET /health/live` — app/main.py:509
- `GET /health/ready` — app/main.py:514
- `GET /version` — app/main.py:520
- `GET /webhook/cloud` — app/main.py:525
- `POST /webhook/cloud` — app/main.py:542
- `POST /webhook/mensagem` — app/main.py:735
- `POST /webhook/audio/transcrever` — app/main.py:760
- `POST /v1/operacao/roteamento` — app/main.py:796
- `POST /webhook/operacao/veiculos/foto` — app/main.py:816
- `GET /v1/conversas` — app/main.py:854
- `GET /v1/conversas/{telefone}/mensagens` — app/main.py:871
- `GET /v1/conversas/{telefone}/estado` — app/main.py:904
- `POST /v1/conversas/{telefone}/pode-responder` — app/main.py:921
- `PATCH /v1/conversas/{telefone}/estado` — app/main.py:938
- `POST /v1/conversas/{telefone}/mensagens` — app/main.py:997
- `POST /v1/consentimentos` — app/main.py:1022
- `POST /v1/leads` — app/main.py:1035
- `POST /v1/integracoes/catalogo/interesses` — app/main.py:1046
- `GET /v1/leads` — app/main.py:1080
- `GET /v1/funil/eventos` — app/main.py:1090
- `GET /v1/auditoria/ctwa` — app/main.py:1109
- `GET /v1/atendimento/resumo` — app/main.py:1161
- `GET /v1/leads.csv` — app/main.py:1173
- `GET /v1/leads/{lead_id}` — app/main.py:1219
- `PATCH /v1/leads/{lead_id}/etapa` — app/main.py:1226
- `GET /v1/config/catalogo-bot` — app/main.py:1238
- `GET /v1/estoque/buscar` — app/main.py:1280
- `GET /v1/estoque/por-placa/{placa}` — app/main.py:1300
- `GET /v1/estoque/veiculos/{veiculo_id}/midia-principal` — app/main.py:1317
- `POST /v1/internal/provisioning/state` — app/main.py:1405
- `POST /v1/simulacoes/solicitar` — app/main.py:1426
- `POST /v1/simular` — app/main.py:1465
- `GET /v1/whatsapp/canais` — app/main.py:1532
- `POST /v1/whatsapp/canais` — app/main.py:1544
- `POST /v1/whatsapp/canais/{canal_id}/principal-estoque` — app/main.py:1561
- `POST /v1/whatsapp/canais/{canal_id}/inativar` — app/main.py:1571
- `POST /v1/whatsapp/canais/{canal_id}/connect` — app/main.py:1581
- `GET /v1/whatsapp/canais/{canal_id}/status` — app/main.py:1598
- `POST /v1/whatsapp/canais/{canal_id}/disconnect` — app/main.py:1608
- `GET /v1/fila-vendedores` — app/main.py:1640
- `GET /v1/ofertas` — app/main.py:1649
- `POST /v1/ofertas/{oferta_id}/assumir` — app/main.py:1686
- `POST /v1/fila-vendedores` — app/main.py:1707
- `PATCH /v1/fila-vendedores/{vendedor_id}` — app/main.py:1726
- `DELETE /v1/fila-vendedores/{vendedor_id}` — app/main.py:1757
- `POST /v1/operacao/solicitacoes-simulacao-humana` — app/main.py:1778
- `POST /v1/operacao/responder` — app/main.py:1817
- `POST /v1/operacao/handoff-humano` — app/main.py:1865
- `POST /v1/operacao/moto-escolhida` — app/main.py:1906
- `GET /v1/operacao/grupo-estoque` — app/main.py:1933
- `PUT /v1/operacao/grupo-estoque` — app/main.py:1952
- `DELETE /v1/operacao/grupo-estoque` — app/main.py:1979
- `GET /v1/operacao/numeros-autorizados` — app/main.py:1986
- `POST /v1/operacao/numeros-autorizados` — app/main.py:1993
- `DELETE /v1/operacao/numeros-autorizados/{telefone}` — app/main.py:2004
- `POST /v1/operacao/veiculos` — app/main.py:2013

## Modelos

- `lojas` — app/models_db.py:19
- `loja_operacional_projecao` — app/models_db.py:33
- `whatsapp_canais` — app/models_db.py:50
- `fila_vendedor` — app/models_db.py:96
- `oferta_lead` — app/models_db.py:128
- `rodizio_ponteiro` — app/models_db.py:153
- `credenciais_servico` — app/models_db.py:160
- `conversas` — app/models_db.py:169
- `mensagens` — app/models_db.py:197
- `leads` — app/models_db.py:220
- `consentimentos` — app/models_db.py:277
- `catalog_attributions` — app/models_db.py:292
- `ctwa_auditoria` — app/models_db.py:324
- `numeros_autorizados` — app/models_db.py:347
- `grupos_estoque` — app/models_db.py:375
- `notificacoes_operacionais` — app/models_db.py:394
- `cloud_evento_falho` — app/models_db.py:435

## Workers

- `CloudRetryWorker` — app/cloud_retry.py:140
- `texto_followup` — app/followup_job.py:45
- `classificar_etapa` — app/followup_job.py:53
- `FollowupWorker` — app/followup_job.py:64
- `start_workers` — app/modo2_workers.py:84
- `stop_workers` — app/modo2_workers.py:147
- `NotificacoesOutboxWorker` — app/notificacoes_outbox_job.py:28
- `start_worker` — app/notificacoes_outbox_job.py:92
- `stop_worker` — app/notificacoes_outbox_job.py:103
- `RodizioWorker` — app/rodizio_job.py:12

## Flags

- `CHATBOT_WHATSAPP_MODO2_ENABLED (default: '')` — app/config.py:120
- `MULTI_WHATSAPP_ENABLED (default: 0)` — app/config.py:123
- `CHATBOT_NOTIF_RETRY_ENABLED (default: 1)` — app/main.py:81
- `CHATBOT_MODO2_WORKERS_ENABLED (default: 1)` — app/main.py:93

## Migrations

- `0001` — alembic/versions/0001_schema_inicial.py
- `0002` — alembic/versions/0002_leads_consentimentos.py
- `0003` — alembic/versions/0003_mensagens_unique_provider.py
- `0004` — alembic/versions/0004_catalog_attribution.py
- `0005` — alembic/versions/0005_numeros_autorizados.py
- `0006` — alembic/versions/0006_lead_attribution_touch.py
- `0007` — alembic/versions/0007_sessao_fotos_whatsapp.py
- `0008` — alembic/versions/0008_cadastro_sessao_e_nome.py
- `0009` — alembic/versions/0009_operacao_menu_sessao.py
- `0010_lead_ctwa` — alembic/versions/0010_lead_ctwa.py
- `0011_ctwa_auditoria` — alembic/versions/0011_ctwa_auditoria.py
- `0012_grupo_estoque_whatsapp` — alembic/versions/0012_grupo_estoque_whatsapp.py
- `0013_tracking_pendente_conversa` — alembic/versions/0013_tracking_pendente_conversa.py
- `0014_loja_operacional_projecao` — alembic/versions/0014_loja_operacional_projecao.py
- `0015_whatsapp_canais` — alembic/versions/0015_whatsapp_canais.py
- `0016_lead_google_click_ids` — alembic/versions/0016_lead_google_click_ids.py
- `0017_canal_id_conversas_msg` — alembic/versions/0017_canal_id_conversas_msg.py
- `0018_notificacoes_operacionais` — alembic/versions/0018_notificacoes_operacionais.py
- `0019_canal_principal_estoque` — alembic/versions/0019_canal_principal_estoque.py
- `0020_fila_vendedor` — alembic/versions/0020_fila_vendedor.py
- `0021_oferta_lead` — alembic/versions/0021_oferta_lead.py
- `0022_conversa_followup_toques` — alembic/versions/0022_conversa_followup_toques.py
- `0023_fila_vendedor_usuario` — alembic/versions/0023_fila_vendedor_usuario.py
- `0024_cloud_evento_falho` — alembic/versions/0024_cloud_evento_falho.py
- `0025_canal_cloud_por_loja` — alembic/versions/0025_canal_cloud_por_loja.py

## Testes

- macOS: `cd chatbot-api && .venv/bin/python -m pytest -q`
- Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
