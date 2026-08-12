# WhatsApp Híbrido — Spike de Coexistência (de-risking) — Implementation Plan

> **For agentic workers:** este é um **spike de de-risking**, não um build TDD. Boa parte dos passos
> é **operação externa manual** (contratar BSP, onboardar um número real, ler QR num celular) que
> só o dono/operador consegue fazer — não é executável por subagente autônomo. Execute-o de forma
> **colaborativa**: o operador faz os passos externos; o agente ajuda na config do Evolution/n8n e
> na observação dos webhooks. Cada tarefa termina num **resultado verificável** (evidência), não num
> teste vermelho/verde. Steps usam checkbox (`- [ ]`) para acompanhamento.

**Goal:** Provar, com **um número de teste**, que a coexistência (WhatsApp Business + Cloud API)
funciona na nossa stack — em especial que os eventos **`smb_message_echoes`** e **`history`** chegam
de forma **utilizável** — e **decidir o encanamento do inbound Cloud** (Evolution repassa vs
Meta→n8n direto), **antes** de comprometer o build.

**Architecture:** onboardar 1 número de teste em coexistência via BSP → obter credenciais Cloud
(phone_number_id + token) → ligar no canal `WHATSAPP-BUSINESS` do Evolution (ou apontar o webhook da
Meta direto pro n8n) → mandar mensagens de teste e **observar** o inbound, incluindo echo e history →
decidir o encanamento e registrar os achados no design.

**Tech Stack:** Evolution API v2 (integração `WHATSAPP-BUSINESS`), n8n, um **BSP com coexistência**
(candidato: 360dialog, por dar credenciais Cloud diretas), Meta WhatsApp Cloud API, um número
WhatsApp Business de teste + um celular, e um segundo número ("cliente de teste") para simular lead.

## Global Constraints

- **Regra nova só no Cloud.** Nada neste spike pode alterar o comportamento dos números **Baileys**
  existentes. Não mexer nas instâncias em produção (ex.: `f447`).
- **Não imprimir segredos** nem números de telefone/JID completos em logs ou evidências (mascarar).
- **Números sob o Business da loja** (onde estão os ads), não sob um negócio novo criado por engano.
- **Fly:** não recriar apps monolíticos, não destruir volumes, não deployar sem conferir
  `deploy/fly/3vm/README.md`. Instância de teste é **efêmera** e separada.
- Evidência de sucesso = mensagens fluindo + atribuição humano×bot correta, **sem** vazar segredo.

---

### Task 1: Escolher e contratar o BSP com coexistência

**Files:** nenhum (setup externo). Registrar a escolha em
`docs/superpowers/specs/2026-08-12-whatsapp-hibrido-coexistencia-design.md` (§14, item "Qual BSP").

- [ ] **Step 1: Avaliar candidatos.** Confirmar em cada BSP: (a) suporta **coexistência**
  (onboarding de app Business existente); (b) entrega **credenciais Cloud diretas**
  (`phone_number_id` + token permanente) pra plugar no **nosso** Evolution, em vez de prender tudo à
  plataforma dele; (c) preço (mensalidade + markup por mensagem). Candidato principal: **360dialog**.
- [ ] **Step 2: Criar conta no BSP escolhido** e vincular ao **Meta Business da loja de teste**
  (onde ficam/ficarão os ads), com o **dono/admin** logando no Facebook — não um perfil pessoal
  aleatório (ver §8.1 do design).
- [ ] **Verificação:** no painel do BSP existe a opção "conectar app Business existente / coexistence"
  e há um caminho documentado pra obter `phone_number_id` + token. Registrar o BSP escolhido na §14.

### Task 2: Preparar o número de teste e o "cliente de teste"

**Files:** nenhum (setup externo).

- [ ] **Step 1:** Separar um **número WhatsApp Business de teste** (chip/eSIM num celular com o app
  WhatsApp Business instalado e algumas conversas/contatos, pra o history sync ter o que sincronizar).
