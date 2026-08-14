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
`n8n/workflow-ai-nao-salvos.json` (nó "Extrair1" — base do `n8n-baileys`);
`portal-gestao/app/loja/` + `whatsapp_canais`.
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
   Meta. O bot atende o cliente, roda a simulação e **distribui o lead aos vendedores por rodízio em
   ordem**; o vendedor assume e fala com o cliente **do WhatsApp dele** (handoff). Robusto e à prova de
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
| Distribuição | **Só rodízio automático**, ordem fixa, um por vez. Sem apontar vendedor à mão. **10 min** pra clicar; sem resposta → próximo. Uma passada e **para**. Primeiro clique vence, mesmo atrasado (§5.3). |
| Confirmação do vendedor | Dois jeitos, **o mesmo assumir**: botão no WhatsApp **ou** botão **Peguei** no sino da Loja. Primeiro que chegar vence. Ver §5.7. Pegou e não ligou: **fica travado**. |
| Cadastro de vendedores | Números + **ordem** da fila: **na Loja, pelo lojista**. Control só escolhe o modo. |
| Fallback (ninguém pega) | **Sem WhatsApp ao dono.** Lead fica `aguardando`. Na Loja: faixa + filtro no Atendimento, e card no Agente com os últimos 7 dias. |
| Canal do aviso ao vendedor | **WhatsApp 1:1** + **sino na Loja só para o `oferecido_a`**, com botão Peguei no próprio sino. Nunca grupo, nunca sino da loja inteira. |
| Timer do rodízio e do bot | **Worker no `chatbot-api`**. n8n só transporta. |
| n8n | **Um workflow por modo.** `n8n-baileys` = o atual, intacto. `n8n-cloud` = novo, só Modo 2. Sem `if` de modo no meio de um workflow. |
| Bot do Modo 2 | **Fork do atual** (mesmo debounce 40s, replay >5 min, intake, simulação, gates). Texto de follow-up + prompt se configuram juntos. Silêncio do cliente: 30 min → msg 1; +1 h sem resposta → msg 2; para. Só enquanto `bot_ativo`. |
| Gatilho do handoff | **Dois gatilhos:** quando a **simulação fica pronta** OU quando o **cliente pede humano** explicitamente, o que vier primeiro. |
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
     gatilho (sim pronta OU pede humano)
       └─► rodízio EM ORDEM, 1:1: msg c/ botão + sino só dele ─► Vend.1 ─(10 min)─► Vend.2 ─► ...
              1º clique vence (mesmo atrasado) ─► inbound "peguei" ─► assumir (trava + Em atendimento)
              central manda wa.me DEPOIS do clique ─► vendedor chama do WhatsApp DELE
              passou por todos sem pegar ─► lead "aguardando" (faixa+filtro no Atendimento)
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
   - a **simulação fica pronta** (resultado volta pra central), ou
   - o **cliente pede humano** explicitamente ("quero falar com alguém").
   O bot avisa o cliente que **já vão chamá-lo** e inicia o rodízio.
4. **Rodízio (§5.3):** a central chama os vendedores **na ordem**, um por vez, até alguém clicar o
   botão de "peguei" — ou até esgotar a fila.
5. **Handoff:** ao travar, a central entrega ao vendedor o contato do cliente (número + link
   `wa.me`). O vendedor chama o cliente **do WhatsApp dele**. A central **se cala** com aquele cliente.

### 5.2 Gatilhos do handoff
Dois, o que vier primeiro (§2). "Cliente pede humano" precisa de detecção simples de intenção
(frase/opção de menu). "Simulação pronta" é o retorno do Motor. Se o gatilho for "pediu humano"
**antes** da simulação, a mensagem de "chama vendedor" vai **sem** resultado de simulação — o template
tem que funcionar com e sem esse campo.

### 5.3 Rodízio (distribuição em ordem)
- **Só automático.** Não há "apontar o vendedor deste lead". Cada lead percorre a lista
  cadastrada **de cima pra baixo**. O 1º da lista sempre recebe primeiro (sem ponteiro
  rotativo). Critérios mais ricos (disponibilidade/performance) ficam pra Fase 2.
- **Fila por loja:** números + ordem, cadastrados **no Portal pelo lojista**. O Portal é a
  fonte da verdade.
- **10 min por vendedor:** a central chama o vendedor `i` por WhatsApp 1:1 (envelope da §5.7)
  **e** liga o sino da Loja **só para ele**. Se ele não clicar em **10 min**, a central chama
  o `i+1` (sino muda de dono).
