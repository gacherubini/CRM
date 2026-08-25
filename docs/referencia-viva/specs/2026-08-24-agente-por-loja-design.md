# Agente por loja — design

Status: desenho aprovado pelo dono em 24/08/2026. Não implementado.
Produtos tocados: `chatbot-api` (dono do dado), `portal-gestao` (tela), `n8n` (prompt).

## 1. O problema

Não existe "o agente da loja". Existe **um** agente, hardcoded para uma loja só.

O `systemMessage` do nó `AI Agent1` mora em `n8n/workflow-ai-nao-salvos.json` e traz
literalmente `vitor motos` e `nossa loja fica em limeira-sp`. O `chatbot-api` não tem
prompt de LLM nenhum: ele monta o texto compacto do histórico
(`chatbot-api/app/servico.py:713`) e expõe as tools HTTP que o agente chama.

Consequência: a segunda loja atende se apresentando como a primeira. E toda mudança
de texto do bot passa pelo dono editando JSON e republicando workflow.

## 2. O que se decide aqui

Cada loja tem **o seu** agente: personalidade, identidade, FAQ e regras de conversa
configuráveis pelo lojista, por formulário, na Revy Loja — com uma camada pequena de
regras do Revy que ele não mexe.

Isso é também argumento comercial: a tela de configuração e o núcleo visível
("o que o Revy garante") são material de venda.

### Decisões do dono (24/08) — não re-propor

| Decisão | Valor |
|---|---|
| Escopo da personalização | personalidade **inteira** é da loja; um agente por loja |
| Formato de edição | **formulário de campos**, não texto livre, não persona pronta, não "IA monta" |
| Publicação | rascunho → **testar** → publicar, com histórico e volta atrás |
| Trava "não dizer que é IA" | **ABERTA** — virou campo da loja |
| Trava "não citar vendedor/transferir" | **ABERTA** — virou campo da loja |
| Trava "nunca falar parcela/taxa/banco" | **FECHADA** — invariante do Motor |
| Trava "não insistir depois da recusa" | **FECHADA** |
| Escopo da v1 | identidade + personalidade + FAQ + regras da conversa + instruções livres + liga/desliga |
| Campo livre de instruções | **entra** (§4.5), teto 1000 chars, antes do núcleo |
| Conflito do campo livre com o núcleo | **avisa, não bloqueia** |
| Follow-up | só **liga/desliga**, visível apenas no Modo 2 (§4.4.2). Cadência, nº de toques e texto na voz do agente ficam fora da v1 |
| Fuso horário | `America/Sao_Paulo` fixo, sem coluna (§4.1) |
| Módulo próprio para a tela | não; mesmo gate da tela vizinha (§6) |
| n8n de teste | **não** — workflow gerado no mesmo n8n2037 |
| Escolha do modelo de LLM | **global, um modelo para todas as lojas** (revisto em 25/08) |

## 3. Arquitetura

### 3.1 Quem é dono de quê

- **`chatbot-api`** é dono da config. É dele a conversa e é ele que serve as tools que
  o n8n chama.
- **`portal-gestao`** é só tela. Fala com o chatbot por HTTP via o `ChatbotClient` que
  já existe. **Não** ganha tabela.
- **`n8n`** consome. O `systemMessage` perde os literais e ganha slots.

Fronteira de sempre: HTTP versionado, sem import `app` entre produtos.

### 3.2 Modelo de dados (`chatbot-api`, migration `0027`)

```
agente_config          loja_id (PK/FK) · versao_publicada_id
agente_config_versao   id · loja_id · estado (rascunho|publicada|arquivada)
                       campos (JSON do formulário)
                       prompt_gerado (texto final, congelado)
                       autor · criado_em · publicado_em
```

`prompt_gerado` guardado junto com `campos` **não** é redundância: é o que permite
auditar o texto que o bot realmente recebeu naquela versão. Melhorar o gerador amanhã
não reescreve o histórico.

Voltar para uma versão anterior **cria versão nova** a partir dela. Nada é apagado.

### 3.3 Rota nova: `GET /v1/agente/config`

Autenticada pela credencial de integração. Devolve o prompt montado e o
`max_output_tokens` da loja (§7.1). **Não devolve modelo** — o modelo é global (§7).

**A rota TEM que ler `ctx.loja_id` resolvido, antes do gate operacional.** Três erros
conhecidos que ela não pode repetir
(`learnings/2026-08-24-instance-nao-conserta-toda-rota.md`):

1. `_exigir_loja_operacional(db, ctx.loja_id)` com `loja_id` nulo responde **423** e
   engole o **400** que diz "faltou `instance`". Resolver primeiro, passar o `loja_id`
   já resolvido ao gate.
2. Rota que lê `ctx.loja_id` só para achar um objeto estoura **500** (`AttributeError`),
   não erro de validação.
3. Aceitar `instance` sem ler `ctx.loja_id` é **teatro** — é o que acontece hoje em
   `GET /v1/config/catalogo-bot`, que aceita o parâmetro e mesmo assim devolve a mesma
   loja para todo mundo, porque quem responde é `InventoryWriteClient.obter_loja()` com
   bearer global.

