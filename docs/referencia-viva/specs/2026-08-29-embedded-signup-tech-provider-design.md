# Embedded Signup + Tech Provider — design (2026-08-29)

Fase 2 do §11 do [`2026-08-12-whatsapp-dois-modos-design.md`](2026-08-12-whatsapp-dois-modos-design.md).
Este spec detalha os §16.5 e §16.6 daquele documento e **substitui** o onboarding
assistido descrito lá.

## 1. Problema

O §16.6 põe a WABA no CNPJ da loja e chama o onboarding de "assistido, manual nos
passos 5-8". **Isso não roda.** Para um token da Revy tocar numa WABA que não pertence
ao negócio dono do app, o app precisa de **Advanced Access** em
`whatsapp_business_management`; sem ele a chamada volta o **erro de código 200** da Graph
(permissão, não o status HTTP 200 — confusão fácil e cara). Advanced Access só sai
por **App Review**, e o App Review pede vídeo do fluxo funcionando.

Ou seja: o passo 4 do §16.5 depende do passo 6. Não há caminho manual que contorne —
o manual é o que está bloqueado.

O que roda hoje é pendurar o número da loja na WABA da Revy (é o que o piloto de 23-24/08
provou). O dono **recusou** esse caminho em 29/08: não faz sentido pôr o WhatsApp do
cliente na Revy agora.

**Resultado desejado:** o lojista conecta o WhatsApp dele ao Modo 2 sozinho, por um botão
na Revy Loja, e a Revy tem Advanced Access aprovado para operar a WABA dele.

## 2. Decisões tomadas com o dono (2026-08-29)

| # | Decisão | Descartado |
|---|---|---|
| 1 | A loja do cliente **espera**. Constrói-se contra business de teste, alvo é o App Review submetido | pôr o número do cliente na WABA da Revy agora |
| 2 | O botão mora na **Revy Loja**; o Control ganha só a visão | botão no Control (o §11 dizia Control) |
| 3 | Cadeia pós-popup **toda automática**, canal nasce `pendente`, portão de liberação no Control | tudo automático sem freio; automático só até o canal |
| 4 | O **Control continua dono do modo**. Conectar propõe; liberar decide | conectar ligar `whatsapp_modo=2` sozinho; derivar o modo do canal |
| 5 | O fluxo aceita **número novo e número existente**, com a decisão do §16.4 numa tela antes do popup | só número novo na v1 |
| 6 | **Só o dono** da loja pode conectar o WhatsApp | gerente também poder |
| 7 | O aviso de loja aguardando liberação é **a visão no Control**, e basta | sino, e-mail ou notificação dedicada |
| 8 | Fica o **SDK canônico**, não o Hosted ES (§4.1) | Hosta ES como plano A |
| 9 | Gerente **vê** a tela de WhatsApp; só o dono **conecta** | esconder a tela do gerente |
| 10 | O Card 4 conserta os rótulos Cloud **e** constrói o fluxo novo | deixar o conserto para depois |

A decisão 9 (29/08) é o recorte fino da 6: esconder a tela inteira do gerente tiraria dele a
resposta de "por que o WhatsApp ainda não está no ar", que é pergunta de rotina de quem toca
a loja. Ele vê o estado e o que falta; o botão que abre o popup é só do dono.

A decisão 10 (29/08) veio de um defeito achado ao levantar o Card 4: com `estado` valendo
`cloud_pendente`, a view de canais mostra o **nome técnico cru** como rótulo e calcula
`pode_conectar = True` — ou seja, oferece o botão Conectar do **Modo 1**, que pede QR na
Evolution, para um canal que é Cloud. Como já existe canal Cloud em produção, o conserto não
espera o fluxo novo: os dois vão no mesmo card, para a tela não ficar meio consertada.

A decisão 6 não é permissão por preferência: quem clica precisa ser **admin do portfólio
empresarial na Meta**, e gerente normalmente não é — ele abriria o popup e travaria lá dentro,
num erro que não temos como explicar.

A decisão 8 pesou que o SDK é o caminho que a Meta documenta, que o lojista não sai da Revy, e
que ele preserva o token por loja (raio de falha de uma loja, §8). O Hosted ES fica registrado
na §4.1 como alternativa avaliada, para não ser redescoberto do zero daqui a três meses.

**Ainda em aberto, e é omissão consciente:** desconexão. O spec cobre conectar e não cobre o
inverso — lojista que sai da Revy, ou que revoga o app no Business Manager dele. Hoje o sistema
não perceberia: seguiria tentando falar por uma WABA que não autoriza mais, e falhando calado.
Decidir na v2, não esquecer.

