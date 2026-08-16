# Chatbot API

Leads, conversas, handoff, roteamento WhatsApp e as tools que o n8n chama. Fonte única de
verdade de conversas e mensagens. Chama Motor e Estoque por HTTP. Banco e migrations
próprios.

Domínio em `app/servico.py`; bootstrap e rotas em `app/main.py`.

## Armadilhas — leia antes de mexer

- **Nunca casar lead ↔ `ctwa_auditoria` por telefone mascarado.** São `***` + 4 dígitos.
  Testada contra o dado real em 08/08, a heurística casou o lead de uma venda com o anúncio
  de **outro cliente** (DDI/DDD e 6 últimos dígitos diferentes). O aviso está repetido em
  `scripts/diagnose_ctwa_sinais.py`.
- **Comparação de `ctwa_source_type` exige `casefold`.** O valor real em produção é
  `FB_Ads`, com maiúsculas; comparar sensível a caixa classifica 205 leads errado.
- **`origem = meta_ctwa` só para quem veio de anúncio** — identificador de anúncio ou
  `ctwa_source_type` em `FAMILIA_ANUNCIO`. O sinal cru (`ctwa_clid`, `meta_ad_id`,
  `ctwa_source_type`) é gravado **sempre**, sem guard. O guard decide se escreve, nunca
  apaga.
- **`FAMILIA_ANUNCIO` é duplicação consciente** com `portal-gestao/app/loja/sales_overview.py`
  — produtos diferentes, sem import entre eles. Mudou aqui, muda lá.
- **`Conversa` é única por `(canal_id, telefone)`**, com `canal_id` nullable: o mesmo
  cliente tem uma linha **por canal**. Qualquer busca por telefone tem de varrer todas e
  ordenar `criada_em ASC` — `aplicar_touch_ctwa` só grava os campos `_first` enquanto
  estão nulos, então o toque mais antigo precisa chegar primeiro.
- **O bot só responde pela instância por onde a conversa entrou.** Canal
  `desconectado`/`inativo` deixa a conversa órfã; **nenhum PATCH de estado resolve** — é
  preciso reconectar o canal por QR (Ajustes na Revy Loja) ou migrar a conversa.
- **Bot mudo em produção mas o chatbot e `/healthz` de pé? A causa costuma estar no n8n, não
  aqui.** Volume do `n8n2037` cheio → o webhook responde **500** (Evolution entra em backoff);
  ou n8n reiniciado há < ~6 min → webhook **404** (Evolution **cancela** o retry no 404).
  Diagnóstico e correção na seção `n8n2037` de `deploy/fly/3vm/README.md`.
- **Nunca ecoar payload inválido nem desligar o rate limit do webhook** em produção
  (`CHATBOT_WEBHOOK_MAX_*`, `CHATBOT_WEBHOOK_RATE_LIMIT_*`; corpo limitado a 32 KiB).
- **O LLM não escolhe identidade autorizada.** `telefone_solicitante` e `Idempotency-Key`
  vêm do webhook real, não do modelo.
- **Não existe IA aqui dentro.** Nem Gemini, nem OpenAI, nem LangChain: o agente vive nos
  workflows do n8n, nos **dois** modos. Este produto expõe as ferramentas que ele chama.
  Foi confundir isso que deixou o Modo 2 sem bot por dois dias — havia rodízio, oferta e
  handoff, e ninguém respondendo o cliente.
- **Modo 2: `/webhook/cloud` devolve `mensagens[]`, e o n8n depende disso.** A assinatura da
  Meta só fecha sobre o **corpo cru**, então validar, deduplicar por `wamid` e persistir
  acontece aqui; o n8n recebe o evento já normalizado e segue no agente. Mudou o formato
  desse retorno? O bot do Modo 2 para. Ver
  [`docs/referencia-viva/design/2026-08-16-whatsapp-modo2-asbuilt.md`](../docs/referencia-viva/design/2026-08-16-whatsapp-modo2-asbuilt.md).
- **Falha no inbound Cloud não pode virar só log.** Já respondemos `200` à Meta (§6.1), então
  ela **não reentrega**: engolir a exceção perde o lead calado. O corpo cru vai para
  `cloud_evento_falho` e o worker `cloud_retry` reprocessa (teto de 5 tentativas).
- **O bot do Modo 2 pode responder a áudio inventado.** O Whisper alucina frase plausível em
  trecho mudo ou com ruído, e o VAD que a spec §5.10 exige **ainda não existe**. Áudio curto
  de rua pode virar texto que o cliente não disse — e o bot age em cima.

## Rodar e testar

```bash
cd chatbot-api
.venv/bin/python -m pytest -q
.venv/bin/python -m alembic upgrade head    # head: confira com `alembic heads`
```

Testes que cobrem os pontos sensíveis:

- `tests/test_whatsapp_outbound.py` — `send_text`: sucesso, classificação dos codes e
  **sanitização do log** (CPF/nascimento redigidos, apikey nunca vaza).
- `tests/test_solicitacoes_simulacao.py` — pedido de simulação humana: maioridade,
  CNH objetiva (sim/não), dedupe por telefone/CPF, qualifica lead, pausa bot,
  enfileira/reenvia alerta, reprocessa dead-letters.
- `tests/test_whatsapp_provider_evolution.py` — provisionamento/estado das instâncias
  (connect/QR, status, logout) sem vazar URL/apikey.
