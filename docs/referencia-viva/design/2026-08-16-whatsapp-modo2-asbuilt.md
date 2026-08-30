# Modo 2 (central Cloud API) — as-built em 2026-08-16

Spec: [`../specs/2026-08-12-whatsapp-dois-modos-design.md`](../specs/2026-08-12-whatsapp-dois-modos-design.md).
Este arquivo diz **o que existe no `main`**, não o que foi planejado. Onde houver
divergência com a spec, a spec é o alvo e este documento é o placar.
Última atualização: **29/08**, quando o onboarding de loja cliente mudou de
caminho (seção "2026-08-29 — como uma segunda loja entra"). O piloto em produção
está em "Piloto do Modo 2", de 23–24/08.

## O buraco que este dia fechou

O Modo 2 foi construído em 13–14/08 e mergeado em 16/08 com a **metade da
distribuição** pronta (rodízio, oferta, trava, handoff, follow-up) e **sem a
metade do atendimento**. Na prática, com a flag ligada e uma loja em Modo 2:

- o cliente escrevia para a central,
- a mensagem era gravada no banco,
- **ninguém respondia**, e
- **nenhum vendedor era chamado, nunca.**

Causa: o `n8n-cloud` era um transporte de **4 nós** (recebe da Meta, repassa,
fim). A §5.9 pede *"cópia do fluxo atual (`workflow-ai-nao-salvos.json`) trocando
Evolution por Graph API — não um bot novo"*. Não havia IA em lugar nenhum: o
`chatbot-api` não tem Gemini/OpenAI/LangChain, e a ferramenta `solicitar_handoff`
— o elo que abre o rodízio — só existia no workflow do Modo 1, apontando para a
Evolution.

O validador do workflow **aprovava** esse estado: ele cravava o formato de 4 nós.
Um validador que sanciona o stub é pior que nenhum, porque dá aval.

## Placar por seção da spec

✅ significa **existe no `main`**. Onde o piloto de 23/08 exercitou a peça em
produção, está escrito *provado*; onde não exercitou, está escrito *não
exercitado* — código verde não é caminho andado.

| Spec | Peça | Estado |
|---|---|---|
| §5.1 | Bot atende o cliente na central | ✅ agente no `n8n-cloud` (fork de 20 nós) — **provado em produção 23/08** |
| §5.2 | Gatilho *simulação pronta* | ✅ via `solicitacoes-simulacao-humana` — não exercitado no piloto |
| §5.2 | Gatilho *simulação falhou* | ✅ mesmo caminho, `motivo=simulacao_falhou` — não exercitado no piloto |
| §5.2 | Gatilho *cliente pede humano* | ✅ `POST /v1/operacao/handoff-humano` — **provado 24/08** |
| §5.3 | Rodízio, ponteiro, 10 min, uma volta | ⚠️ `rodizio.py` + worker — **primeira oferta provada 24/08**. A **reoferta nunca era enviada** (só trocava de dono no banco); corrigido em 24/08, ver abaixo. Ponteiro, prazo e volta completa seguem **sem prova em produção**: a fila do piloto tem um vendedor só |
| §5.4 | Silêncio pós-handoff, re-notificação | ✅ `pos_handoff.py` — **silêncio provado 24/08** (`bot_ativo=False`); re-notificação não exercitada. O **follow-up estava quebrado** pelo mesmo defeito de outbound do rodízio, corrigido junto em 24/08 |
| §5.5 | Vendedor × cliente por variantes | ✅ |
| §5.7 | "Peguei" = clique, primeiro vence | ✅ trava idempotente — **clicado em produção 24/08**, oferta ficou `travada`. "Primeiro vence" com dois cliques concorrentes segue não exercitado |
| §5.8 | Control escolhe o modo | ✅ `whatsapp_modo` por loja; no piloto a projeção foi semeada à mão, o Control não escreveu. **Desde 29/08 a projeção `2` também ativa** o canal `cloud_pendente` — mesmo lever, sem rota nova. O Control **ainda não** mostra o estado de cada loja |
| §5.9 | Fork do fluxo atual | ✅ gerado, 20 nós; publicado e **ativo** no `n8n2037` desde 23/08 |
| §5.9 | Debounce 40 s | ✅ herdado |
| §5.9 | Follow-up 30 min + 1 h | ✅ prazos e regras |
| §5.9 | Classificação das 6 etapas | ⚠️ **só `so_oi`** |
| §5.9 | Recusa não cutuca | ❌ **não existe** |
| §5.10 | Mídia pelo Graph, `language: pt` | ✅ |
| §5.10 | Transcrição só no Modo 2 | ✅ |
| §5.10 | VAD / baixa confiança → fallback | ❌ **não existe** |
| §5.11 | Simulação que falha | ✅ |
| §6.1 | 200 imediato + dedup por `wamid` | ✅ — o dedup tinha um bug de reentrega pós-restart, corrigido em produção (`922a365`, abaixo) |
| §6.1 | "Processar depois" (retry) | ✅ `cloud_evento_falho` + worker |
| §6.2 | Segredo da Meta só no chatbot | ✅ validador recusa vestígio |
| §6.3 | Gate fail-closed (flag + loja + projeção) | ✅ — **provado 23/08**: com a loja `teste` semeada, `loja_opera_modo2()` devolve `True` e a linha `phone_number_id sem loja` sumiu do log |