Herdadas e **não re-propostas**: billing (cada loja põe o cartão dela na WABA dela e paga a
Meta direto; a Revy fatura só o software — Tech Provider não tem linha de crédito) e
**Embedded Signup v4** (o v2 morre em 15/10/2026).

## 3. O que já está pronto e não se refaz

- Verificação de negócio da Revy: **Verificada em 24/08**. É o degrau 2 do §16.5.
- Ficha do app: ícone, política de privacidade, categoria, URLs legais — 16/08.
- App Ao Vivo, vinculado ao portfólio `4040462592922875`.
- Corpo do template `chama_vendedor` fixado pelo §16.2.
- Webhook da Meta → n8n → chatbot, com assinatura conferida.

## 4. Arquitetura — fronteira entre produtos

O `portal-gestao` serve a página e o SDK. O navegador recebe `code`, `waba_id`,
`phone_number_id` e `business_id`.

**Quem troca o `code` por token é o `chatbot-api`**, porque a troca exige o App Secret, que
já mora lá (`CHATBOT_META_APP_SECRET`) e não ganha segunda cópia. O portal repassa e nunca
vê segredo da Meta. Mantém o invariante: canais são do Chatbot, integração é HTTP versionado.

Rota nova: `POST /v1/whatsapp/canais/cloud/onboarding`, com os quatro campos no corpo. A
loja sai da credencial, nunca do corpo.

**Síncrona de ponta a ponta no primeiro elo.** O `code` tem TTL de **30 segundos** — não
sobrevive a fila, backoff ou máquina fria.

## 4.1 Bifurcação DECIDIDA: fica o SDK (Hosted ES descartado, 29/08)

**Descoberto em 29/08, depois de o design estar fechado.** O painel do caso de uso oferece
**"Cadastro incorporado hospedado pela Meta"**: *"Hosted ES is a pre-configured
implementation of Embedded Signup that is hosted by Meta. You can get a link to Hosted ES
in the App Dashboard and add it to your website or customer portal."*

São dois caminhos, e o §4 acima descreve **só o segundo**:

| | Hosted (Meta hospeda) | Custom (SDK, o do §4) |
|---|---|---|
| Página do signup | da Meta | sua, na Revy Loja |
| SDK, `config_id`, troca do `code` | **não existem** | todo o §4 e §7 elo 1 |
| Corrida de 30 s | **não existe** | restrição de arquitetura |
| Token por loja | provavelmente **não** — System User com Advanced access sobre WABA compartilhada | sim, cifrado (§8) |
| Como se sabe que conectou | webhook (`account_update` / `PARTNER_ADDED`), a confirmar | retorno do popup |
| Tela `decidindo` do §16.4 | página sua **antes** do link | dentro do fluxo |

**O que isso muda se for Hosted:** o §4 encolhe para um redirecionamento, o elo 1 do §7 some,
e o §8 muda de assunto — sem token por loja não há o que cifrar, e o "efeito colateral bom"
(raio de falha por loja) deixa de valer, voltando ao token único do §16.7.

**O que NÃO muda:** o portão do Control (§9), as colunas de retomada (§5), o template por
WABA (§7 elo 4) e a tela de decisão do §16.4 — esta só muda de lugar.

**Decidido em 29/08 (decisão 8 do §2): fica o SDK, o caminho do §4.** Ele é o documentado
na doc pública — o Hosted ES aparece só no painel, e não em `developers.facebook.com` —,
mantém o lojista dentro da Revy e preserva o token por loja, que é o que dá o raio de falha
por loja do §8. **Não re-propor o Hosted ES.** O Card 2 foi executado nessa premissa e já
está em `main`.

## 5. Dados

`WhatsAppCanal` já tem `waba_id` e `template_oferta` sem caminho de escrita
(`models_db.py:75-79`). Este projeto é esse caminho. Somam-se:

- `business_id` do cliente
- `onboarding_elo`: até onde a cadeia chegou (para retomada)
- `onboarding_erro`: por que parou, em texto para a tela
- token da loja e PIN de duas etapas, **cifrados em repouso**