- [ ] **Step 2:** Separar um **segundo número** ("cliente de teste") num outro aparelho, pra simular
  um lead mandando mensagem.
- [ ] **Verificação:** os dois números existem, o de teste está no app Business com histórico, e você
  consegue trocar mensagem manual entre eles.

### Task 3: Onboardar o número de teste em coexistência (via BSP)

**Files:** nenhum (fluxo externo Meta/BSP).

- [ ] **Step 1:** Rodar o fluxo de coexistência do BSP: login Facebook (admin do Business) →
  "conectar app Business existente" → dados do negócio + número → verificar número → **ler o QR no
  app WhatsApp Business** do celular de teste → **aprovar compartilhar até 6 meses de histórico**.
- [ ] **Step 2:** Confirmar no painel do BSP/Meta que o número ficou **`is_on_biz_app = true`** e
  **`platform_type = CLOUD_API`** (coexistência ativa), sob o Business da loja de teste.
- [ ] **Verificação:** número aparece **conectado** em coexistência; você tem em mãos o
  `phone_number_id` e um **token** de acesso. (Guardar em `.secrets.local`, nunca commitar.)

### Task 4: Ligar o número no canal `WHATSAPP-BUSINESS` do Evolution

**Files:**
- Referência: `chatbot-api/app/whatsapp_provider.py:219` (`integration`) e o payload de
  `/instance/create`.
- Referência: `deploy/fly/3vm/set-evolution-webhook.ps1` (padrão de config de webhook).
- Referência: `deploy/fly/evolution/fly.toml` (Evolution de teste).

- [ ] **Step 1:** Numa **instância de teste efêmera** do Evolution, criar a instância com
  `integration: "WHATSAPP-BUSINESS"`, passando `phone_number_id` + token (não é `WHATSAPP-BAILEYS`,
  não tem QR). Seguir a doc do Evolution para o canal Cloud.
- [ ] **Step 2:** Configurar o **webhook da Meta** (pelo painel do BSP/Meta) apontando para o
  endpoint do **Evolution** de teste; assinar os campos `messages`, **`smb_message_echoes`** e
  **`history`**.
- [ ] **Verificação:** a instância fica com estado **`open`/conectada** e o `fetchInstances` mostra
  o número Cloud. Nenhuma instância Baileys de produção foi tocada.

### Task 5: Validar o inbound básico (cliente → bot) chegando ao destino

**Files:**
- Referência: `n8n/workflow-ai-nao-salvos.json` (nó "Extrair1"); endpoint do chatbot
  `POST /webhook/mensagem` (`chatbot-api/app/main.py`).

- [ ] **Step 1:** Do "cliente de teste", mandar uma mensagem de texto para o número de teste.
- [ ] **Step 2:** Observar o caminho: Meta → (Evolution) → n8n. Capturar o **payload cru** do evento
  `messages` (mascarando telefones).
- [ ] **Verificação:** a mensagem chega ao n8n de forma **parseável** (dá pra extrair
  `telefone`, `texto`, `provider_message_id = wamid...`). Anotar as diferenças de shape vs o payload
  Baileys atual (subsídio pro futuro `n8n-cloud`).

### Task 6: Validar o `smb_message_echoes` — o teste CRÍTICO

**Files:** nenhum (observação de webhook).

- [ ] **Step 1:** Do **app WhatsApp Business** do número de teste (simulando o vendedor humano),
  responder o "cliente de teste".
- [ ] **Step 2:** Confirmar que chega um evento **`smb_message_echoes`** com `to` (o cliente),
  conteúdo, `timestamp`, `id`.
- [ ] **Step 3:** Confirmar a **separação de autoria**: mensagens enviadas pela **Cloud API** (bot)
  **não** aparecem no `smb_message_echoes`; só as do app/dispositivo linkado (humano). Ou seja, tudo
  que chega no echo é **humano**.
- [ ] **Verificação (gate do spike):** conseguimos, a partir dos eventos, dizer com segurança
  **"um humano falou nesta conversa"** vs "só o bot falou". Se **sim**, a regra da §4 é implementável.
  Se **não** (echo não chega ou não é distinguível), **parar** e reavaliar antes de qualquer build.