## O fork é gerado, não escrito à mão

`n8n/fork_cloud_workflow.py` monta o `workflow-cloud.json` a partir do
`workflow-ai-nao-salvos.json`. O AI Agent, o Gemini, a memória e as ferramentas
saem **byte-a-byte iguais** — um fork escrito à mão vira outro bot na primeira
divergência, que é o que a §5.9 proíbe. Mudou o Modo 1? Rode de novo e commite.

O gerador **recusa referência órfã** (`$('Nó')` apontando para nó que ficou para
trás). Foi ele que pegou, na primeira execução, o `AI Agent1` citando
`Registrar mensagem e ler handoff1` e o `Gate resposta mais recente1` citando
`Gate somente nao salvos1` — o erro que um fork por recorte comete calado e só
aparece em produção. Resolvido com **dois nós-ponte de mesmo nome**, em vez de
reescrever o agente.

### O que muda do Modo 1 para o Modo 2

| | Modo 1 | Modo 2 |
|---|---|---|
| Entrada | webhook Evolution | dois webhooks Meta (GET verificação, POST `rawBody`) |
| Assinatura | — | conferida no chatbot, sobre o corpo cru |
| Saída | `sendText` Evolution | `POST /v1/operacao/responder` no chatbot |
| `solicitar_handoff` | avisa a equipe pela Evolution | **abre o rodízio** |
| Gate virgem/salvo | isSaved na Evolution | não se aplica (central é só-bot, §5.9) |
| Grupo de estoque | sim | não (grupo é Modo 1) |

Fora do fork **de propósito**: `enviar_foto_veiculo` (manda mídia pela Evolution;
a central precisaria de envio de imagem pelo Graph, que não existe) e
`cadastrar_veiculo` (grupo de estoque). `enviar_link_catalogo` cobre "quero ver
as motos" — o bot manda o **link**, não as fotos.

## O que falta (dívida conhecida, em ordem de risco)

**1. VAD / baixa confiança no áudio (§5.10) — o mais urgente.**
A própria spec chama de *"o risco real, não o WER"*: o Whisper **inventa frase
plausível** em áudio mudo ou só com ruído, e aqui o bot **age** em cima da
transcrição. Um áudio de 2 s de moto passando pode virar uma frase inventada e o
bot responde àquilo. A spec manda: sem voz detectada não vai ao provider;
transcrição vazia ou suspeita cai no fallback "manda por texto". Hoje vai tudo
direto ao provider e o texto volta sem filtro.

**2. Recusa não cutuca (§5.9, regra 5).**
Cliente que responde "valeu", "não precisa" ainda leva os dois toques do
follow-up. Não há nada no `chatbot-api` sobre recusa.