**`estado` não ganha coluna nem vocabulário novo.** `WhatsAppCanal.estado` já existe e o
Modo 2 já tem os seus valores em `whatsapp_provider.ESTADOS_VALIDOS`: `cloud_pendente`,
`cloud_ativo`, `cloud_restrito`, `cloud_banido`. O `falhou` de uma versão anterior deste
spec era vocabulário duplicado: a cadeia que quebra deixa o canal em `cloud_pendente` e diz
onde parou em `onboarding_elo` / `onboarding_erro`. Estado é onde o canal está; o par de
onboarding é por que ele ainda não saiu de lá.

`evolution_instance` continua guardando o `phone_number_id`, como o §16.3 manda.
**Não renomear** — é a chave de roteamento do inbound nos dois modos e é `UNIQUE`, que é
a garantia de um número por loja.

## 6. Fluxo do lojista

```
sem_canal -> decidindo -> autorizando -> conectando -> pendente -> ativo
                                              |
                                              v
                                           falhou
```

**`decidindo`** é a tela do §16.4 e é a mais importante do projeto: é o único momento em
que o lojista toma decisão irreversível. Número novo, ou o que ele já anuncia — perdendo o
histórico do celular e virando bot-only para sempre. As três linhas do trade-off (histórico,
reconhecimento, CTWA) ficam na tela e o botão só acende depois da escolha. A escolha **é** o
aceite; não há "li e concordo".

Junto, a lista do que ele precisa ter em mãos: ser admin do portfólio empresarial, cartão
para a WABA, e o chip. Descobrir que não é admin dentro do popup é o pior lugar possível.

**`autorizando`** é o popup, com o `config_id` da configuração v4 do Facebook Login for
Business. Quem conduz a escolha do número, o SMS e a migração é a Meta.

**`conectando`** roda os elos e mostra progresso por elo, não spinner.

**`pendente`** mostra o que falta e de quem é: template em análise (Meta), meio de pagamento
(lojista), fila de vendedores (lojista, autoatendida) — e empurra para a fila, a única
acionável na hora. Diz que a liberação é da Revy, sem fingir que ele está no ar.

**`falhou`** é estado de tela, não de banco: o canal continua `cloud_pendente` e a tela lê
`onboarding_elo` e `onboarding_erro` (§5). Ela nomeia o elo e o dono. O caso mais comum —
número ainda ativo no aplicativo —
falha **dentro** do popup e pode não gerar evento nenhum; por isso `autorizando` precisa de
saída explícita de "não deu certo", nunca espera infinita.

## 7. A cadeia no servidor

| # | Elo | Retentável | Chamada |
|---|---|---|---|
| 1 | `code` → token de negócio | **não** (TTL 30 s) | `GET /{v}/oauth/access_token` com `client_id`, `client_secret`, `code` |
| 2 | inscrever o app na WABA | sim, idempotente | `POST /{waba_id}/subscribed_apps` — **verificado em produção 23/08** |
| 3 | registrar o número com PIN | **com teto** — ver abaixo | `POST /{phone_number_id}/register` com `messaging_product=whatsapp` e `pin` de 6 dígitos |
| 4 | criar e submeter o template na WABA do cliente | sim | `POST /{waba_id}/message_templates`, corpo fixado pelo §16.2 |
| 5 | fechar o canal como `cloud_pendente` | sim | rota nova |

**Correção de 29/08, escrevendo o Card 3: a linha do canal nasce depois do elo 1, não no
elo 5.** A tabela e o parágrafo abaixo se contradiziam — se o canal só aparecesse no fim,
uma falha no elo 2 perderia o token do elo 1, que tem TTL de 30 s e não é retomável, e o
lojista voltaria ao popup, o oposto do que o parágrafo promete. O elo 5 continua existindo:
ele é o *fecho* da cadeia (`onboarding_elo = 5`), não a criação da linha.

**O elo 3 tem teto duro e caro: 10 chamadas por número numa janela móvel de 72 h.**
Estourar devolve o erro `133016` e **impede o registro daquele número pelas 72 h
seguintes** — o cliente fica sem WhatsApp por três dias por causa de um botão. Então o
"tentar de novo" do §6 **não pode chamar o elo 3 livremente**: ele conta as tentativas no
canal, para em um limite bem abaixo de 10, e a partir daí a tela diz para falar com a Revy
em vez de oferecer outro clique. Um retry automático com backoff neste elo está **proibido**.

O token do elo 1 é um **Business Integration System User access token**, com escopo no
cliente onboardado — é ele que vai cifrado no canal (§8).

**Duas etapas não se desliga pela API**, então o PIN é obrigatório e nosso: é por isso que
o §8 guarda o PIN, não por conveniência.

