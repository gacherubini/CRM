---
gatilho: driver preenche campo com mascara e o portal reclama do valor, ou o passo SEGUINTE morre em campo_nao_encontrado
produto: motor-simulacao
custo: 9 tarefas do PAN em 19/09 saindo como "campo Placa nao encontrado" — a Placa nao tinha nada a ver
fonte: repo
verificado_em: 2026-09-19
---
# Campo com mascara aceita menos do que voce digitou, e o erro aparece tres passos depois

Sim `023321da` (19/09, print do evento 7676). O go!PAN mostrava:

    (59) 90333-655
    Telefone ou DDD invalidos.

Onze digitos foram digitados, dez ficaram, e o **primeiro** foi o que sumiu:
`55990333655` virou `5990333655`, que a mascara re-renderizou como DDD 59 — que
nao existe. Com o telefone invalido o portal **desabilita a busca de placa**;
o driver entao procurou o campo Placa, nao achou, e saiu com
`campo_nao_encontrado - campo Placa nao encontrado`.

O resultado no banco acusava um campo que estava perfeito. Duas rodadas inteiras
foram gastas olhando seletor de placa.

A causa de fundo nao era a mascara, era o **silencio**: `_digitar_mascarado`
(`app/motor/pan_portal.py:523`) conferia os digitos em 3 tentativas e, quando as
tres falhavam, caia num `box.fill(valor)` final **sem conferir nada** e retornava
como se tivesse dado certo. Campo torto + retorno normal = diagnostico errado
garantido.

O que mudou (19/09):

- espera de 150 ms **depois de limpar** e antes de digitar — a diretiva de
  mascara re-renderiza apos `Control+a`/`Delete` e engole a tecla de quem digita
  em cima dela;
- o `fill` de ultimo recurso tambem e conferido;
- nada bateu? levanta `IntervencaoNecessaria("campo_nao_confere")` dizendo o
  **campo** e **quantos** caracteres faltaram. Nunca o valor: o mesmo helper
  carrega CPF e celular.

Regra geral: **helper de preenchimento que nao confere e que nao levanta produz
bug em outro lugar.** O sintoma sempre aparece no passo seguinte, e o passo
seguinte leva a culpa.

Primos: [[2026-09-16-modal-agente-go-pan-reabre-depois-do-login]] — mesmo
`campo_nao_encontrado` no mesmo driver, causa completamente diferente (overlay);
[[2026-09-19-print-do-driver-sai-da-tela-errada]] — a outra forma de o
diagnostico mentir no PAN/Motrix.
