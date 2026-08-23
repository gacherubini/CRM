---
gatilho: responder se uma feature ja foi implementada
produto: todos
custo: um produto morto em producao por dias
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# Confira contra a spec, nunca contra a suite

O Modo 2 do WhatsApp passou em 440 testes, teve PR revisado, mergeou e deployou — e
estava morto. O workflow do n8n cloud tinha **4 nos** (recebe da Meta, repassa ao
chatbot, fim) onde a spec pedia uma copia do fluxo de 32 nos trocando Evolution por Graph
API. O cliente escrevia para a central, a mensagem era gravada, **ninguem respondia e
nenhum vendedor era chamado**. Rodizio, oferta, trava, handoff e follow-up existiam, e
eram todos inalcancaveis.

O agravante: o validador **aprovava o stub** — ele cravava o formato de 4 nos. Validador
que sanciona o stub e pior que nenhum, porque da aval.

Quando o dono perguntar "isso foi implementado?", abra a **spec** e percorra o caminho do
usuario. Teste verde e merge limpo nao provam que a feature existe. Descoberto em
16/08/2026.