**Depois do elo 1 o popup nunca mais é necessário** — o token já está guardado. Falha do
elo 2 em diante retoma no servidor a partir de `elo_concluido`. Só o elo 1 devolve o
lojista ao popup.

**Os elos 2 e 4 são idempotentes de propósito.** `subscribed_apps` repetido não dói e
template já existente é **sucesso**, não erro. Tratá-los como falha transforma retry
inofensivo em laço. O elo 3 é a exceção — ver o teto acima.

**O elo 2 é o que precisa de teste dedicado.** É o que falhou calado na WABA da Revy em
23/08: sem ele, o teste do painel funciona e mensagem real nunca chega. Num fluxo
automático ele é invisível até um cliente sumir.

**Template.** `chama_vendedor`, `pt_BR`, `UTILITY`, uma variável, botão `[Peguei]`
(`QUICK_REPLY`). Tem de casar exatamente com `oferta_envio.py:74`, senão o envio falha.
Ficar em `UTILITY` é o que segura o custo: como `MARKETING` cada oferta custa ~10x.

**Aprovação do template chega por webhook**, assinando o campo
`message_template_status_update` — mesmo caminho que já existe, sem rota nova. É o que faz
o portão do Control mostrar status de verdade em vez de mandar olhar o painel.

## 8. Segredos

Token da loja e PIN cifrados em repouso, chave em secret nova. **Nunca** em rota de leitura
nem em log — a tela de números lista canais. O PIN é gerado por nós e guardado: o lojista
não tem uso para ele, e PIN perdido trava o re-registro do número.

**Efeito colateral bom:** hoje um token de System User da Revy alcança todas as lojas e, se
cair, derruba todas juntas (dívida do §16.7). Com token por loja, o raio da falha vira uma
loja. O §16.7 encolhe sozinho.

## 9. O portão do Control

Nenhum caminho de escrita novo. O Control já projeta `whatsapp_modo` para o chatbot, com
versionamento. "Liberar a loja" continua sendo só isso, e o chatbot ativa o canal `pendente`
quando a projeção chega dizendo `2`. Um lever, uma fonte.

O Control ganha **visão**: estado do canal, elo que falhou, status do template.

## 10. A metade que não é código

**Tech Provider:** aceite de termos, sem taxa. O degrau que costuma travar — verificação de
negócio da Revy — já está feito.

> **A declaração de Tech Provider é PRÉ-REQUISITO DE TUDO, não etapa final.** Descoberto em
> 29/08 tentando criar a configuração: enquanto o app for um app de WhatsApp "direto" (WABA
> própria, o arranjo do piloto), a única variação de login oferecida é *General* — a de
> **WhatsApp Embedded Signup não existe na lista**. Sem ela não há `config_id`, sem
> `config_id` não há popup, e sem popup não há nada para construir nem para filmar.
>
> Onde se declara: **WhatsApp → Início rápido**, seção *Scale your Business*, opção
> **Independent Tech Provider**.
>
> **Risco a conferir na hora:** é o mesmo app que serve o piloto em produção. Depois de
> declarar, confirmar que `GET /{waba_id}/subscribed_apps` ainda lista o app e que o número
> de teste ainda responde. Painel que muda arranjo em silêncio é defeito conhecido desta
> base.

### 10.1 Pré-requisitos antes de submeter

| Pré-requisito | Estado |
|---|---|
| Protótipo funcionando do caso de uso | é o que este spec constrói |
| Verificação de negócio da Revy | **feito** 24/08 |
| Ficha do app: ícone, política de privacidade, categoria, URLs legais | **feito** 16/08 |
| App Ao Vivo | **feito** 16/08 |
| Usuários de teste com papel **dev ou admin** no app | fazer antes de gravar |

### 10.2 O que se submete — por permissão, nunca do projeto

Duas permissões, ambas em Advanced:

| Permissão | Justificativa escrita | Screencast |
|---|---|---|
| `whatsapp_business_management` | somos Tech Provider e gerenciamos números e **templates** dos clientes | criação de template |
| `whatsapp_business_messaging` | somos Tech Provider e **enviamos e recebemos** mensagens pelos clientes | envio e recebimento |

Cada uma leva **justificativa própria e vídeo próprio**. Um vídeo demonstrando as duas é
causa comum de reprovação.

**O screencast tem de ser gravado na interface do negócio, não na experiência do
consumidor.** Isto é requisito de produto, não de gravação — ver §10.4.

**Não pedir `whatsapp_business_manage_events`.** Pedir permissão desnecessária é a causa de
reprovação nº 1, e a atribuição CTWA de hoje vem do `ad_id` no payload da mensagem, não
dela.