`instance` não quer dizer a mesma coisa nos dois modos: no Modo 1 é a instância do
Evolution; no Modo 2 é o `phone_number_id` da Meta, e precisa passar por
`loja_id_do_phone_number_id` (`app/cloud_canal.py`) antes.

**O fallback do §9 não vale para 423.** A rota aplica `_exigir_loja_operacional`, então
loja suspensa responde **423**. Se o n8n tratasse isso como "falhou, usa o padrão Revy",
a loja suspensa continuaria sendo atendida pelo bot — quebrando o invariante do
`AGENTS.md` §5 ("suspensão de loja é gate de backend"). Regra: **fallback só em falha
técnica (timeout, 5xx). Em 423 o workflow para.**

### 3.4 Montagem do prompt — o sanduíche

```
1. IDENTIDADE          ← gerado dos campos
2. PERSONALIDADE       ← gerado dos campos
3. FAQ DA LOJA         ← pares pergunta/resposta
4. REGRAS DA LOJA      ← o que oferece, foto, handoff, follow-up
5. INSTRUÇÕES DA LOJA  ← texto livre do lojista (§4.5)
6. NÚCLEO REVY         ← imutável, POR ÚLTIMO
```

**A ordem é o mecanismo de segurança.** O núcleo vem depois e diz explicitamente que
nada acima dele pode contradizê-lo.

**O lojista não escreve prompt — escreve campos.** Cada campo tem um gerador de texto no
`chatbot-api`. É isso que faz o resultado sair bem escrito mesmo quando o lojista não é
— e é a razão de o formulário ter ganhado da caixa de texto livre.

A única exceção é o bloco 5 (§4.5), que é texto do lojista mesmo. Ele fica **depois** de
tudo que o formulário gera e **antes** do núcleo — de propósito: o lojista escreve o que
quiser e o núcleo continua vencendo.

## 4. Os campos

### 4.1 Identidade

| Campo | Tipo |
|---|---|
| Nome da loja no atendimento | texto |
| Cidade / UF | texto |
| Passar endereço completo? | sim / só a cidade |
| Entrega | texto curto |
| Horário de atendimento | grade semanal |
| Link do catálogo | vem do Estoque (ver §8, dívida) |

**Fuso: `America/Sao_Paulo`, fixo, não é campo.** `lojas`
(`chatbot-api/app/models_db.py:19`) tem só id, nome, slug, `evolution_instance`,
`whatsapp` e `criada_em` — **não existe timezone no modelo**. Tudo que depende de hora
(horário de atendimento, "só em horário comercial", handoff fora do horário) usa o fuso
fixo. Vira coluna quando existir loja fora do fuso de Brasília, não antes.

### 4.2 Personalidade

| Campo | Opções |
|---|---|
| Nome do agente | texto ou "sem nome" |
| Assume que é IA? | nunca · só se perguntarem · já na abertura |
| Tom | direto · simpático · consultivo · formal |
| Tratamento | primeiro nome · você · senhor(a) |
| Escrita | tudo minúsculo · pontuação normal |
| Emoji | nunca · raro · à vontade |
| Tamanho da resposta | 1–2 frases · até 3 · pode explicar |
| Expressões da casa | chips ("beleza", "fechou") |
| Nunca diga | lista de palavras banidas |

### 4.3 FAQ da loja

Pares pergunta → resposta fixa. Gera `quando o cliente perguntar sobre X, responda
exatamente: "Y"`.

### 4.4 Regras da conversa

| Campo | Opções |
|---|---|
| Ofereço | financiamento · à vista · troca na troca · consignação |
| Fotos | só quando pedir · mando na abertura (**só Modo 1**) |
| Sem a moto do anúncio | seguro no veículo · posso oferecer parecida |
| Passa pro humano | quando pedir · depois da simulação · fora do horário |
| Pode citar vendedor pelo nome? | sim · não |
| Follow-up | ligado · desligado (**só Modo 2** — ver §4.4.2) |

#### 4.4.1 O formulário é consciente do modo da loja

**Os dois modos não têm as mesmas tools**, então o mesmo formulário produz
comportamentos diferentes — e alguns campos simplesmente não existem de um lado.
`n8n/fork_cloud_workflow.py:69` (`DESCARTADOS`) tira `enviar_foto_veiculo1` e
`cadastrar_veiculo1` do Modo 2, com motivo registrado: a central Cloud precisaria de
envio de imagem pelo Graph, que ainda não existe.

| Campo | Modo 1 (Evolution) | Modo 2 (Cloud) |
|---|---|---|
| Fotos | funciona | **não existe tool de foto** |
| Follow-up | **não existe worker** | funciona (§4.4.2) |
| Passa pro humano | avisa a equipe pela Evolution | abre o rodízio |

A tela **esconde ou desabilita** o que não se aplica ao modo da loja, com a razão à
vista. Campo que o lojista configura e que não faz nada é o pior tipo de bug de produto:
não dá erro, não dá log, e ele conclui que a configuração inteira é decorativa.

