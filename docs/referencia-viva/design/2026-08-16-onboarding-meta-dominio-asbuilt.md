# Onboarding Meta + domínio próprio — as-built (16/08/2026)

O que **existe e está verificado** depois da sessão de 16/08. Não é plano: cada linha
aqui foi conferida contra o RDAP, o DNS ou uma resposta HTTP real, não contra painel.

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
| 3 — verificação da empresa (CNPJ) | escala: sair dos 250/24h | não iniciado |
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

| Nome | Para quê |
|---|---|
| `CHATBOT_META_VERIFY_TOKEN` | tem que ser idêntico ao digitado no painel da Meta |
| `CHATBOT_META_APP_SECRET` | Chave Secreta do app; valida a assinatura do inbound |
| `CHATBOT_GRAPH_TOKEN` | token de **System User**, permanente — o do painel expira em 24h |

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

**Esta semana — terminar o site e a URL**

- [ ] delegação `.br` propagar e apontar para a Cloudflare (conferir por `nslookup -type=NS`, não por painel)
- [ ] custom domain `revyapp.com.br` e `www` no projeto Pages, certificado emitido
- [ ] testar e-mail de verdade para `contato@revyapp.com.br`
- [ ] preencher no app da Meta: as três URLs legais, `Domínios do aplicativo`, e-mail de contato, Categoria e ícone — hoje Termos e Exclusão apontam para `facebook.com`, o que lê como não configurado
- [ ] vincular o app ao portfólio empresarial (fim da tela Básico)
- [ ] commit e deploy do `app2037` com a remoção do `/site` — **só depois** que `revyapp.com.br` responder, senão o 301 aponta para o vazio

**Fim de semana de 22–23/08 — WhatsApp central da loja, para rodar segunda 24/08**

- [ ] apontar o webhook para o n8n e assinar `messages`
- [ ] os três secrets acima no `app2037`
- [ ] ciclo completo no **número de teste** antes de qualquer chip: mensagem → n8n → bot → rodízio → handoff
- [ ] eSIM de operadora brasileira com **voz/SMS** — eSIM de viagem (Airalo, Holafly) é só dados, não recebe SMS e **não serve**
- [ ] número que **nunca teve WhatsApp**; e uma vez na Cloud API ele fica **bot-only**, não volta a funcionar no app
- [ ] Etapa 2 do painel: substituir o número de teste pelo número real
- [ ] projetar `whatsapp_modo = 2` **numa loja só**

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
- Telefone do cartão CNPJ está truncado em 8 dígitos: `(19) 98469808`. O site anuncia
  `+55 51 98033-6365`. **Declarar o mesmo número dos dois lados** na verificação.
