---
gatilho: trabalhar no repo com outra sessao de agente aberta ao mesmo tempo
produto: todos
custo: meia hora depurando um bug que era commit alheio
fonte: repo
verificado_em: 2026-08-24
---
# Suite vermelha no meio da tarefa pode ser commit de outra sessao, nao seu

Em 24/08 duas sessoes trabalharam neste repo ao mesmo tempo. Do lado de ca, no
espaco de uma tarefa: o `--verificar` passou, depois reprovou com 10 divergencias
em `chatbot-api/app/models_db.py`; um teste que contava 25 migrations passou a
contar 26; e o contador de learnings da `como-funciona.html` furou **tres vezes**.
Nenhuma das tres tinha a ver com a mudanca que estava sendo feita — eram os
commits `c370f13`, `062033a`, `807e97f`, `23210a6` e `c8cb66e` entrando por baixo.

O primeiro reflexo — "meu patch quebrou isso" — custa caro. Antes de depurar
teste que passou ha cinco minutos, rode `git log --oneline -3` e `git status`. Se
o `HEAD` mudou, o chao mudou.

Consequencias praticas:

- **Nunca `git add -A` nem `git add <pasta>` inteira.** Some so os seus caminhos.
  Ainda assim conte com o inverso: os 16 carimbos de `verificado_em` desta sessao
  foram varridos para o commit `c8cb66e` da outra, que adicionou a pasta
  `learnings/` inteira.
- **Nao mexa no indice para testar coisa nenhuma.** `git add` de teste entra no
  commit alheio. Para exercitar hook ou gatilho, isole com
  `GIT_INDEX_FILE=<arquivo temporario>` — os comandos git filhos herdam a
  variavel e o indice de verdade nao e tocado.
- **Nao regere o mapa em cima de arvore com mudanca alheia nao commitada.** O
  mapa ficaria descrevendo codigo que ninguem commitou.
- Numero chumbado a mao em teste (`assertEqual(len(entradas), 25)`) vira alarme
  falso no primeiro commit dos outros. Derive a contagem da pasta.

Contexto util: `--verificar` compara o mapa commitado com o codigo da **arvore de
trabalho**, entao ele acende assim que outra sessao commita codigo sem regerar.
Isso e o comportamento certo, e desde 24/08 o hook `.githooks/pre-commit` regera e
inclui o mapa sozinho — ver [[2026-08-23-teste-verde-nao-prova-que-a-feature-existe]]
para o principio irmao: verde nao prova o que voce acha que prova.