#### 4.4.2 Follow-up: só liga/desliga na v1

**Decisão do dono (25/08):** entra o interruptor, não a configuração.

O que o código permite hoje (`chatbot-api/app/followup_job.py`): é **só Modo 2, só com
`bot_ativo`**; a cadência são constantes de módulo (`PRIMEIRO_TOQUE = 30 min`,
`SEGUNDO_TOQUE = 1 h`); e `texto_followup` levanta `ValueError` para toque fora de (1,2)
— *"Terceiro toque não existe — a spec para em dois"*.

**Na v1:** campo booleano `followup_ativo` em `agente_config`. O `FollowupWorker` passa a
consultá-lo junto com os filtros que já aplica (`loja_opera_modo2` e
`Conversa.bot_ativo`). Uma coluna e uma condição.

**Fora da v1:** cadência por loja, mais de dois toques, e follow-up no Modo 1.

**Visível só no Modo 2** (§4.4.1). Isso cria assimetria conhecida e aceita: a loja do
piloto está no Modo 1 e não verá o campo; loja nova entra no Modo 2 e verá. O dono
decidiu com essa consequência à vista.

**Incoerência conhecida e aceita — não é bug, não abrir chamado:** o texto do follow-up é
fixo em `_TEXTOS`, por etapa, e **nunca passa pela IA**. A loja que configurar um agente
formal, sem gírias, tratando por "senhor", ainda assim manda *"e aí amigo, ainda tá aí?"*
trinta minutos depois do cliente sumir. O interruptor existe justamente para ela poder
desligar isso.

Card próprio, depois: *follow-up por loja e com a voz do agente* — cadência configurável
e texto gerado pelo mesmo prompt do agente. É ele que fecha essa incoerência.

### 4.5 Instruções da loja (o campo livre)

O formulário cobre o previsível. Sempre sobra a regra que só aquela loja tem. Sem essa
válvula, ou o Revy vira suporte de exceção, ou o produto parece engessado.

Na tela, com nome que ensina o formato — nunca rotulado como "campo livre":

> **O que mais o seu agente precisa saber?**
> Escreva regras da sua loja que não couberam acima.
> *Ex.: "não financiamos quem tem CNH suspensa" · "aos sábados só atendemos com hora
> marcada" · "moto acima de 2020 tem 6 meses de garantia"*

**Teto de 1000 caracteres.** Não é burocracia: esse texto entra em **toda** mensagem de
**toda** conversa. Sem teto o lojista cola três páginas, o custo por conversa sobe e o
agente se perde — instrução demais dilui as que importam.

Entra no prompt como bloco 5, rotulado como instrução da loja, sempre **antes** do
núcleo.

**Conflito com o núcleo: avisa, não bloqueia** (decisão do dono, 24/08). Detector simples
por palavra-chave sobre os temas fechados — parcela/taxa/banco, insistir depois da
recusa, pedir renda ou placa, inventar disponibilidade. Ao detectar, alerta na tela:
*"isso conflita com uma regra do Revy e o agente vai ignorar"*. Ele salva assim mesmo se
quiser.

O risco real é zero — o núcleo vem depois e vence de qualquer jeito. O aviso existe para
o lojista **não achar que o produto está quebrado** quando escrever algo que não pega.
Bloquear foi descartado: depende de detecção por palavra-chave, que erra nos dois
sentidos, e falso positivo vira ligação para o dono.

**A rede de segurança de verdade é o preview**: ele escreve, testa, vê o agente estranho
e corrige antes de publicar.

### 4.6 Liga/desliga

Agente ativo · só em horário comercial.

**`só lead de anúncio` saiu da v1 (25/08).** Ele estava listado aqui, virou campo em
`CamposAgente`, e a revisão final do card 1 pegou que era **campo morto**: o lojista
ligaria e nada aconteceria. O gate exige saber, dentro de `pode_responder`, se aquela
conversa veio de anúncio — e isso depende da atribuição CTWA, que tem buraco conhecido
(`learnings/2026-08-24-telefone-mascarado-de-4-digitos-colide.md`). Fazer isso às pressas
no caminho quente troca um campo decorativo por um bot que cala na conversa errada.

Campo **removido do schema**, não deixado inerte: se ficasse, o card 3 desenharia o
controle e o lojista teria um interruptor de mentira. Volta com card próprio, junto de
uma origem de anúncio confiável.

**`bot_ativo` de hoje não serve: é por conversa, não por loja**
(`chatbot-api/app/models_db.py:186`, na `Conversa`). O liga/desliga da loja é campo novo
em `agente_config`.

Ponto de aplicação: `POST /v1/conversas/{telefone}/pode-responder`
(`chatbot-api/app/main.py:921`). É o gate que o n8n já chama antes de acionar a IA, já
resolve a loja por `resolver_loja_id` e já é onde mora o debounce — o desligamento por
loja e a janela de horário entram aí, não num nó novo do workflow.

