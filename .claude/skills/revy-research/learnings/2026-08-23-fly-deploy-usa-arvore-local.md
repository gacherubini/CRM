---
gatilho: deployar no Fly
produto: deploy
custo: um dia de reconciliacao
fonte: infra
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# `fly deploy` empacota a arvore local, nao o commit

`fly deploy` sobe a **arvore de trabalho**, nao o que esta no git. Em 14/07/2026 se
descobriu que motor e portal tinham sido deployados de arquivos nao-commitados: o banco
do Motor estava na migration 0011 e o repo ia so ate 0009; havia driver, `providers.py`
e telas que existiam **so dentro da imagem**. O deploy seguinte quebrou no
`alembic upgrade head` com "Can't locate revision 0011".

Se um deploy falhar com revisao alembic inexistente, producao esta **a frente** do repo:
recupere o codigo de dentro da imagem antes de qualquer novo deploy, porque deployar o
repo atrasado **regride producao**.

Antes de deployar: `git status` limpo e conferido contra `origin/main` (ja aconteceu de
o local estar 73 commits atras na hora do deploy).