- `tests/test_fluxo_modo2_ponta_a_ponta.py` — atravessa webhook → gatilho → oferta → clique
  → trava. Existe porque os testes unitários passavam com o produto morto: cada função tinha
  teste chamando ela direto e ninguém percorria "chega mensagem → o rodízio começa".
- `tests/test_cloud_retry.py` — o "processar depois" da §6.1, incluindo o teto de tentativas.

## Rotas do Modo 2 que o `n8n-cloud` chama

O agente do Modo 2 vive no `n8n/workflow-cloud.json` (gerado — ver
`n8n/fork_cloud_workflow.py`). Estas são as portas que ele usa aqui:

| Rota | Papel |
|---|---|
| `POST /webhook/cloud` | inbound da Meta; confere assinatura no corpo cru, deduplica por `wamid`, persiste e **devolve `mensagens[]`** para o agente seguir |
| `GET /webhook/cloud` | verificação do webhook da Meta (`hub.challenge`) |
| `POST /v1/operacao/responder` | saída do bot. Existe porque o token do Graph **não pode entrar no workflow** (spec §6.2) |
| `POST /v1/operacao/handoff-humano` | 3º gatilho da §5.2. Sem CPF/nascimento de propósito — "pediu humano" pode vir antes da simulação |

Workers do Modo 2 (`app/modo2_workers.py`, todos atrás de `MODO2_ENABLED`): `rodizio`
(expira oferta), `followup` (30 min + 1 h) e `cloud_retry` (reprocessa inbound que falhou).

## Gates antes do alerta de simulação

`POST /v1/operacao/solicitacoes-simulacao-humana` só envia ao grupo depois de, nesta ordem:

1. **Nascimento válido + maioridade** (`>= 18` em `America/Sao_Paulo`). Menor retorna
   HTTP 200 com `bloqueado=true`, `motivo_bloqueio=menor_de_idade` e a mensagem fixa ao
   cliente — sem lead/pausa/alerta.
2. **CNH objetiva** (`sim` ou `não`). Resposta vaga → `motivo_bloqueio=cnh_nao_confirmada`
   e `faltando: ["cnh"]` (sem envio). **Não ter CNH não bloqueia**: `não`/`não tenho`
   é confirmação válida e a solicitação segue para o grupo com `CNH: NÃO`.
3. **Dedupe**: mesma `Idempotency-Key`, ou solicitação recente do mesmo telefone/CPF
   (janela `CHATBOT_SIMULACAO_DEDUPE_HORAS`, default 48h) → reutiliza o atendimento e
   **não** reenvia o alerta.

Todo bloqueio grava `motivo_bloqueio` no log (`simulação bloqueada motivo=...`) e no body.

## Alerta de simulação ao grupo de estoque

Código F0–F3 pronto (2026-08-13): tabela `notificacoes_operacionais`, worker
`notificacoes_outbox_job` no lifespan, dead-letter após `CHATBOT_NOTIF_MAX_ATTEMPTS`.
Residual é smoke do workflow, não implementação.

Quando um cliente pede financiamento (após os gates), o bot pausa a conversa e envia
**"🚨 precisa de simulação humana"** ao grupo de estoque (`solicitacoes_simulacao.py`). Se
esse envio falha, o cliente fica preso em `handoff` **e ninguém fica sabendo** — o sintoma
é "o bot parou de responder" para aquele cliente.

O envio grava em `notificacoes_operacionais` (outbox): `status`, `attempts`,
`last_error_code`, `next_attempt_at`. O drenador (`processar_pendentes`) reprocessa
`pending`/`failed` com `attempts < MAX_TENTATIVAS_ALERTA`; ao esgotar vira **dead-letter**
(`next_attempt_at = NULL`) e **não reprocessa mais**.

| `last_error_code` | Significa | Ação |
|---|---|---|
| `evolution_group_forbidden` | instância **não é participante** do grupo | readicionar o número ativo ao grupo |
| `evolution_target_not_found` | grupo/JID não existe para essa instância | corrigir o `destino_jid`/grupo da loja |
| `evolution_send_failed` (HTTP 5xx) | erro transitório do Evolution | normalmente resolve no retry |
| `evolution_unreachable` | não conectou no Evolution | rede/URL do Evolution |
| `grupo_estoque_nao_configurado` | loja sem grupo configurado | configurar o grupo de estoque |

Diagnóstico:

```bash
fly logs -a app2037 | rg "sendText falhou|alerta simulação"    # corpo já sanitizado
```

```sql
SELECT loja_id, status, attempts, last_error_code, next_attempt_at, created_at
FROM notificacoes_operacionais
WHERE tipo = 'simulacao_humana' AND status <> 'sent'
ORDER BY created_at DESC;
```

Para reprocessar **um** dead-letter, zere `attempts`, ponha `next_attempt_at = NULL` e
`status = 'pending'` no id escolhido; o worker (`notificacoes_outbox_job`, ligado no
lifespan) reenvia no ciclo seguinte. ⚠️ Isso **reenvia o alerta real ao grupo**, com a PII
daquele cliente — prefira o registro mais recente.

---

Histórico (origem CTWA honesta, tracking pendente multi-canal, desmascaramento do erro do
Evolution): [`../docs/nao-plano/historico/chatbot.md`](../docs/nao-plano/historico/chatbot.md).
