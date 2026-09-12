---
gatilho: deployar o motor2037 ou mudar env/timeout de um worker de banco
produto: motor-simulacao
custo: bug de lease atribuido ao codigo quando metade era config que nunca chegou
fonte: infra
verificado_em: 2026-09-12
---
# `fly deploy` do motor2037 nao atualiza os workers de cada banco

`motor-worker-bradesco`, `-santander`, `-fontecred` e `-pan` foram criados pela Machines
API e **nao tem process group**. O `fly deploy . -a motor2037 -c deploy/fly/3vm/fly.worker.toml`
so atualiza a Machine do grupo `app` (`dark-waterfall-6402`). Em 12/09 o deploy terminou
com exit 0 e os quatro workers seguiram na imagem velha.

O `[env]` do `fly.worker.toml` tambem **nao chega neles**. A config de cada worker tinha so
`MOTOR_WORKER_PROVEDOR` e `MOTOR_WORKER_TIPOS`; o resto caia no default do codigo. O toml
dizia `MOTOR_TASK_LEASE_SECONDS=480`, mas o Bradesco rodava com **300 s** — o lease que
vencia no meio do "Analisando dados" em 10/09.

Depois do `fly deploy`, para cada worker (continua `stopped`):

    fly image show -a motor2037
    fly machine update <id> -a motor2037 --image <registry.fly.io/motor2037:deployment-...> \
      --env CHAVE=valor --skip-start -y

O `--env` do `machine update` **mescla**: `PROVEDOR` e `TIPOS` ficam. Confira com
`fly image show -a motor2037` (todas na mesma tag) e
`fly machine status <id> -a motor2037 -d` (bloco `env`).