**3. Classificação das etapas do follow-up (§5.9).**
`classificar_etapa` devolve sempre `"so_oi"`. A tabela das 6 etapas existe com os
textos exatos da spec, mas cinco são código morto: quem parou no anúncio ou no
catálogo recebe *"e aí amigo, ainda tá aí?"*. Depende do estado do intake, que
ainda não existe — está isolado numa função só para o intake plugar depois.

**4. Foto de moto no Modo 2.**
Precisa de envio de imagem pelo Graph + rota no chatbot.

## Onde mexer

| O quê | Arquivo |
|---|---|
| Gerar o workflow | `n8n/fork_cloud_workflow.py` |
| Invariantes do workflow | `n8n/validate_workflow_cloud.py` |
| Gate único do Modo 2 | `chatbot-api/app/rodizio.py::loja_opera_modo2` |
| Gatilhos do handoff | `chatbot-api/app/handoff_gatilhos.py` |
| Follow-up (prazos e textos) | `chatbot-api/app/followup_job.py` |
| Áudio (download, transcrição) | `chatbot-api/app/audio.py` |
| Retry do inbound | `chatbot-api/app/cloud_retry.py` |
| Workers do Modo 2 | `chatbot-api/app/modo2_workers.py` |
| Elos que falam com a Graph (29/08) | `chatbot-api/app/meta_onboarding.py` |
| Ordem, retomada e teto do onboarding (29/08) | `chatbot-api/app/onboarding_cloud.py` |
| Portão do Control que ativa o canal (29/08) | `chatbot-api/app/provisioning.py::_liberar_canal_cloud` |
| Tela de conexão na Loja (29/08) | `portal-gestao/app/web/loja_whatsapp.py` + `app/loja/whatsapp_canais.py` |

**Nunca edite `n8n/workflow-cloud.json` à mão** — o validador compara com o que o
gerador produz e sai com código 1. Ajuste o gerador e rode.

## Estado operacional

Flag `CHATBOT_WHATSAPP_MODO2_ENABLED=1` no `app2037` desde 16/08. O gate é
fail-closed em três condições (§6.3): flag, loja operacional e projeção
`whatsapp_modo == "2"` vinda do Control. Até 23/08 **nenhuma loja tinha essa
projeção**, então os workers subiam e não tocavam em nada.

**23/08: as credenciais da Meta deixaram de ser pendência.** Verify token, App Secret,
token de System User (permanente) e `phone_number_id` estão nos secrets do `app2037`; o
webhook está verificado com o campo `messages` assinado; o app está Ao Vivo e **inscrito
na WABA**; o `chama_vendedor` foi submetido. A entrada foi provada ponta a ponta, inclusive
com payload assinado pela própria Meta. Detalhe, testes e armadilhas em
[`2026-08-16-onboarding-meta-dominio-asbuilt.md`](2026-08-16-onboarding-meta-dominio-asbuilt.md),
seção "Sessão 23/08". A verificação de CNPJ da Revy foi submetida em 23/08 e saiu
**Verificada em 24/08** — não bloqueou o piloto, e em 29/08 virou pré-requisito do
Tech Provider.

## Piloto do Modo 2 — noite de 23/08, em produção

Rodou no `app2037` com o **número de teste** da Meta (`+1 555 200-0666`, WABA
`1057786396969642`). O que foi montado do nosso lado:

| Peça | Estado no piloto |
|---|---|
| Loja `teste` no Postgres do chatbot | `loja_id = 63cb8fba-8fc2-4767-b2cd-de92532850fb`, `evolution_instance = 1227059273831581` (o `phone_number_id` do número de teste) |
| Projeções operacionais | semeadas **à mão** com `version=1`: `loja = ativa` e `whatsapp_modo = 2`. Version baixa de propósito, para o Control sobrescrever depois sem ficar `stale` |
| Fila de vendedores | um vendedor, `5551995941020`, ordem 1 |
| Gate | `rodizio.loja_opera_modo2()` devolve `True` |
| Flags | as **três** em `1`: `REVY_CONTROL_WHATSAPP_MODO2_ENABLED` (Control), `CHATBOT_WHATSAPP_MODO2_ENABLED` e `MULTI_WHATSAPP_ENABLED` (chatbot). As duas do chatbot já estavam ligadas — são três, não uma |
| Workflow | `wCloudMeta0001` republicado no `n8n2037` com o token de serviço da loja `teste`, ativado com `update:workflow --active=true`, n8n reiniciado, webhook respondendo |

