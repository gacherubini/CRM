---
gatilho: simulacao de banco volta "sem oferta" e voce vai procurar bug no driver
produto: motor-simulacao
custo: o card do Motrix ficou uma sessao inteira com a causa errada escrita nele
fonte: repo
verificado_em: 2026-09-16
---
# `motrix_sem_oferta` e decisao de credito, nao defeito de robo

O card de 04/09 registrou "falta **um CPF que o Motrix aprove**" e, junto, a suspeita de
que o driver estivesse errando o passo. As duas leituras estavam mal fundamentadas. O que
a captura de rede mostra:

    POST /v3/loan-vehicle-simulations/calculation  ->  200  []

Lista vazia. Sem `message`, sem `reason`, sem `errors`, sem `note` — conferido no corpo da
resposta e no registro da simulacao depois dela (`GET/PUT /loan-vehicle-simulations/<id>`).
O texto "Nao ha oferta de credito disponivel para este cliente" e o Angular renderizando
array de tamanho zero. Nao existe motivo para o driver ler, porque o portal nao manda um.

Duas hipoteses caras foram derrubadas com **uma** rodada cada, comparando o corpo enviado:

| rodada | baseValue | entrada | financiado | LTV sobre a FIPE | resposta |
|---|---|---|---|---|---|
| 04/09 | 21.900 | 0 | 21.900 | 112% | `[]` |
| 06/09 | 19.610 | 5.000 | 14.610 | 75% | `[]` |

- **Nao e LTV.** 112% e 75% recusam igual.
- **Nao e a mascara do campo de entrada.** `downPaymentValue` chegou `5000.00` na
  requisicao. O `_preencher` do driver ja relia o campo; a captura confirma do outro lado.
- **Nao e a regra do produto.** R0 tem `minLoanValue 0`, `maxLoanValue 999999999`,
  `minTerm 0`, `maxTerm 999`, sem limite de idade. Ela nao barra nada nessa faixa.
- **Nao e conta sem linha de credito.** `GET /v3/loans/search` lista 3 propostas reais da
  loja em 20, 21 e 27/08 — mesma regra R0, prazo 48, taxa ~5,1% a.m., financiado
  17,4k a 18,0k, e **uma delas com entrada 0**.

"Cliente Elegivel" (status 104) do passo 1 tambem engana: o `person-validation` manda so
CPF e celular e devolve `income: null`, `birthDate: null`, `loanMaxValue: null`. E checagem
cadastral, nao aprovacao de credito.

**E nao e o tomador.** Tres CPFs diferentes, todos "Cliente Elegivel", todos `[]` —
inclusive um perfil de 64 anos, parecido com os dois que a loja aprovou (44 e 60). E o CPF
de teste recebeu oferta de **quatro** bancos no mesmo dia, com a mesma moto: Fontecred
(24/36/48), Pan (48), Bradesco (24/36/48, financiando os R$ 21.900 sem entrada) e Santander
(24/36/48). Credito ele tem. O outlier e o Motrix.

O que sobra e a conta ou o funding: os tres contratos sairam em 20, 21 e 27/08 e nada
ofertou depois disso. Quem responde e o gerente do Motrix, nao o codigo — mesma prateleira
do login desativado do BV.

Armadilha de raciocinio a nao repetir: eu li idade nos tres contratos (60, 44, 44) e
conclui perfil de credito, ignorando a tabela dos quatro bancos que ja estava no repo. Tres
pontos nao sao amostra; a rodada do `probe_todos` era o dado forte e estava a um `cat` de
distancia.

Regra pratica para qualquer banco daqui em diante: **antes de mexer no driver, compare o
corpo que ele envia com o de uma operacao que o banco aceitou.** O portal guarda as
fechadas (no Motrix, `/loans`), e a comparacao custa zero login se a sessao estiver quente.
Ler o DOM diz que a tela mudou; ler a requisicao diz se o pedido estava certo.

Primos: [[2026-09-04-spa-com-api-nao-e-driver-de-api]] — a mesma captura de rede que nao
serve para trocar o Playwright por HTTP e a que responde esta pergunta em minutos; e
[[2026-08-23-driver-playwright-engole-o-clique-que-falha]] — la o codigo de erro final
apontava para a tela errada, aqui o card apontava para a causa errada.

**16/09 — `consulta_cpf_sem_resposta` em prod nao e o driver.** Duas sims do Fly
(`f2773195`, `9c66b130`) queimaram 120s x2 na validacao do CPF sem nenhuma das
frases da espera aparecer. Na mesma hora, o `probe_todos --bancos motrix` do IP
residencial do dono respondeu em **22s** com `motrix_sem_oferta` (RECUSA), driver
correto. Nas mesmas sims o Bradesco saiu `saida_de_rede_divergente` (IP do proxy
diferente do esperado) — a suspeita e o caminho de rede do worker, nao o
portal: **olhe o proxy/IP de saida antes de mexer no driver**. O print do evento
(na branch `triagem-simulacoes`) confirma a tela na proxima ocorrencia pos-deploy.

**19/09 — o print de 18/09 respondeu: era tela nova, nao rede.** O blob de
`consulta_cpf_sem_resposta` (sim `afa4e02d`) mostra o passo "Consulta CPF" com o
CPF preenchido e, em vermelho, **"Cliente não elegível"** — o portal RESPONDEU. A
espera do driver (`motrix.py:461`) so conhecia o positivo "Cliente elegível" e
"CPF inválido"; "Cliente não elegível" nao casava, entao o passo esperava os 120s
e saia como erro tecnico. E recusa de negocio:

- `NAO_ELEGIVEL` passou a casar na espera e no parser, e sai `credito_recusado`;
- `motrix_sem_oferta` tambem virou `credito_recusado` — e o unico codigo que o
  Portal pinta como "Credito recusado" (`_veredito_do_codigo`), entao recusa de
  credito parava de aparecer como "Falhou".

Licao reforcada: para banco com recusa, **comece pelo print do evento** — ele
responde em um olhar o que o `codigo_erro` esconde.