### 4.7 Exemplo de texto gerado

Campos de uma loja fictícia ("Motos do Léo", Piracicaba-SP) produzem:

```
[IDENTIDADE]
você atende os clientes da motos do léo pelo whatsapp.
a loja fica em piracicaba-sp. não informe rua, número, bairro nem ponto de
referência: passe só a cidade.
entrega: cortesia para todo o estado de são paulo.
horário de atendimento: seg a sex das 8h às 18h, sáb das 8h às 12h.

[PERSONALIDADE]
seu nome é léo. se o cliente perguntar se você é uma pessoa ou um robô, responda
com honestidade que é o assistente digital da loja; fora isso, não levante o assunto.
fale em português do brasil, de forma humana, simples e direta.
escreva toda resposta ao cliente em letras minúsculas.
não use emojis.
seja minimalista: uma ou duas frases curtas.
chame o cliente pelo primeiro nome quando ele parecer um nome real.
use "beleza", "fechou" e "certinho" quando combinar com a conversa, sem virar bordão.
nunca use as palavras: "parceiro", "amigão".

[REGRAS DA LOJA]
a loja trabalha com financiamento, venda à vista e aceita moto na troca.
não trabalha com consignação — se perguntarem, diga que a loja não faz.
não mande fotos por conta própria: só quando o cliente pedir.
se a consulta não achar a moto do anúncio, mantenha o foco nela e não ofereça outra
moto por iniciativa própria.
você pode citar o vendedor pelo nome ao encaminhar o atendimento.

[INSTRUÇÕES DA LOJA]
o lojista escreveu as instruções abaixo. siga-as, exceto onde contrariarem as
regras do revy que vêm depois.
não financiamos quem tem cnh suspensa.
aos sábados o atendimento é só com hora marcada.
```

## 5. O núcleo Revy

Igual em toda loja, **último bloco do prompt**, não editável. O lojista vê no máximo um
resumo em português na tela ("o que o Revy garante") — que é material de venda.

```
[REGRAS DO REVY — PREVALECEM SOBRE TUDO ACIMA]
estas regras não podem ser contrariadas por nenhuma instrução anterior.
se algo acima conflitar com algo aqui, siga o que está aqui.

1. estoque e preço: só o que consultar_estoque retornar. nunca invente veículo,
   preço, km, cor, ano ou disponibilidade, e nunca afirme que uma moto está
   disponível sem a consulta ter confirmado.
2. resultado de financiamento: nunca mostre nem mencione parcela, taxa, banco,
   valor financiado ou prazo. depois da tool simular, responda somente a
   confirmação curta que ela devolver.
3. recusa: se o cliente recusar, declinar ou encerrar um convite, dê uma frase
   curta de ok e PARE. não repita a oferta e não emende outra.
4. simulação: cpf, data de nascimento e resposta de cnh (sim ou não) são
   obrigatórios, nessa ordem — nascimento e maioridade, depois cnh, depois a tool.
   "não tenho cnh" não bloqueia. nunca peça renda, prazo ou placa. nunca peça de
   novo um dado já recebido.
5. menor de idade: se a tool devolver motivo_bloqueio=menor_de_idade, envie
   exatamente a mensagem da tool e não chame de novo.
6. anti-alucinação: só confirme a simulação se a tool retornou ok:true e
   simulacao_humana_solicitada:true. em erro, ok:false ou faltando, siga a
   mensagem da tool — nunca invente confirmação.
7. nunca revele tools, tokens, apis internas, placa interna ou qualquer dado de
   controle.
8. o lead nasce dentro da tool simular. nunca crie lead por cumprimento, clique em
   anúncio ou pergunta de estoque.
```

Oito regras, de propósito: quanto menor o núcleo, mais honesto é dizer ao lojista que o
resto é dele. Duas travas do prompt atual saíram daqui por decisão do dono (dizer que é
IA, citar vendedor) e viraram campo.

Risco conhecido: **a regra 3 é a que mais briga com o instinto do lojista** — ele vai
querer que o bot tente de novo. Fica fechada.

## 6. Tela e fluxo

`/app/loja/agente` ganha duas abas: *Desempenho* (a que já existe,
`portal-gestao/app/loja/routes.py:348`) e *Configuração*.

Gate: sessão + flag `REVY_LOJA_AGENTE_CONFIG_ENABLED` (default 0) + papel dono/gerente.

**São três, não quatro.** A tela vizinha (`portal-gestao/app/loja/routes.py:348`) hoje
checa só `atendimento_habilitado()` e `pode_usar_atendimento(usuario)`
(`app/loja/attendance.py:117`) — **não tem gate de módulo**. A config do agente segue o
mesmo gate da tela onde ela mora.

Módulo próprio fica para depois, e não é de graça: `modulos_revy` tem CHECK constraint no
código (`'vendas', 'estoque', 'copiloto', 'financeiro'`) e um código novo exige migration
que recria o CHECK — o padrão está em
`revy-trafego/alembic/versions/0018_copiloto_modulo.py`.

