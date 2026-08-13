# Runbook de go-live do Chatbot WhatsApp

> **Ambiente canônico:** lab Fly.io (`crm-419` / `gru`), stack **3-VM** (`deploy/fly/3vm/`).
> **Estado em 2026-07-24:** 3-VM **no ar**; estoque restrito ao grupo escolhido no Portal;
> workflow `wAiNaoSalvos0001` publicado com 31 nós. Próximo: selecionar o grupo e fazer o E2E.
> Detalhe: `docs/referencia-viva/planos/2026-07-22-plano-menu-estoque-wa-e-fotos-fix.md`.
>
> Estado vivo da suíte: `docs/referencia-viva/contexto-compacto.md`. Planos: `docs/nao-plano/historico/README.md`.
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
- **E5** cadastro de veículo por WA somente no grupo de estoque escolhido. ✅
- **E6** foto automática WhatsApp → Estoque → Catálogo, com sessão curta para lote. ✅
- Motor: **Santander e Fontecred reais** (`real: true`); mock só para provedores sem driver real.
  Ver tabela de campos em `docs/referencia-viva/planos/2026-07-13-plano1a-task12-bancos-reconhecimento.md`.

## 1. Apps e URLs (lab Fly)

| Papel | App | URL / nota |
|---|---|---|
| App bundle (chatbot+estoque+portal+catálogo+n8n* ) | `app2037` | suíte no supervisord; n8n pode ser app separado |
| n8n | `n8n2037` | `https://n8n2037.fly.dev` |
| Evolution | `evolution2037` | `https://evolution2037.fly.dev` (mídia do chatbot usa HTTPS, não só flycast) |
| Postgres | `suite-pg` | always-on |
| Motor API / worker | `motor2037` (+ workers on-demand) | simulações reais |
| Portal / Catálogo | hosts no bundle `app2037` | ver `deploy/fly/3vm/README.md` |

\* Layout exato: `deploy/fly/3vm/README.md`. Legado monólito `chatbot2037`/`estoque2037` só se ainda existir no org.

Subir a suíte (se estiver parada):

```bash
bash deploy/fly/up-all.sh
```

Segredos só em `deploy/fly/.env.production.local` (ignorado). Nunca commitar tokens.

Em uma instalação nova, crie uma vez o volume da app Estoque; não recrie nem apague em deploys
seguintes. No lab `estoque2037`, ele já existe, está anexado e criptografado:

```bash
fly volumes create estoque_media --app estoque2037 --region gru --size 1
```

O `estoque-api/fly.toml` já monta esse volume em `/data`, publica somente a URL HTTPS
`/public/v1/media` e restringe as URLs persistidas ao host `estoque2037.fly.dev`.

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
   `CHATBOT_AUDIO_EVOLUTION_API_KEY` como secret; a URL Flycast já está no `fly.toml`. Mantenha o
   provider `none` até homologar um endpoint HTTP de transcrição. O binário é temporário e apagado
   após a chamada.
6. Foto de estoque também é baixada server-side. No lab, `CHATBOT_IMAGE_EVOLUTION_URL` já aponta
   para a Evolution configurada e a chave reutiliza o secret de áudio; o JID do grupo é validado
   antes do download. Privado e outros grupos são ignorados sem resposta. O Estoque precisa de
   `ESTOQUE_MEDIA_PUBLIC_BASE_URL=https://<domínio>/public/v1/media`, volume persistente montado em
   `ESTOQUE_MEDIA_STORAGE_DIR` e backup operacional desse volume.

## 3. Migrations Chatbot

No lab, migrations devem estar em head. Se acabou de deployar código novo:

```bash
# exemplo — ajustar ao processo atual do app chatbot2037
fly ssh console -a chatbot2037 -C "cd /srv && alembic upgrade head"
```

(Confirme o working dir da imagem se o entrypoint já roda Alembic no boot.)

## 4. n8n (lab)

- UI: `https://n8n2037.fly.dev`
- Estado verificado em 24/07/2026: health OK; workflow `wAiNaoSalvos0001` publicado com
  31 nós. O backup consistente foi criado no volume antes da atualização. Para futuras atualizações,
  usar primeiro o preview de
  `n8n/update_live_workflow.js`; no Fly, usar
  `--chatbot-base-url=https://app2037.fly.dev` e
  `--evolution-base-url=https://evolution2037.fly.dev`. `--apply` é uma ação operacional
  explícita. Sem esses parâmetros, o script mantém os nomes do compose local.
- **Não usar** `app2037.flycast:8080` nem `evolution2037.flycast:8080` nos nós n8n.
  Em 04/08/2026 essas URLs causaram, respectivamente, `ECONNRESET` e `ENOTFOUND`,
  interrompendo o workflow antes da gravação da mensagem. O gerador
  `prepare-workflow.ps1` já usa os hosts HTTPS corretos por padrão.
- Antes de importar, confirmar no nó `Extrair1` que o bloqueio de replay continua
  presente: mensagens sem timestamp válido, com mais de 300 segundos ou mais de
  120 segundos no futuro devem retornar `[]` antes de qualquer gravação/resposta.
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
| `cadastrar_veiculo1` | `POST /v1/operacao/veiculos` | E5: exige o `grupo_jid` escolhido; cria publicado |
| `Salvar foto no estoque1` | `POST /webhook/operacao/veiculos/foto` | E6: exige grupo escolhido; binário fica server-side |

Chatbot precisa de `ESTOQUE_API_URL` + `ESTOQUE_API_TOKEN` (e Motor, se a simulação for real)
nos secrets do Fly. Sem Estoque, `por-placa` e cadastro E5 falham ou esvaziam.

Configurar o grupo de estoque:

1. Entre no Portal como dono/gerente.
2. Abra **Configurações → Grupo do estoque**.
3. Escolha um grupo da instância Evolution e salve.
4. Envie `menu` no grupo escolhido.

Os números da equipe são legado/identificação. Depois de selecionar um grupo, não concedem acesso
ao menu em conversa privada.

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
- Veículos cadastrados pelo WhatsApp já entram publicados; confirme que a URL pública de mídia
  aponta para o Estoque e que o Catálogo consegue acessá-la.
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
6. Equipe autorizada: enviar os dados do veículo por texto; confirmar `publicado=true`. Enviar
   várias JPEG/PNG/WebP sem repetir a placa durante a sessão; para veículo antigo, colocar a placa
   na primeira foto. Conferir a galeria no Catálogo. Reprocessar a mensagem de cadastro e confirmar
   o mesmo `veiculo_id`; reprocessar uma foto e confirmar que não duplica. Repetir com número não
   autorizado e confirmar que nada foi baixado ou gravado.
7. Estoque: executar `python -m app.cli limpar-midias-orfas` e conferir a prévia. O worker aplica
   automaticamente a limpeza a cada seis horas, com carência de uma hora; conferir o backup e os
   logs antes de alterar esses limites.

## 9. Go-live

- Ao religar o n8n, o workflow já deve carregar **Active**; não repetir importação.
- Acompanhar as primeiras conversas (n8n executions + logs Chatbot).

## 10. Rollback imediato

- Desativar o workflow no n8n (Active off). O bot para de responder na hora.
- Opcional: `bash deploy/fly/down-all.sh` só se for desligar a suíte inteira (pede confirmação;
  **não** rodar sem o dono pedir).
