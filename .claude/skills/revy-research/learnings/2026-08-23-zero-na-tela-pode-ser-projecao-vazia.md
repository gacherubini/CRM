---
gatilho: investigar numero zerado numa tela da Loja
produto: portal-gestao
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# Zero na tela costuma ser projecao vazia, nao dado ausente

O Copiloto dava "0 leads este mes" numa loja com ~413 leads reais. O funil le `total_leads`
da projecao local `FunilEvento` (eventos `lead_criado` materializados do Chatbot), e essa
projecao estava **vazia** naquela loja. A contagem viva
(`funil_periodo.elegiveis`, de `chatbot.listar_leads()` — a mesma fonte do painel "Por onde
as pessoas chegam", que mostrava 413 certo) era calculada e **descartada**, porque o
fallback so entrava quando o valor era `None`, e ele era `0`.

Antes de sair procurando o dado, pergunte de qual das duas fontes a tela le: a **projecao
materializada** ou a **contagem viva** por HTTP. Fallback que testa `None` em vez de valor
falsy erra exatamente no caso interessante.

Corrigido em 14/08/2026 (commit `bc5fc5b`) so para a **contagem**: com projecao vazia e
Chatbot com leads no periodo, `total_leads` usa `elegiveis` e o status vira `parcial`.
**Segue em aberto** por que a `FunilEvento` nao materializa os `lead_criado` daquela loja —
enquanto isso, as **taxas** e os tempos do funil continuam sem numero, porque a coorte vem
da projecao vazia.
