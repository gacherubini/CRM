# WhatsApp em dois modos: Baileys+grupo OU Central Cloud API (escolha por loja no Control)

**Data:** 2026-08-12 (revisão 2026-08-13)
**Status:** Spec **fechada** com o dono (brainstorm 2026-08-12 + sessão 2026-08-13).
Pronto para o plano de implementação. Este arquivo é o canônico.
**Substitui:** a abordagem anterior de coexistência **por vendedor** (`smb_message_echoes` + history
sync), **descartada** em favor do modelo de **central só-bot** (ver §14). Os planos daquela abordagem
(design de coexistência, spike de coexistência e regra Cloud/n8n de coexistência) foram **removidos**
— este é o documento canônico do "problema do WhatsApp".
**Produtos afetados:**
- `revy-control`: escolhe `whatsapp_modo` por loja (1 XOR 2) e projeta saúde. Não opera QR nem fila.
- `portal-gestao` (Loja): opera o modo escolhido — telas mudam (§5.8). Cadastro da fila (Modo 2)
  é do lojista aqui.
- `chatbot-api`: central bot do Modo 2 (intake, gatilho de handoff, rodízio, trava, detecção
  vendedor×cliente). Modo 1 mantém o gate atual intacto.
- `n8n`: novo workflow `n8n-cloud` (inbound/outbound Cloud). `n8n-baileys` = o atual, sem mudança.
- `motor`: simulação (já existe; sem mudança de contrato).
- `evolution`: **permanece só Baileys** (Modo 1). Não entra no Modo 2.
Cada produto mantém banco/migrations próprios; colunas/tabelas novas ficam **dentro** do banco de
cada um. Sem import Python entre produtos — integração por contrato HTTP/evento.
**Referências:**
`chatbot-api/app/operacao.py` (`_decidir_cliente_ou_ignorar`, `decidir_roteamento` — gate do Modo 1
não muda); `chatbot-api/app/main.py` (`webhook_mensagem` — modelo normalizado agnóstico de canal);
`chatbot-api/app/whatsapp_provider.py:219` (`integration` — ponto de troca de canal, fica Baileys no
Modo 1); `chatbot-api/app/whatsapp_outbound.py`; `chatbot-api/app/whatsapp_groups.py` (grupo, Modo 1);
`chatbot-api/app/audio.py:71` + `chatbot-api/app/vehicle_photo.py` (download de mídia hoje acoplado
à Evolution — §5.10); `chatbot-api/app/operacao.py::normalizar_telefone` / `variantes_telefone`
(match de número do vendedor — §5.5);
`n8n/workflow-ai-nao-salvos.json` (nó "Extrair1" — base do `n8n-baileys`);
`portal-gestao/app/loja/` + `whatsapp_canais`;
`portal-gestao/app/loja_operacao_auditoria.py:24` (`assumir | devolver | reatribuir` já existe).
**Memória do projeto:** `whatsapp-passkey-bloqueia-evolution`.

---

## 1. Problema e resultado desejado

