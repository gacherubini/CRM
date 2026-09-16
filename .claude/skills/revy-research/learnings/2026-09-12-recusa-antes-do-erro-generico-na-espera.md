---
gatilho: tela de recusa de crédito cai em erro técnico genérico em vez de RejeicaoNegocio
produto: motor-simulacao
custo: 4 bancos recusando o cliente de teste e os 4 saindo como FALHA técnica (32s a 274s cada)
fonte: repo
verificado_em: 2026-09-16
---
# Recusa do banco se checa ANTES do erro genérico na espera

Em 12/09 os quatro drivers viram a tela real de recusa e os quatro
classificaram errado: Pan culpou o campo Celular (`campo_nao_encontrado`),
Fontecred e os demais caíram em `portal_simulacao_erro` / `portal_falhou`.
O caso que engana: o Fontecred falhou no **mesmo segundo** do
`simulacao_enviada` com `portal_simulacao_erro`, mas o texto visível do modal
("Este CPF não atende aos critérios mínimos…") não contém "Ocorreu um erro"
nem "falha" — alguma outra coisa na tela da recusa casa o regex genérico, e
ele vencia a corrida porque era checado primeiro.

Regra: em todo `_passo_aguardar_*`, a sonda de recusa (`_levantar_se_recusado`)
vem **antes** do `Ocorreu um erro|falha`. Texto de recusa nunca aparece em
tela de aprovado (há teste por banco garantindo), então a prioridade não gera
falso positivo; a ordem inversa gera falso erro técnico.

**16/09 — o mesmo padrão fora da espera.** O Fontecred recusou o CPF durante o
passo do veículo: o modal ("Este CPF não atende aos critérios mínimos…") ficou
por cima, o `select#produto` não resolveu e o resultado saiu
`veiculo_nao_resolvido` (falha), não `credito_recusado`. A sonda agora roda
depois da consulta do CPF (`_passo_dados_pessoais`), no polling do produto
(`_aguardar_produto`) e imediatamente antes do erro de veículo
(`_confirmar_produto_resolvido`). Padrão geral: **qualquer passo que espera a
tela mudar é um passo onde a recusa pode ser a resposta**.

**16/09 18:00 — a mesma recusa pode ter mais de uma frase.** O go!PAN mostrou
uma SEGUNDA tela de recusa depois do Simular ("Proposta recusada / Não
conseguimos aprovar o crédito com as condições digitadas") que o regex não
conhecia: a espera queimou os 505s e saiu `timeout_driver` (sim 9c66b130, placa
TKL5E99). O regex de recusa agora cobre as duas frases. Ao ver um banco queimar
o timeout de ofertas, compare o print com o regex antes de culpar o portal.

Primos: [[2026-09-06-motrix-recusa-sem-motivo-e-200-com-lista-vazia]] — lá a
recusa era lista vazia sem frase; aqui a frase existe mas o erro genérico a
encobria. E a armadilha do `motor-simulacao/README.md`: "`codigo_erro` aponta
para a tela errada — olhe o screenshot do primeiro evento de falha".
