---
gatilho: ligar o embedded signup depois do App Review, ou popup do Modo 2 que nao abre
produto: portal-gestao
custo: duas noites de painel da Meta procurando campo que a doc nao lista junto
fonte: externo
verificado_em: 2026-09-08
---
# O `config_id` nao basta: o popup morre em TRES campos de OAuth, nao dois

O App Review saiu em 07/09/2026 com `whatsapp_business_messaging` e
`whatsapp_business_management`. O §15 do spec do embedded signup prometia uma sequencia
curta para esse dia: criar a configuracao do Login, copiar o `config_id`, por
`PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID` no `[env]` do `fly.app.toml`, deployar.

**Tudo isso foi feito, o botao acendeu, e o `FB.login` reprovou na cara do lojista** com
*"A opcao JSSDK nao esta ativada"*, depois com *"Recurso indisponivel — o Login do Facebook
esta indisponivel para ele no momento"*.

Os tres campos que faltavam moram todos na **mesma tela**: `/apps/<app_id>/business-login/settings/`
(a **segunda** "Configuracoes" do menu do Login for Business — a primeira e a lista de
*configurations*, outra tela).

| Campo | Vinha | Precisa |
|---|---|---|
| Entrar com o SDK do JavaScript | Nao | **Sim** |
| Dominios permitidos para o SDK do JavaScript | vazio | `https://app2037.fly.dev/` |
| **URIs de redirecionamento do OAuth validos** | **vazio** | `https://app2037.fly.dev/` |

Ligados os dois primeiros em 07/09, a janela passou uma vez e depois voltou a reprovar por
24 h. O terceiro so foi achado em 08/09. **"Usar modo estrito para URIs de redirecionamento"
vinha ligado**, e modo estrito com lista vazia nao deixa nenhum redirect passar — por isso
a lista vazia era fatal, nao apenas incompleta. Preenchido o terceiro, o popup abriu na
tela "Conecte sua conta facilmente a Revy".

A doc do embedded signup diz que o dominio tem de estar em **Allowed Domains e Valid OAuth
Redirect URIs**. Os dois campos ficam na mesma pagina, um embaixo do outro, e ainda assim
preenchemos so um: o de cima tem nome obvio, o de baixo parece do fluxo de redirect
classico que o SDK nao usa.

## A armadilha dentro da armadilha: o toast verde mente

No campo de URIs, digitar e apertar **Enter** cria o chip **e dispara um toast verde "As
alteracoes foram salvas"**. Nao salvou. Quem salva e o botao **"Salvar alteracoes"** no
rodape da pagina, que so aparece depois de alguma mudanca e fica abaixo da dobra — o
proprio toast o encobre.

Sintoma: recarregar a pagina e a lista voltar vazia, sem erro nenhum. Aconteceu duas vezes
em 08/09, uma com o dono e uma com o agente.

**Confira sempre com o "Validador da URI de redirecionamento", no topo da mesma tela, e
depois de um reload completo.** Ele e a unica leitura confiavel: com a lista salva ele
responde *"Este e um URI de redirecionamento valido para este aplicativo"*.

## Dois sumidouros de tempo que nao se repetem

- **"Pronto para publicar" NAO e gate.** E o rotulo das permissoes aprovadas no caso de
  uso. Nao existe botao de publicar permissao: a pagina `Publicar` (`/apps/<id>/go_live/`)
  so oferece "Tirar do ar" e o menu Acoes da permissao so oferece "Reduzir o acesso".
- **`public_profile` em "Pronto para teste" e pista falsa.** O menu Acoes dela oferece
  "Adicionar a analise do app", o que da a impressao de pendencia. O Login for Business e
  regido pelo `config_id`, que **substitui** o `scope` do login classico — o nivel de
  acesso do `public_profile` nao governa este fluxo. Nao submeta para analise por causa
  disto.

## A licao que sobrevive a este caso

O gate de uma integracao da Meta mora em lugares que nao se olham: App Review (permissao),
a *configuration* v4 (`config_id`), e as configuracoes de OAuth do app — que sozinhas ja
sao **tres** campos. Ter quase todos em dia da erro dentro do popup, onde nem log nosso nem
teste alcanca.

E o erro so aparece quando alguem clica. O JS desta tela tinha teste que
renderizava o template como texto e passava verde; exercite-o no navegador.
