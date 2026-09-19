---
gatilho: harness bash que roda nos dois SOs
produto: chatbot-api
custo: suite inteira vermelha com mensagem apontando para o bot quando o quebrado era o oraculo
fonte: externo
verificado_em: 2026-09-19
---
# `python3` no Windows pode ser o stub da Store: teste execução, não presença

Em 19/09, o oráculo do loop e2e chamava `python3` direto. No Windows do dono,
o `python3` do PATH é o stub da Microsoft Store: **existe, sai 49 e imprime
nada** no stdout. As chamadas devolviam vazio, o wait estourava e todo cenário
ficava vermelho com "bot nao respondeu" — mensagem que aponta para o bot
quando o quebrado era o oráculo.

Fix em `e2e-loop/config.sh`: escolher o interpretador testando **execução**
(`python3 -c "" >/dev/null 2>&1`), não presença (`command -v`). Vale para
qualquer harness bash que roda nos dois SOs.