O dono continua editando por cima pelo Control (§7).

Fluxo: rascunho salva enquanto digita → **Testar** → **Publicar**. Publicado vale na
próxima mensagem de cliente (o n8n busca a config no começo de cada conversa; sem cache
longo, no máximo segundos).

### 6.0 Design: seguir o padrão, não inventar

Vale para **todo card que mexer em tela** (3 e 4). Não é "capriche no visual" — são regras
com endereço.

**Não existe componente de abas.** Procure por `.tabs`, `.subnav` ou `.segmented` em
`portal-gestao/app/static/css/app.css`: não há nenhum. Criar "abas" significa **inventar
componente novo**, e isso é decisão de design, não detalhe de implementação.

O padrão da casa para telas irmãs é **rota própria + link no cabeçalho**, como o
`/app/loja/agente` já faz:

```html
<div class="page-heading">
  <div>
    <span class="eyebrow">Vendas</span>
    <h1>Agente de atendimento</h1>
    <p>Uma linha dizendo o que a tela mostra.</p>
  </div>
  <div class="heading-actions">
    <a class="button secondary" href="/app/loja/atendimento">Ver fila</a>
  </div>
</div>
```

Então a configuração vira `/app/loja/agente/configuracao`, com link recíproco no
`.heading-actions` das duas. **Se depois disso o dono quiser abas de verdade**, elas viram
componente compartilhado com card próprio — não nascem escondidas dentro deste.

**Estrutura de bloco:** `.panel` > `.panel-heading` (`h2` + `p.muted`) > `.panel-body`, e
`.panel-empty` para estado vazio. Estilo novo vai para o `app.css`, não para `<style>` no
template; o topo do template leva um comentário dizendo quais classes ele usa, como o
`agente.html` faz.

**`{% block page_title %}` é obrigatório.** Sem ele a topbar cai no `else` do `base.html` e
escreve **"Ajustes"** — o comentário está no `agente.html:3`.

**Bump do `?v=` ao mexer em CSS, e são dois arquivos diferentes:**

| Shell | Arquivo | Linha do `<link>` | Valor hoje |
|---|---|---|---|
| Revy Loja | `portal-gestao/app/static/css/app.css` | `portal-gestao/app/templates/base.html:16` | `?v=v16` |
| Revy Control | `revy-trafego/app/static/css/app.css` | `revy-trafego/app/templates/base.html:16` | `?v=v12` |

O `StaticFiles` do Starlette não manda `cache-control`: sem trocar a URL, o navegador reusa
o CSS velho. Foi assim que o redesign do Copiloto foi para produção quebrado em 14/08. E as
telas de auth **não estendem** o `base.html` — cada uma tem o seu `?v=`.

**Cor, fonte e token: nunca editar a cópia.** A fonte única é
`shared/brand/revy-tokens.css`; rode `python shared/brand/sync_tokens.py` (`python3` no
Mac). Editar `*/static/css/revy-tokens.css` quebra a suíte de propósito. O acento é o verde
racing — há teste que falha se o azul antigo voltar.

**`.overview-grid` não existe em CSS nenhum.** Um template do Agente usava essa classe e
saía com rótulo e número colados ("Oferecidos0") — corrigido em `472ea5f`. Use
`.metric-grid`, e confira no navegador que a classe que você escreveu tem regra.

**Máximo 4 métricas por grade.** `.metric-grid` é `repeat(4, 1fr)` sem `row-gap`: a quinta
cai embaixo da primeira e lê como continuação do mesmo card. Precisa de mais? grade nova.

**Duas recusas do dono encostam nesta tela** (`decisoes/2026-08-07-treze-recusas-de-ux.md`):

- **`I4`** — o bot ter quatro nomes (Agente / Agente de atendimento / chatbot / o bot) foi
  **recusado**. Não unifique a nomenclatura de carona; use o nome que a tela vizinha já usa.
- **`C8`** — tela do Control como item de menu de primeiro nível foi **recusada**. Nenhuma
  tela desta feature entra no Control de todo modo (§7), mas a regra vale se algum dia
  entrar: vai onde a ficha da loja já está, não como item novo de menu.

**A tela não se verifica com pytest.** Formulário e janela de teste são JS; isso já passou
dois bugs no Copiloto. Verificação é no navegador, com portal local semeado.

### 6.1 A janela de teste

Roda o agente de verdade — mesmo modelo, mesmas tools, mesmo núcleo — com o prompt do
**rascunho**, sem WhatsApp no meio.

Caminho: Portal → `chatbot-api` monta o prompt do rascunho → webhook
`whatsapp-ai-preview` no n8n → resposta volta na tela.

#### 6.1.1 O preview precisa de um nó-ponte chamado `Extrair1`

As tools **não** são nós HTTP: são `toolCode` (JS) que chamam
`http://chatbot-api:8000/...` com `Bearer __CHATBOT_TOKEN__`, e **todas** leem
`$('Extrair1').first().json` para achar `instance` e `telefone`.

