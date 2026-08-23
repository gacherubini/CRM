# Propostas de mudanca no protocolo

O agente escreve aqui quando **este protocolo** falhou — nao quando o codigo
falhou. Uma linha por proposta: o que falhou, o que mudaria. O dono le e decide.
Proposta aplicada sai desta lista e entra no `SKILL.md`.

| Data | O que falhou no protocolo | O que eu mudaria |
|---|---|---|
| 2026-08-23 | **O passo 2 (frescor) vai gritar lobo logo depois do commit certo.** O selo guarda o SHA de quando o mapa foi gerado, que e sempre ANTERIOR ao commit que grava o mapa. Quando o §6 for obedecido — mexeu em rota, regerou o mapa, commitou os dois juntos — o `git diff <selo>..HEAD -- <produto>/` do passo 2 vai listar as proprias mudancas daquele commit e acusar o produto como desatualizado. Ou seja: quanto mais certo o agente age, mais o aviso dispara a toa. E o modo de falha que o design nomeia (`aviso que dispara a toa e aviso que se aprende a ignorar`) chegando pela porta dos fundos. | Nao usar o SHA do selo para frescor. Derivar do git: `git log -1 --format=%H -- .claude/skills/revy-research/mapa/` da o commit que atualizou o mapa por ultimo, e o diff passa a ser `<esse>..HEAD -- <produto>/`. Fica correto sozinho, inclusive quando mapa e codigo viajam no mesmo commit, e dispensa o selo para esta finalidade (ele continua util como procedencia). Achado pelo ensaio cego da Task 11; nao implementado porque muda o protocolo, e protocolo e do dono. |