- **Primeiro clique vence:** o botão de uma oferta anterior **continua válido** até o lead
  travar. Se o vendedor 1 estoura, o 2 é oferecido, e o 1 clica o botão velho antes do 2,
  o 1 leva. O 2 recebe um recado de "já foi pego" (sem `wa.me`). Trava é **idempotente**:
  o primeiro `assumir` ganha; clique seguinte é ignorado.
- **Uma passada e para:** percorre todos ≥1 vez. Sem ninguém clicar, **encerra** (não
  recomeça). O lead fica `aguardando`.
- **Pegou e não ligou:** o lead **fica travado** com ele. Não devolve à fila. Dono resolve
  no Portal (reatribuir/devolver).
- **Timer:** worker no `chatbot-api` (estado `oferecido_a` + prazo). n8n não espera.
- **Estado do lead:** `aguardando` → `oferecido_a(vendedor_i)` → `travado(vendedor)` /
  `esgotou_fila`. Tudo visível no Portal.

### 5.4 Handoff, silêncio e o que sobrou na fila
- Depois de travado, a central **não responde mais** aquele cliente. Se o cliente voltar a escrever,
  o padrão é **re-notificar o vendedor travado** (não reabrir o bot).
- O chat real vendedor↔cliente acontece **no celular do vendedor** e a central **não o vê** —
  trade-off aceito do modelo handoff (§13).
- **Fallback = Loja, ao vivo.** Sem template às 19h, sem campo de WhatsApp do dono. Quem
  ninguém pegou fica `aguardando` e aparece em dois lugares (§5.8):
  1. **Atendimento** — faixa no topo ("N leads sem vendedor") + filtro de estado **Aguardando**,
     só dono/gerente. Clique na faixa aplica o filtro. Dali o dono assume/reatribui.
  2. **Agente** — card dos **últimos 7 dias**: atendidos (travados), perdidos, aguardando,
     oferecidos. Não substitui a barra agente × handoff do mês; é o recorte da fila.

### 5.5 A central recebe cliente E vendedor (roteamento por remetente)
O número central recebe inbound de **dois tipos** de remetente:
- **Cliente (lead):** número desconhecido → conversa do bot.
- **Vendedor:** número **cadastrado** na loja → o inbound (clique do botão / texto) é tratado como
  **comando de controle** (trava do lead), não como conversa de cliente.
O `n8n-cloud`/`chatbot-api` decide pelo **cadastro de vendedores** da loja (§7).

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

**O contato do cliente (`wa.me`) só vai DEPOIS do clique** (WhatsApp ou sino). Se o número
for na mensagem de oferta, o vendedor chama sem o backend saber.

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
| Loja — cadastro da fila | Não existe. | Números + ordem, pelo lojista. |

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

## 7. Peças novas a construir

1. **Control:** campo `whatsapp_modo` por loja (1 XOR 2) + provisionamento (padrão de módulo
   provisionável do Control).
2. **Cadastro de vendedores + ordem da fila** (por loja): números e **ordem**, cadastrados **na
   Loja pelo lojista**; estado de trava por lead. Exposto ao chatbot por contrato.
3. **Central bot (Modo 2)** no `chatbot-api`: intake, 2 gatilhos, detecção vendedor×cliente, trava
   por clique (primeiro vence), silêncio pós-handoff, recado "já foi pego" no clique perdedor.
4. **`n8n-cloud`:** inbound (parse Meta + `referral`) e outbound (Graph API: texto + template +
   interativo). Sem timer.
5. **Motor de rodízio + timer no `chatbot-api`:** 10 min por vendedor, uma passada, para. Worker
   do próprio chatbot — não Wait do n8n.
6. **Template Utility com botão de resposta rápida** aprovado na Meta para o "chama vendedor"
   (variáveis: nome do cliente, veículo, resultado da simulação **quando houver**; **sem**
   `wa.me` neste envelope). Mais a variante interativa grátis quando a janela está aberta.
7. **Atendimento (Modo 2):** faixa "N sem vendedor" + filtro **Aguardando** (dono/gerente).
8. **Handoff:** **depois** do peguei, mandar o `wa.me` ao vendedor que venceu (mensagem livre).
9. **Sino 1:1 na Loja:** só o `oferecido_a` vê a oferta **com botão Peguei** (mesmo assumir).
10. **Agente (Modo 2):** card dos últimos 7 dias (atendidos / perdidos / aguardando / oferecidos).
11. **Follow-up de silêncio (Modo 2):** 30 min + 1 h, textos configuráveis, worker no chatbot.

## 8. Onboarding da central (direto na Meta, dev mode)