### 10.3 Onde se submete

App Dashboard → **App Review** → **Permissions and Features**, pedindo Advanced Access em
cada permissão separadamente. Cada linha abre três campos: o texto da justificativa, o
upload do vídeo, e o botão de submeter. O progresso fica visível na mesma tela.

**Deixar em rascunho conta como não submetido** e é causa de reprovação registrada.
Turnaround médio ~24 h depois de submetido de verdade.

### 10.4 Consequência de produto: o `management` precisa de tela

`whatsapp_business_messaging` já tem o que gravar — a tela de **Atendimento** da Loja é
interface de negócio, com vendedor mandando e recebendo.

`whatsapp_business_management` **não tem**. No desenho da §7 o template nasce no elo 4,
automático e invisível. Screencast de servidor rodando sozinho não sustenta o pedido.

Então entra no escopo uma superfície visível de templates na Revy Loja: listar os templates
da WABA da loja com o status de cada um, e **criar/reenviar o `chama_vendedor` por ação
explícita**. O caminho automático do elo 4 continua sendo o normal; a tela é o mesmo código
com um botão na frente, e é ela que a câmera grava.

Não é tela de fachada para o revisor: é também o conserto de um buraco real — hoje, template
reprovado ou pausado pela Meta não tem lugar nenhum onde a loja veja ou refaça.

### 10.5 A ordem é contra-intuitiva

Constrói-se contra um business de teste, grava, e só então submete.

## 11. Testes

Suíte do `chatbot-api`: cada elo idempotente, retomada a partir de `elo_concluido`, e canal
saindo de `pendente` só pela projeção do Control.

Duas armadilhas já registradas se aplicam inteiras:

- **teste verde não prova que a feature existe** — foi assim que o Modo 2 foi entregue sem bot;
- **JS só se verifica no navegador** — o popup é JS; checagem no navegador com portal local,
  não só pytest.

Comandos, a partir da pasta do produto:
`.venv/bin/python -m pytest -q` (macOS) e `.\.venv\Scripts\python.exe -m pytest -q` (Windows).

**Ganho de brinde:** conectar **duas** lojas pelo fluxo é a primeira prova real do multi-loja,
consertado em 24/08 e nunca exercitado com mais de uma loja.

## 12. Riscos

| Risco | Mitigação |
|---|---|
| **Advanced Access negado** — mata o projeto inteiro; sem ele a WABA do cliente é intocável | Não há como reduzir antes de submeter, e não há como submeter antes de construir. Seguir a submissão-modelo da Meta ao pé da letra e contar com uma rodada de ida e volta |
| Sequência exata de chamadas dos elos 1 e 3 não confirmada | Spike contra o business de teste **antes** de virar task |
| Elo 2 falha calado | Teste dedicado; é o defeito que esta base já cometeu uma vez |
| **Retry do elo 3 queima o número por 72 h** (`133016`, teto de 10/72 h) | Contador no canal, teto bem abaixo de 10, e nenhum retry automático. É a única tentativa do fluxo que tem custo irreversível de dias |
| Lojista perde o histórico sem ter entendido | A tela `decidindo` é requisito, não enfeite |
| Reprovação por forma, não por mérito: vídeo único para as duas permissões, justificativa faltando, permissão a mais, submissão deixada em rascunho | São as causas de reprovação que a própria Meta lista. §10.2 e §10.3 existem para isso |

## 13. Fora de escopo / não re-propor

- Pôr número de cliente na WABA da Revy (recusado em 29/08).
- Solution Partner / faturar a mensagem junto da mensalidade (exige linha de crédito).
- Derivar `whatsapp_modo` do canal (decisão 4).
- Renomear `evolution_instance`.
- Embedded Signup v2.
- Pedir `whatsapp_business_manage_events` no App Review (§10.2).

## 14. Ordem de execução

Um eixo por vez, na ordem:

0. **Declarar o app como Independent Tech Provider** (§10). É portão, não etapa final: sem
   ele a variação de Embedded Signup não existe e o passo 1 não tem como começar.
1. **Spike** da sequência exata de chamadas contra o business de teste (elos 1 e 3).
2. Cadeia no `chatbot-api` (rota, elos, dados, segredos).
3. Tela na Revy Loja (`decidindo` → popup → `conectando` → `pendente`).
4. **Tela de templates na Revy Loja** (§10.4) — sem ela não há screencast do `management`.
5. Visão e portão no Revy Control.
6. Gravar **dois** screencasts, escrever **duas** justificativas, submeter em
   App Review → Permissions and Features.

