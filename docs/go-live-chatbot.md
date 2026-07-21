# Runbook de go-live do Chatbot WhatsApp

> **Ambiente canônico:** lab Fly.io (`crm-419` / `gru`), não o compose local antigo.
> Estado típico: bot **NÃO no ar de propósito** até o passo final (ativar workflow no n8n).
> Nada neste doc liga o bot sozinho — o toggle Active é manual.
>
> Estado vivo da suíte: `docs/contexto-compacto.md`. Planos: `docs/plans/README.md`.
> Código: branch **`main`** (não use branches `feat/*` antigas citadas em docs legados).

## 0. O que já está pronto (não refazer)

- Gate "somente não salvos" **fail-closed** (`isSaved === false`) no runtime do n8n. ✅
- Chatbot: webhook com auth opt-in (`CHATBOT_WEBHOOK_TOKEN` + header `X-Webhook-Token`) e
  **dedupe** no banco (`mensagens(loja_id, provider_message_id)`, migration `0003`). ✅
- CPF **mascarado** no texto das mensagens. ✅
- Consentimento **não é exigido** (decisão de produto). ✅
- Portal: Leads, Conversas + handoff, Simulação. ✅
- **E3 auto-pausa:** `from_me` do atendente → `bot_ativo=false`; saída do bot com
  `origem_bot=true` + mesmo `provider_message_id` não pausa. ✅
- **E5** cadastro de veículo por WA (números autorizados). ✅
- Motor: **Santander e Fontecred reais** (`real: true`); mock só para provedores sem driver real.
  Ver tabela de campos em `docs/plans/2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

## 1. Apps e URLs (lab Fly)

| Papel | App | URL / nota |
|---|---|---|
| Chatbot API | `chatbot2037` | privado / flycast (n8n chama internamente) |
| n8n | `n8n2037` | `https://n8n2037.fly.dev` |
| Evolution | `evolution2037` | `https://evolution2037.fly.dev/manager` |
| Portal | `portal2037` | `https://portal2037.fly.dev` |
| Motor | `motor2037` | simulações reais (Santander/Fontecred) |
| Estoque | `estoque2037` | fonte de verdade dos veículos |

Subir a suíte (se estiver parada):

```bash
bash deploy/fly/up-all.sh
```

Segredos só em `deploy/fly/.env.production.local` (ignorado). Nunca commitar tokens.

**Local (opcional):** `deploy/chatbot-standalone/docker-compose.yml` ainda existe para dev isolado;
go-live da loja no lab = Fly + n8n2037.

## 2. Segurança do canal (webhook)

1. Segredo forte (se ainda não houver no Fly):

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Secret no app Chatbot (`CHATBOT_WEBHOOK_TOKEN`) **e** header `X-Webhook-Token` nos nós n8n
   que chamam `POST /webhook/mensagem` (entrada e saída do bot). Faça os dois juntos:
   token no Chatbot sem header no n8n = 401 e bot “morto”.
3. Token de API do Chatbot (`Authorization: Bearer …`) nos tools do workflow — distinto do
   webhook token quando configurado assim no lab.
4. O Chatbot rejeita payloads acima de 32 KiB, normaliza/valida telefone e aplica rate limit
   configurável antes da autenticação. Ajuste `CHATBOT_WEBHOOK_MAX_*` e
   `CHATBOT_WEBHOOK_RATE_LIMIT_*` somente se o volume real exigir; nunca use rate limit zero em
   produção.
5. Áudio é baixado pela Chatbot API via Evolution, nunca pelo modelo. Configure
   `CHATBOT_AUDIO_EVOLUTION_URL` + `CHATBOT_AUDIO_EVOLUTION_API_KEY`; mantenha o provider `none`
   até homologar um endpoint HTTP de transcrição. O binário é temporário e apagado após a chamada.

## 3. Migrations Chatbot

No lab, migrations devem estar em head. Se acabou de deployar código novo:

```bash
# exemplo — ajustar ao processo atual do app chatbot2037
fly ssh console -a chatbot2037 -C "cd /srv && alembic upgrade head"
```

(Confirme o working dir da imagem se o entrypoint já roda Alembic no boot.)

## 4. n8n (lab)

- UI: `https://n8n2037.fly.dev`
- Workflow de produção esperado: **WhatsApp IA - Somente Nao Salvos** (ou id local
  `wAiNaoSalvos0001` / nome equivalente no volume).
- Webhook de produção: `/webhook/whatsapp-ai` (confirmar path no workflow ativo).
- Credencial **Gemini** configurada e testada no n8n (sem ela a mensagem chega e a IA não responde).
- Nós HTTP Evolution: chave da instância nos nós do tipo
  “Consultar contato” / “Responder WhatsApp” (nomes podem variar com sufixo `1`).