- **Piloto:** app próprio do Revy na Meta em **dev mode**, com um **número de teste** — sem
  verificação de negócio completa — para provar o fluxo. As credenciais Cloud (`phone_number_id` +
  token) são nossas, plugadas no `n8n-cloud`. **Sem BSP.**
- **Produto (fase seguinte):** virar **Tech Provider** (verificação de negócio + app review de
  `whatsapp_business_messaging` + embedded signup) para o lojista conectar sozinho pelo Control.
  Timeline realista 2–6 semanas de burocracia; sem taxa da Meta pelo programa.
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
- Pior caso numa passada: 1 template por vendedor **ainda frio**. Quem já clicou "peguei" nas
  últimas 24h não gera cobrança.
- Check-in matinal **não** entra: deslocaria o custo para todo vendedor, todo dia, mesmo sem lead,
  e o template "está na loja?" arrisca recategorização Marketing.
- Modo 1 continua ~R$0 (Baileys, reativo).

## 10. Validação (smoke leve — substitui o spike pesado)

O spike de coexistência (BSP, QR, `smb_message_echoes`, history) **deixa de existir**. No lugar, um
**smoke de Cloud API padrão** em dev mode:

1. Registrar o número de teste na Cloud API (dev mode).
2. `n8n-cloud` recebe um `messages` inbound do cliente de teste e o repassa parseável ao chatbot.
3. Enviar um **template Utility com botão** da central pro número de um "vendedor de teste" e receber
   o **clique do botão** de volta (trava).
4. Confirmar o `referral`/`ad_id` num inbound vindo de um clique de anúncio de teste (CTWA).

**Critério de sucesso:** cliente→bot→simulação→chama vendedor (ordem)→clique trava→handoff, ponta a
ponta, num número de teste, sem vazar segredo. É trabalho de implementação, **não** um gate à parte.

## 11. Faseamento

**Fase 1 — Piloto (este spec vira plano):**
- Control: toggle `whatsapp_modo` por loja.
- Modo 1 exposto como opção (sem mudar comportamento).
- Modo 2 numa loja piloto: central Cloud API em dev mode, `n8n-cloud`, cadastro+rodízio em ordem,
  template com botão, handoff, faixa/filtro Aguardando, card de 7 dias no Agente. Rodar o smoke (§10).

**Fase 2 — Produto (spec seguinte):**
- Revy como **Tech Provider** + embedded signup no Control (self-serve de onboarding Cloud).
- Configuração fina do rodízio (X min, ordem) na UI.
- Proativo pro cliente + templates de marketing (se/quando fizer sentido).
- Billing por loja Cloud.

## 12. Riscos & mitigações

| Risco | Mitigação |
|---|---|
| Vendedores não respondem o rodízio | Uma passada (10 min cada) e **para**. Leads ficam `aguardando` na faixa/filtro do Atendimento. |
| Clique atrasado vs oferta nova | Primeiro clique vence; o perdedor recebe "já foi pego". Trava idempotente. |
| Pegou e não ligou | Fica travado. Sem auto-devolver. Dono reatribui no Portal. |
| Template com botão precisa de aprovação Meta | Submeter cedo no piloto; conteúdo é transacional (Utility), aprovação costuma ser rápida. Confirmar suporte a botão de resposta rápida no template. |
| Central não loga o chat vendedor↔cliente | Trade-off aceito do handoff; o registro do **lead** (não do chat) fica no Portal. Reavaliar na Fase 2. |
| Dev mode limita destinatários | Piloto usa números de teste registrados; produção exige verificação (Fase 2). |
| Cliente estranhar "número novo" do vendedor | Comum em venda de veículo; a central avisa "o vendedor Fulano vai te chamar agora". |
| Passkey em números que ficam no Baileys (Modo 1) | Modo 1 é legado; parear limpo 1x, não churnar. Passkey **não** afeta o Modo 2. |

## 13. Fora de escopo / não re-propor

- **Coexistência por-vendedor** (`smb_message_echoes` + history sync) — descartada (§14).
- **Caixa compartilhada na central** (vários vendedores atendendo pelo mesmo número) — o dono
  escolheu **handoff**, não shared inbox.
- **Misto na mesma loja** (alguns Baileys + uma central juntos) — proibido: 1 XOR 2 por loja.
- **Rodízio em loop infinito** — o dono decidiu **uma passada e para**; o não-atendido vira resumo
  diário, não insistência sem fim.
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
| 1 | Quem escolhe o vendedor | **Só rodízio automático**, de cima pra baixo. Sem apontar à mão. |
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
