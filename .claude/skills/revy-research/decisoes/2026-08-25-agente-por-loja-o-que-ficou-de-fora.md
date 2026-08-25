---
decidido: 2026-08-24 e 2026-08-25
nao_reproponha: modelo de LLM por loja, teto de tokens por loja, cadencia de follow-up por loja, "so lead de anuncio", persona pronta, texto livre no lugar do formulario
---
# Agente por loja — o que o dono decidiu deixar de fora

Cada linha foi desenhada, avaliada e recusada. A spec inteira esta em
`docs/referencia-viva/specs/2026-08-24-agente-por-loja-design.md`.

| Recusado | Em vez disso | Por que |
|---|---|---|
| **modelo de LLM por loja** | um modelo global | perde-se canario na troca e plano comercial por modelo, e o dono aceitou isso com a consequencia a vista. Nada de coluna `modelo`, nada de rota, nada de tela no Control |
| **`maxOutputTokens` por loja** | 250 fixo para todas | 250 tokens sao ~175 palavras, muito mais do que qualquer resposta de WhatsApp deste bot. O teto nunca foi o limitador; a instrucao e. E o teto fixo e a rede que impede resposta descontrolada. O campo "tamanho da resposta" continua por loja, mas age pelo **texto** do prompt |
| **cadencia de follow-up por loja** | so liga/desliga, e so no Modo 2 | o worker so existe no Modo 2 e a cadencia sao constantes de modulo. O texto dos toques nao passa pela IA: a loja formal ainda manda "e ai amigo" — **incoerencia conhecida e aceita**, e o interruptor existe para ela poder desligar |
| **"so lead de anuncio"** | nada, por enquanto | era campo morto: o gate dependeria da atribuicao CTWA, que tem buraco conhecido. Foi **removido do schema**, nao deixado inerte, para a tela nao desenhar um interruptor de mentira |
| **persona pronta / "IA monta o prompt" / caixa de texto livre** | formulario de campos, com um gerador de texto por campo | e o que faz o resultado sair bem escrito mesmo quando o lojista nao e. A unica valvula de texto livre e o bloco "o que mais seu agente precisa saber", com teto de 1000 chars, sempre **antes** do nucleo |
| **bloquear o campo livre quando conflita com o nucleo** | avisar, e salvar assim mesmo | a deteccao e por palavra-chave e erra nos dois sentidos; falso positivo vira ligacao para o dono. O risco real e zero — o nucleo vem depois e vence |
| **reabrir a regra 3 do nucleo (insistir apos a recusa)** | fechada | e a que mais briga com o instinto do lojista, e por isso mesmo fica no nucleo |
| **n8n separado para o preview** | terceiro workflow no mesmo n8n2037 | o n8n nao dorme (decisao 14/07): outra VM 24 h por um lojista clicando numa tela. E o canonico ja roda sem gravar execucao, o que o preview herda |
| **modulo proprio para a tela de configuracao** | mesmo gate da tela vizinha | `modulos_revy` tem CHECK constraint no codigo, e codigo novo exige migration so para isso |

Duas travas do prompt antigo **foram abertas** de proposito e viraram campo da loja: dizer
que e IA, e citar vendedor/transferir. Nao as devolva ao nucleo.
