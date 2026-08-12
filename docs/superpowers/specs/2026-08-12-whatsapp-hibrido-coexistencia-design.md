# WhatsApp híbrido: Baileys + API oficial (coexistência), escolha por número

**Data:** 2026-08-12
**Status:** Design em revisão — aguardando aprovação do dono antes do plano de implementação
**Produtos afetados:** `motor`/`evolution` (canal `WHATSAPP-BUSINESS`), `chatbot-api` (gate de
roteamento + parse por canal), `n8n` (pipelines de inbound), `portal-gestao` (config de canal por
número, upload de foto de estoque, notificação ao vendedor). Nenhum banco novo entre produtos;
tabelas/colunas novas **dentro** do banco de cada produto.
**Referências:**
`chatbot-api/app/operacao.py:736` (`_decidir_cliente_ou_ignorar`) e `:772` (`decidir_roteamento`);
`chatbot-api/app/whatsapp_provider.py:219` (`integration: "WHATSAPP-BAILEYS"`);
`chatbot-api/app/whatsapp_outbound.py`; `chatbot-api/app/whatsapp_groups.py`;
`n8n/workflow-ai-nao-salvos.json` (nó "Extrair1"); `deploy/fly/3vm/set-evolution-webhook.ps1`;
`deploy/fly/evolution/fly.toml` (`CONFIG_SESSION_PHONE_VERSION`);
`portal-gestao/app/loja/qr_efemero.py` + `whatsapp_canais`.
Memória do projeto: `whatsapp-passkey-bloqueia-evolution`.

---

## 1. Resultado desejado

