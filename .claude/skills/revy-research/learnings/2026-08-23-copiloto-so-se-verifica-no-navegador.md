---
gatilho: mexer no JS de uma tela do portal
produto: portal-gestao
custo: 2 bugs em producao em 2 dias
fonte: repo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# `pytest` renderiza o HTML e nao executa uma linha de JS

O chat do Copiloto (`portal-gestao/app/templates/loja/copiloto.html`) tem toda a logica em
JS inline: renderizador de markdown, revelacao progressiva, polling. **Pytest so prova que
as strings existem no HTML.** Dois bugs reais passaram por essa cegueira em 15-16/08/2026:
a revelacao progressiva nunca rodava (`terminar()` chamava `revelarTudo()` no mesmo tick
em que `revelar()` agendava o rAF); e aba oculta congela `requestAnimationFrame`, entao a
resposta sumia ate o dono voltar para a aba — e trocar de aba durante os 10-45 s de espera
e o uso normal dele, nao o caso raro.

Mudou JS? suba local e olhe, alem dos testes. Receita (~2 min): script Python que aponta
`PORTAL_DATABASE_URL` para um sqlite em arquivo, define os segredos de sessao e de API com
valores de mentira, liga `REVY_LOJA_SHELL_ENABLED` e `REVY_LOJA_COPILOTO_ENABLED`, desliga
entitlements e os workers, cria `Usuario` + `LojaOperacionalProjecao(state="ativa")`, chama
`criar_turno`/`concluir_turno` para semear uma resposta com negrito, lista e tabela, e por
fim `uvicorn.run(app)`. Armadilhas: a tabela e `usuarios` (nao `usuario`) e o script precisa
de `sys.path.insert` apontando para `portal-gestao/`.

Automacao de navegador nao substitui: ela estrangula a aba em segundo plano, o rAF nao
dispara e esperar por uma promise de rAF trava o renderizador. Olhe voce mesmo.
