---
gatilho: mudar a cor de fundo de um estado ativo no tema escuro
produto: portal-gestao
fonte: repo
verificado_em: 2026-09-13
---
# Regra com `[data-theme]` vence classe nova por especificidade, em silêncio

`.nav-link.active { color: X }` (0,2,0) perde para
`[data-theme="dark"] .nav-link.active` (0,3,0) — o atributo conta como classe
na especificidade. Aconteceu na pílula ativa da navbar: fundo `--brand` com
texto `--brand-ink` ficou certo no claro e invisível no escuro (texto pintado
de `--brand` sobre fundo `--brand`), e o pytest não acusa nada de layout.

Quem pintar fundo de estado ativo no escuro precisa repetir o seletor com o
atributo: `html[data-theme="dark"] .nav-link.active` (0,3,1). Conferir no
navegador nos dois temas antes de dizer que acabou — vale para qualquer
componente com variante `[data-theme]` pré-existente no `app.css`.
