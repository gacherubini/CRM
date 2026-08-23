---
decidido: 2026-08-23
nao_reproponha: a skill editar o proprio SKILL.md
---
# O `SKILL.md` nao se auto-edita; a valvula e `propostas.md`

O `SKILL.md` carrega em **todo** disparo da skill. Se o agente puder edita-lo sozinho, ele
deriva: vira 400 linhas que ninguem revisou e que todo mundo paga em contexto para sempre.

Achou que o protocolo esta errado? escreva **uma linha** em
`.claude/skills/revy-research/propostas.md` e siga a tarefa. O humano decide o que entra.

Isso vale so para o `SKILL.md`. `learnings/` e `decisoes/` crescem e sao podados pelo
proprio agente, e o mapa e saida de script — erro no mapa e erro no gerador, nunca edicao a
mao.