O WhatsApp passou a **exigir passkey** para parear novos aparelhos em contas marcadas. O Baileys
(usado pelo Evolution) **não implementa** esse handshake, então número marcado **não conecta** — o QR
nunca fecha (issues abertas evolution-api #2618 e Baileys #2672). Nenhuma versão do Baileys resolve.

**Resultado desejado:** manter **duas formas de operar o WhatsApp**, escolhidas **por loja no Revy
Control** e **mutuamente exclusivas** (uma loja é um modo OU o outro, nunca os dois):

1. **Modo 1 — Baileys + grupo** (o que existe hoje): cada vendedor no próprio número Baileys, com o
   **grupo de estoque** ativo (foto de veículo + aviso de simulação). Continua disponível para quem já
   tem número pareado / número não-marcado. Aceita o risco de passkey (é o legado).
2. **Modo 2 — Central Cloud API** (novo): um **número central por loja**, só-bot, na API oficial da
   Meta. O bot atende o cliente, roda a simulação e **distribui o lead aos vendedores por rodízio
   rotativo**; o vendedor assume e fala com o cliente **do WhatsApp dele** (handoff). Robusto e à prova de
   passkey, porque os **números dos vendedores não pareiam com bot nenhum**.

**Não-objetivos desta fase:** produtizar o self-serve de onboarding Cloud (embedded signup no
Portal); mensagem proativa da central pro cliente (templates de marketing); migrar todas as lojas.

## 2. Decisões tomadas com o dono (2026-08-12)

| Tema | Decisão |
|---|---|
| Dois modos | **Baileys+grupo (1)** OU **Central Cloud API (2)**. Ambos permanecem suportados. |
| Onde escolhe | **No Revy Control**, campo por loja `whatsapp_modo`. **1 XOR 2** — uma loja **não** pode ter os dois. |
| Modo 1 | É **o comportamento atual sem mudança**. O trabalho é só **expor como opção explícita** no Control. Grupo de estoque **volta/permanece** neste modo. |
| Canal da central (Modo 2) | **Cloud API pura, só-bot.** Nenhum humano atende pela central → **não é coexistência**. Cai fora `smb_message_echoes`, history sync, QR, aprovação de histórico e a regra "humano já falou". |
| Vendedores no Modo 2 | **Não são bots.** Usam o WhatsApp normal deles. Nenhum número de vendedor pareia com Evolution → passkey **não os afeta**. |
| Como o vendedor fala com o cliente | **Handoff:** a central passa o contato do cliente ao vendedor, que chama o cliente **do próprio WhatsApp** (outro número; o cliente vê um número novo). **Não** é caixa compartilhada. |
| Distribuição | **Só rodízio automático**, **ponteiro rotativo** na ordem cadastrada, um por vez. Sem apontar vendedor à mão. **10 min** pra clicar; sem resposta → próximo. Uma volta e **para**. Primeiro clique vence, mesmo atrasado (§5.3). |
| Confirmação do vendedor | Dois jeitos, **o mesmo assumir**: botão no WhatsApp **ou** botão **Peguei** no sino da Loja. Primeiro que chegar vence. Ver §5.7. Pegou e não ligou: **fica travado**. |
| Cadastro de vendedores | **Nome** + número + **ordem** da fila: **na Loja, pelo lojista**. Control só escolhe o modo. |
| Fallback (ninguém pega) | **Sem WhatsApp ao dono.** Lead fica `aguardando`. Na Loja: faixa + filtro no Atendimento, e card no Agente com os últimos 7 dias. |
| Canal do aviso ao vendedor | **WhatsApp 1:1** + **sino na Loja só para o `oferecido_a`**, com botão Peguei no próprio sino. Nunca grupo, nunca sino da loja inteira. |
| Timer do rodízio e do bot | **Worker no `chatbot-api`**. n8n só transporta. |
| n8n | **Um workflow por modo.** `n8n-baileys` = o atual, intacto. `n8n-cloud` = novo, só Modo 2. Sem `if` de modo no meio de um workflow. |
| Bot do Modo 2 | **Fork do atual** (mesmo debounce 40s, replay >5 min, intake, simulação, gates). Texto de follow-up + prompt se configuram juntos. Silêncio do cliente: 30 min → msg 1; +1 h sem resposta → msg 2; para. Só enquanto `bot_ativo`. |
| Gatilho do handoff | **Três gatilhos**, o que vier primeiro: **simulação pronta**, **simulação falhou** no Motor (§5.11) ou **cliente pede humano**. |
| Mídia do cliente | **Áudio e imagem entram, só no Modo 2** (§5.10). A Meta manda `media_id`; o **chatbot** baixa no Graph e transcreve o áudio no código — a central tem que ouvir pra responder. Não transcreveu / não baixou → responde o cliente pedindo texto. **Modo 1 não ganha transcrição.** |
| Encanamento Cloud | **Meta ↔ n8n-cloud direto.** Webhook da Meta aponta pro `n8n-cloud`; envio via **Graph API**. Central **independente do Evolution** (Evolution fica só no Baileys/Modo 1). |
| Onboarding da central | **Direto na Meta, sem BSP.** Piloto roda em **dev mode** com número de teste. App próprio do Revy. |

## 3. Arquitetura (visão)

```
                    Revy Control: whatsapp_modo por loja (1 XOR 2)
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼ Modo 1 (legado)                                        ▼ Modo 2 (novo)
  Vendedor A ─ Baileys(QR) ─► Evolution ─► n8n-baileys ─┐   Cliente ─► [Central Cloud API]
  Vendedor B ─ Baileys(QR) ─► Evolution ─► n8n-baileys ─┤     │  (só-bot)  ▲
  grupo de estoque (foto + aviso de simulação)          │     │            │ Meta ◄─► n8n-cloud
                                                         ├─► chatbot-api ─► Motor / Estoque
                                                         │     (núcleo agnóstico de canal)
                                                         │
   Modo 2 handoff:  bot faz intake + simulação ──────────┘
     gatilho (sim pronta OU sim falhou OU pede humano)
       └─► rodízio PONTEIRO ROTATIVO, 1:1: msg c/ botão + sino só dele ─(10 min)─► próximo ─► ...
              1º clique vence (mesmo atrasado) ─► inbound "peguei:oferta_id" ─► assumir (trava)
              central manda wa.me + resumo DEPOIS do clique ─► vendedor chama do WhatsApp DELE
              e avisa o CLIENTE quem vai chamar (nome + número do vendedor)
              deu a volta sem ninguém pegar ─► lead "aguardando" (faixa+filtro no Atendimento)
```

- **Núcleo agnóstico:** o `chatbot-api` recebe o payload **normalizado** pelo n8n
  (`{instance, telefone, texto, provider_message_id, ...}`), então o núcleo muda pouco. O
  `provider_message_id` já é string opaca — `wamid.XXX` (Cloud) cabe.
- **Roteamento por número** já existe: o n8n roteia por `body.instance`. Modo 1 e Modo 2 caem no
  mesmo `chatbot-api`, diferenciados pela config da loja/instância.

## 4. Modo 1 — Baileys + grupo (legado, agora opção explícita)

**Comportamento = o de hoje. Não muda nada no fluxo.** O único trabalho é **tornar o modo uma
escolha** no Control, em vez do único caminho:

- Cada vendedor no próprio número Baileys (QR no Evolution), como já é.
- **Grupo de estoque ativo:** foto de veículo → download via Baileys (fluxo atual); aviso de
  "simulação pronta" → mensagem no grupo (fluxo atual).
- Gate de roteamento **inalterado** (`_decidir_cliente_ou_ignorar`: `conversa_tem_resposta`,
  `is_saved`, `chat_found`).
- **Passkey:** risco aceito. Serve para números já pareados ou não-marcados; parear limpo 1x e não
  churnar QR.

Ou seja: o "Evolution velho" fica exatamente como está. Nenhuma regra do Modo 2 vaza pra cá.

## 5. Modo 2 — Central Cloud API (novo)

### 5.1 Fluxo ponta-a-ponta

1. **Cliente → central.** O cliente manda mensagem para o número central da loja (o número dos
   anúncios). A central é Cloud API, só-bot.
2. **Bot atende:** intake (nome, veículo de interesse, CPF/nascimento, dados de financiamento) e
   dispara a **simulação** no Motor (contrato atual `/v1/simulacoes`).
3. **Gatilho de handoff** (o que vier primeiro):
   - a **simulação fica pronta** (resultado volta pra central),
   - a **simulação falha** no Motor (erro/timeout — §5.10), ou
   - o **cliente pede humano** explicitamente ("quero falar com alguém").
   O bot avisa o cliente que **já vão chamá-lo** e inicia o rodízio.
4. **Rodízio (§5.3):** a central chama os vendedores **em ponteiro rotativo**, um por vez, até
   alguém clicar o botão de "peguei" — ou até fechar a volta na fila.
5. **Handoff:** ao travar, a central entrega ao vendedor o contato do cliente (número + link
   `wa.me`) **e** avisa o cliente **quem** vai chamá-lo (nome + número do vendedor), pra ele não
   estranhar o número novo. O vendedor chama o cliente **do WhatsApp dele**. A central **se cala**
   com aquele cliente (§5.4).

### 5.2 Gatilhos do handoff
Três, o que vier primeiro (§2): **simulação pronta**, **simulação falhou** (§5.10) e **cliente pede
humano**. "Cliente pede humano" precisa de detecção simples de intenção (frase/opção de menu).
"Simulação pronta" é o retorno do Motor. Se o gatilho for "pediu humano" **antes** da simulação, a
mensagem de "chama vendedor" vai **sem** resultado de simulação — o template tem que funcionar com e
sem esse campo.

### 5.3 Rodízio (ponteiro rotativo)
- **Só automático.** Não há "apontar o vendedor deste lead". Critérios mais ricos
  (disponibilidade/performance) ficam pra Fase 2.
- **Ponteiro rotativo por loja**, persistido: a fila é **circular** e o ponteiro **avança a cada
  oferta emitida** (não a cada lead). Lead novo começa em quem está na vez, não sempre no 1º da
  lista — assim a carga se divide e dois leads simultâneos caem em vendedores diferentes.
- **Um lead pendente por vendedor:** vendedor que já tem oferta aberta (ou está fora/inativo no
  cadastro) é **pulado**. Se **todos** estiverem pendentes, o lead fica em `aguardando_vez` e é
  oferecido assim que a primeira posição liberar; o relógio da volta só começa na primeira oferta.
- **Fila por loja:** **nome** + número + ordem, cadastrados **no Portal pelo lojista**. O Portal é a
  fonte da verdade. O nome é obrigatório — é ele que vai no aviso ao cliente (§5.1).
- **10 min por vendedor:** a central chama o vendedor da vez por WhatsApp 1:1 (envelope da §5.7)
  **e** liga o sino da Loja **só para ele**. Se ele não clicar em **10 min**, a central chama o
  próximo do ponteiro (sino muda de dono).
- **Primeiro clique vence:** o botão de uma oferta anterior **continua válido** até o lead
  travar. Se o vendedor 1 estoura, o 2 é oferecido, e o 1 clica o botão velho antes do 2,
  o 1 leva. O 2 recebe um recado de "já foi pego" (sem `wa.me`). Trava é **idempotente**:
  o primeiro `assumir` ganha; clique seguinte é ignorado. Isso exige que o clique diga **qual
  lead** — ver `payload` do botão na §5.7.
- **Uma volta e para:** o lead percorre a fila **uma vez** a partir de onde o ponteiro estava, dá a
  volta e **encerra** ao chegar de novo em quem começou. Não recomeça. O lead fica `aguardando`.
- **Fila vazia ou sem ninguém elegível:** loja Modo 2 sem vendedor cadastrado (ou todos inativos) →
  o lead entra direto em `aguardando`, com a faixa do Atendimento. A central não deixa o cliente
  no vácuo: manda o mesmo aviso de "já vão te chamar" e para.
- **Pegou e não ligou:** o lead **fica travado** com ele. Não devolve à fila. Dono resolve
  no Portal (reatribuir/devolver).
- **Timer:** worker no `chatbot-api` (estado `oferecido_a` + prazo). n8n não espera.
- **Estado do lead:** `aguardando` / `aguardando_vez` → `oferecido_a(vendedor)` →
  `travado(vendedor)` / `esgotou_fila`. Tudo visível no Portal.

### 5.4 Handoff, silêncio e o que sobrou na fila

**Cliente que volta a escrever na central depois do handoff.** É o caso normal, não a exceção: a
central é o número do anúncio, e o cliente não sabe que o atendimento mudou de número — ainda mais
enquanto o vendedor não ligou. O bot está calado (`bot_ativo=false`), então sem regra o cliente fala
sozinho. A regra é:

- **Ao cliente:** um recado curto, **uma vez a cada 6 h** por lead — "o {vendedor} já está com seu
  atendimento e vai te chamar do {número}". Não reabre o bot, não reentra no intake.
- **Ao vendedor travado:** cutucão **no máximo 1 por hora** por lead, sempre pelo envelope
  **grátis**: sino da Loja **sempre**, e WhatsApp **só se a janela de 24 h dele estiver aberta**.
  Re-notificação **nunca** gasta template pago — senão um cliente ansioso com 5 mensagens vira 5
  cobranças e 5 pokes do mesmo lead.
- Mensagem do cliente nesse estado **conta** no Portal (fica na conversa e atualiza o lead), só não
  gera resposta do bot.

**O resto do pós-handoff:**
- Fora da regra acima, a central **não responde mais** aquele cliente e não reabre o bot.
- O chat real vendedor↔cliente acontece **no celular do vendedor** e a central **não o vê** —
  trade-off aceito do modelo handoff (§13).
- **Fallback = Loja, ao vivo.** Sem template às 19h, sem campo de WhatsApp do dono. Quem
  ninguém pegou fica `aguardando` e aparece em dois lugares (§5.8):
  1. **Atendimento** — faixa no topo ("N leads sem vendedor") + filtro de estado **Aguardando**,
     só dono/gerente. Clique na faixa aplica o filtro. Dali o dono assume/reatribui. A faixa conta
     o que está **em aberto agora** (`aguardando` + `esgotou_fila` não resolvidos), sem recorte de
     data — some quando alguém assume.
  2. **Agente** — card dos **últimos 7 dias**: atendidos (travados), perdidos, aguardando,
     oferecidos. Não substitui a barra agente × handoff do mês; é o recorte da fila.

  Definições do card (7 dias corridos, por loja):
  - **atendidos** — leads que travaram com um vendedor (`travado`), pelo clique ou pelo Portal.
  - **oferecidos** — leads com oferta viva agora (`oferecido_a` / `aguardando_vez`).
  - **aguardando** — a fila deu a volta e ninguém pegou (`esgotou_fila`), ou não havia vendedor
    elegível; segue sem dono.
  - **perdidos** — lead que morreu sem atendimento humano: cliente sumiu antes do gatilho de
    handoff (follow-up esgotado sem resposta) ou recusou. **Não** é o mesmo que "aguardando":
    aguardando é culpa da fila, perdido é o cliente que saiu.

### 5.5 A central recebe cliente E vendedor (roteamento por remetente)
O número central recebe inbound de **dois tipos** de remetente:
- **Cliente (lead):** número desconhecido → conversa do bot.
- **Vendedor:** número **cadastrado** na loja → o inbound (clique do botão / texto) é tratado como
  **comando de controle** (trava do lead), não como conversa de cliente.
O `n8n-cloud`/`chatbot-api` decide pelo **cadastro de vendedores** da loja (§7).

**Comparação de número é por variantes, não por string.** Reusar
`chatbot-api/app/operacao.py::normalizar_telefone` + `variantes_telefone` (só dígitos, DDI 55, 9º
dígito). A Cloud API devolve o `wa_id` em E.164 sem `+`; o lojista digita como quiser. Sem isso a
detecção vendedor×cliente falha e o clique do vendedor vira "conversa de cliente".

Vendedor cadastrado que manda **texto solto** (não clique) para a central: não vira lead e não
acorda o bot. Se ele tem oferta aberta, a central responde só "use o botão"; senão, ignora.

### 5.6 Atribuição CTWA
Com um número central, o **anúncio aponta pra central** e o `referral`/`ad_id` chega no inbound da
primeira mensagem — o `n8n-cloud` extrai e alimenta a atribuição existente. Um número por loja
**simplifica** a atribuição (não piora).

### 5.7 "Peguei" = clique que volta como inbound (é o assumir)

O bot manda ao vendedor **uma mensagem com botão**. O vendedor **não digita**. O clique chega na
central como inbound — webhook `button` (template) ou `interactive` (mensagem interativa). O
`chatbot-api` trata esse inbound como **comando de controle** (§5.5), não como conversa de cliente,
e executa o mesmo contrato do **assumir** que já existe no Portal
(`portal-gestao` `atendimento_handoff` + `registrar_handoff_local`):

- `bot_ativo=false` na conversa do cliente (central se cala);
- `AtendimentoAtribuicao` para aquele vendedor;
- o workspace de Atendimento mostra **Em atendimento** (`resolver_estado` já mapeia
  `bot_ativo=false`).

**Dois envelopes, um significado:**

| Janela 24h com aquele vendedor | Envelope | Custo |
|---|---|---|
| Fechada (ele ainda não falou com a central) | Template Utility + botão de **resposta rápida** | cobrado (~R$0,03–0,04) |
| Aberta (ele já clicou/respondeu nas últimas 24h) | Mensagem interativa (`type=interactive`) com o mesmo botão | grátis |

Não há check-in matinal. O próprio primeiro "peguei" do dia abre a janela; os pokes seguintes
àquele vendedor no mesmo dia usam mensagem interativa. Cobra-se o **primeiro toque por vendedor
com janela fechada**, não um template por lead.

**O clique tem que dizer QUAL lead.** O mesmo vendedor pode ter mais de uma oferta viva (a dele e
uma velha que ainda vale, §5.3), então o botão carrega o identificador da oferta:

- **Interativa:** `interactive.button_reply.id = "pego:<oferta_id>"` — volta idêntico no inbound.
- **Template:** botão de resposta rápida devolve `button.payload`; o payload do template é fixo por
  botão, então o `<oferta_id>` entra ali na montagem do envio (um `payload` por oferta).
- O `chatbot-api` resolve `oferta_id → lead` e aplica o `assumir` idempotente. Payload ausente ou
  desconhecido → trata como "já foi pego" e **não** trava nada por adivinhação.

**O contato do cliente (`wa.me`) só vai DEPOIS do clique** (WhatsApp ou sino). Se o número
for na mensagem de oferta, o vendedor chama sem o backend saber. Junto do `wa.me` vai o **pacote
completo do lead**: nome, veículo, o que o cliente falou, resultado da simulação se houver **e os
dados de intake — CPF, nascimento, CNH**. O vendedor precisa disso na mão pra continuar o
atendimento (e pra simular no banco quando o Motor falhou, §5.11); mandar só um link obrigaria ele
a abrir o Portal no meio da conversa.

Regra do pacote: vai **só depois do clique**, **só** para o vendedor que travou, **nunca** na
mensagem de oferta e **nunca** para quem perdeu o clique. O envio fica **registrado no Portal**
(auditoria de quem recebeu o quê, quando). Dado pessoal trafegando no WhatsApp pessoal do vendedor
é uma escolha consciente do dono — o registro é o que permite auditar depois.

**Peguei no sino** = o mesmo `assumir` do clique WhatsApp. O item do sino do `oferecido_a`
tem botão **Peguei** (não é só “abrir conversa”). Primeiro que chegar (sino ou WhatsApp)
vence; o outro vira “já foi pego”.

Proibido no WhatsApp: texto solto, botão URL, `wa.me` na oferta. O botão do app tem que
voltar inbound. O do sino chama o backend direto — não é um link mágico na mensagem.

**1:1, não grupo.** Só o `oferecido_a` recebe WhatsApp **e** o sino com Peguei. Dono/gerente
não veem esse sino. Nenhuma regra disto vaza para o Modo 1.

### 5.8 Control escolhe o modo; a Loja muda a tela

O **tipo de atendimento** é o `whatsapp_modo` (1 XOR 2). Mora **só no Revy Control**, na
ficha da loja (aba WhatsApp / prontidão). A Loja **não** oferece esse toggle — ela opera
o modo que o Control gravou.

| Superfície | Modo 1 (Baileys + grupo) | Modo 2 (central Cloud) |
|---|---|---|
| Control — ficha da loja | Escolhe modo 1. Saúde dos canais Evolution. | Escolhe modo 2. Saúde da central Cloud. Sem QR. |
| Loja — Ajustes / canais WA | QR, vários números, reconectar. Como hoje. | Sem QR de vendedor. Número central (Cloud) + lista ordenada de vendedores. |
| Loja — grupo de estoque | Ativo (foto + aviso de simulação). | Fora. Foto/aviso não passam por grupo. |
| Loja — foto do veículo | Grupo **e** upload no form de estoque (card da fila). | **Só** upload no form de estoque. Sem isso o Modo 2 não publica foto. |
| Loja — Atendimento | Lista de hoje. Sem faixa de fila esgotada. | Faixa "N sem vendedor" + filtro **Aguardando**. Sino 1:1 com **Peguei**. |
| n8n | `n8n-baileys` (o de hoje). Sem mudança. | `n8n-cloud` novo. Meta ↔ Graph. Sem Evolution. |
| Loja — Agente | Página atual: mês, só-agente × transferidos, série diária. | A mesma página **mais** o card dos últimos 7 dias (atendidos / perdidos / aguardando / oferecidos). |
| Loja — cadastro da fila | Não existe. | Nome + número + ordem, pelo lojista. |

Trocar o modo no Control **não** migra conversa antiga. Loja Modo 2 esconde QR e grupo; Loja
Modo 1 esconde fila, faixa Aguardando e o card de 7 dias.

Foto de veículo **não entra neste plano**. O card
[`docs/fila/2026-08-12-foto-veiculo-upload-portal.md`](../../fila/2026-08-12-foto-veiculo-upload-portal.md)
é eixo à parte (Loja + Estoque) e vale nos dois modos: no 1 é atalho além do grupo; no 2 é
o único jeito de publicar. Fazer esse card **antes** ou em paralelo do piloto Modo 2 — senão
a loja Cloud não coloca foto no catálogo.

Sino geral **também é eixo à parte**
([`docs/fila/2026-08-12-notificacao-central-simulacao-pronta.md`](../../fila/2026-08-12-notificacao-central-simulacao-pronta.md)
Fase B1): desacoplar o sino do Copiloto, com elegibilidade por tipo. Isso o Modo 2 usa
para o aviso 1:1 do `oferecido_a`. **Não** aplicar a Fase B2/B9 daquele card (blast
`simulacao_pronta` + desligar o grupo) — aqui o grupo fica no Modo 1 e o “ninguém pegou”
é a faixa do Atendimento.

### 5.9 Bot do Modo 2 — fork do atual + cutucão no silêncio

O núcleo (chatbot-api) é o de hoje. O `n8n-cloud` é **cópia do fluxo atual** (`workflow-ai-nao-salvos.json`)
trocando Evolution por Graph API — não um bot novo. O que se herda sem discutir de novo:

- debounce 40s (só a última mensagem);
- replay >5 min bloqueado;
- intake + simulação no Motor;
- gate virgem / salvo / “humano já falou” **não se aplica** no Modo 2 da mesma forma (a central
  é só-bot; quem assume é o peguei);
- parcela **não** vai ao cliente pelo bot.

**Follow-up se o cliente some** (só Modo 2, só enquanto `bot_ativo`, só na conversa com o
**cliente** — nunca no vendedor):

1. 30 min sem resposta do cliente → mensagem 1 da etapa.
2. +1 h ainda sem resposta → mensagem 2 da etapa.
3. Para. Sem terceiro toque. Cliente responder no meio **zera** o relógio.
4. Handoff / `bot_ativo=false` **cancela** follow-ups pendentes.
5. Recusa (“valeu”, “não precisa”) **não** cutuca.

O bot **não** inventa o texto: classifica a etapa e escolhe o par abaixo. Sem certeza →
linha “só deu oi”. **Sem** etapa “pediu foto e sumiu”.

| Parou em | 30 min | +1 h |
|---|---|---|
| Só deu oi / sumiu | `e aí amigo, ainda tá aí? te ajudo a achar uma moto` | `amigo, se ainda quiser dar uma olhada nas motos é só responder. fico por aqui` |
| Anúncio (à vista ou financiar) | `amigo, você queria essa moto à vista ou financiada? me fala que eu sigo` | `ainda consigo te ajudar nessa moto do anúncio. me diz se é à vista ou financiamento` |
| Vendo opções / não escolheu | `amigo, viu alguma que te interessou? me fala qual que eu te mostro melhor` | `se alguma moto te pegou, me manda o modelo que eu continuo. senão a gente deixa quieto` |
| Quis financiar, faltou dado | `amigo, pra eu simular falta só [o que falta]. me manda que eu já encaminho` | `sem esses dados eu não consigo simular. se ainda quiser, me passa que eu resolvo agora` |
| Mandou o catálogo e sumiu | `amigo, deu uma olhada no catálogo? me fala qual moto que eu te atendo nela` | `se viu alguma, me manda o modelo. se não for a hora, tudo bem` |
| À vista / “quanto é” e sumiu | `amigo, ficou alguma dúvida no valor? te explico direto` | `se ainda quiser fechar à vista me chama que eu sigo com você` |

`[o que falta]` = cpf, nascimento e/ou cnh, só o que ainda não veio.

Timer no worker do `chatbot-api`. O `n8n-baileys` não muda.

Fluxo e tom além do follow-up: **iguais ao atual**, salvo o que o Modo 2 já muda
(central só-bot, peguei, silêncio pós-handoff, sem grupo).

### 5.10 Áudio e imagem do cliente (mídia pela Meta)

O Modo 2 **recebe áudio e imagem** do cliente. Áudio é o formato mais comum do cliente de moto —
não pode cair no vazio. O caminho de hoje **não serve**: `chatbot-api/app/audio.py:71` e
`vehicle_photo.py` baixam o binário **autenticado na Evolution** (`CHATBOT_AUDIO_EVOLUTION_URL` /
`_API_KEY`), e no Modo 2 não existe Evolution.

**Como fica:**

1. A Meta manda no inbound `type: audio|image` com um **`media_id`** (não o binário).
2. `n8n-cloud` repassa `{media_id, mime, sha256}` no payload normalizado — **não** baixa nada.
3. `chatbot-api` baixa **no Graph**: `GET /{media_id}` devolve uma **URL assinada de vida curta**
   (~5 min) que exige o token no header `Authorization`. Download é **síncrono**, na hora do
   inbound — não dá pra enfileirar pra depois, a URL expira.
4. **Áudio:** transcreve com o provider já existente (`AUDIO_TRANSCRIPTION_*`) e segue o fluxo
   normal com o texto transcrito.
5. **Imagem:** entra na conversa e vai no resumo do handoff (§5.7). O bot **não interpreta**
   imagem nesta fase (sem OCR): se o intake esperava um dado (CPF, CNH), ele pede **por texto**.
6. **Não deu:** provider desligado, transcrição falhou, download falhou, mídia acima do limite ou
   mime não suportado → a central **responde o cliente pedindo texto** (`CHATBOT_AUDIO_FALLBACK_TEXT`,
   hoje "Não consegui entender o áudio. Pode me enviar por texto?"). Nunca ficar mudo.

**Consequências pro plano:**

- `audio.py` precisa de um **downloader por canal** (Evolution para o Modo 1, Graph para o Modo 2);
  a transcrição em si não muda.
- **Transcrição liga só no Modo 2.** A central *precisa* ouvir — é ela que atende, não tem humano
  do outro lado pra dar play no áudio. No Modo 1 quem recebe o áudio é o próprio vendedor, no
  celular dele, então não há o que transcrever. Ou seja: `AUDIO_TRANSCRIPTION_PROVIDER` passa a ser
  resolvido **por canal/modo**, não por variável global do processo — hoje é `"none"` no ambiente e
  ligar global mudaria o Modo 1 de tabela. Modo 1 fica **exatamente como está**.
- Limites: `CHATBOT_AUDIO_MAX_BYTES` é 8 MB e a Meta aceita áudio até 16 MB — conferir o teto pra
  não rejeitar o que a Meta entregou (ou rejeitar de propósito, com o fallback).
- O binário continua **efêmero**: transita pela API, não é persistido no Chatbot nem no n8n (regra
  atual de `vehicle_photo`/`audio`).

**Provider de transcrição: Groq `whisper-large-v3`.**

O contrato de `HttpTranscriptionProvider` já é genérico — multipart `file`, resposta JSON com
`text`/`texto` — que é a forma da API Whisper. O Groq expõe exatamente isso em
`https://api.groq.com/openai/v1/audio/transcriptions`, então **pluga sem escrever código**: é só
`CHATBOT_AUDIO_TRANSCRIPTION_URL` + `_TOKEN`.

| | |
|---|---|
| Escolhido | Groq **`whisper-large-v3`** (não o `turbo`) — US$ 0,111/h |
| Por que não o turbo | turbo é o large-v3 podado de 32 pra 4 camadas de decoder: volta ao nível do large-v2. Português sofre pouco, mas sofre — e a diferença de custo (US$ 0,04 vs 0,111/h) é ruído nesse volume |
| Por que não OpenAI | mesmo formato, mesma família de modelo, 3x o preço (whisper-1 a US$ 0,36/h). Vale como **troca de 2 variáveis** se o Groq cair |
| Plano B de qualidade | **AssemblyAI Universal-3.5** (US$ 0,21/h) — melhor pt medido em benchmark independente (4,9% WER multilíngue), mas API própria: exige adaptador |
| Descartados | Deepgram Nova-3 (9,3–10,7% WER em pt no FLEURS, pior que Whisper, e sem compatibilidade); ElevenLabs Scribe e GPT-Transcribe (sem número independente de pt) |

- **`language` tem que ser `pt`, não `pt-BR`.** `audio.py` manda hoje `data={"language": "pt-BR"}`
  e o campo é **ISO-639-1** (duas letras): dependendo do provider isso é ignorado em silêncio
  (perde acurácia) ou volta 400. Corrigir junto.
- **`ogg`/opus passa direto.** A nota de voz do WhatsApp chega `audio/ogg; codecs=opus` e o Groq
  aceita ogg — **sem transcodificar**.
- Custo: ~US$ 0,83/mês por loja no cenário de 450 min (§9). Cobrança mínima de 10 s por request no
  Groq — um "oi" de 3 s conta 10 s; irrelevante nesse volume.

**Alucinação em silêncio é o risco real, não o WER.** O Whisper **inventa texto plausível** em
trecho mudo ou só com ruído (falha conhecida do large-v3), e aqui o bot **age** em cima da
transcrição: um áudio de 2 s de barulho de rua vira uma frase inventada e o bot responde àquilo.
Regra:

- **VAD antes de mandar** (ou duração mínima de fala): áudio sem voz detectada não vai ao provider.
- **Baixa confiança / transcrição vazia / suspeita → o fallback da regra 6**, não o texto duvidoso.
  Melhor pedir por escrito do que o bot responder ao que o cliente não disse.
- Os 5–8% de WER que o Whisper mostra em português são **áudio limpo de benchmark**. Cliente na rua
  com moto passando fica na faixa de 15–25%. Dimensionar a expectativa por esse número.

### 5.11 Simulação que falha no Motor

Erro ou timeout do Motor **não deixa o lead parado esperando um resultado que não vem**. É o
terceiro gatilho de handoff (§5.2):

- **Dispara o rodízio** igual ao "simulação pronta". O template de oferta vai sem o campo de
  resultado (§5.2 já exige que funcione sem ele).
- **Ao vendedor, depois do clique:** o pacote completo do lead — nome, veículo, entrada, o que o
  cliente falou **e CPF/nascimento/CNH** — pra ele simular à mão no banco, mais o `wa.me` e o link
  do lead no Portal. É exatamente o pacote da §5.7; aqui ele é o insumo do trabalho manual.
- **Ao cliente:** a central avisa que **o vendedor vai fazer a simulação** e diz **quem** vai
  chamar — nome e número do vendedor — pra ele não estranhar o número novo. Mesmo aviso da §5.1.
- Parcela continua **não** indo ao cliente pelo bot (invariante). Quem fala número é o vendedor.

**Janela de 24 h do cliente:** se o resultado (ou o erro) do Motor voltar mais de 24 h depois da
última mensagem do cliente, a janela fechou e texto livre não passa. Nesse caso a central **não**
gasta template com o cliente: só dispara o rodízio, e quem reabre a conversa é o vendedor, do
WhatsApp dele.

## 6. Encanamento Cloud — Meta direto ↔ n8n-cloud

- **Inbound:** webhook da Meta (campos `messages` + `referral`) aponta **direto** para o
  `n8n-cloud`. Sem Evolution no caminho Cloud.
- **Outbound:** envio via **Graph API** (REST simples).
  - bot ↔ cliente: texto livre (janela aberta pelo inbound do cliente) — grátis.
  - "chama vendedor": template Utility com botão se a janela com aquele vendedor está
    **fechada**; mensagem interativa com o mesmo botão se está **aberta** (§5.7).
- **Por quê direto e não via Evolution:** o suporte Cloud do Evolution mostrou-se frágil (CHANGELOG
  sem menção, repo dedicado à parte, issue #807). Como o Modo 2 é **Cloud API pura** (não
  coexistência), não há nada do Evolution a reaproveitar aqui — mais limpo apontar direto pra Meta.
- **Dois workflows n8n** (§3): `n8n-baileys` (atual, intacto) e `n8n-cloud` (novo). Sem `if` de
  modo no meio. Cada loja aponta o webhook do canal para o workflow do **seu** modo.

### 6.1 Webhook da Meta: verificação, assinatura e reentrega

O `n8n-cloud` fica **exposto na internet** recebendo POST da Meta. Sem isso, qualquer um injeta lead:

- **GET de verificação:** responder o `hub.challenge` só quando `hub.verify_token` bate com o nosso.
- **POST:** validar `X-Hub-Signature-256` (HMAC-SHA256 do corpo **cru** com o App Secret) e
  **descartar** o que não bate. Corpo cru — se o n8n já parseou, a assinatura não fecha.
- **Reentrega:** a Meta reentrega o webhook se não receber `200` rápido. Responder `200`
  **imediatamente** e processar depois; deduplicar por **`wamid`** (o `provider_message_id` já é a
  chave, o replay >5 min não cobre reentrega em segundos).
- **Statuses:** o mesmo webhook traz `statuses` (sent/delivered/read/**failed**). No mínimo logar o
  `failed` — template reprovado ou número inválido some em silêncio sem isso.

### 6.2 Credenciais Cloud: quem é dono do quê

O `n8n-cloud` é **um** workflow para **N lojas**, então precisa mapear número → loja:

- **`phone_number_id` + `waba_id`** (identificam a central da loja) ficam em `whatsapp_canais` na
  **Loja**, ao lado dos canais Evolution de hoje. É o cadastro que o lojista/dono já usa.
- **Token do sistema, App Secret e verify token** são **do Revy** (um app na Meta, §8): variável de
  ambiente / credencial do n8n. **Não** por loja, **não** no banco, **não** no git.
- O Control grava só o `whatsapp_modo` — não guarda credencial nem opera a central.
- Roteamento do inbound: `entry[].changes[].value.metadata.phone_number_id` → loja. Número
  desconhecido → descarta e loga.

### 6.3 Rollout e loja suspensa

- **Flag `whatsapp_modo_2` default OFF** no código (invariante do projeto). Com a flag off, o
  Control não oferece o modo 2 e o `n8n-cloud` não roteia. Ligar por loja no piloto.
- **Loja suspensa não funciona — ponto.** A suspensão é gate de **backend**, não item de menu: o
  webhook responde `200` pra Meta e **descarta**; o bot não responde; o rodízio não emite oferta;
  ofertas pendentes expiram sem passar pro próximo; sino não toca; follow-up não dispara. O gate
  mora no `chatbot-api` (um ponto), não espalhado na UI.

## 7. Peças novas a construir

1. **Control:** campo `whatsapp_modo` por loja (1 XOR 2) + provisionamento (padrão de módulo
   provisionável do Control), atrás da flag `whatsapp_modo_2` (default OFF, §6.3).
2. **Cadastro de vendedores + ordem da fila** (por loja): **nome** + número + **ordem**, cadastrados
   **na Loja pelo lojista**; ativo/inativo; estado de trava por lead. Exposto ao chatbot por
   contrato. Nome é obrigatório (vai no aviso ao cliente).
3. **Central bot (Modo 2)** no `chatbot-api`: intake, **3 gatilhos** (§5.2), detecção
   vendedor×cliente por `variantes_telefone`, trava por clique (primeiro vence, resolvida por
   `oferta_id`), silêncio pós-handoff com re-notificação limitada (§5.4), recado "já foi pego" no
   clique perdedor.
4. **`n8n-cloud`:** inbound (verificação + assinatura §6.1, parse Meta + `referral` + `media_id`,
   dedup por `wamid`, `statuses`) e outbound (Graph API: texto + template + interativo). Sem timer,
   sem download de mídia.
5. **Motor de rodízio + timer no `chatbot-api`:** ponteiro rotativo persistido por loja, 10 min por
   vendedor, um lead pendente por vendedor, uma volta e para. Worker do próprio chatbot — não Wait
   do n8n.
6. **Template Utility com botão de resposta rápida** aprovado na Meta para o "chama vendedor"
   (variáveis: nome do cliente, veículo, resultado da simulação **quando houver**; **sem**
   `wa.me` neste envelope). Mais a variante interativa grátis quando a janela está aberta.
7. **Atendimento (Modo 2):** faixa "N sem vendedor" + filtro **Aguardando** (dono/gerente).
8. **Handoff:** **depois** do peguei, mandar ao vendedor que venceu o `wa.me` + **pacote completo
   do lead, com CPF/nascimento/CNH** + link do Portal (§5.7), com registro de auditoria do envio,
   **e** avisar o cliente quem vai chamá-lo (nome + número). O mesmo pacote
   vale quando o dono **assume da faixa** ou **reatribui** no Portal — reusa
   `assumir | devolver | reatribuir`, que já existe
   (`portal-gestao/app/loja_operacao_auditoria.py:24`, `main.py:1289`); só falta o envio.
9. **Sino 1:1 na Loja:** só o `oferecido_a` vê a oferta **com botão Peguei** (mesmo assumir).
10. **Agente (Modo 2):** card dos últimos 7 dias (atendidos / perdidos / aguardando / oferecidos).
11. **Follow-up de silêncio (Modo 2):** 30 min + 1 h, textos configuráveis, worker no chatbot.
12. **Mídia Cloud (§5.10):** download no Graph (`media_id` → URL assinada) como downloader
    alternativo ao da Evolution em `audio.py`/`vehicle_photo.py`; transcrição resolvida **por
    canal/modo** e ligada **só no Modo 2**, apontando pro Groq `whisper-large-v3`; corrigir
    `language` de `pt-BR` para `pt`; VAD/baixa confiança caindo no fallback "manda por texto".
13. **Gate de suspensão + flag (§6.3)** no `chatbot-api`: um ponto, cobrindo inbound, rodízio,
    sino e follow-up.

## 8. Onboarding da central (direto na Meta, dev mode)

- **Piloto:** app próprio do Revy na Meta em **dev mode**, com um **número de teste** — sem
  verificação de negócio completa — para provar o fluxo. As credenciais Cloud (`phone_number_id` +
  token) são nossas, plugadas no `n8n-cloud`. **Sem BSP.**
- **Token: System User, não o do painel.** O token que a Meta mostra na tela do app é
  **temporário (24 h)** — plugado no `n8n-cloud`, o piloto funciona hoje e morre amanhã de manhã.
  O certo desde o piloto: criar um **System User** no Business Suite, dar a permissão de WhatsApp e
  gerar o token **permanente**. Vale para `n8n-cloud` e para o download de mídia no Graph (§5.10).
- **Dev mode = 5 destinatários**, cadastrados à mão no painel. O rodízio consome isso rápido:
  1 cliente de teste + 3 vendedores já são 4 de 5. Dá pra provar rodízio, "primeiro clique vence" e
  handoff; **não** dá pra testar fila grande. Dimensionar o cenário do smoke (§10) por esse teto.
- **Produto (fase seguinte):** virar **Tech Provider** (verificação de negócio + app review de
  `whatsapp_business_messaging` + embedded signup) para o lojista conectar sozinho pelo Control.
  Timeline realista 2–6 semanas de burocracia; sem taxa da Meta pelo programa.
- **Verificação de negócio é por loja, e é da loja.** Sair do dev mode para atender cliente real
  exige o Business Manager da loja verificado — ordem de dias úteis quando o CNPJ está redondo, mas
  trava por documento errado, não por código. É burocracia do lojista, não do Revy.
- **Assets Meta:** o número da central entra **sob o Meta Business da loja** (onde estão os ads) —
  favorece o CTWA. Login do onboarding é do **admin/dono do Business**.

## 9. Custos (Brasil, aprox. 2026)

| Mensagem | Quando | Custo |
|---|---|---|
| **Serviço** (dentro de 24h) | bot ↔ cliente; "chama vendedor" interativo se a janela com o vendedor está aberta | **Grátis** |
| Template **Utility** (com botão) | primeiro toque em vendedor com janela **fechada** | ~R$0,03–0,04/entrega |
| Template **Marketing** | não é nosso fluxo (e "está na loja?" de manhã cairia aqui se recategorizado) | ~R$0,32 |
| Licença da API | — | Grátis |

- Se o 1º da fila pega o primeiro lead do dia, o custo típico é **um** template (~R$0,04).
  Os leads seguintes daquele vendedor no mesmo dia são grátis. Sem custo de resumo ao dono.
- Pior caso numa volta: 1 template por vendedor **ainda frio**. Quem já clicou "peguei" nas
  últimas 24h não gera cobrança.
- Check-in matinal **não** entra: deslocaria o custo para todo vendedor, todo dia, mesmo sem lead,
  e o template "está na loja?" arrisca recategorização Marketing.
- **Re-notificação nunca gera template** (§5.4): cliente insistindo não vira custo.
- **Transcrição de áudio** (§5.10) é custo **fora desta tabela** — provider por minuto, não Meta.
  Entra na conta do piloto Modo 2, e **só nele**: o Modo 1 não transcreve nada. Groq
  `whisper-large-v3` a US$ 0,111/h dá **~US$ 0,83/mês por loja** no cenário de 30 leads/dia com 40%
  mandando ~3 áudios de 25 s (~450 min/mês). Ordem de grandeza: **menos que 100 templates**.
- Modo 1 continua ~R$0 (Baileys, reativo).

## 10. Validação (smoke leve — substitui o spike pesado)

O spike de coexistência (BSP, QR, `smb_message_echoes`, history) **deixa de existir**. No lugar, um
**smoke de Cloud API padrão** em dev mode:

1. Registrar o número de teste na Cloud API (dev mode).
2. `n8n-cloud` recebe um `messages` inbound do cliente de teste e o repassa parseável ao chatbot.
3. Enviar um **template Utility com botão** da central pro número de um "vendedor de teste" e receber
   o **clique do botão** de volta (trava).
4. Confirmar o `referral`/`ad_id` num inbound vindo de um clique de anúncio de teste (CTWA).
5. Mandar um **áudio** do cliente de teste e ver a transcrição virar texto no chatbot; desligar o
   provider e ver o fallback "manda por texto" chegar ao cliente (§5.10).
6. **Aferir o pt-BR antes de fechar o provider:** juntar ~30 áudios reais de cliente (rua, ruído,
   sotaque) e rodar no Groq `whisper-large-v3` e no plano B. Incluir 2–3 áudios **mudos/só ruído**
   pra ver se alucina. Se o Groq não segurar, trocar é mudar 2 variáveis (§5.10).
7. Rejeitar um POST com `X-Hub-Signature-256` inválido (§6.1).

**Critério de sucesso:** cliente→bot→simulação→chama vendedor (ordem)→clique trava→handoff, ponta a
ponta, num número de teste, sem vazar segredo. É trabalho de implementação, **não** um gate à parte.

## 11. Faseamento

**Fase 1 — Piloto (este spec vira plano):**
- Control: toggle `whatsapp_modo` por loja.
- Modo 1 exposto como opção (sem mudar comportamento).
- Modo 2 numa loja piloto (flag `whatsapp_modo_2` ON só nela): central Cloud API em dev mode,
  `n8n-cloud` com verificação/assinatura, cadastro+rodízio rotativo, template com botão e
  `oferta_id`, handoff com aviso ao cliente, mídia (áudio/imagem) pelo Graph, gate de suspensão,
  faixa/filtro Aguardando, card de 7 dias no Agente. Rodar o smoke (§10).

**Fase 2 — Produto (spec seguinte):**
- Revy como **Tech Provider** + embedded signup no Control (self-serve de onboarding Cloud).
  **Nascer no embedded signup v4:** o v2 é descontinuado em **15/10/2026**. Não copiar tutorial
  velho.
- **Tech Provider não tem linha de crédito** — e isso define o billing: cada loja põe o meio de
  pagamento dela na própria WABA e **paga a Meta direto**; o Revy fatura só o software. Os ~R$0,04
  de template (§9) **não** passam pelo caixa do Revy. Faturar a mensagem junto da mensalidade
  exigiria ser **Solution Partner** (que exige linha de crédito) — decisão de negócio, não de
  código.
- Configuração fina do rodízio (X min, ordem) na UI.
- Proativo pro cliente + templates de marketing (se/quando fizer sentido).
- Billing por loja Cloud.

## 12. Riscos & mitigações

| Risco | Mitigação |
|---|---|
| Vendedores não respondem o rodízio | Uma volta (10 min cada) e **para**. Leads ficam `aguardando` na faixa/filtro do Atendimento. |
| Clique atrasado vs oferta nova | Primeiro clique vence; o perdedor recebe "já foi pego". Trava idempotente. |
| Pegou e não ligou | Fica travado. Sem auto-devolver. Dono reatribui no Portal. |
| Template com botão precisa de aprovação Meta | Submeter cedo no piloto; conteúdo é transacional (Utility), aprovação costuma ser rápida. Confirmar suporte a botão de resposta rápida no template. |
| Central não loga o chat vendedor↔cliente | Trade-off aceito do handoff; o registro do **lead** (não do chat) fica no Portal. Reavaliar na Fase 2. |
| Dev mode limita destinatários | **5** no total (§8): 1 cliente de teste + 3 vendedores = 4. Cenário do smoke cabe nesse teto; fila grande não. Produção exige verificação de negócio da loja. |
| Token temporário de 24 h derruba o piloto no dia seguinte | System User com token permanente desde o começo (§8). |
| Cliente estranhar "número novo" do vendedor | Comum em venda de veículo; a central avisa "o vendedor Fulano vai te chamar agora". |
| Passkey em números que ficam no Baileys (Modo 1) | Modo 1 é legado; parear limpo 1x, não churnar. Passkey **não** afeta o Modo 2. |
| Webhook Cloud exposto na internet | `hub.verify_token` no GET + `X-Hub-Signature-256` no POST; número desconhecido descartado (§6.1). |
| URL de mídia da Meta expira (~5 min) | Download síncrono no inbound, com fallback "manda por texto" se falhar (§5.10). |
| Transcrição ruim vira intake errado | Fallback pede texto em vez de adivinhar; dado de intake (CPF/CNH) nunca vem de imagem nesta fase. |
| Whisper **alucina** em áudio mudo/ruidoso e o bot responde ao que o cliente não disse | VAD antes de mandar, duração mínima, baixa confiança → fallback. Áudios mudos entram no smoke (§10, item 6). |
| Vendedor com muitos leads ao mesmo tempo | Ponteiro rotativo + teto de **uma** oferta pendente por vendedor (§5.3). |

## 13. Fora de escopo / não re-propor

- **Coexistência por-vendedor** (`smb_message_echoes` + history sync) — descartada (§14).
- **Caixa compartilhada na central** (vários vendedores atendendo pelo mesmo número) — o dono
  escolheu **handoff**, não shared inbox.
- **Misto na mesma loja** (alguns Baileys + uma central juntos) — proibido: 1 XOR 2 por loja.
- **Rodízio em loop infinito** — o dono decidiu **uma volta e para**; o não-atendido fica na faixa
  do Atendimento, não vira insistência sem fim.
- **OCR / leitura de imagem pelo bot** — imagem entra e vai pro vendedor (§5.10), mas dado de
  intake (CPF, CNH) o bot pede **por texto**. Interpretar imagem fica pra depois.
- **Baixar mídia no n8n** — o `n8n-cloud` repassa `media_id`; quem baixa e transcreve é o chatbot.
- **Transcrição de áudio no Modo 1** — não. Lá o áudio chega no celular do vendedor, que ouve;
  transcrever só geraria custo. A config de transcrição é **por canal/modo**, nunca global.
- **Reabrir o bot quando o cliente volta a escrever pós-handoff** — não. Só o recado da §5.4.
- **BSP** — onboarding direto na Meta.
- **Logar o chat vendedor↔cliente** no Modo 2 — o chat acontece no celular do vendedor; fora de
  escopo desta fase.
- **Baixar a versão do Baileys** para escapar do passkey — nenhuma versão resolve.
- **Check-in matinal** ("está na loja?") — o primeiro peguei do dia já abre a janela; o bom-dia
  só gera custo extra e risco de recategorização Marketing.
- **"Peguei" por texto solto, URL ou link do Portal** — o backend não fica sabendo, ou fica
  frágil. Só botão que volta inbound.
- **`wa.me` na mensagem de oferta** — o vendedor chamaria sem travar o lead.
- **Apontar vendedor à mão neste lead** — só rodízio automático. Fica pra Fase 2 se fizer falta.
- **Sino da loja inteira na oferta** — só o `oferecido_a`. Dono vê o que sobrou na faixa do Atendimento.
- **Resumo WhatsApp às 19h / campo do número do dono** — o recorte mora na Loja, ao vivo.
- **Devolver à fila se pegou e não ligou** — não. Travou, ficou.
- **Timer no Wait do n8n** — não. Worker no `chatbot-api`.
- **Um n8n com `if` de modo** — não. Dois workflows.
- **Follow-up no Modo 1** — não. O `n8n-baileys` não ganha cutucão.

## 14. Alternativa descartada: coexistência por-vendedor

A abordagem anterior (design de coexistência, agora removido) mantinha **um número por
vendedor** e usava **coexistência** (app Business + Cloud API no mesmo número), com
`smb_message_echoes` para separar humano×bot e history sync para semear "quem já conversou". Era
correto, mas **mais caro e frágil**: exigia onboarding com QR + aprovação de histórico por vendedor,
dependia de eventos que o Evolution não repassa bem, e trazia uma regra de roteamento nova por canal.

O modelo de **central só-bot + handoff** entrega o mesmo resultado (bot atende, humano assume) com
**muito menos máquina**: número de bot dedicado (Cloud API padrão, não coexistência), zero eventos de
echo/history, e os números dos vendedores livres de qualquer pareamento. Por isso a coexistência foi
descartada.

## 15. Decisões fechadas nesta revisão (2026-08-13)

Nada em aberto de produto. Contrato HTTP da fila (Portal → chatbot) é detalhe do plano.

| # | Tema | Decisão |
|---|---|---|
| 1 | Quem escolhe o vendedor | **Só rodízio automático**. Sem apontar à mão. (Ordem revista no #13: ponteiro rotativo.) |
| 2 | Sino | WhatsApp 1:1 + sino só no `oferecido_a`, **com botão Peguei**. |
| 3 | Tempo por oferta | **10 min**. |
| 4 | Resumo ao dono | **Na Loja**, ao vivo: faixa+filtro no Atendimento + card 7 dias no Agente. Sem WhatsApp 19h. |
| 5 | Timer | **Worker no `chatbot-api`**. |
| 6 | Clique atrasado | **Primeiro clique vence.** Botão velho continua válido até travar. Perdedor ouve "já foi pego". |
| 7 | Pegou e não ligou | **Fica travado.** Dono resolve no Portal. Sem auto-devolver. |
| 8 | Número do dono | **Não existe.** Caiu com o template das 19h. |
| 9 | Peguei no sino | **Sim.** Mesmo assumir do WhatsApp. |
| 10 | n8n | **Um por modo.** `n8n-baileys` intacto; `n8n-cloud` novo. |
| 11 | Silêncio do cliente | **30 min → msg 1; +1 h → msg 2; para.** Texto por etapa (§5.9). Sem cutucão de foto. |

### 15.1 Fechado na 2ª passada (2026-08-13)

| # | Tema | Decisão |
|---|---|---|
| 12 | Áudio e imagem | **Entram**, com **Groq `whisper-large-v3`** (AssemblyAI como plano B), e a transcrição liga **só no Modo 2** — a central precisa ouvir pra responder; no Modo 1 quem ouve é o vendedor. Meta manda `media_id`; o **chatbot** baixa no Graph e transcreve no código. Falhou → responde o cliente pedindo texto. Nunca ficar mudo. §5.10 |
| 13 | Ordem do rodízio | **Ponteiro rotativo** por loja, avança a cada oferta. Não é mais "sempre do topo". Um lead pendente por vendedor; quem tem oferta aberta é pulado. §5.3 |
| 14 | Cliente escreve depois de travado | Recado ao cliente **1× por 6 h**; cutucão ao vendedor **1× por hora**, só em envelope **grátis** (sino sempre, WhatsApp só com janela aberta). Nunca template pago. §5.4 |
| 15 | Loja suspensa | **Não funciona.** Gate de backend no `chatbot-api`: descarta inbound, não responde, não oferece, não toca sino, não cutuca. §6.3 |
| 16 | Simulação falha no Motor | Vira **gatilho de handoff**. Pacote completo (inclusive CPF/nascimento/CNH) vai ao vendedor pelo WhatsApp depois do clique; cliente é avisado de que **o vendedor** vai simular. §5.11 |
| 17 | Cliente sabe quem vai chamar | Ao travar, a central manda ao cliente **nome + número do vendedor**. Vale pra todo handoff, não só o de erro do Motor. §5.1 |
| 18 | Dados do lead ao vendedor | **Pacote completo por WhatsApp**, CPF/nascimento/CNH incluídos, **só depois do clique** e só pro vendedor que travou, com registro de auditoria. Link do Portal não substitui. §5.7 |
| 19 | Identidade do clique | Botão carrega `oferta_id` (`pego:<oferta_id>`); sem isso "primeiro clique vence" não fecha com duas ofertas vivas. §5.7 |