### O que o ciclo provou

Nesta ordem, cada passo com carimbo de log:

1. `POST /webhook/cloud` → **200**, com a loja resolvida pelo `phone_number_id`.
   A linha `phone_number_id sem loja` deixou de aparecer.
2. `POST /v1/conversas/{tel}/pode-responder` → **200**.
3. O bot formulou resposta e `POST /v1/operacao/responder` → **200 às 23:49:17
   de 23/08**. O bot respondeu ao cliente de verdade.

### A volta completa, na madrugada de 24/08

O cliente pediu um humano, o rodízio ofereceu o lead, o vendedor tocou em
**Peguei**, e o banco ficou assim:

```
ofertas:    5034a589  estado=travada  vendedor=827819cc  cliente=555180336365
conversas:  555195941020  bot_ativo=True   status=aberta     (o vendedor)
            555180336365  bot_ativo=False  status=handoff    (o cliente)
```

`estado=travada` é a trava idempotente do §5.7; `bot_ativo=False` com
`status=handoff` é a central se calando. O vendedor `827819cc` é o único da fila.

**É a primeira volta completa do Modo 2 em produção.** A feature foi mergeada em
16/08 com a metade da distribuição pronta e, até esta noite, **nenhum vendedor
tinha sido chamado, nunca** — era exatamente o buraco que abre este documento.

E saiu **de graça**: com a janela de 24 h do vendedor aberta, a oferta foi
`interactive`, sem tocar no `chama_vendedor`.

### O que continua sem prova

- **Fila com mais de um vendedor:** ponteiro, prazo de 10 min e a volta que para
  no fim. A fila do piloto tem um só, então o rodízio nunca rodou — e foi ao
  preparar esse teste que se descobriu que a reoferta **nem sairia**.
- **Dois cliques concorrentes** — o "primeiro vence" nunca disputou.
- **Re-notificação do §5.4** e o follow-up de 30 min / 1 h.
- **Template com janela fechada:** todo o piloto correu dentro da janela, então o
  caminho pago nunca foi exercitado — e ele depende do `chama_vendedor`, hoje
  reclassificado como `MARKETING`.
- **Áudio:** não há provider de transcrição configurado, e o VAD não existe.

### Três achados que valem registro

**1. Bug corrigido em produção (`922a365`).** Em `main.py`, `_wamid_ja_visto`
chamava `_wamids_vistos.add(wamid)` — `.add()` é método de `set`, e a estrutura é
`OrderedDict`. O ramo só é alcançado quando o wamid já está em `mensagens` mas
saiu do cache em memória, isto é, **reentrega depois de restart do processo**.
Efeito: o webhook devolvia 500, a Meta reentregava por não receber 200, e o 500 se
repetia em laço. Trocado por `_marcar_wamid_visto`. Suíte do `chatbot-api`: 459
testes passando.

**2. O template `chama_vendedor` foi reclassificado pela Meta de `UTILITY` para
`MARKETING` — e foi **aprovado assim**.** Utility custa ~R$ 0,03–0,04 por entrega e
Marketing ~R$ 0,32 — cerca de **10× por oferta**. Contorno usado no piloto: com a
janela de 24 h do vendedor aberta, a oferta sai como mensagem `interactive`,
grátis e sem template. Ações possíveis: contestar a categoria no painel, ou
reescrever o corpo para parecer transacional (hoje ele manda exatamente uma
variável, o nome do vendedor).

**3. Armadilha do número de teste: a allow-list casa a string enviada, e o
`wa_id` brasileiro chega sem o nono dígito.** O bot responde para
`conversa.telefone`, que guarda o `wa_id`, então o envio era recusado com
`(#131030) Recipient phone number not in allowed list` até o número **sem o 9**
ser cadastrado no painel. É limitação de número de teste — em número real não
existe allow-list, e o código está correto.

### Uma loja por vez — **fechado em 24/08**

