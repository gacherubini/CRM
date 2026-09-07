---
gatilho: driver de banco reprova um passo olhando o estado da janela em vez do campo
produto: motor-simulacao
custo: uma rodada perdida, e o mesmo erro ja tinha sido corrigido uma funcao adiante
fonte: repo
verificado_em: 2026-09-07
---
# O modal continuar aberto nao prova que a escolha falhou

Fontecred, sim `20260907-001124`. O driver clicou "Selecionar" no modal "Selecione o
modelo correto para esta placa", esperou o titulo sumir por 10s, nao sumiu, e levantou
`modelo_placa_nao_escolhido`. A screenshot desmente o codigo: **atras do modal aberto, o
formulario ja mostrava "FZ25 250 FAZER FLEX" em Selecione um produto**. O clique tinha
funcionado. O portal so nao fechou a janela.

O detalhe que faz esta lição valer: o mesmo driver ja tinha aprendido isso **uma funcao
adiante**. `_confirmar_produto_resolvido` existe desde 04/09 exatamente porque
"o clique nao deu erro" nao era criterio, e le `select#produto`. `_resolver_modal_placa`,
imediatamente antes, continuou julgando pela janela.

Regra: **o criterio de sucesso de um passo e o dado que o passo deveria ter gravado, lido
de volta da pagina.** Nunca a visibilidade de um container, nunca "o clique nao levantou
excecao". Vale para modal, overlay, toast e spinner — todos somem quando querem.

O que sobra do modal aberto e um problema separado e menor: ele vira overlay e esvazia
campo mais adiante (sim `20260904-151456`). Trata-se fechando best-effort **depois** de
confirmar a escolha, nao reprovando o passo.

Nao confundir com [[2026-08-23-driver-playwright-engole-o-clique-que-falha]]: la o clique
falhou e o `except: pass` escondeu. Aqui o clique funcionou e a checagem e que estava
olhando para a coisa errada. Os dois terminam no mesmo lugar — um `codigo_erro` que aponta
para a tela errada — por caminhos opostos.

Rodada de 07/09 00:00, IP residencial, placa FUV7G58 / R$ 21.900, apos a correcao:
Pan 38s OK (so o prazo 48), Bradesco 64s OK, Fontecred 82s OK, Santander 135s OK,
Motrix RECUSA — ver
[[2026-09-06-motrix-recusa-sem-motivo-e-200-com-lista-vazia]].

O Santander falhou **uma vez** antes disso com tela propria dele ("Ocorreu um erro ...
(Erro TimeOut)") e passou na repetida, sem nenhuma mudanca de codigo. Portal de banco a
meia-noite erra sozinho: antes de abrir bug, repita.
