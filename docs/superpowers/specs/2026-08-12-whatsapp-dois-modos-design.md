# WhatsApp em dois modos: Baileys+grupo OU Central Cloud API (escolha por loja no Control)

**Data:** 2026-08-12
**Status:** Decisões estruturais **fechadas** com o dono (brainstorm 2026-08-12) — pronto para o plano
de implementação. Aguardando revisão do dono sobre o texto do spec.
**Substitui:** a abordagem anterior de coexistência **por vendedor** (`smb_message_echoes` + history
sync), **descartada** em favor do modelo de **central só-bot** (ver §14). Os planos daquela abordagem
(design de coexistência, spike de coexistência e regra Cloud/n8n de coexistência) foram **removidos**
— este é o documento canônico do "problema do WhatsApp".
**Produtos afetados:**
- `revy-control` / `portal-gestao`: toggle `whatsapp_modo` por loja + cadastro de vendedores e ordem
  da fila (Modo 2, feito pelo lojista).
- `chatbot-api`: central bot do Modo 2 (intake, gatilho de handoff, rodízio, trava, detecção
  vendedor×cliente, resumo diário). Modo 1 mantém o gate atual intacto.
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
| Distribuição | **Rodízio em ordem fixa (um vendedor por vez).** Percorre a lista **na ordem cadastrada**; cada vendedor tem **X min** pra responder; sem resposta → próximo. **Passa por todos ≥1 vez; depois de uma passada completa sem ninguém pegar, PARA** (sem loop infinito). |
| Confirmação do vendedor | O vendedor confirma que pegou **clicando num botão** na mensagem (não texto solto). O clique volta pro bot e **trava** o lead com ele. |
| Cadastro de vendedores | Números + **ordem** da fila são cadastrados **no Portal, pelo lojista**. |
| Fallback (ninguém pega) | **Sem aviso por-lead.** O lead fica "aguardando" no Portal. **No fim do dia**, a central manda **um resumo ao dono**: quantos leads ficaram sem atendimento. |
| Canal do aviso ao vendedor | **WhatsApp individual** da central (Cloud API) via **template Utility** com botão (msg parte da central, fora da janela de 24h). |
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
       └─► rodízio EM ORDEM: template c/ botão ─► Vend.1 ─(X min)─► Vend.2 ─► ... ─► Vend.N
              clicou o botão ─► trava o lead ─► handoff: vendedor chama o cliente do WhatsApp DELE
              passou por todos sem pegar ─► lead "aguardando" (resumo ao dono no fim do dia)
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
- **Fila por loja:** lista **ordenada** dos vendedores (número + ordem), cadastrada **no Portal pelo
  lojista**. O Portal é a fonte da verdade.
- **Ordem fixa, sem rotação:** cada lead percorre a lista **de cima pra baixo**. O 1º da lista sempre
  recebe primeiro (não há ponteiro round-robin rotativo).
- **X min por vendedor:** a central chama o vendedor `i` por WhatsApp (template Utility **com botão**).
  Se ele não clicar o botão em **X min**, a central chama o `i+1`.
- **Confirmação por botão:** o vendedor clica "peguei" no template → o clique chega à central → o lead
  **trava** com ele e a central **para** de chamar os outros.
- **Uma passada e para:** o rodízio **passa por todos ≥1 vez**. Se chegar ao fim da fila sem ninguém
  clicar, **encerra** (não recomeça em loop). O lead fica `aguardando`.
- **Estado do lead:** `aguardando` → `oferecido_a(vendedor_i)` → `travado(vendedor)` /
  `esgotou_fila`. Tudo visível no Portal.

### 5.4 Handoff, silêncio e resumo do fim do dia
- Depois de travado, a central **não responde mais** aquele cliente. Se o cliente voltar a escrever,
  o padrão é **re-notificar o vendedor travado** (não reabrir o bot).
- O chat real vendedor↔cliente acontece **no celular do vendedor** e a central **não o vê** —
  trade-off aceito do modelo handoff (§13).
- **Fallback = resumo diário.** Não há aviso por-lead quando ninguém pega. **No fim do dia**, a central
  manda **um** template ao **dono** com o total (e lista) de leads que ficaram `aguardando`, pra ele
  resolver no Portal.

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

## 6. Encanamento Cloud — Meta direto ↔ n8n-cloud

- **Inbound:** webhook da Meta (campos `messages` + `referral`) aponta **direto** para o
  `n8n-cloud`. Sem Evolution no caminho Cloud.
