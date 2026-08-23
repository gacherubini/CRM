---
decidido: 2026-07-14
nao_reproponha: auto-stop ou keepalive no evolution2037 e no n8n2037
---
# Evolution e n8n ficam sempre ligados; os outros dormem

Decisao do dono: `evolution2037` (a sessao do WhatsApp cai se a maquina suspender) e
`n8n2037` (automacoes e cron) ficam **sempre ligados** — `auto_stop_machines = false`,
`min_machines_running = 1` no `fly.toml` e `autostop=off` aplicado na maquina. Os demais
apps seguem em auto-stop e acordam sob demanda em 1-2 s.

Nao propor economia ligando auto-stop nesses dois; e nao propor keepalive nos outros, que
so acelera o fork de volume do Fly.

O combinado geral e **tudo no minimo de recursos**: 512 MB para portal, catalogo, estoque e
chatbot; 2 GB para o motor (Chromium, proposital); 1 GB para n8n e Evolution.
