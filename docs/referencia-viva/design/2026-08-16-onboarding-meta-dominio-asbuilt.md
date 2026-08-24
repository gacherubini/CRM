# Onboarding Meta + domínio próprio — as-built (16/08, atualizado em 23/08/2026)

O que **existe e está verificado** depois das sessões de 16/08 (domínio, site, conta na
Meta) e 23/08 (webhook, token, inscrição na WABA, template, documentos do CNPJ). Não é
plano: cada linha aqui foi conferida contra o RDAP, o DNS, o Graph API ou uma resposta
HTTP real — nunca contra painel.

Complementa [`2026-08-16-whatsapp-modo2-asbuilt.md`](2026-08-16-whatsapp-modo2-asbuilt.md),
que descreve o bot. Este cobre a infraestrutura que faltava para ele sair do laboratório.

Versão de leitura, com os mesmos fatos em checklists clicáveis — útil para acompanhar do
celular enquanto se clica nos painéis: <https://claude.ai/code/artifact/bff93889-3be9-4e75-af3c-a8cae3c29218>
(privada, acessível apenas pelo dono da conta).

## Placar dos quatro portões da Meta

A verificação da Meta não é uma etapa, são quatro em sequência, cada uma destravada pela
anterior. Só a terceira olha o CNPJ.

| Portão | O que destrava | Situação |
|---|---|---|
| 1 — conta pessoal do Facebook | criar o app | **feito** 16/08 |
| 2 — app + produto WhatsApp + vínculo | o botão "Iniciar verificação" existir | **feito** 16/08 |
| 3 — verificação da empresa (CNPJ) | escala: sair dos 250/24h | **submetida** 23/08, em análise (~2 dias úteis) |
| 4 — nome de exibição "Revy" | o cliente ver "Revy" no lugar do número | bloqueado pelo 3 |

**O portão 3 não bloqueia o piloto.** Ver "Limites sem CNPJ" no fim.

## Domínio

`revy.com.br` **não é nosso** — registrado em 29/05/2025 pela Drexia Marketing e
Publicidade (CNPJ 45.889.181/0001-97), em parking, vencendo 20/10/2026. Não planejar em
cima disso.

Registrado no lugar:

| | |
|---|---|
| Domínio | `revyapp.com.br` |
| Criado | 16/08/2026, expira 16/08/2027 |
| **Titular** | 66.261.888 CAUA SCARPA SCHNEIDER — **CNPJ** 66.261.888/0001-24 |
| Conta registro.br | GACHE45 (Gabriel Cherubini), admin/técnico/cobrança |
| Nameservers | `demi.ns.cloudflare.com` / `scott.ns.cloudflare.com` |
| DNSSEC | **removido** (`delegationSigned: false`) |

**Registrar no CNPJ e não no CPF foi decisão deliberada.** O titular fica público no
RDAP do registro.br — foi assim que se descobriu o dono do `revy.com.br`. Com o domínio
no CNPJ, o revisor da Meta confirma sozinho que o site e a empresa dos documentos são a
mesma entidade. É a prova de vínculo mais barata que existe, e vem de graça.

### Armadilha do DNSSEC (custou o maior risco do dia)

Domínio `.br` que nasce no DNS do registro.br nasce **com DNSSEC ligado**, assinado pelas
chaves deles. Trocar o nameserver para externo deixando o DS no lugar faz todo resolvedor
que valida DNSSEC devolver SERVFAIL: o domínio **some do país inteiro** e o erro não diz
por quê. A maioria dos provedores brasileiros valida.

Aqui o DS caiu sozinho ao sair do DNS do registro.br (confirmado por RDAP), mas a ordem
correta é **remover o DNSSEC primeiro, trocar o nameserver depois**, e conferir por RDAP,
não pelo painel.

### Janela de transição de ~2h

O registro.br não delega para nameserver externo na hora: mostra *"os servidores DNS do
domínio se encontram em transição"* com contador de ~2 horas. Antes disso, o RDAP segue
mostrando os nameservers antigos com `status: nicbr waiting activation` — **isso não é
falha de salvamento**, e refazer a operação não adianta.

## Site

Saiu do bundle do Fly. Antes: `app2037.fly.dev/site/`, servido por um nginx `:8081` dentro
da imagem. Agora: **Cloudflare Pages**, projeto `revyapp`, por direct upload.

