---
gatilho: Fontecred (ou outro portal) sai `login_timeout` e voce vai mexer no timing, no seletor do campo de e-mail ou na credencial
produto: motor-simulacao
custo: 3 min de browser queimados por rodada fingindo lentidao, e uma investigacao inteira apontada para o lugar errado
fonte: repo
verificado_em: 2026-09-20
---
# `login_timeout` do Fontecred era a pagina de bloqueio da Cloudflare

O codigo gravado no historico dizia `login_timeout`. O print do evento
`falha_portal` mostrava outra coisa: **"Sorry, you have been blocked — You are
unable to access fontecred.com.br"**, com Ray ID da Cloudflare.

Ray IDs medidos: `a3dcabf918fdf191` (19/09) e `a3e1d06dfb04f8bf` (20/09 12:21).

O portal **nunca viu** a tentativa. A Cloudflare responde na borda, com 403, antes
de a requisicao chegar no banco. Nenhuma senha foi testada, nada foi registrado
do lado deles. O driver ficava procurando o campo de e-mail numa pagina de aviso
ate estourar.

## Por que saia classificado errado

`_assert_portal_acessivel` (`app/motor/playwright_base.py:404`) so conhecia as
assinaturas da **Akamai** (`Access Denied`, `errors.edgesuite`). A pagina da
Cloudflare nao casava com nenhuma e passava batida. Corrigido em 20/09: o
detector reconhece o bloqueio e levanta `IntervencaoNecessaria("portal_bloqueado")`.

Ganho de tempo alem do diagnostico: `IntervencaoNecessaria` retorna sem retry
(`app/processamento.py:479`), enquanto `ErroTransitorio` repete. A rodada de
20/09 12:16 gastou duas tentativas (~120 s + ~60 s); agora falha uma vez, em
segundos.

## A armadilha de quem for mexer nisso

**Case a pagina de bloqueio, nunca a marca.** O portal do Fontecred fica ATRAS da
Cloudflare: a pagina boa de login tambem carrega `/cdn-cgi/` e `__CF$cv$params`.
Detector que procure "Cloudflare" ou "cdn-cgi" derruba login que estava
funcionando. As assinaturas usadas sao `Sorry, you have been blocked`,
`Attention Required! | Cloudflare` e `error code: 1020`.

Regressao que segura isso:
`tests/test_playwright_base.py::test_pagina_normal_atras_da_cloudflare_nao_e_bloqueio`.

## O que isto NAO explica

Qual regra disparou. De fora ninguem descobre — a pagina omite de proposito. So
quem tem o painel cola o Ray ID e ve a linha. Por isso pedir liberacao ao banco
com o Ray ID vale mais que comprar IP no escuro, e continua pendente no card
(`docs/fila/2026-09-10-motor-rpa-multiloja-cloud.md:560`).

Datacao que restringe a hipotese: em 19/09 as 09:48 o Fontecred saiu
`credito_recusado` e as 14:13 saiu **com oferta**, no mesmo IP do Fly. As 16:49 ja
estava bloqueado. Nao e ban de ASN do Fly — e o endereco especifico que queimou,
numa tarde de ~19 rodadas mais 24 logins da investigacao do Bradesco. O Bradesco
virou na mesma janela (ultimo login bom 14:16).

Primo que NAO se aplica aqui:
[[2026-09-19-recaptcha-do-bradesco-cinco-suspeitos-eliminados]] — la o IP ja foi
eliminado por medicao. Sao camadas diferentes: Cloudflare julga rede antes da
pagina existir, reCAPTCHA v3 julga comportamento dentro da pagina ja carregada.
Trocar de saida resolve um e nao encosta no outro
([[2026-09-13-dataimpulse-sticky-egress-bradesco]]).
