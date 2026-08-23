---
gatilho: dimensionar limite da Cloud API ou tratar verificacao de CNPJ como bloqueio
produto: chatbot-api
---
# O teto de 250 conta so conversa que a empresa inicia

Conta **nao verificada** na Cloud API tem teto de **250 clientes unicos por 24h rolantes**
— e o teto conta **so conversa iniciada pela empresa** (template, fora da janela). Conversa
que o cliente inicia, e toda troca dentro das 24h contadas a partir da ultima mensagem
**dele**, nao consome nada. So a mensagem do cliente reinicia a janela; a do bot nao
estende.

**Nao ha prazo para verificar.** Da para operar nao verificado por tempo indeterminado, e
existe subida de tier sem verificacao (1.000 contatos unicos em 30 dias com qualidade alta
sobe para 1.000/24h). O que a verificacao do CNPJ compra nao e volume: e **nome de
exibicao** (sem ela o cliente ve os digitos crus), **mais de 2 numeros** (a terceira loja
exige CNPJ) e disparo em massa para a base.

Desde 07/10/2025 o limite e **por portfolio**, nao por numero: espalhar em mais numeros nao
ganha capacidade. A saida de escala e Embedded Signup / Tech Provider, com WABA no
portfolio de cada loja.

Como o funil e inbound por CTWA, o bot inteiro roda dentro da janela e o gasto real dos 250
e so follow-up de quem sumiu (ordem de 15-20/dia). Tratar o CNPJ como bloqueador atrasa o
lancamento a toa: priorize-o na terceira loja ou na primeira campanha para a base. O risco
a vigiar no lugar do teto e a **nota de qualidade** — bloqueio/denuncia acima de 2-3%
derruba o numero, e cutucada repetida em quem nao responde cabe na regra e mesmo assim
queima.
