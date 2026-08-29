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
| 5 | gravar o canal `cloud_pendente` | sim | rota nova |

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
