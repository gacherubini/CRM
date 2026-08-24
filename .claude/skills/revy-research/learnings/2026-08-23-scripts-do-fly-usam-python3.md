---
gatilho: ligar ou desligar as maquinas do Fly pelos scripts do repo
produto: deploy
custo: lab ligado a noite inteira
fonte: repo
verificado_em: 2026-08-24
---
# `down-all.sh` diz "nenhuma machine" e nao para nada

`deploy/fly/down-all.sh` e `up-all.sh` parseiam o `fly machine list --json` com
**`python3`**, que nao existe no Windows do dono (so `python`). O pipe falha em silencio,
o script imprime "nenhuma machine" para todos os apps e **nao para nada** — parece que
derrubou o lab e os apps seguem `started` gastando.

A correcao (detectar `python3 || python`) segue **pendente** desde 01/08/2026.

Enquanto isso, pare na mao — so `stop`, nunca apagar volume ou app:

    export PATH="$HOME/.fly/bin:$PATH"
    fly machine list -a <app>
    fly machine stop <ID> -a <app>

Apps do 3-VM: `app2037 n8n2037 evolution2037 suite-pg motor2037` (o motor tem varias
machines/workers).
