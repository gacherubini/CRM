---
gatilho: ligar o embedded signup depois do App Review; popup do Modo 2 que nao abre;
  popup que abre para o admin e da "Recurso indisponivel" para o lojista
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
- **`public_profile` em "Pronto para teste": EM DISPUTA desde 09/09.** Ate 08/09 este
  learning afirmava "pista falsa, nao submeta para analise por causa disto". A afirmacao
  foi escrita olhando so o caminho do admin. Ver "Em disputa" logo abaixo antes de agir.

## Em disputa desde 09/09: `public_profile` governa o lojista?

**O que aconteceu.** Em 09/09 o popup abria para o dono (admin do app) e dava *"Recurso
indisponivel — como estamos atualizando detalhes adicionais para esse aplicativo, o Login
do Facebook esta indisponivel para ele no momento"* para a pessoa da loja, numa conta
pessoal comum sem funcao no app. Os tres campos de OAuth desta pagina ja estavam salvos e
conferidos pelo validador; o diagnostico deste learning ja tinha sido aplicado.

Painel todo verde: app publicado, App Review aprovado em 07/09, empresa verificada,
provedora de tecnologia verificada, Data Use Checkup concluido, config v4 existindo com as
duas permissoes do WhatsApp em acesso avancado.

**Hipotese A — o bullet acima esta certo.** O `config_id` substitui o `scope`, entao o
nivel de acesso do `public_profile` nao entra neste fluxo, e a causa do erro da lojista e
outra coisa ainda nao olhada.

**Hipotese B — o bullet esta errado.** As duas coisas convivem: o `config_id` decide
*quais* permissoes sao pedidas, e o nivel de acesso decide *para quem o dialogo
renderiza*. A doc de App Review da Meta diz "approved features are active for all app
users, but unapproved features are only active for users with a role on the app", que e
exatamente o recorte observado. Tres fontes externas descrevem o mesmo sintoma no Embedded
Signup e apontam `public_profile` em acesso padrao como causa.

**Por que o bullet pode ter nascido errado.** Ele foi escrito em 07-08/09 debugando um
sintoma diferente — o popup nao abria *para o admin*, e a causa eram os tres campos de
OAuth. Nunca existiu um nao-admin tentando ate 09/09. O `verificado_em` deste arquivo cobre
o caminho do admin, nao este.

**O teste que decide, e a unica coisa que fecha a disputa.** Uma conta **sem nenhuma funcao
no app** (nem admin, nem desenvolvedor, nem testador) abre o popup:

- abriu -> hipotese B, o bullet estava errado; acesso avancado em `public_profile` e
  pre-requisito de producao e este arquivo deve ser reescrito
- nao abriu -> hipotese A, `public_profile` e ruido; procurar a causa em outro lugar e
  registrar aqui onde

Adicionar a pessoa como **testador** do app faz o popup abrir de qualquer jeito e por isso
**nao serve** como teste — so como contorno, e o dono recusou o contorno em 09/09 por ser
producao.

**Custo de errar para cada lado.** Submeter `public_profile` para analise arrasta as duas
permissoes do WhatsApp para o bloco "Acesso existente para renovacao", que no modelo de
casos de uso entra automatico e nao da para desmarcar. Elas seguem funcionando durante a
analise, mas voltam a ser julgadas — e a rodada anterior levou 9 dias. Nao submeta por
palpite.

## A licao que sobrevive a este caso

O gate de uma integracao da Meta mora em lugares que nao se olham: App Review (permissao),
a *configuration* v4 (`config_id`), e as configuracoes de OAuth do app — que sozinhas ja
sao **tres** campos. Ter quase todos em dia da erro dentro do popup, onde nem log nosso nem
teste alcanca.

E o erro so aparece quando alguem clica. O JS desta tela tinha teste que
renderizava o template como texto e passava verde; exercite-o no navegador.
