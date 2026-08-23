# Propostas de mudanca no protocolo

O agente escreve aqui quando **este protocolo** falhou — nao quando o codigo
falhou. Uma linha por proposta: o que falhou, o que mudaria. O dono le e decide.
Proposta aplicada sai desta lista e entra no `SKILL.md`.

| Data | O que falhou no protocolo | O que eu mudaria |
|---|---|---|

## Aplicadas

- **2026-08-23 — o selo fazia o frescor gritar lobo.** O passo 2 comparava
  `<selo>..HEAD`, e o selo e lido antes do commit que grava o mapa: quando o
  `AGENTS.md` §6 era obedecido (regerar e commitar junto), o diff listava as
  mudancas do proprio commit certo. Virou `gerar_mapa.py --frescor`, que deriva
  a base de `git log -1 -- mapa/`. Achado pelo ensaio cego; aprovado pelo dono
  no mesmo dia. Teste `test_o_bug_que_esta_proposta_consertou`.
