---
gatilho: conferir uma tela da Loja em largura estreita (390px) no navegador
produto: portal-gestao
custo: duas rodadas de captura que pareciam mobile e eram desktop
fonte: repo
verificado_em: 2026-09-11
---
# `resize_window` responde "Successfully resized" e nao redimensiona nada

Em 11/09/2026, conferindo as quatro telas reprovadas pela Loja, o plano era 1920 e 390.
O 1920 saiu. O 390 nao — e o pior e que ele **parecia** ter saido.

    resize_window(width=390, height=844)  ->  "Successfully resized window ... to 390x844"
    javascript: innerWidth                ->  1920

A janela do Chrome estava maximizada; o Windows ignora o resize e a ferramenta reporta
sucesso assim mesmo. As tres capturas seguintes vieram com 1568px de largura e o layout de
desktop inteiro, sidebar e tudo — se eu tivesse confiado nelas, teria dito "responsivo
conferido" olhando para a tela larga.

Segunda tentativa, iframe de 390px na propria pagina (viewport proprio, media query de
verdade): os quatro iframes renderizaram cinza com icone de documento quebrado e
`contentDocument` voltou `null`. O preview do `prototype_atendimento.py` nao serve
enquadrado.

Duas regras:

1. **Meça, nao confie na resposta do resize.** `innerWidth` e
   `documentElement.scrollWidth > clientWidth` custam uma chamada e dizem a verdade sobre
   largura e transbordo horizontal. Captura de tela nao prova viewport.
2. **Se as duas tentativas falharem, diga que nao conferiu** em vez de esticar o que a
   captura larga mostrou. Ficou assim no commit `db21a83`: 1920 conferido, estreito nao.

O caminho que sobra, quando o estreito for o ponto da tarefa: pedir ao dono para
desmaximizar a janela antes, ou abrir o DevTools no modo dispositivo na mao — nenhum dos
dois o agente faz sozinho.

Primo de [`2026-08-23-teste-verde-nao-prova-que-a-feature-existe.md`]: nos dois casos a
ferramenta respondeu "ok" para uma pergunta que ela nao tinha respondido.