O WhatsApp passou a **exigir passkey** pra parear novos aparelhos em contas marcadas. O Baileys
(usado pelo Evolution) **não implementa** esse handshake, então o número marcado **não conecta**
(o QR nunca fecha; issues abertas evolution-api #2618 e Baileys #2672). Não é bug de config nem
da versão do Baileys — nenhuma versão resolve.

Queremos que cada vendedor possa operar o WhatsApp por um caminho **robusto e à prova de passkey**
— a **API oficial da Meta (Cloud API) em modo coexistência** — **sem** perder o que hoje só o
Baileys faz, e **sem** obrigar quem não tem WhatsApp Business a migrar. Ou seja: **os dois canais
vivos ao mesmo tempo, escolhidos por número.**

Não-objetivos desta fase: migrar todo mundo pro Cloud; recurso proativo de mensagem pro cliente
(templates); produtizar o toggle self-serve no Portal (é Fase 2, ver §11).

## 2. Decisões já tomadas com o dono

| Tema | Decisão |
|---|---|
| Modelo de números | **Um número por vendedor**, cada um com seu próprio bot (Evolution multi-instância) — como já é hoje (ex.: instâncias do Pedro e do Cauã). Não há número central único. |
| Canal por número | **Híbrido permanente:** cada número é **Baileys (QR)** ou **Cloud/coexistência (WhatsApp Business)**. Baileys **não sai** — fica pra quem não tem WhatsApp Business. |
| Linha do cliente | Número **pessoal Business do vendedor** → **coexistência** (app + Cloud API no mesmo número). O vendedor continua usando o app na mão dele. |
| Regra de roteamento | Trocar o `is_saved` (agenda) por **"o bot responde a menos que um humano já tenha falado na conversa"** no lado Cloud. Verificado como viável na Meta (§4, §5). Baileys mantém o gate atual. |
| Grupo de estoque | **Eliminado.** É só operacional (a equipe tem outro grupo social). Foto de veículo → **upload no Portal**; aviso de simulação → **notificação ao vendedor** (§6). Isso remove a necessidade de número/eSIM dedicado no Baileys. |
| Aviso de simulação | É **interno, pro vendedor** (nunca pro cliente). Disparado quando os dados estão coletados (hoje) e, no futuro, quando a **simulação der certo**. **Canal plugável** (Portal / SMS / WhatsApp central) — decisão de canal **adiada** (§6.2, §14). Portal = fonte da verdade (carrega o resultado). |
| Mídia do cliente | Cliente **só manda texto** → **sem** reescrita de download de mídia no lado Cloud. |
| Proativo pro cliente | **Fase futura.** Quando existir, usa **template Utility** aprovado (§9). Não entra agora. |
| n8n | **Dois pipelines** (um Cloud, um Baileys), no futuro quando for buildar (§7). Mais limpo que um n8n com `if` no meio. |
| Onboarding Fase 1 | Via **BSP** que suporta coexistência (ex.: 360dialog) — **sem** o Revy virar Tech Provider (§8). |
| Onboarding Fase 2 | **Toggle self-serve no Portal** → Revy vira **Tech Provider** (embedded signup) ou segue via BSP (§8, §11). |

## 3. Arquitetura

### 3.1 Visão

```
Vendedor A (Business)  ── coexistência ──►  [n8n Cloud]  ┐
  bot + humano no mesmo número                            │
                                                          ├──► chatbot-api  ──► Motor/Estoque
Vendedor B (sem Business) ── Baileys (QR) ─►  [n8n Baileys]┘   (agnóstico de canal)
```

- **Envio** continua pelos endpoints genéricos do Evolution (`/message/sendText`, `/message/sendMedia`)
  — funcionam nos dois canais. Ponto de troca central: `chatbot-api/app/whatsapp_provider.py:219`
  (`integration` passa a poder ser `WHATSAPP-BUSINESS`) e o payload de `/instance/create`.
- **Recebimento** diverge por canal (§5, §7). O `chatbot-api` **não vê o payload cru** — o n8n
  normaliza pra `{instance, telefone, texto, provider_message_id, ...}` (modelo já agnóstico de
  canal em `main.py:webhook_mensagem`).
- **Roteamento multi-número** já existe: o n8n roteia por `body.instance`, e cada canal é uma
  instância do Evolution (`WhatsAppCanal.evolution_instance`).

### 3.2 O que muda pouco (a favor)

- Núcleo Python: quase intacto (n8n normaliza; Pydantic agnóstico).
- `provider_message_id`: tratado como string opaca — `wamid.XXX` (Cloud) cabe no limite atual.
- Presença/"digitando" e PTT: **não usados** — nada a migrar.

## 4. Regra de roteamento unificada

Hoje o gate (`_decidir_cliente_ou_ignorar`, `operacao.py:736`) usa três sinais: `conversa_tem_resposta`
(nosso banco), `is_saved` (agenda, via Baileys `findChats`) e `chat_found` (histórico pré-bot no WA).
O Cloud API **não tem agenda**, então `is_saved` some como fonte.

**Regra nova (equivalente e mais determinística):**

> **O bot responde, a menos que um humano já tenha falado naquela conversa.**

Os três casos colapsam num sinal só — *um humano já falou aqui?*:
- **Humano já falou** → bot cala (o humano é dono). Cobre `is_saved` (conhecido de verdade ≈ alguém
  com quem já se conversou) e `chat_found` (histórico pré-bot = humano).
- **Sem histórico** → bot responde (lead novo).
- **Histórico só do bot** → bot continua (é a thread dele, mesmo de dias atrás). Equivale ao
  `conversa_tem_resposta` atual.

**Fonte da autoria por canal:**
- **Cloud:** humano = `smb_message_echoes`; passado = seed do history sync; bot = o que **nós**
  enviamos pela Cloud API (nosso registro); cliente = inbound normal.
- **Baileys:** mantém `is_saved`/`chat_found` nativos (não muda o comportamento atual).

> **Escopo:** a regra nova (§4 e a coexistência da §5) vale **só para números Cloud**. Números
> **Baileys não mudam** — seguem `is_saved`/`chat_found` e o comportamento atual (o "Evolution
> velho" fica como está). Só a **notificação ao vendedor** (§6.2) é unificada entre os dois canais.

**Mudanças de comportamento aceitas pelo dono** (só no lado Cloud):
1. Contato "salvo mas nunca conversado" ganha **uma** saudação do bot antes do humano assumir. Raro.
2. Cliente antigo que mandou msg e ninguém respondeu → o bot **responde agora** (recupera lead
   abandonado). Hoje talvez ignorasse.

## 5. Coexistência (o que habilita a regra)

**Onboarding** (o vendedor faz, ~minutos): login Facebook → "Conectar app Business existente" →
dados do negócio + número → verificação por SMS/ligação → **ler QR no app WhatsApp Business** →
**aprovar compartilhar até 6 meses de histórico** → conectar. Exige passar por um **provedor**
(BSP na Fase 1; embedded signup próprio na Fase 2) — não existe coexistência "na mão" pelo painel.

**Fatos verificados na Meta (2026-08-12):**
- `smb_message_echoes`: entrega as mensagens que a empresa manda **pelo app Business ou dispositivo
  linkado** (humano), com `to`, conteúdo, `timestamp`, `id`. **Exclui** mensagens da Cloud API →
  separação humano×bot **limpa** (tudo que aparece no echo é humano).
- History sync: **180 dias** de mensagens + **todos os contatos** com WhatsApp, via webhooks
  `history` e `smb_app_state_sync`, concluído em até 24h. Semeia "quem já teve conversa" (pré-bot =
  humano). **Depende de o vendedor APROVAR** o compartilhamento no onboarding; se recusar, cai no
  plano B (começa do zero, echo cobre daí pra frente — pior caso, uma saudação torta).

Fontes: Meta "Onboard WhatsApp Business app users"; Meta webhook reference `smb_message_echoes`;
360dialog "Coexistence webhooks".

## 6. Grupo de estoque → eliminado

O grupo era **só operacional** (a equipe tem outro grupo social), então **morre**. Suas duas funções
se realocam:

### 6.1 Cadastro de estoque (foto de veículo)
Sai do WhatsApp: o vendedor **sobe a foto no Portal/estoque**. O grupo é **aposentado** (§13), então
o `grupos_estoque`/`whatsapp_groups.py` e o download de mídia via Baileys (`vehicle_photo.py`) desse
fluxo deixam de ser exercitados. Atrito: **mudança de hábito** do vendedor.

### 6.2 Aviso "simulação pronta" (interno, pro vendedor)
Fluxo: o cliente conversa **só com o bot**; o bot coleta CPF/nascimento/dados de financiamento; o
sistema roda a simulação; **quando dá certo, o vendedor é avisado** (o cliente nunca recebe esse
aviso). Como o bot roda **no próprio número do vendedor**, **não dá** pra avisá-lo por WhatsApp no
mesmo número (não se manda pra si mesmo).

Solução: **notificação ao vendedor via canal plugável**, com o **Portal como fonte da verdade**
(guarda o resultado da simulação + o lead; o aviso externo é só "cutucada + link"):
- **Portal** (push/badge in-app): grátis, rico. Base.
- **SMS**: universal, sem template/opt-in/24h; ~centavos, texto puro + link (atenção a filtro de
  operadora no BR).
- **WhatsApp de um número central** (Utility ~R$0,04): rico, mas exige 1 número central + template.

Modelar como **abstração de notificação com canal configurável** (por vendedor, se quiser). **A
escolha do canal fica adiada** (§14) — trocar depois é barato.

> **Unificado entre canais:** como o grupo morre para **todos**, esse aviso é o **mesmo** para
> vendedor Baileys e vendedor Cloud — a notificação é **desacoplada do canal do WhatsApp** (é uma
> notificação interna do vendedor). Baileys e Cloud usam o mesmíssimo mecanismo.

### 6.3 Handoff (vendedor assume o cliente)
O vendedor responde o cliente **do próprio número** (o mesmo que o bot atende). No Cloud, isso gera
`smb_message_echoes` → marcamos "humano assumiu" → o bot recua. No Baileys, o comportamento atual.

## 7. n8n — dois pipelines (futuro de build)

Em vez de um n8n com `if` de payload, **dois workflows**:
- `n8n-baileys`: recebe o webhook do Evolution (payload Baileys atual, nó "Extrair1").
- `n8n-cloud`: recebe o webhook do **Cloud** (payload Meta + `smb_message_echoes` + `history`).

Os dois normalizam e caem no **mesmo** `chatbot-api` (`/webhook/mensagem`). Decisão de encanamento
do inbound Cloud (Evolution→n8n **ou** Meta→n8n direto) sai do **spike** (§10).

> **Achado da pesquisa (2026-08-12):** o CHANGELOG do Evolution **não menciona** coexistência /
> `smb_message_echoes` / `history`; existe um repo **dedicado** à coexistência Cloud à parte
> (`iragazzisrl/whatsapp-api-cloud-coexistence`); e a issue #807 mostra atrito no webhook Cloud do
> Evolution. → **Lean: Meta→n8n direto** para o inbound Cloud (Evolution fica no Baileys + envio
> Cloud opcional). O spike vira **confirmação** disso, não decisão do zero.

## 8. Onboarding & Tech Provider

- **Fase 1 (piloto):** onboarding do número do vendedor via **BSP que suporta coexistência** (ex.:
  360dialog, que dá acesso direto às credenciais Cloud pra plugar no Evolution/n8n). **Não** exige
  o Revy virar Tech Provider. Mais rápido, menor compromisso.
- **Fase 2 (self-serve):** pra o lojista/vendedor clicar "usar API oficial" **dentro do Revy** e
  conectar sozinho, o Revy precisa ser **Tech Provider** (criar app Meta, app review, aceitar
  Partner Solution, integrar o SDK de embedded signup) — ou seguir amarrado a um BSP. No modelo
  Tech Provider, **cada vendedor paga a Meta direto**; o Revy cobra só o software.

**Dificuldade de virar Tech Provider** (para dimensionar a Fase 2): não é difícil tecnicamente — é
mais **burocracia + espera**. Envolve criar o app Meta, passar por **verificação de negócio**
(documentos da empresa; dias a semanas, às vezes vai-e-volta), **app review** das permissões
`whatsapp_business_management`/`whatsapp_business_messaging` (Meta pode pedir ajustes) e integrar o
SDK de embedded signup (engenharia moderada). Timeline realista: **2–6 semanas**. **Sem taxa** da
Meta pelo programa (Tech Provider não tem credit line). Por isso a Fase 1 vai **via BSP** — usa a
infra já aprovada e não deixa a burocracia travar o piloto. Nota de nomenclatura: "começar como
BSP" = **usar** um BSP (ser cliente dele), não **virar** um BSP.

### 8.1 Estrutura de assets Meta por loja (e fricção do onboarding)

Cada loja (ex.: **Moto Center**) tem **um Meta Business** que já é dono da **conta de Facebook Ads**
que os vendedores usam. Os **números de WhatsApp dos vendedores entram sob esse mesmo Business** —
é o correto e ainda **favorece a atribuição CTWA** (anúncio → conversa no mesmo negócio). O login do
Facebook no onboarding é do **admin/dono do Business**, **não** do Facebook pessoal de cada vendedor.

> ⚠️ **Gotcha:** garantir que os números caiam **sob o Business da loja** (onde estão os ads), não
> sob um negócio novo que o Facebook cria se um vendedor logar com um perfil sem acesso. O **dono
> conduz** (ou concede papel de admin).

**Fricção separada (mata a sensação de "longo"):**
- **1× por loja (o dono):** login Facebook + setup/verificação do negócio + conexão com o BSP.
- **Por vendedor (curto):** abrir o WhatsApp Business e **ler um QR** + aprovar histórico — 2-3
  toques no celular dele (parecido com o QR que ele já lê no Baileys hoje). O vendedor **não** mexe
  no Facebook. Na **Fase 2** (Tech Provider), esse passo vira um fluxo único **dentro do Revy**.

## 9. Custos (Brasil, aprox. 2026)

| Mensagem | Quando | Custo |
|---|---|---|
| **Serviço** (resposta dentro de 24h) | conversa normal do bot | **Grátis** |
| Template **Utility** | proativo transacional (futuro: "simulação pronta" pro cliente) | ~R$0,04 |
| Template **Marketing** | promoção (não é nosso fluxo) | ~R$0,38 |
| SMS (aviso ao vendedor, se escolhido) | notificação interna | ~centavos (varia por provedor) |
| Licença da API | — | Grátis |

- Uso atual (bot reativo, texto, dentro de 24h) = **~R$0**.
- **Cada número Cloud tem seu próprio custo** — "ligar o Cloud" é **por vendedor**, não um clique
  único. Via BSP, some uma mensalidade + possível markup.

## 10. Spike (validação obrigatória antes de comprometer)

Antes de construir, provar na nossa stack:
1. Onboardar **um número de teste** em coexistência via BSP.
2. Plugar no canal `WHATSAPP-BUSINESS` do Evolution (token + phone_number_id).
3. Verificar o **inbound chegando no n8n**, incluindo **`smb_message_echoes`** e **`history`**.
4. **Decidir o encanamento:** se o Evolution **repassa** esses campos → Meta→Evolution→n8n; se
   **não** → apontar o webhook da Meta **direto pro n8n** na linha Cloud.

Critério de sucesso: mensagem do cliente, resposta do bot, e **resposta do humano pelo app**
aparecem corretamente atribuídas (bot vs humano) no destino.

## 11. Faseamento

**Fase 1 — Piloto (este spec vira plano):**
- Onboardar 1 número (o do vendedor bloqueado pelo passkey) em coexistência via BSP.
- Rodar o **spike** (§10) e fixar o encanamento do inbound Cloud.
- **Eliminar o grupo**: foto → Portal; aviso → notificação (canal a definir, começar pelo Portal).
- Implementar a **regra de roteamento nova** no lado Cloud (echo + seed do history), mantendo o
  Baileys intacto para os demais números.

**Fase 2 — Produto (spec seguinte):**
- **Toggle por número/loja** no Portal (`WhatsAppCanal.integracao = baileys | cloud`) + wizard de
  onboarding por canal (QR vs embedded signup).
- Revy como **Tech Provider** (ou BSP) para self-serve.
- **Dois n8n** (§7) como arquitetura oficial.
- **Proativo pro cliente + templates** (§9).
- Billing por vendedor.

## 12. Riscos & mitigações

| Risco | Mitigação |
|---|---|
| History sync depende de aprovação do vendedor | Se recusar, plano B (echo cobre daí pra frente; pior caso, 1 saudação torta). Pedir aprovação no onboarding. |
| Evolution pode não repassar `echo`/`history` | Spike decide; fallback Meta→n8n direto na linha Cloud. |
| Passkey em qualquer número que **fique** no Baileys | Baileys é só pra quem não tem Business; parear limpo 1x e não churnar QR. |
| Mudança de hábito (foto no Portal, sair do grupo) | Grupo é só operacional; comunicar a equipe; UI simples de upload. |
| Custo por vendedor no Cloud | Reativo é grátis; só proativo/SMS custa centavos; decisão de billing na Fase 2. |

## 13. Fora de escopo / não re-propor

- **Manter o grupo de estoque no WhatsApp** para números Cloud — Cloud API não faz grupo, nem com
  coexistência (sincroniza 1:1, não grupo). Decisão: eliminar o grupo.
- **Mesmo número em Baileys e Cloud ao mesmo tempo** — mutuamente exclusivos. Coexistência é
  **app Business + Cloud**, não Baileys + Cloud.
- **Baixar a versão do Baileys** para escapar do passkey — nenhuma versão resolve.
- **Reescrita de download de mídia no Cloud** — cliente só manda texto; foto de veículo vira upload
  no Portal.

## 14. Perguntas abertas / decisões adiadas

1. **Canal do aviso ao vendedor** (Portal / SMS / WhatsApp central) — adiado; começar pelo Portal,
   modelar como abstração plugável.
2. **Qual BSP** para o piloto (360dialog é o candidato por dar credenciais Cloud diretas).
3. **Aviso direcionado vs broadcast** — no modelo por-vendedor, cada bot avisa o próprio vendedor;
   confirmar se há caso de encaminhar a outro vendedor.
4. **Alcance exato do history sync** (contatos vs mensagens, quanto tempo) — confirmar no spike.