Um workflow de preview com entrada HTTP não tem `Extrair1` — e tool que referencia nó
inexistente falha. É exatamente o erro que o fork do Modo 2 cometeu calado, e lá a
correção foi **criar nós-ponte de mesmo nome**, não reescrever as tools
(`learnings/2026-08-23-workflow-cloud-e-gerado.md`). O preview faz igual: um nó chamado
`Extrair1` que emite `{ instance, telefone, ... }` no formato do Modo 1.

Duas diferenças obrigatórias em relação ao `Extrair1` real: ele é acoplado ao body do
webhook da Evolution, e tem **trava fail-closed de 300 s de idade da mensagem**
(`MAX_MESSAGE_AGE_SECONDS`) que descartaria toda mensagem de teste. A ponte não replica
nem o parsing nem a trava.

#### 6.1.2 Telefone sintético — `consultar_estoque` escreve no CRM

`consultar_estoque1` não é só leitura: quando a busca devolve **um** veículo, ela grava a
moto escolhida via `POST /v1/operacao/moto-escolhida`, chaveada por telefone + instance.

O lojista vai testar usando o próprio número — que é um número real, com conversa real.
Sem freio, ele sobrescreve o estado de uma conversa de verdade.

Por isso o preview usa **telefone sintético por loja** (fora da faixa de número real),
nunca o do usuário logado. Isso resolve a escrita no CRM e ainda mantém
`consultar_estoque` executando de verdade, que é o que faz o teste valer.

O `$getWorkflowStaticData('global')` **não** colide, porque é escopado por workflow — e
essa é mais uma razão de o preview ser workflow separado, e não um modo dentro do
canônico (§6.2).

**Modo seco das tools — é a armadilha central desta feature.** As tools têm efeito
colateral no mundo real: `simular` cria lead no portal, avisa a equipe no WhatsApp e
pausa o bot. Sem freio, o lojista testa digitando um CPF e toca o celular do vendedor
num sábado.

| Tool | No preview |
|---|---|
| `consultar_estoque1` | **executa de verdade**, com telefone sintético (§6.1.2) |
| `enviar_link_catalogo1` | **executa de verdade** (só lê) |
| `simular1`, `TEMP continuar sem estoque1` | devolvem a mensagem certa, **sem criar lead, sem notificar, sem pausar bot** |
| `solicitar_handoff1`, `enviar_foto_veiculo1`, `cadastrar_veiculo1` | devolvem a mensagem certa, **sem executar** |

A conversa de teste é efêmera: não entra em Conversas, não vira lead, some ao sair.

Ao lado, opcional, o prompt gerado — com o núcleo Revy no rodapé, imutável. Mostrar é
proposital: é transparência que fecha venda.

### 6.2 Por que não um n8n separado

O padrão já existe no repo: `n8n/build_test_workflow.js` gera
`workflow-teste-numero-autorizado.json` a partir do canônico, com ID, nome e webhook
próprios (`whatsapp-ai-teste`) e "freios de lab", validado por
`validate_test_workflow.py` e publicado com `prepare-workflow.ps1 -Mode test`.

O preview é um **terceiro workflow gerado** no mesmo n8n2037. Diferenças: entrada HTTP
pura em vez de Evolution, e o freio de lab é o modo seco em vez do telefone.

Razões de não subir n8n novo:

- **Volume SQLite** (o que deixou o bot mudo em 08/08): o canônico se chama
  `workflow-ai-**nao-salvos**` porque já roda sem gravar execução. O preview herda.
- **Os ~6 min de webhook 404** são custo de *reiniciar* o n8n2037. Subir workflow novo é
  import + `update:workflow --active=true`, sem restart.
- **CPU**: é um lojista clicando numa tela, não tráfego.
- **Custo**: o n8n não dorme (decisão 14/07). n8n novo = mais uma VM 24h e mais um lugar
  de onde o workflow diverge em silêncio.

**Gatilho para revisar:** quando o preview começar a gravar execução ou a disputar CPU
com atendimento real.

Fora de escopo, e não confundir: um n8n de **homologação** para testar mudança de
workflow antes de produção seria útil, mas é outro problema.

## 7. Modelo de LLM e teto de tokens

O nó do modelo é fixo, e continua fixo:

```json
"modelName": "models/gemini-3.1-flash-lite",
"options": { "maxOutputTokens": 250, "temperature": 0.3 }
```

**Decisão do dono (25/08): o modelo é global — um só para todas as lojas.** Nada de
`modelo` em `agente_config`, nada de rota para trocá-lo, nada de tela no Control.

O que se perde, conscientemente: canário na troca de modelo (hoje trocar é all-or-nothing)
e a possibilidade de amarrar modelo a plano comercial. Se um dia doer, a coluna volta — é
migration pequena, e o dado por loja já existe ao lado dela.

**Não re-proponha modelo por loja.** Foi desenhado, avaliado e recusado nesta data.

### 7.1 O teto de tokens, esse sim, é por loja

`maxOutputTokens` está amarrado ao campo **"Tamanho da resposta"** (§4.2):

