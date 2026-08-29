---
gatilho: por uma loja cliente no Modo 2, ou seguir o onboarding assistido do §16.6
produto: chatbot-api
custo: o as-built prometia um caminho manual que nao existe
fonte: externo
verificado_em: 2026-08-29
---
# O onboarding assistido do §16.6 nao e "manual e trabalhoso" — ele esta bloqueado

O §16.6 do spec dos dois modos descreve o onboarding de uma loja como assistido: a loja
cria a WABA dela, compartilha com a Revy, e a Revy faz os passos 5-8 na mao. O as-built
`2026-08-16-onboarding-meta-dominio-asbuilt.md` repete isso na lista "Ainda aberto —
nosso lado". **Os dois estao errados sobre a parte que importa.**

Para um token da Revy tocar numa WABA que **nao pertence ao negocio dono do app**, o app
precisa de **Advanced Access** em `whatsapp_business_management`. Sem ele a Graph devolve
o **erro de codigo 200** (permissao — nao confundir com HTTP 200). Advanced Access so sai
por **App Review**, e o App Review pede video do fluxo funcionando.

Isso fecha o circulo do §16.5: o degrau 4 (App Review) depende do degrau 6 (embedded
signup construido). **Nao ha caminho manual que contorne, porque e o manual que esta
bloqueado.** Compartilhar a WABA por *Assign partner* funciona do lado do lojista e nao
adianta nada do nosso: o ativo aparece e a API recusa.

## O que roda hoje, e por que foi recusado

Pendurar o numero da loja **dentro da WABA da Revy**. O ativo passa a ser do proprio
negocio dono do app, Standard Access basta, e foi exatamente isso que o piloto de 23-24/08
provou ponta a ponta. O preco: a Revy e faturada pela mensagem (inverte o §11), e a **nota
de qualidade e o teto passam a ser compartilhados** entre todas as lojas — uma loja que
toma bloqueio queima a reputacao das outras.

**O dono recusou em 29/08:** nao poe WhatsApp de cliente na WABA da Revy. O alvo virou o
App Review. Ver [[2026-08-23-teto-de-250-conta-so-outbound]] para o que a verificacao de
CNPJ compra de verdade — e ela vira pre-requisito do Tech Provider, que e o unico uso dela
que se concretizou.

## Dois detalhes que mudam desenho

- O `code` do embedded signup tem TTL de **30 segundos**, nao "poucos minutos". Nao
  sobrevive a fila, backoff ou maquina fria: a troca por token e sincrona ou nao acontece.
- O App Review pede **tres** demonstracoes em video, nao uma: o fluxo de signup, o **envio
  de mensagem** e a **criacao de template**.

Design completo em
[`docs/referencia-viva/specs/2026-08-29-embedded-signup-tech-provider-design.md`].
Ver tambem [[2026-08-23-canal-cloud-nao-se-cadastra-pela-api]], que e a metade do problema
que mora no nosso lado.
