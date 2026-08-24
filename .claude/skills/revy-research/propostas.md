# Propostas de mudanca no protocolo

O agente escreve aqui quando **este protocolo** falhou — nao quando o codigo
falhou. Uma linha por proposta: o que falhou, o que mudaria. O dono le e decide.
Proposta aplicada sai desta lista e entra no `SKILL.md`.

| Data | O que falhou no protocolo | O que eu mudaria |
|---|---|---|
| 2026-08-24 | O passo 2 manda seguir calado quando ouve `mapa em dia`, e agora o `--frescor` pode imprimir tambem os learnings que pedem reconferencia — saida que o protocolo nao descreve. | Uma frase no passo 2: "listou learning a reconferir? confira antes de decidir em cima dele e carimbe `verificado_em`". |
| 2026-08-24 | Nada no protocolo diz que `fonte: repo` podia declarar a afirmacao que o script confere. Hoje o `--verificar` so prova que o caminho citado existe; que `.metric-grid` ainda seja `repeat(4, 1fr)` continua dependendo de alguem reler. | Campo opcional `ancora:` no cabecalho do learning (`arquivo` + trecho que precisa continuar la), conferido pelo `--verificar`. Custa uma linha por learning e transforma apodrecimento silencioso em suite vermelha. |

## Aplicadas

- **2026-08-23 — o selo fazia o frescor gritar lobo.** O passo 2 comparava
  `<selo>..HEAD`, e o selo e lido antes do commit que grava o mapa: quando o
  `AGENTS.md` §6 era obedecido (regerar e commitar junto), o diff listava as
  mudancas do proprio commit certo. Virou `gerar_mapa.py --frescor`, que deriva
  a base de `git log -1 -- mapa/`. Achado pelo ensaio cego; aprovado pelo dono
  no mesmo dia. Teste `test_o_bug_que_esta_proposta_consertou`.