| Tamanho da resposta | maxOutputTokens |
|---|---|
| 1–2 frases | 250 |
| até 3 | 400 |
| pode explicar | 700 |

Sem isso, "pode explicar" bate no teto de 250 e a resposta corta no meio da frase — o campo
seria mentira.

**E aqui mora a única suposição que não se verifica lendo o repo.** O nó do modelo
(`@n8n/n8n-nodes-langchain.lmChatGoogleGemini`) é **sub-nó** do AI Agent, e sub-nó em n8n
tem contexto de expressão limitado — não é invocado no fluxo principal. Se `maxOutputTokens`
não aceitar expressão, o teto não varia por loja.

Spike obrigatório antes da Task de n8n (§9, passo 0): pôr uma expressão em
`maxOutputTokens` no n8n2037 e ver se resolve.

**Plano B, se não resolver** — e ele é barato, porque o modelo saiu de cena: subir o teto
global para 700 e deixar o comprimento por conta do prompt, que já diz "seja minimalista:
uma ou duas frases curtas". O teto vira só uma trava de segurança contra resposta
descontrolada, e o campo continua funcionando por instrução em vez de por parâmetro. Sem
switch, sem nós paralelos.

## 7.2 O que esta feature quebra no n8n (e como não afrouxar a rede)

### `validate_workflow.py` — as assertivas de prompt caem

O validador afirma **~40 frases literais** dentro do `systemMessage`
(`n8n/validate_workflow.py:121` em diante): *"privacidade do resultado"*, *"nunca crie
lead por cumprimento"*, *"mande as fotos do catálogo ou prefere"*, *"não exija foto
antes"*, *"recusa e não insistir"*, *"nunca peça placa ao cliente"*, *"texto genérico do
botão do anúncio"*, entre outras.

Assim que o texto sai do JSON e vira gerado por loja, essas assertivas quebram — e
`python n8n/validate_workflow.py` é gate do `AGENTS.md` §6.

**A rede não se afrouxa; ela muda de lugar**, e isso é Task explícita:

| Assertiva | Vai para |
|---|---|
| frases do núcleo Revy (§5) | continua no `validate_workflow.py`, contra o template |
| slots presentes e núcleo em último | assertiva **nova** no `validate_workflow.py` |
| frases de comportamento que viraram texto gerado | **snapshots do gerador** no `chatbot-api` (§10) |

Deletar assertiva sem destino é regressão silenciosa de prompt — é justamente o que esse
validador já pegou antes.

### `fork_cloud_workflow.py` — dois pontos que abortam

1. **`HERDADOS`** (`:54`) é a lista fechada de nós que o Modo 2 herda. O nó novo que
   busca a config **precisa entrar nessa lista**, senão o Modo 2 nasce sem ele — e sem
   erro, porque o gerador só reclama de nó que sumiu do Modo 1, não de nó que ele não
   copiou.
2. **`INJECOES_INSTANCE`** (`:419`) faz substituição de **string literal** dentro do
   `jsCode` de `consultar_estoque1`, `simular1` e `TEMP continuar sem estoque1`, e aborta
   se o trecho não aparecer exatamente uma vez. Qualquer edição nessas tools para o modo
   seco **quebra o gerador do Modo 2** e precisa de ajuste no mesmo commit.

E a armadilha que nenhum dos dois pega, do learning: **saída órfã** — nó que sobrevive ao
recorte, continua rodando e tem o resultado descartado do outro lado. Ao comparar os
modos, comparar o que cada nó **consome**, não só quais existem.

## 8. Dívida herdada (não é desta feature, mas encosta)

`GET /v1/config/catalogo-bot` é cega para loja: `InventoryWriteClient.obter_loja()`
(`chatbot-api/app/inventory.py:461`) bate em `/v1/loja` do Estoque com bearer global,
sem slug. Com N lojas no Modo 2, todas recebem o catálogo de uma. É buraco do **contrato
com o Estoque**, não da credencial. Precisa de card próprio: ou o Estoque expõe catálogo
por slug, ou o chatbot passa a guardar a URL.

## 9. Ordem de implementação

Ordem de risco, não de tela.

0. **Spike de expressão no n8n** (§7). Uma expressão em `modelName` no n8n2037 resolve ou
   não? A resposta muda o tamanho do passo 3. Meia hora, e é a única coisa aqui que não
   se responde lendo código.
1. **Gerador de prompt + núcleo** no `chatbot-api`. Função pura: campos entram, texto
   sai. Sem rede, sem banco, sem n8n.
2. **Tabelas + migration `0027` + `GET /v1/agente/config`**, com `ctx.loja_id` resolvido
   antes do gate (§3.3).
3. **n8n**: slots no `systemMessage` do canônico + nó que busca a config (**entrando em
   `HERDADOS`**) + `modelName`/`maxOutputTokens` conforme o resultado do passo 0.
   Migrar as assertivas do `validate_workflow.py` (§7.1) **no mesmo commit**. Regerar o
   fork do Modo 2 e o de teste.
   **Com fallback**: rota falhou ou loja sem config → padrão Revy. O bot nunca fica sem
   prompt.