O spike vem primeiro porque o §16.5 marcou confiança "média" na sequência do passo 6, e a
conferência de 29/08 confirmou a forma, não todos os endpoints.

**A ordem foi quebrada de propósito em 29/08.** Os passos 2, 3 e 6 foram feitos antes do 1,
porque o spike depende do App Review e o App Review depende de haver o que mostrar. Toda a
cadeia foi escrita a partir da documentação e testada com transporte falso — por isso o
cliente HTTP mora num módulo só dele, `app/meta_onboarding.py`: quando o spike corrigir um
formato de corpo, o conserto é local.

## 15. O que falta (29/08/2026)

Estado: passos 0, 2, 3 e 6 feitos; 1, 4 e 5 não. `app2037` em `ce4e2ab`.

### O gate — nada anda sem isto

**App Review submetido em 29/08, sem resposta.** Sem Advanced Access não há `config_id`; sem
`config_id` o popup não abre; sem popup nenhuma loja conecta. Não há contorno: o que existe
de código não conecta ninguém enquanto a Meta não responder.

Se for aprovado, a sequência é curta: criar a configuração do Login, copiar o `config_id`,
pôr `PORTAL_META_APP_ID` e `PORTAL_META_CONFIG_ID` no `[env]` do `fly.app.toml`, deployar.
O botão da tela acende sozinho — **nenhuma linha de código muda**.

Se for reprovado, o §12 lista as causas que a própria Meta publica, e todas são de forma:
vídeo único para as duas permissões, justificativa faltando, permissão a mais, submissão
deixada em rascunho. Reprovação por forma se corrige e se resubmete.

### O que não tem prova

**O JS do popup nunca rodou em navegador.** Os testes renderizam o template como texto e
provam que os ids saem no HTML e que o `disabled` some. `FB.login`, o listener de `message`
e os três caminhos de desistência não foram exercitados uma vez. É o mesmo buraco que deixou
passar dois bugs em 15-16/08. A lista do que precisa ser clicado está no fim do card 4
(`../planos/2026-08-29-embedded-signup-4-tela-na-loja.md`).

**A sequência de chamadas nunca foi conferida contra a Meta.** É o passo 1, e é o risco que
o §12 já apontava. Fica concentrado nos formatos de corpo de `tests/test_meta_onboarding.py`.

### Os dois eixos que não viraram card

**Tela de templates na Loja (§10.4).** Não existe. O motivo original — sem ela não há
screencast do `management` — foi contornado gravando o painel da Meta, então ela deixou de
ser pré-requisito da submissão. Continua sendo pré-requisito do produto: sem ela o lojista
não vê se o template dele foi aprovado, e o webhook que grava esse status já está no ar
alimentando uma tela que ninguém construiu.

**Visão no Control (§14.5).** O **portão** funciona: projetar `whatsapp_modo=2` ativa o
canal. A **visão** não existe — hoje não há onde olhar em que passo cada loja está, qual elo
falhou, nem o status do template. O dado está todo no canal (`onboarding_elo`,
`onboarding_erro`, `template_oferta`); falta a tela.

### Depois que a primeira loja conectar

Nada disto é código:

- liberar a loja no Control (projetar `whatsapp_modo=2`);
- cadastrar a fila de vendedores dela — sem fila o handoff não tem para quem ir;
- esperar a Meta aprovar o template **na WABA dela**, que chega pelo webhook;
- conectar uma **segunda** loja, que é a primeira prova real do multi-loja (§11).

### Dívidas pequenas, nenhuma bloqueante

- A tela de canais ainda fala de **QR** no cabeçalho e em "Adicionar número", mesmo para loja
  que só tem canal Cloud.
- `version: "v21.0"` está fixo no template do popup e não é o mesmo lugar onde o chatbot fixa
  a versão da Graph. Divergirem não dá aviso.
- "Tentar de novo" leva à tela de decisão; não há rota de retry dedicada.
- A auditoria do POST usa `acao="conectar", provedor="cloud"`; `ACOES_CANAL` não tem ação
  própria para o embedded signup.
- `registro_tentativas` não sai no `_canal_dict`, então a tela não sabe quantas tentativas
  restam antes do teto.
- **Contestar a categoria do `chama_vendedor`** — aprovado como `MARKETING`, ≈10x o custo por
  mensagem, prazo até **22/10/2026**. É a única pendência deste spec com data.