| URL canônica | |
|---|---|
| `revyapp.com.br/` | landing |
| `revyapp.com.br/privacidade` | Política de Privacidade |
| `revyapp.com.br/termos` | Termos de Serviço |
| `revyapp.com.br/exclusao-de-dados` | Exclusão de dados |

**Sem `.html`.** O Pages faz 308 de `/privacidade.html` para `/privacidade`; os links
internos e os `canonical` já apontam para a forma limpa. Ao preencher os campos do app na
Meta, usar a forma sem extensão.

As três páginas legais foram escritas em 16/08 a partir do que o código **realmente faz**
(payload pessoal cifrado em repouso no motor, índice cego do CPF, telefone mascarado na
auditoria), não de modelo genérico. Todas trazem razão social, CNPJ e endereço no rodapé —
que é o que a Meta procura.

Direct upload **não converte para Git depois**. Atualização é por
`npx wrangler pages deploy site --project-name=revyapp`, ou arrastando de novo. A escolha
foi consciente: integração Git daria à Cloudflare leitura do monorepo inteiro para servir
uma landing de quatro arquivos.

### O que mudou no `deploy/fly/3vm/`

- `nginx-edge.conf`: proxy `/site/ → :8081` e entrada `site2037.fly.dev` do map **removidos**;
  no lugar, 301 para `revyapp.com.br`. São **dois** blocos (`= /site` e `^~ /site/`) de
  propósito — `^~ /site` sozinho engoliria `/sitemap.xml`.
- `Dockerfile.app`: removidos os três `COPY site/*`, o `COPY site-nginx.conf` e o `ln -sf`.
- `site-nginx.conf`: deletado.
- `.dockerignore` (raiz e 3vm): `site/` agora sai do contexto de build.

Publicar o site **deixou de ser deploy do Fly**. Portal, Control, catálogo, chatbot e
mídia não foram tocados.

## E-mail

Cloudflare Email Routing em `revyapp.com.br`. Destino `revystartup@gmail.com`, verificado.
Endereço público `contato@revyapp.com.br`, encaminhamento. Catch-all fica **desligado** de
propósito: encaminhar qualquer endereço vira ímã de spam assim que o domínio aparece.

Só recebe. Para **enviar** de `contato@` depois (Workspace, Zoho), o SPF tem que ser
**mesclado** num registro só — dois TXT de SPF invalidam os dois.

## Meta

| | |
|---|---|
| App | `Revy` — App ID `1370395535203964` |
| WABA | `1057786396969642` |
| Número de teste | `+1 555 200-0666` — Phone Number ID `1227059273831581` |
| Conta Cloudflare | `9ee6d1a6fb9eb76a75fd8c63161a3365`, zona `baa9f3a733c7b1ab56f4c969fd01aad3` |

**Testado e funcionando em 16/08 23:25:** template enviado do número de teste para
`+55 51 98033-6365`, com dois webhooks `messages` de volta. O caminho de saída está vivo.

Esses webhooks caem **no console da Meta**, não no `wCloudMeta0001`. Ligar a entrada é o
passo seguinte.

### Entrada: o webhook vai para o n8n, não para o chatbot

```
Callback URL:  https://n8n2037.fly.dev/webhook/whatsapp-cloud
```

Dois webhooks no mesmo path — `GET` de verificação e `POST` de inbound. O n8n **não valida**
o verify token: repassa a verificação para `GET /webhook/cloud` no chatbot, que compara com
`secrets.compare_digest` e devolve o `hub.challenge` **em texto puro** (aspas de JSON
reprovam). A assinatura do `POST` é conferida no chatbot sobre o corpo cru.

Assinar o campo `messages` na lista de webhook fields — sem isso a Meta não entrega nada,
mesmo com a URL certa.

### Secrets do `app2037` (conferir por nome, nunca por valor)

| Nome | Para quê | Estado |
|---|---|---|
| `CHATBOT_META_VERIFY_TOKEN` | tem que ser idêntico ao digitado no painel da Meta | posto 23/08 |
| `CHATBOT_META_APP_SECRET` | Chave Secreta do app; valida a assinatura do inbound | posto 23/08 |
| `CHATBOT_GRAPH_TOKEN` | token de **System User**, permanente — o do painel expira em 24h | posto 23/08 |
| `CHATBOT_GRAPH_PHONE_NUMBER_ID` | número de onde a central fala; fallback do `cloud_canal.py` quando a loja não tem canal | posto 23/08 (`1227059273831581`, o de teste) |
| `CHATBOT_GRAPH_TEMPLATE_OFERTA` | nome do template de oferta | **não posto de propósito** — o default do código já é `chama_vendedor` |