O piloto rodou com **uma** loja porque o Modo 2 só atendia uma: um workflow
`n8n-cloud` serve N lojas mas autenticava com um token que pertence a UMA loja.
O chatbot então procurava a conversa na loja do token, não na de quem falou, e
devolvia `conversa_nao_encontrada` — o agente parava **sem erro nenhum**, só `200`
e silêncio.

Consertado e no ar em `654f5d4`. O desenho é o da spec §6.2:

- `CredencialServico.loja_id` aceita `NULL`, e o papel `integracao` marca o token da
  plataforma (`python -m app.cli criar-credencial-integracao`, migration `0026`);
- `auth.resolver_loja_id(db, ctx, instance)` decide de quem é o pedido: credencial de
  loja manda como sempre, credencial de integração resolve pela `instance`. **Sem
  `instance` é `400`** — fail-closed, porque cair em "alguma" loja mandaria a mensagem
  de uma loja pela outra;
- toda rota do bot passou a usar o resolvedor, e o `fork_cloud_workflow.py` injeta a
  `instance` nas seis chamadas. Quem cobra é o `validate_workflow_cloud.py`;
- o `-Mode cloud` do `prepare-workflow.ps1` passou a exigir `CHATBOT_API_TOKEN_CLOUD`
  e **falha** sem ela — reusar o token do Modo 1 era o próprio bug.

**O que ainda não está provado:** o multi-loja de verdade. Tudo foi verificado com
uma loja — e com uma loja o código quebrado se comporta igual ao consertado. Falta
cadastrar a central Cloud de uma **segunda** loja.

*(Escrito em 24/08: "hoje só sai por escrita direta no banco: `POST /v1/whatsapp/canais`
não grava `waba_id`". A primeira metade **deixou de valer em 29/08** — existe rota. A
segunda continua verdadeira: `POST /v1/whatsapp/canais` segue sem `waba_id`. Ver a seção
de 29/08 no fim.)*

Exceção deliberada, fora do escopo daquele card: `GET /v1/config/catalogo-bot` é cega
para loja e `instance` não a conserta — ela não lê `ctx.loja_id`, quem responde é o
cliente do Estoque com bearer global e sem slug. É buraco do contrato com o Estoque.

Detalhe do card:
[`../planos/2026-08-23-modo2-multiloja-credencial-de-integracao.md`](../planos/2026-08-23-modo2-multiloja-credencial-de-integracao.md).

## Noite de 24/08 — dois furos entre o banco e o WhatsApp

A volta completa provou o caminho feliz com **um** vendedor. Ao preparar o teste
com dois, apareceram dois furos que o caminho feliz não toca. Os dois tinham
teste verde por cima. Corrigidos e no ar em `app2037` v158 (`f355ba6`).

### 1. A reoferta trocava de dono no banco e ninguém era avisado

`RodizioWorker.run_once` expirava a oferta vencida, chamava `abrir_oferta` para o
próximo vendedor e **parava ali**: `enviar_oferta` só existia no caminho da
primeira oferta, em `handoff_gatilhos`. O `_ciclo_rodizio` nem outbound recebia.

Efeito: passados os 10 min o lead mudava de dono no banco e **o celular do
vendedor 2 nunca tocava**. O rodízio inteiro — ponteiro, prazo, a volta que para
— existia só como estado.

O teste que deixou isso passar (`tests/test_rodizio_job.py`) afirmava
`nova.vendedor_id != oferta.vendedor_id`: a linha do banco, nunca o envio. É o
mesmo defeito do `n8n-cloud` de 4 nós que abre este documento — verde e vazio.

Junto: a volta esgotada passou a avisar o cliente, **uma vez só**. Antes ele ouvia
"já estou chamando um vendedor" e depois silêncio para sempre.

**O achado de tabela:** acrescentar `send_template_button` e
`send_interactive_button` ao `_OutboundPorLoja` **não bastava**. Ele passava o
`phone_number_id` para `outbound_para_loja`, que pergunta "a loja `<pnid>` é
Modo 2?", ouve não e devolve o transporte do **Modo 1** — `AttributeError`.
Corrigido com `loja_id_do_phone_number_id` em `cloud_canal.py`, que
`_loja_por_phone_number_id` passou a usar em vez de duplicar.

