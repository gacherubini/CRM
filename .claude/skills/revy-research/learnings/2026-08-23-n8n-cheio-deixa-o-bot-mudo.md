---
gatilho: o bot do WhatsApp parou de responder sem ninguem ter mexido no codigo
produto: n8n
custo: um dia de bot mudo em producao
---
# Bot mudo com tudo verde = volume do n8n cheio

Em 08/08/2026 o bot ficou mudo em producao com Evolution, n8n2037, app2037 e suite-pg
todos `started`, checks passando e `/healthz` = ok. Causa: o volume do `n8n2037`
(`/home/node/.n8n`, 1 GB) estava **100% cheio** — o `database.sqlite` tinha crescido para
856 MB guardando o payload inteiro de cada execucao (~1 GB por semana). Sem espaco, toda
execucao estoura `SQLITE_FULL`, o `POST /webhook/whatsapp-ai` responde **500**, a
Evolution entra em backoff de ~350 s e ninguem responde. Nada a ver com o codigo.

Diagnostico pela cadeia Evolution -> n8n -> Chatbot:

    fly logs -a evolution2037   # sendData-Webhook ... status code 500 = a quebra e no n8n
    fly logs -a n8n2037         # SQLITE_FULL / Error in handling webhook request
    fly ssh console -a n8n2037 -C "df -h /home/node/.n8n"

(No Windows o `fly ssh` cospe `Error: The handle is invalid` no fim, mas o output vem
inteiro.)

Fix aplicado em 08/08: volume estendido de 1 para 3 GB (`fly volumes extend`, redimensiona
online, sem restart) e retencao ligada por secret — janela deslizante de 7 dias, sem
salvar progresso nem execucao manual, com vacuum no startup. O banco estabiliza em ~1
semana de dados e para de crescer. Sucesso continua sendo salvo de proposito: "respondeu
errado" conta como execucao de **sucesso** no n8n, so crash conta como erro. Apagar
execucao do n8n nao perde conversa — elas vivem no `chatbot-api`.