## Sessão 23/08 — o encanamento do Modo 2 fechou

Tudo aqui foi conferido contra resposta HTTP real (Graph API, log do `app2037`), não
contra painel. O que o painel diz e o Graph desmente, vale o Graph.

### O que passou a existir

| Peça | Estado | Como foi conferido |
|---|---|---|
| Webhook da Meta | verificado e salvo | `hub.challenge` volta cru pelo n8n |
| Campo `messages` | assinado | lista de webhook fields do painel |
| App `Revy` | **Ao Vivo** | barra lateral → *Publicar* → etiqueta "Publicado" |
| Token de System User | permanente | `debug_token`: `SYSTEM_USER`, `expires_at: 0` |
| App inscrito na WABA | sim | `GET /{waba}/subscribed_apps` lista `Revy` |
| Template `chama_vendedor` | `PENDING`, categoria `UTILITY` | `GET /{template_id}` |

### Os cinco testes que provaram a entrada

Na ordem, do mais isolado ao mais completo:

| # | Teste | Esperado | Resultado |
|---|---|---|---|
| 1 | `GET /webhook/cloud` no chatbot, token certo | challenge cru | `12345` |
| 2 | idem via `n8n2037` | challenge cru, **sem envelope JSON** | `12345` |
| 3 | idem, token errado | reprova | `403 verify token inválido` |
| 4 | `POST` assinado direto no chatbot | aceita | `200 {"ok":true,"mensagens":[]}` |
| 5 | `POST` com assinatura forjada | recusa | `401 assinatura inválida` |
| 6 | `POST` assinado **via n8n** | corpo cru chega inteiro | log: `POST /webhook/cloud 200 "n8n"` |

O 6 é o que a Task 5 do card de fechamento chamava de *"o teste que decide tudo"*: se o
n8n reserializasse o corpo, o HMAC não fecharia e viria `401`. Veio `200`.

Depois, o botão **Teste** do campo `messages` no painel — primeiro payload assinado pela
**Meta**, não por nós:

```
phone_number_id sem loja: 123456123
POST /webhook/cloud 200 OK   ("n8n")
```

O `123456123` é o número fictício do payload de teste. O chatbot validou a assinatura,
parseou, não achou loja dona e descartou logando — o comportamento que a §6.2 pede.

### Armadilha: app não inscrito na WABA é silêncio, não erro

Antes da inscrição, `GET /{waba}/subscribed_apps` devolvia **só** o
`WA DevX Webhook Events 1P App` (id `2202427980234937`) — o app interno que o botão
*Teste* do painel usa. Ou seja: **o teste do painel chegava e mensagem real não chegaria**,
sem erro em lugar nenhum. Webhook verificado, campo assinado, token válido, e silêncio.

Corrigido com `POST /{waba}/subscribed_apps` usando o token de System User. **Toda WABA
nova precisa disso** — inclusive a de cada loja, quando o desenho do §16.6 entrar.

### Armadilha: o token de System User precisa de DOIS ativos

Atribuir só a WABA faz a tela *Atribuir permissões* abrir vazia, com
*"Nenhuma permissão disponível — atribua uma função do app ao usuário do sistema"*. O
usuário do sistema precisa de **Apps → Revy (acesso total)** *e*
**Contas do WhatsApp → a WABA (acesso total)**. São ativos separados: um diz quem fala,
o outro sobre o quê.

Expiração: **Nunca**. A Meta recomenda 60 dias presumindo rotação automática, que não
existe aqui — e um token que morre sozinho derruba todas as lojas em silêncio (dívida
conhecida, §16.7 da spec).

### O template de oferta, e por que ele tem exatamente uma variável

`oferta_envio.py:74` manda `variaveis=[vendedor.nome]` e um botão de resposta rápida. O
template aprovado tem que casar com isso ou o envio falha:

```
nome    chama_vendedor        idioma  pt_BR        categoria  UTILITY
corpo   "Olá {{1}}, lead novo na loja. Toque em Peguei para assumir o atendimento."
botão   [Peguei]  (QUICK_REPLY)
```

O corpo espelha de propósito o `resumo` do envelope interativo (`oferta_envio.py:55`) —
a §5.7 diz *"dois envelopes, um significado"*. Sem `wa.me`, sem botão de URL, sem telefone
do cliente: o contato só vai **depois** do clique.