- **Outbound:** envio via **Graph API** (REST simples) — texto livre dentro da janela de 24h e
  **template Utility com botão** para o "chama vendedor" e para o resumo diário (fora da janela).
- **Por quê direto e não via Evolution:** o suporte Cloud do Evolution mostrou-se frágil (CHANGELOG
  sem menção, repo dedicado à parte, issue #807). Como o Modo 2 é **Cloud API pura** (não
  coexistência), não há nada do Evolution a reaproveitar aqui — mais limpo apontar direto pra Meta.
- **Dois workflows n8n** (§3): `n8n-baileys` (atual, intacto) e `n8n-cloud` (novo). Sem `if` de
  payload no meio.

## 7. Peças novas a construir

1. **Control:** campo `whatsapp_modo` por loja (1 XOR 2) + provisionamento (padrão de módulo
   provisionável do Control).
2. **Cadastro de vendedores + ordem da fila** (por loja): números e **ordem**, cadastrados **no
   Portal pelo lojista**; estado de trava por lead. Exposto ao chatbot/n8n-cloud por contrato (para o
   roteamento por remetente e o rodízio).
3. **Central bot (Modo 2)** no `chatbot-api`: intake, 2 gatilhos, detecção vendedor×cliente, trava do
   lead por clique de botão, silêncio pós-handoff.
4. **`n8n-cloud`:** inbound (parse Meta + `referral`) e outbound (Graph API: texto + template com
   botão).
5. **Motor de rodízio + timer:** percorrer a fila em ordem, esperar X min por vendedor, parar após
   uma passada completa (candidato pro timer: nó Wait do `n8n-cloud`).
6. **Template Utility com botão** aprovado na Meta para o "chama vendedor" (variáveis: nome do
   cliente, veículo, resultado da simulação **quando houver**, link de assumir; botão "peguei").
7. **Resumo diário ao dono:** job de fim de dia que conta os leads `aguardando` e manda um template
   ao dono.
8. **Handoff:** montar o `wa.me`/deep-link com o número do cliente para o vendedor abrir a conversa.

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
| **Serviço** (dentro de 24h) | bot ↔ cliente | **Grátis** |
| Template **Utility** (com botão) | "chama vendedor" (por tentativa) e resumo diário | ~R$0,04/msg |
| Template **Marketing** | não é nosso fluxo | ~R$0,38 |
| Licença da API | — | Grátis |

- Custo real do Modo 2 ≈ **1 template por vendedor chamado, numa única passada**. Fila de 3
  vendedores no pior caso (ninguém pega) = ~R$0,12/lead. Se o 1º pega, ~R$0,04. + ~R$0,04/dia do
  resumo ao dono. Barato.
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
  template com botão, handoff, resumo diário ao dono. Rodar o smoke (§10).

**Fase 2 — Produto (spec seguinte):**
- Revy como **Tech Provider** + embedded signup no Control (self-serve de onboarding Cloud).
- Configuração fina do rodízio (X min, ordem) na UI.
- Proativo pro cliente + templates de marketing (se/quando fizer sentido).
- Billing por loja Cloud.

## 12. Riscos & mitigações

| Risco | Mitigação |
|---|---|
| Vendedores não respondem o rodízio | Uma passada completa pela fila (X min cada) e **para** — sem loop. Leads não pegos viram resumo diário ao dono; estado visível no Portal. |
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

## 15. Perguntas abertas / decisões adiadas

1. **X min do rodízio** — default sugerido **5 min** por vendedor, configurável por loja. Confirmar no
   piloto.
2. ~~Ordem da fila~~ **Resolvido:** **ordem fixa** cadastrada no Portal (o 1º da lista sempre recebe
   primeiro; sem rotação). Critérios mais ricos (disponibilidade/performance) ficam pra Fase 2.
3. ~~Fallback quando ninguém pega~~ **Resolvido:** **uma passada e para**; sem aviso por-lead; **resumo
   diário ao dono** dos leads `aguardando`. Definir a hora do resumo (ex.: 19h) no plano.
4. **Onde mora o timer do rodízio** — nó Wait do `n8n-cloud` vs worker no `chatbot-api`. Decidir no
   plano de implementação.
5. ~~Cadastro dos números de vendedor~~ **Resolvido:** **no Portal, pelo lojista** (números + ordem).
   Falta só o **contrato** de como o `n8n-cloud`/chatbot consulta a lista (roteamento por remetente +
   rodízio) — detalhe do plano.
6. ~~"Pego" palavra vs botão~~ **Resolvido:** **botão** de resposta rápida no template. Confirmar o
   suporte exato ao botão no template Utility na implementação.