**Colateral:** o mesmo defeito quebrava o **follow-up do Modo 2** — todo cutucão
saía pelo adapter Evolution com um `phone_number_id` da Cloud no lugar da
instância. Consertou junto, sem ninguém ter tocado no `followup_job.py`.

### 2. O handoff falava duas vezes

Na conversa do piloto, às 00:06 de 24/08, o cliente recebeu duas mensagens
seguidas dizendo a mesma coisa: `Já estou chamando um vendedor para falar com
você.` (backend, `handoff_gatilhos.py`) e `pronto, ja estou chamando um vendedor
pra falar com voce.` (agente).

A segunda é a tool `solicitar_handoff1`, que devolve
`{"mensagem": "pronto, ja estou chamando..."}` — texto que o agente ecoa como
resposta dele e o `Responder WhatsApp1` envia.

No Modo 1 isso não acontece: lá o handoff avisa o **grupo** e o backend não fala
com o cliente. O fork por recorte manteve a `mensagem` da tool enquanto o Modo 2
ganhou o aviso no backend, e ninguém viu que os dois passaram a se sobrepor.

`disparar_handoff` ganhou `avisar_cliente`; a rota `/v1/operacao/handoff-humano`
passa `False`. `solicitacoes_simulacao` fica com o default `True`: naquele caminho
não há agente no turno e o backend segue sendo a única voz.

**A §5.3 mudou de dono.** "O cliente não fica no vácuo" continua valendo, mas quem
avisa agora é o agente — o backend deixou de ser a rede. Se o turno do agente
morrer depois da chamada da tool, o cliente fica sem resposta. O caminho inverso
seria pior: o `Responder WhatsApp1` **sempre** envia o output do agente, então
calá-lo exigiria um nó IF dentro do fork gerado.

## O bot do Modo 2 fala igual ao do Baileys, mas não soa igual

Pergunta levantada em 24/08 ao reler a conversa do piloto: o Modo 2 parece menos
humano. O `systemMessage` **não** é a causa — ele é byte a byte o mesmo nos dois
workflows (17.090 caracteres, mesmo sha), assim como o Gemini, a memória e 4 das
5 tools. Dos 16 nós compartilhados só 5 divergem, e 4 divergem por motivo
legítimo: o payload da Meta não é o da Evolution.

A diferença está na **entrega**:

| Peça | Modo 1 (Baileys) | Modo 2 (cloud) |
|---|---|---|
| `Atraso anti-ban1` | calcula `__delayAntiBan` | **byte a byte idêntico**, calcula igual |
| `Responder WhatsApp1` | manda `{ number, text, delay }` | manda `{ telefone, texto }` |
| Resultado | a Evolution segura a mensagem mostrando **"digitando…"** e espaça os envios | delay **descartado**: mensagens instantâneas e em rajada |

O nó continua vivo e a saída é órfã. E não há para onde mandar mesmo que
quisesse: `WhatsAppOutboundPort.send_text` é `(instance, number, text)`, sem
delay, e `/v1/operacao/responder` também não aceita. Na Cloud API o "digitando"
não é parâmetro de envio — é chamada à parte, e precisa do `wamid` da mensagem do
cliente, que a rota hoje não recebe.

Dois pontos menores do mesmo nó: o filtro que força minúsculas, tira emoji e troca
`!` por `.` é **incondicional** no Modo 2, enquanto no Modo 1 só vale para
`fluxo.acao === 'cliente'`; e ele passa por cima de **URL e código** — um slug com
maiúscula quebra o link, e o `Cód:` do CTWA viraria `cód:`.

Trabalho pendente, com card próprio:
[`../../fila/2026-08-24-modo2-humanizacao-da-entrega.md`](../../fila/2026-08-24-modo2-humanizacao-da-entrega.md).

Import do workflow: ver a armadilha em
[`../../../deploy/fly/3vm/README.md`](../../../deploy/fly/3vm/README.md) —
`import:workflow` **desativa** o workflow e `publish:workflow` não reativa; só
`update:workflow --active=true` liga.

