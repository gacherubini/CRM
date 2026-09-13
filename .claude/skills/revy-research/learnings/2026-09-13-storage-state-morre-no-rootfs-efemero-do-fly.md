---
gatilho: sessão quente (storage_state) não é reusada entre jobs nos workers Playwright do Fly, ou banco pede captcha em todo login
produto: motor-simulacao
custo: todo job do Bradesco era login frio; o reCAPTCHA voltava mesmo com a sessão gravada
fonte: infra
verificado_em: 2026-09-13
---
# storage_state no worker do Fly morre no stop: o rootfs é efêmero

As machines `motor-worker-*` foram criadas pela Machines API **sem volume** e com
`persist_rootfs` no default (`never`). O rootfs do Fly é "blank slate on every
startup", então `/srv/data/storage_state` (o default de `MOTOR_STORAGE_STATE_DIR` é
`data/storage_state`, relativo ao WORKDIR `/srv`) é apagado toda vez que o worker para
por idle. O `MOTOR_STORAGE_STATE_DIR` do `[env]` do `fly.worker.toml` nem chega nessas
machines — mesma armadilha do deploy que não atualiza worker de banco.

Evidência em produção (Omni, 13/09): `sessao_gravada` às 02:18:25 e `sessao_fria` às
02:26:12 na **mesma** machine. O driver tinha gravado a sessão; o arquivo não estava
mais lá no boot seguinte.

Consequência: warm session nunca funcionou de fato nos workers do Fly — todo job era
login frio, e o `captcha_login` do Bradesco reaparecia mesmo depois de corrigir o
driver para gravar o `storage_state` logo após o login.

Correção operacional:

    fly machine update <id> -a motor2037 --rootfs-persist always --skip-start -y

em cada worker. `always` (não `restart`) sobrevive também a deploy de imagem, que aqui
é frequente. `fly machine status <id> -d` mostra o campo em `rootfs.persist`. Volume
montado em `/srv/data` ou o blob cifrado no Postgres são as alternativas duráveis.
`persist_rootfs` é cache: o Fly ainda pode limpar em manutenção.

Primo: `2026-09-12-fly-deploy-nao-atualiza-worker-por-banco` — as machines criadas
pela Machines API são a fonte da maioria das surpresas com worker de banco.
