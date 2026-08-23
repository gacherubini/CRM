---
gatilho: escrever teste do outbox de provisionamento do Control
produto: revy-trafego
custo: um teste vermelho acusado de bug por 8 dias
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# Destino real no teste do outbox esta errado por construcao

`test_process_pending_falha_marca_failed_e_incrementa_attempts` falhava com
`MultipleResultsFound` desde antes de 08/08/2026 e parecia bug do outbox. **Era bug do
teste.** Os hooks de provisionamento fazem fan-out para os **cinco** destinos reais
(chatbot, estoque, portal, motor, catalogo) e fazem isso **duas vezes** durante
`_store_with_snapshot`, porque o snapshot muda de versao entre criar a loja e configurar o
portfolio: dois `event_id`, dois eventos legitimos, 10 linhas no outbox antes de o teste
enfileirar qualquer coisa. O teste usava o destino real `"motor"` com `.one()` filtrando
por `(loja_id, destination)` e sempre achava 2. `enqueue_delivery` e idempotente por
`event_id`, e versoes diferentes **sao** eventos diferentes: o outbox esta certo.

Neste arquivo, todo teste que afirma sobre "a" linha de um destino real esta errado por
construcao. Use **destino sintetico** (ex.: `"motor-falha"`, que os hooks nunca emitem) e
afirme por `row.id`, como fazem os testes vizinhos. Corrigido em 16/08/2026; a suite do
revy-trafego foi a 504 passed, 0 failed.
