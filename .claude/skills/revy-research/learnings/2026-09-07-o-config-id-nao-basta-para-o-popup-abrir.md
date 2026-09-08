---
gatilho: ligar o embedded signup depois do App Review, ou popup do Modo 2 que nao abre
produto: portal-gestao
custo: uma noite de painel da Meta procurando um botao que nao existe
fonte: externo
verificado_em: 2026-09-07
---
# O `config_id` nao basta: o popup morre em dois campos de OAuth

O App Review saiu em 07/09/2026 com `whatsapp_business_messaging` e
`whatsapp_business_management`. O §15 do spec do embedded signup prometia uma sequencia
curta para esse dia: criar a configuracao do Login, copiar o `config_id`, por
`PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID` no `[env]` do `fly.app.toml`, deployar.

**Tudo isso foi feito, o botao acendeu, e o `FB.login` reprovou na cara do lojista:**

    A opcao JSSDK nao esta ativada
    Defina a opcao "Login com o SDK do Javascript" como Sim em developers.facebook.com

Faltavam dois campos que o spec nao menciona, os dois na tela de OAuth do app
(`/apps/<app_id>/business-login/settings/`, a **segunda** "Configuracoes" do menu do Login
for Business — a primeira e a lista de *configurations*, outra tela):

- **Entrar com o SDK do JavaScript** = Sim (vinha Nao)
- **Dominios permitidos para o SDK do JavaScript** = `https://app2037.fly.dev/` (vinha vazio)

Ligados os dois, a janela passa.

## O outro sumidouro de tempo: "Pronto para publicar" nao e gate

Depois da aprovacao as duas permissoes aparecem como **"Pronto para publicar"** no caso de
uso, e isso parece um botao pendente. Nao e. A pagina `Publicar`
(`/apps/<app_id>/go_live/`) so oferecia **"Tirar do ar"** — o app ja estava no ar — e o
menu Acoes da permissao so oferece **"Reduzir o acesso"**, que so existe para quem ja esta
no nivel de cima. **Nao procure botao de publicar permissao: ele nao existe.**

## A licao que sobrevive a este caso

O gate de uma integracao da Meta mora em **tres** lugares que nao se olham: App Review
(permissao), a *configuration* v4 (`config_id`), e as **configuracoes de OAuth do app**
(JSSDK e dominio). Ter dois em dia e nao ter o terceiro da erro dentro do popup, onde nem
log nosso nem teste alcanca.

E o erro so apareceu porque alguem clicou. Ver
[[2026-08-23-copiloto-so-se-verifica-no-navegador]]: o JS desta tela tinha teste que
renderizava o template como texto e passava verde.