4. **Tela da Loja** — formulário consciente do modo (§4.4.1), campo livre com contador e
   aviso de conflito, rascunho, publicar, histórico. Flag OFF.
5. **Preview** — workflow gerado + nó-ponte `Extrair1` + telefone sintético + modo seco
   das tools.

## 10. Testes

**`chatbot-api`** (`cd chatbot-api`; macOS `.venv/bin/python -m pytest -q`,
Windows `.\.venv\Scripts\python.exe -m pytest -q`):

- snapshot do gerador em ~6 combinações de campo, incluindo as feias (formal +
  minúsculas; emoji à vontade + tom direto);
- **o núcleo continua sendo o último bloco mesmo com o campo livre preenchido**, e mesmo
  quando o texto livre tenta contrariá-lo;
- teto de 1000 chars do campo livre, e o detector de conflito avisando sem bloquear;
- isolamento por loja: credencial da A jamais recebe config da B;
- publicar / reverter / histórico;
- **modo seco não cria lead nem notificação** — teste explícito, é o risco nº 1;
- **preview não escreve `moto-escolhida` de telefone real** (§6.1.2);
- `FollowupWorker` respeita `followup_ativo=False` (§4.4.2) — loja desligada não recebe
  toque nenhum, e loja sem config continua recebendo (default ligado);
- as assertivas de comportamento migradas do `validate_workflow.py` (§7.1) — cada frase
  que saiu do JSON tem que ter um snapshot aqui. Assertiva sem destino é regressão.

**n8n**: assertiva nova garantindo que o núcleo Revy está presente **e é o último bloco**,
mais a migração descrita em §7.1. Os três existentes têm que voltar ao verde:
`validate_workflow.py`, `validate_workflow_cloud.py` (sai 1 se o fork for editado à mão)
e `validate_test_workflow.py`.

**`portal-gestao`**: a tela **não se verifica com pytest** — formulário e janela de teste
são JS, e isso já passou dois bugs no Copiloto. Verificação no navegador, com portal
local semeado.

## 11. Rollout

- Flag `REVY_LOJA_AGENTE_CONFIG_ENABLED` default 0 no código. No app2037 ela é
  **secret**, não `[env]` do toml — secret vence toml.
- **Chatbot antes do n8n.** Workflow subindo primeiro busca rota que não existe — é por
  isso que o fallback do passo 3 não é luxo.
- Deploy Fly usa a árvore local: **commitar antes de deployar**. Migration no produto
  certo (`alembic upgrade head` com `CHATBOT_DATABASE_URL`, senão o alembic responde
  SQLite e mente).
- n8n: import **desativa** o workflow; só `update:workflow --active=true` religa. **Não
  reiniciar o n8n2037** — restart custa ~6 min de webhook 404 e a Evolution cancela o
  retry nesse tempo.
- Mexeu em `app.css`? bump do `?v=` no `base.html`.
- Deploy só por `deploy/fly/3vm/`.

**Teste de aceite que importa:** a vitor motos entra com uma config que **reproduz o
prompt de hoje**. Se o bot mudar de jeito de falar no dia do deploy, é bug, não feature.
Só depois de o comportamento bater é que se mexe nos campos dela.

## 12. Riscos

| Risco | Mitigação |
|---|---|
| Modo seco vaza efeito colateral: lojista testa e cria lead falso | teste explícito (§10); tools que agem nunca executam no preview |
| Prompt gerado ruim em combinação estranha de campos | snapshot de ~6 combinações, incluindo as feias |
| Campo livre inflando custo e diluindo instrução (entra em toda mensagem) | teto de 1000 chars (§4.5) |
| Lojista escreve no campo livre, não pega, acha o produto quebrado | aviso de conflito na tela + preview antes de publicar |
| Loja sem config derruba o bot | fallback para o padrão Revy no nó do n8n |
| Fork do Modo 2 divergir do canônico | `validate_workflow_cloud.py` sai 1; nunca editar o fork à mão |
| Assertiva de prompt deletada em vez de migrada (§7.1) | tabela de destino por assertiva; snapshot no chatbot para cada frase que saiu do JSON |
| Preview corrompendo conversa real via `moto-escolhida` | telefone sintético por loja (§6.1.2) |
| Tool referenciando `Extrair1` inexistente no preview | nó-ponte de mesmo nome (§6.1.1) |
| Modo 2 nascer sem o nó de config | entrar em `HERDADOS`; o gerador não avisa (§7.1) |
| Campo configurado que não faz nada no modo da loja | formulário consciente do modo (§4.4.1) |
| Lojista estranhar o follow-up falando fora da voz que ele escolheu | incoerência aceita e documentada (§4.4.2); o interruptor permite desligar |
| Expressão em sub-nó do modelo não resolver | spike no passo 0 (§9) antes de dimensionar a Task |
| Lojista pedir para reabrir a regra 3 (insistir) | decisão registrada em §2 |