- Placeholders `__INSTANCE__`, `__EVOLUTION_KEY__`, `__CHATBOT_TOKEN__` e
  `__CHATBOT_WEBHOOK_TOKEN__` só no **runtime** — nunca commitar valores reais no JSON em `n8n/`.
- O template versionado não possui bypass por telefone: os gates de handoff, deduplicação e
  contato não salvo valem para todos os números.

### 4.1 Tools do workflow → Chatbot API

| Tool n8n (nome típico) | Endpoint | Uso |
|---|---|---|
| `consultar_estoque1` | `GET /v1/estoque/buscar?termo=` | busca marca/modelo |
| `consultar_por_placa1` | `GET /v1/estoque/por-placa/{placa}` | unidade pela placa |
| `simular1` | `POST /v1/simulacoes/solicitar` + handoff | enfileira com `placa` + `telefone` + `cpf` + `nascimento` + `entrada`; não espera o resultado e pausa o bot |
| `registrar_lead1` | `POST /v1/leads` | telefone + interesse (+ nome opcional) |
| `registrar_consentimento1` | `POST /v1/consentimentos` | opcional — não bloqueia |
| `solicitar_handoff1` | `PATCH /v1/conversas/{tel}/estado` | `bot_ativo: false` |
| `cadastrar_veiculo1` | `POST /v1/operacao/veiculos` | E5: números autorizados |

Chatbot precisa de `ESTOQUE_API_URL` + `ESTOQUE_API_TOKEN` (e Motor, se a simulação for real)
nos secrets do Fly. Sem Estoque, `por-placa` e cadastro E5 falham ou esvaziam.

Autorizar telefone de equipe (E5), via CLI no container do Chatbot quando necessário:

```bash
python -m app.cli autorizar-numero --slug <loja> --telefone 5511... --papel dono
```

## 5. Evolution

- Instância `loja1` (ou nome do lab) = **open/connected** no Manager.
- WhatsApp de lab documentado no contexto (não espalhar em commits novos).
- **fromMe / E3:** a instância deve emitir mensagens com `key.fromMe=true`. No webhook
  Evolution → n8n, **não filtrar** `fromMe` no provedor.
- Contrato n8n ↔ Chatbot:
  1. Inbound: `{ instance, telefone, texto, provider_message_id, from_me }`
  2. Saída do bot (após `sendText`): mesmo webhook com
     `from_me: true`, `origem_bot: true`, `provider_message_id` do retorno Evolution
  3. Gate: se `fromMe` ou `duplicada` ou `bot_ativo !== true` → não chamar o agente

## 6. Portal e catálogo (junto com o go-live)

- Portal com `CHATBOT_API_TOKEN`, `ESTOQUE_API_TOKEN`, `MOTOR_URL` + `MOTOR_TOKEN`.
- Publicar veículos no catálogo se a demo incluir vitrine (`Publicar no catálogo`).
- Senha do dono real (não deixar default de lab se for uso externo).

## 7. Decisões de produto ANTES de ir ao ar

- **Simulação:** o bot nunca entrega cotação, estimativa, parcelas, taxas ou bancos ao cliente.
  Ele solicita a simulação internamente, pausa a conversa e informa que um vendedor trará o
  resultado. Credenciais e detalhes bancários permanecem no Motor/Portal.
- Campos por banco (placa, celular, entrada…) → mapa de reconhecimento; o n8n/Chatbot deve
  coletar o que o provedor escolhido exige.
- CPF mascarado; sem gate de consentimento (decisão tomada). Retenção/expurgo LGPD ainda é
  backlog administrativo (#2A), sem controle de exclusão pelo cliente.

## 8. Validação (número de teste antes de soltar geral)

1. Contato **SALVO** → bot **não** responde.
2. Contato **NÃO salvo** → bot responde (IA completa, não só eco Evolution).
3. Fluxo: estoque (termo ou **placa**) → lead → solicitação de simulação → mensagem de espera →
   `bot_ativo=false`; conferir o resultado somente no Portal/Registros.
4. Handoff E3: 1 msg pelo celular do lojista → `bot_ativo=false`. Mensagem do próprio bot não pausa.
5. Portal: conversa em `/app/conversas`, handoff refletido.

## 9. Go-live

- Ativar o workflow no n8n (toggle **Active**).
- Acompanhar as primeiras conversas (n8n executions + logs Chatbot).

## 10. Rollback imediato

- Desativar o workflow no n8n (Active off). O bot para de responder na hora.
- Opcional: `bash deploy/fly/down-all.sh` só se for desligar a suíte inteira (pede confirmação;
  **não** rodar sem o dono pedir).