Ficar em `UTILITY` é o que importa. Reclassificado como `MARKETING`, cada oferta custaria
~10× (§9).

### Correção no `workflow-cloud`: `lastNode` envelopa o challenge

O webhook GET do `wCloudMeta0001` estava com `responseMode: lastNode`, e o n8n serializa
a saída do nó: a Meta recebia `{"data":"<challenge>"}` em vez do challenge. Como ela
compara o **corpo inteiro**, a verificação reprovaria — e o sintoma seria só
*"não foi possível validar o token"*, mandando procurar no lugar errado.

Corrigido no gerador (`n8n/fork_cloud_workflow.py`): `responseMode: responseNode` mais um
nó `Responder verificacao` (`respondToWebhook`, `respondWith: text`,
`responseBody: {{ $json.data }}`). O `n8n/validate_workflow_cloud.py` passou a exigir
esse formato, então não regride calado. Workflow subiu de 20 para **21 nós**.

Publicação: `prepare-workflow.ps1` ganhou o **`-Mode cloud`** (antes só tratava o
workflow do Modo 1, e o cloud precisava das quatro transformações à mão).

### Verificação de CNPJ: submetida em 23/08

Os documentos foram gerados e batidos contra o site, e a verificação foi **submetida em
23/08**. A Meta anunciou análise de ~2 dias úteis.

| Item | Valor |
|---|---|
| Nome legal | `66.261.888 CAUA SCARPA SCHNEIDER` — o cartão CNPJ traz *Título do Estabelecimento* vazio, então **"Revy" não entra no campo de nome legal** |
| CNPJ | `66.261.888/0001-24` — MEI, ME, **ATIVA** desde 14/04/2026, CNAE 73.19-0-02 |
| Endereço | `Rua Paulista, 228 — Boa Vista — Limeira/SP — 13486-107`, **sem complemento** |
| Telefone | `+55 19 99846-9808` |
| Site / e-mail | `https://revyapp.com.br` · `contato@revyapp.com.br` |

**Documento principal: o CCMEI** (`gov.br/mei` → *Emitir Certificado de MEI*, login do
titular), duas páginas — a 2ª é o Termo de Ciência com o QR de validação e **vai junto**.
Ele escreve "RUA PAULISTA" por extenso, batendo letra a letra com o rodapé do site,
enquanto o cartão CNPJ abrevia "R PAULISTA". Reserva: o cartão CNPJ
(`solucoes.receita.fazenda.gov.br/servicos/cnpjreva/cnpjreva_solicitacao.asp`).

**O telefone truncado deixou de ser pendência.** O cartão CNPJ imprime `(19) 9846-9808` —
o mesmo número sem o nono dígito, truncagem de cadastro antigo. **O CCMEI não imprime
telefone nenhum**, então não existe string para divergir. O que a Meta compara é nome
legal + endereço.

O site foi alinhado ao cadastro em 23/08: `+55 19 99846-9808` no bloco Contato da landing
e no bloco de identidade das três páginas legais. O **`wa.me/5551980336365` ficou intacto
de propósito** — é por ele que o lead fala com a Revy, e apontar o botão de WhatsApp para
um número sem WhatsApp mataria a captação para ganhar uma linha de rodapé.


### O caminho na interface, e as três armadilhas dele

**Não é em *Autorizações e verificações*** — essa tela só trata autorização de anúncio
(CBD, apostas, Singapura). O fluxo mora em **Central de Segurança**, rolando até o fim, na
seção *Verificação da empresa*; o caso de uso é **"O app exige acesso a permissões no Meta
for Developers"**. O botão *Ver detalhes*, ao lado de *Não verificada* em
*Informações da empresa*, cai no mesmo lugar.

Respostas do questionário: **Empresa individual** (MEI é um titular só; *Empresa privada* é
Ltda) e **Tem registro** — a própria descrição dessa opção cita o CCMEI pelo nome.

**Armadilha 1 — o fluxo lê os *Detalhes da empresa*, e eles estavam podres.** Razão social
era `Revy`, site era `https://app2037.fly.dev/site/`, telefone vazio e endereço só `Brasil`.
Corrigir isso é **pré-requisito**, não detalhe: é esse bloco que o revisor compara com o
documento. Ao digitar o endereço, o `228` virou `22` — conferir depois de salvar. O campo
*Nome comercial alternativo* fica **vazio**: não há documento que ligue "Revy" ao CNPJ, e
preencher convida a Meta a pedir um que não existe.

