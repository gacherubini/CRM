---
gatilho: descobrir se uma flag de rollout esta ligada em producao
produto: deploy
fonte: infra
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# O `[env]` do toml nao diz o estado da flag

As flags `REVY_*` / `MULTI_*` do bundle `app2037` estao setadas como **secrets do Fly**,
nao no `[env]` do `deploy/fly/3vm/fly.app.toml`. E **secret vence `[env]`** — verificado
em 07/08/2026: o toml dizia `REVY_CONTROL_DASHBOARD_ENABLED = "0"` e a rota respondia
como ligada. Grep no toml da a resposta errada com toda a confianca.

Dois jeitos de descobrir o estado real sem ler valor (secrets sao write-only):

1. `fly secrets list -a app2037` mostra o **digest** de cada valor. Secrets com o mesmo
   digest tem o mesmo valor — compare com uma flag que voce sabe estar ligada e infira
   on/off sem decifrar nada.
2. Melhor ainda: bata na rota gated e olhe o status. 404 = off; 303/redirect para login
   = on. Ex.: `/trafego/app/control/dashboard`, `/app/loja/atendimento`.