### Task 7: Validar o `history` sync (semente do passado)

**Files:** nenhum (observação de webhook).

- [ ] **Step 1:** Após o onboarding (Task 3), confirmar que chegaram os webhooks **`history`** e
  **`smb_app_state_sync`** (mensagens dos últimos ~180 dias + contatos), dentro de ~24h.
- [ ] **Step 2:** Verificar que dá pra derivar, do history, **quem já teve conversa** (mensagens
  enviadas pela empresa no passado = humano) — a semente da regra da §4/§5.
- [ ] **Verificação:** temos entradas de history utilizáveis pra semear "conhecidos/já-conversou".
  Registrar o **alcance real** (contatos vs mensagens, período) na §14 do design (pergunta aberta 4).

### Task 8: Decidir o encanamento do inbound Cloud

**Files:** decisão registrada em
`docs/superpowers/specs/2026-08-12-whatsapp-hibrido-coexistencia-design.md` (§7 e §10).

- [ ] **Step 1:** Com base nas Tasks 5–7, responder: **o Evolution repassa** `messages` +
  `smb_message_echoes` + `history` de forma utilizável?
- [ ] **Step 2:** Se **sim** → encanamento **Meta → Evolution → n8n** (mantém o Evolution como
  gateway). Se **não** → apontar o webhook da Meta **direto pro n8n** na linha Cloud (Evolution só
  para envio).
- [ ] **Verificação:** decisão escrita, com a evidência que a sustenta, na §7/§10 do design.

### Task 9: Registrar achados e destravar os planos de código

**Files:**
- Modify: `docs/superpowers/specs/2026-08-12-whatsapp-hibrido-coexistencia-design.md` (§7, §10, §14).
- Create (opcional): `docs/superpowers/specs/2026-08-12-whatsapp-hibrido-coexistencia-README.md`
  com o resumo dos achados do spike (padrão dos outros specs com README).

- [ ] **Step 1:** Escrever os achados: encanamento decidido, atribuição humano×bot confirmada,
  alcance do history sync, e quaisquer *gotchas* (ex.: campos que o Evolution não repassa).
- [ ] **Step 2:** Fechar as perguntas abertas da §14 que o spike resolveu (BSP escolhido, alcance do
  history, encanamento).
- [ ] **Step 3: Commit.**

```bash
git add docs/superpowers/
git commit -m "docs(whatsapp): achados do spike de coexistência + encanamento decidido"
```

- [ ] **Verificação:** o design está atualizado o suficiente pra escrever os **planos de código**
  (notificação unificada, foto→Portal, regra Cloud + pipeline n8n) sem chute de encanamento.

---

## Self-Review (cobertura vs §10 do spec)

- §10 pede: onboardar número de teste (Task 3) → plugar no `WHATSAPP-BUSINESS` do Evolution
  (Task 4) → verificar inbound incluindo echo/history (Tasks 5–7) → decidir encanamento (Task 8).
  **Coberto.**
- Critério de sucesso do §10 ("mensagem do cliente, resposta do bot, e resposta do humano pelo app
  aparecem corretamente atribuídas") → Tasks 5, 6 (e envio pelo bot como controle). **Coberto.**
- Sem placeholders: cada task tem ação concreta + verificação. As partes "externas" são inerentes ao
  spike (não há como TDD-ar contratar BSP ou ler QR).

## O que vem depois (planos de código, gated no spike)

1. **Notificação unificada ao vendedor** (Portal-first, canal plugável) — §6.2. Quase independente
   do spike; pode começar em paralelo.
2. **Foto de estoque → upload no Portal** — §6.1. Independente.
3. **Regra de roteamento Cloud ("humano já falou") + pipeline `n8n-cloud`** — §4/§5/§7. **Depende**
   do encanamento decidido na Task 8.
4. **Fase 2:** toggle por número (`WhatsAppCanal.integracao`), embedded signup, Tech Provider — §11.