**Armadilha 2 — o telefone truncado voltou, e só o e-mail o dissolve.** A tela de upload tem
**duas** seções: *Verificar a razão social* e *Verificar telefone*. O CCMEI **não aparece na
lista da segunda**, porque não imprime telefone — e o único documento que imprime é o
cartão CNPJ, com `(19) 9846-9808`, sem o nono dígito. O que resolve é a tela seguinte, de
conexão com a empresa, onde as exigências documentais **diferem por método**:

| Método | O documento precisa ter |
|---|---|
| **Email** | razão social **e o endereço _ou_ o telefone** |
| Ligação / SMS / WhatsApp | razão social **e o telefone** |

Só o **Email** aceita endereço no lugar do telefone — e o CCMEI tem razão social + endereço.
É por isso, e não por ser o "Recomendado", que ele é o caminho: entrega um documento só, que
bate limpo, e tira o cartão CNPJ da jogada. Nunca alinhar o telefone declarado à versão de 8
dígitos para "casar" com o cartão: número truncado não recebe SMS e trava a confirmação.

**Armadilha 3 — voltar consome o método.** Depois de um *Voltar* na tela do código, **Email**
e **Verificação de domínio** sumiram da lista, deixando só as três que exigem telefone no
documento. Reabrir o fluxo pelo *Ver detalhes* devolve as opções.

O e-mail tem que ser **`contato@revyapp.com.br`**: o catch-all está desligado de propósito,
então qualquer outro endereço do domínio não existe e o código se perde sem erro. Código
válido por 60 minutos, e ele cai na aba **Social** do Gmail, não na Primary.

## Limites sem CNPJ verificado

O teto de **250 clientes únicos por 24h rolantes** conta **só conversa iniciada pela
empresa** (template, fora da janela). Conversa que o cliente inicia, e toda troca dentro
das 24h contadas a partir da última mensagem **dele**, não consome nada. Só a mensagem do
cliente reinicia a janela; mensagem do bot não estende.

Como o funil é CTWA, o bot inteiro roda dentro da janela de serviço. Numa loja, o gasto
real é só follow-up de quem sumiu.

**Não há prazo para verificar** — dá para operar não verificado por tempo indeterminado.
O que a verificação compra não é volume:

- **nome de exibição** — conta não verificada não é elegível; quem não salvou vê os dígitos;
- **mais de 2 números** — e como o design é um número central **por loja**, isso é
  literalmente **duas lojas**. A terceira exige o CNPJ.

Desde 07/10/2025 o limite é **por portfólio**, não por número: não dá para ganhar
capacidade espalhando em mais números.

**01/10/2026** — mensagem de serviço volta a ser cobrada. Conversa nascida de anúncio
Click-to-WhatsApp entra como *free entry point* e **continua grátis**, com janela de 72h.
Lead orgânico passa a custar por mensagem. Manter o CTWA como porta de entrada deixou de
ser questão de atribuição e virou questão de custo.

## O que falta

**Fechado em 23/08** (conferido por HTTP/Graph, não por painel)

- [x] delegação `.br` propagou — `nslookup -type=NS` devolve `demi`/`scott.ns.cloudflare.com`
- [x] `revyapp.com.br` e as três URLs legais respondem **200 em HTTPS**, certificado emitido
- [x] ficha do app preenchida: três URLs legais, `Domínios do aplicativo`, e-mail, categoria
      *Negócio e Páginas*, ícone
- [x] app vinculado ao portfólio empresarial (`business_id=4040462592922875`)
- [x] app **publicado** (Ao Vivo) — na interface nova isso mora na barra lateral em
      **Publicar**, não num interruptor no topo; a etiqueta vira "Publicado" e aparece
      *Tirar do ar*
- [x] webhook apontado para o n8n, verificado, campo `messages` assinado
- [x] os secrets no `app2037` (tabela acima) — quatro, não três
- [x] app inscrito na WABA (`subscribed_apps`) — **não estava**, e é silêncio quando falta
- [x] template `chama_vendedor` submetido (`UTILITY`, `pt_BR`)
- [x] documentos da verificação de CNPJ gerados e batidos contra o site

**Ainda aberto — Meta**

- [ ] meio de pagamento na WABA (item da Etapa 2) — sem ele, mensagem iniciada pela empresa
      não sai, e é ela que o rodízio usa com janela fechada
