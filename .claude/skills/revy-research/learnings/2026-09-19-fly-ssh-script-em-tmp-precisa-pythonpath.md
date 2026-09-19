---
gatilho: rodar script python via fly ssh console
produto: chatbot-api
custo: escrita remota de teste falhando com ModuleNotFoundError depois do cd certo
fonte: repo
verificado_em: 2026-09-19
---
# Script em /tmp via `fly ssh console` não importa `app` sem PYTHONPATH

Em 19/09, o `e2e-loop/fila-dono.sh` (stdin do `fly ssh console -a app2037`)
gravava o script num arquivo em `/tmp` e rodava `python` apontando pra ele
depois de `cd /srv/chatbot`: o `import app` falhava porque `sys.path[0]` é o
diretório do **script** (`/tmp`), não o cwd. O `cd` não adianta.

Fix: `PYTHONPATH=/srv/chatbot` explícito na chamada. `python -m` (o que o
`provisionar.sh` usa) não sofre disso, porque o `-m` põe o cwd no caminho.

Não é o mesmo problema do learning do `-C` no Windows (quoting entre camadas):
este é resolução de módulo do Python e vale nos dois SOs.
