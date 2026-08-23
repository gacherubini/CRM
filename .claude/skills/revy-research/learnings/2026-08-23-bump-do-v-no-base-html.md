---
gatilho: mexer em app.css do portal ou do control
produto: portal-gestao / revy-trafego
custo: um deploy com layout quebrado em producao
---
# Sao dois `app.css`, e cada mudanca precisa de `?v=` novo

Sao **dois** arquivos, um por shell: `portal-gestao/app/static/css/app.css` (Revy Loja,
`/` e `/app`) e `revy-trafego/app/static/css/app.css` (Revy Control, `/trafego`). Um
glob que so olha dentro de `portal-gestao` trata metade do problema e o Control fica
para tras — ja aconteceu.

O `StaticFiles` do Starlette **nao** manda `cache-control` (so `etag`/`last-modified`),
entao sem trocar a URL o navegador reusa o CSS velho. Em 14/08/2026 o redesign do
Copiloto foi para producao com o template novo e o `app.css?v=v12` velho: botao gigante,
composer sem estilo, tudo no topo.

Toda mudanca em `app.css` -> suba `?v=vN` na linha do `<link>` em `base.html` -> commit
-> deploy. Armadilha: as telas de auth (`login.html`, `convite_aceitar.html`,
`senha_esqueci.html`, `senha_redefinir.html`) **nao estendem** o `base.html` e tem cada
uma o seu proprio `?v=`.