## 2026-08-29 — o template saiu da fila, e saiu como Marketing

Conferido no WhatsApp Manager: `chama_vendedor` esta **`Ativo`, categoria Marketing**. Nao
esta mais `PENDING` — o que significa que o custo de ~10x por oferta **ja vale em
producao**, nao e mais risco futuro.

O aviso no painel diz: *"Este modelo nao atendeu as nossas diretrizes de utilidade e foi
atualizado para marketing"*, com **analise disponivel ate 22/10/2026**.

**Vale contestar, e o argumento e forte:** o destinatario do `chama_vendedor` e o
**vendedor da propria loja**, nao o consumidor. E notificacao operacional sobre um evento
especifico (um lead que acabou de chegar), com botao para atribuir o atendimento, sem
oferta, preco ou chamada promocional. O classificador provavelmente leu "lead novo na
loja" como divulgacao.

**O custo real e menor do que os 10x sugerem**, porque o template so entra quando a janela
de 24 h do vendedor esta **fechada** — com ela aberta o codigo manda `interactive`, que e
gratis. Foi por causa desta reclassificacao que esse contorno existe.

## 2026-08-29 — como uma segunda loja entra

O piloto rodou com **uma** loja, e a seção "Uma loja por vez" fechou o lado do
código. Faltava o lado da Meta: como o número de uma loja cliente chega à
central. Em 29/08 essa resposta mudou.

**O caminho que este documento pressupunha não existe.** O §16.6 descrevia um
onboarding assistido — a loja compartilha a WABA, a Revy faz o resto na mão.
Tocar a WABA de outro negócio exige **Advanced Access** em
`whatsapp_business_management`, e isso só sai por **App Review**. Sem ele a Graph
recusa. O contorno que funcionaria — pendurar o número da loja dentro da WABA da
Revy — **o dono recusou**: nota de qualidade e teto passariam a ser
compartilhados, e uma loja bloqueada queimaria a reputação das outras.

O caminho novo é o **Embedded Signup**, com a Revy como Tech Provider: o lojista
conecta sozinho, por um botão na Revy Loja. **App Review submetido em 29/08, sem
resposta.** Enquanto não sai, não há `config_id`, o popup não abre, e nenhuma
segunda loja entra.

Existe código, no ar em `app2037` (`ce4e2ab`): a cadeia dos cinco elos no
chatbot, a rota `POST /v1/whatsapp/canais/cloud/onboarding`, os segredos da loja
cifrados, e a tela na Loja. **Nada disso tocou a Meta de verdade** — os testes
usam `httpx.MockTransport`, e o JS do popup nunca rodou em navegador.

Detalhe, armadilhas e o que falta clicar em
[`2026-08-16-onboarding-meta-dominio-asbuilt.md`](2026-08-16-onboarding-meta-dominio-asbuilt.md),
seção "Sessão 29/08". O design está em
[`../specs/2026-08-29-embedded-signup-tech-provider-design.md`](../specs/2026-08-29-embedded-signup-tech-provider-design.md).

### O que muda para o Modo 2 propriamente

- **O portão do Control é o mesmo lever, e ganhou um efeito.** Projetar
  `whatsapp_modo = 2` continua sendo o que liga a loja (§6.3), e desde 29/08
  também **ativa** o canal parado em `cloud_pendente`. Sem rota nova. O que
  **não** foi feito: o Control não tem visão nenhuma do estado de cada loja —
  quem quiser saber em que pé está uma conexão olha a tela da Loja ou o banco.
- **Registrar número é a chamada mais cara da cadeia.** A Meta aceita 10 por
  número em 72 h móveis; estourar devolve `133016` e deixa o número **três dias
  sem WhatsApp**. O elo 3 para em 5 tentativas e **não tem retry automático** —
  retry aqui está proibido. Nenhum worker do Modo 2 pode ganhar essa chamada
  depois.
- **O `chama_vendedor` de cada loja nasce pedindo `UTILITY`**, e o da Revy foi
  aprovado como `MARKETING` (seção anterior). Se a Meta repetir a
  reclassificação, ela repete loja por loja.
