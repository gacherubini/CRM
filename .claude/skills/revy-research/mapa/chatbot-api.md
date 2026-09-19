# chatbot-api · 65 rotas · 19 modelos · 4 workers · 4 flags · 29 migrations

Gerado de `2563e8b`. NAO editar a mao — saida de `gerar_mapa.py`.
Migration head: `0029_mensagem_audio`

## Rotas

- `GET /health/live` — app/main.py:524
- `GET /health/ready` — app/main.py:529
- `GET /version` — app/main.py:535
- `GET /webhook/cloud` — app/main.py:540
- `POST /webhook/cloud` — app/main.py:557
- `POST /webhook/mensagem` — app/main.py:803
- `POST /webhook/audio/transcrever` — app/main.py:828
- `POST /v1/operacao/roteamento` — app/main.py:864
- `POST /webhook/operacao/veiculos/foto` — app/main.py:884
- `GET /v1/conversas` — app/main.py:922
- `GET /v1/conversas/{telefone}/mensagens` — app/main.py:939
- `GET /v1/conversas/{telefone}/estado` — app/main.py:972
- `POST /v1/conversas/{telefone}/pode-responder` — app/main.py:989
- `PATCH /v1/conversas/{telefone}/estado` — app/main.py:1035
- `POST /v1/conversas/{telefone}/mensagens` — app/main.py:1098
- `POST /v1/conversas/{telefone}/audios` — app/main.py:1123
- `POST /v1/consentimentos` — app/main.py:1165
- `POST /v1/leads` — app/main.py:1178
- `POST /v1/integracoes/catalogo/interesses` — app/main.py:1189
- `GET /v1/leads` — app/main.py:1223
- `GET /v1/funil/eventos` — app/main.py:1233
- `GET /v1/auditoria/ctwa` — app/main.py:1252
- `GET /v1/atendimento/resumo` — app/main.py:1304
- `GET /v1/leads.csv` — app/main.py:1316
- `GET /v1/leads/{lead_id}` — app/main.py:1362
- `PATCH /v1/leads/{lead_id}/etapa` — app/main.py:1369
- `GET /v1/config/catalogo-bot` — app/main.py:1381
- `GET /v1/agente/config` — app/main.py:1426
- `GET /v1/agente/rascunho` — app/main.py:1476
- `PUT /v1/agente/rascunho` — app/main.py:1487
- `POST /v1/agente/publicar` — app/main.py:1502
- `POST /v1/agente/preview` — app/main.py:1529
- `GET /v1/agente/versoes` — app/main.py:1586
- `POST /v1/agente/versoes/{versao_id}/restaurar` — app/main.py:1606
- `GET /v1/estoque/buscar` — app/main.py:1624
- `GET /v1/estoque/por-placa/{placa}` — app/main.py:1650
- `GET /v1/estoque/veiculos/{veiculo_id}/midia-principal` — app/main.py:1667
- `POST /v1/internal/provisioning/state` — app/main.py:1755
- `POST /v1/simulacoes/solicitar` — app/main.py:1776
- `POST /v1/simular` — app/main.py:1815
- `GET /v1/whatsapp/canais` — app/main.py:1882
- `POST /v1/whatsapp/canais` — app/main.py:1894
- `POST /v1/whatsapp/canais/cloud/onboarding` — app/main.py:1922
- `POST /v1/whatsapp/canais/{canal_id}/principal-estoque` — app/main.py:1966
- `POST /v1/whatsapp/canais/{canal_id}/inativar` — app/main.py:1976
- `POST /v1/whatsapp/canais/{canal_id}/connect` — app/main.py:1986
- `GET /v1/whatsapp/canais/{canal_id}/status` — app/main.py:2003
- `POST /v1/whatsapp/canais/{canal_id}/disconnect` — app/main.py:2013
- `GET /v1/fila-vendedores` — app/main.py:2045
- `GET /v1/ofertas` — app/main.py:2054
- `POST /v1/ofertas/{oferta_id}/assumir` — app/main.py:2091
- `POST /v1/fila-vendedores` — app/main.py:2112
- `PATCH /v1/fila-vendedores/{vendedor_id}` — app/main.py:2131
- `DELETE /v1/fila-vendedores/{vendedor_id}` — app/main.py:2162
- `POST /v1/operacao/solicitacoes-simulacao-humana` — app/main.py:2183
- `POST /v1/operacao/responder` — app/main.py:2223
- `POST /v1/operacao/handoff-humano` — app/main.py:2275
- `POST /v1/operacao/moto-escolhida` — app/main.py:2323
- `GET /v1/operacao/grupo-estoque` — app/main.py:2351
- `PUT /v1/operacao/grupo-estoque` — app/main.py:2370
- `DELETE /v1/operacao/grupo-estoque` — app/main.py:2397
- `GET /v1/operacao/numeros-autorizados` — app/main.py:2404
- `POST /v1/operacao/numeros-autorizados` — app/main.py:2411
- `DELETE /v1/operacao/numeros-autorizados/{telefone}` — app/main.py:2422
- `POST /v1/operacao/veiculos` — app/main.py:2431

## Modelos

- `lojas` — app/models_db.py:19
- `loja_operacional_projecao` — app/models_db.py:33
- `whatsapp_canais` — app/models_db.py:57
- `fila_vendedor` — app/models_db.py:123
- `oferta_lead` — app/models_db.py:155
- `rodizio_ponteiro` — app/models_db.py:180
- `credenciais_servico` — app/models_db.py:187
- `conversas` — app/models_db.py:200
- `mensagens` — app/models_db.py:228
- `leads` — app/models_db.py:258
- `consentimentos` — app/models_db.py:315
- `catalog_attributions` — app/models_db.py:330
- `ctwa_auditoria` — app/models_db.py:362
- `numeros_autorizados` — app/models_db.py:385
- `grupos_estoque` — app/models_db.py:413
- `notificacoes_operacionais` — app/models_db.py:432
- `cloud_evento_falho` — app/models_db.py:473
- `agente_config_versao` — app/models_db.py:500
- `agente_config` — app/models_db.py:536

## Workers

- `CloudRetryWorker` — app/cloud_retry.py:140
- `FollowupWorker` — app/followup_job.py:64
- `NotificacoesOutboxWorker` — app/notificacoes_outbox_job.py:28
- `RodizioWorker` — app/rodizio_job.py:25

## Flags

- `CHATBOT_WHATSAPP_MODO2_ENABLED (default: '')` — app/config.py:149
- `MULTI_WHATSAPP_ENABLED (default: 0)` — app/config.py:152
- `CHATBOT_NOTIF_RETRY_ENABLED (default: 1)` — app/main.py:88
- `CHATBOT_MODO2_WORKERS_ENABLED (default: 1)` — app/main.py:100

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
- `0026_credencial_integracao` — alembic/versions/0026_credencial_integracao.py
- `0027_agente_config` — alembic/versions/0027_agente_config.py
- `0028_canal_onboarding` — alembic/versions/0028_canal_onboarding.py
- `0029_mensagem_audio` — alembic/versions/0029_mensagem_audio.py

## Testes

- macOS: `cd chatbot-api && .venv/bin/python -m pytest -q`
- Windows: `cd chatbot-api && .\.venv\Scripts\python.exe -m pytest -q`