- [ ] aprovação do `chama_vendedor` (estava `PENDING`)
- [ ] **resultado** da verificação do CNPJ — submetida 23/08 (CCMEI + confirmação por
      e-mail), análise ~2 dias úteis
- [ ] eSIM de operadora brasileira com **voz/SMS** — eSIM de viagem (Airalo, Holafly) é só dados, não recebe SMS e **não serve**
- [ ] número que **nunca teve WhatsApp**; e uma vez na Cloud API ele fica **bot-only**, não volta a funcionar no app
- [ ] Etapa 2 do painel: registrar o número real ao lado do de teste

**Ainda aberto — nosso lado (é o que trava o ciclo ponta a ponta)**

- [ ] cadastrar o canal da loja. **A instrução antiga estava errada**: `POST
      /v1/whatsapp/canais` **não aceita `waba_id`** — o schema tem só `evolution_instance` e
      `e164_or_label`, e `register_channel` nunca grava WABA nem template. Para o piloto basta
      um canal com `evolution_instance = <phone_number_id>` (cura o inbound; o outbound cai no
      fallback do ambiente). Loja real precisa de `waba_id` + `template_oferta`, hoje só por
      escrita direta no banco. Ver o learning `canal-cloud-nao-se-cadastra-pela-api`
- [x] flags do Modo 2 no `app2037` — **são três**, e as três ficaram em `1` em 23/08:
      `REVY_CONTROL_WHATSAPP_MODO2_ENABLED` (o rádio na ficha da loja),
      `CHATBOT_WHATSAPP_MODO2_ENABLED` (rodízio e workers) e `MULTI_WHATSAPP_ENABLED`
      (a rota de canais, que sem ela responde 404). As duas do chatbot já estavam ligadas
- [ ] projetar `whatsapp_modo = 2` **numa loja só**
- [ ] cadastrar a fila de vendedores (autoatendido na Loja)
- [ ] ciclo completo no **número de teste** antes de qualquer chip: mensagem → n8n → bot →
      rodízio → handoff. Hoje pararia em `phone_number_id sem loja`, que é a mesma linha
      de log do teste do painel
- [ ] provider de transcrição (Groq) — `CHATBOT_AUDIO_TRANSCRIPTION_URL` / `_TOKEN`

**Conferido em 23/08, no fim da sessão**

- [x] `contato@revyapp.com.br` entrega de verdade — o código da Meta chegou no
      `revystartup@gmail.com` pelo Email Routing, na aba **Social** do Gmail
- [x] 301 de `/site` no `app2037` — `https://app2037.fly.dev/site/` responde
      `301 → https://revyapp.com.br/`, e as páginas legais respondem 200

**Dívida que precede cliente real:** o **VAD do áudio** (§5.10). O Whisper inventa frase
plausível em áudio mudo e o bot **age** em cima da transcrição — dois segundos de moto
passando viram uma frase que não existiu. O as-built do Modo 2 já marca como risco nº 1.

## Pendências fora do caminho crítico

- Conta Cloudflare está em `G.cherubini@edu.pucrs.br`. E-mail institucional some quando
  se forma — e essa conta controla DNS, site e e-mail do domínio. Trocar para
  `revystartup@gmail.com` e ligar 2FA.
- Alerta de segurança aberto na conta do registro.br.
- Sem nome fantasia no cartão CNPJ, nada liga "Revy" ao CNPJ além do site. Registrar na
  JUCESP resolve o portão 4 na raiz: **não exige consulta de viabilidade**, assina com
  senha gov.br (sem certificado digital), DARE ~R$ 95, poucos dias úteis. Fazer só quando
  for verificar — antes disso não serve para nada.
- Nome fantasia na JUCESP **não é marca**. Marca é INPI, e uma agência já segurou o
  `revy.com.br`.
- Telefone do cartão CNPJ está truncado em 8 dígitos: `(19) 9846-9808`, sem o nono. Dar isso
  por encerrado foi **cedo demais**: a seção *Verificar telefone* do fluxo de verificação
  pede documento com telefone, e aí o cartão é o único que serve. Nesta submissão o caminho
  do e-mail contornou (ver "as três armadilhas"), mas se a Meta recusar, o conserto de raiz
  é atualizar o telefone no cadastro do MEI e reemitir o cartão com nove dígitos. O site já
  anuncia `+55 19 99846-9808` nas quatro páginas; o `wa.me/5551980336365` da landing é o
  canal de captação e fica como está.
