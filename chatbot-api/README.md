# Chatbot API

Leads, conversas, handoff, roteamento WhatsApp e tools do n8n. Chama Motor e Estoque por HTTP.
Domínio em `app/servico.py`; bootstrap/rotas em `app/main.py`. Banco/migrations próprios.

```bash
cd chatbot-api
.venv/bin/python -m pytest -q          # suíte completa
.venv/bin/python -m alembic upgrade head
```

---

## Diagnóstico: alerta de simulação ao grupo de estoque falhando

Quando um cliente pede financiamento, o bot pausa a conversa e envia o alerta
**"🚨 precisa de simulação humana"** ao grupo de estoque (`solicitacoes_simulacao.py`).
Se esse envio falha, o cliente fica preso em `handoff` **e ninguém fica sabendo** — o
sintoma é "o bot parou de responder" para aquele cliente.

O envio grava o resultado em `notificacoes_operacionais` (outbox): `status`, `attempts`,
`last_error_code`, `next_attempt_at`. O drenador (`processar_pendentes`) reprocessa
`pending`/`failed` com `attempts < MAX_TENTATIVAS_ALERTA`; ao esgotar, o registro vira
**dead-letter** (`next_attempt_at = NULL`) e **não reprocessa mais**.

### Erro do Evolution desmascarado

Antes, um `sendText` que falhava só guardava o code genérico `evolution_send_failed` e
descartava o corpo real do Evolution — cegava o diagnóstico. Agora
`app/whatsapp_outbound.py` **classifica** a falha num code durável e **loga o corpo real
sanitizado** (apikey removida; dígitos longos — CPF/telefone/nascimento — redigidos como
`[num]`, pois o texto do alerta contém PII e o provedor pode ecoá-lo). Nenhum corpo bruto
é persistido.

Códigos e ação correspondente:

| `last_error_code` / log | Significa | Ação |
|---|---|---|
| `evolution_group_forbidden` | instância **não é participante** do grupo | readicionar o número ativo ao grupo de estoque no WhatsApp |
| `evolution_target_not_found` | grupo/JID não existe para essa instância | corrigir o `destino_jid`/grupo da loja |
| `evolution_send_failed` (HTTP 5xx) | erro transitório do Evolution | normalmente resolve no retry |
| `evolution_unreachable` | não conectou no Evolution | rede/URL do Evolution |
| `grupo_estoque_nao_configurado` | loja sem grupo configurado | configurar o grupo de estoque |

### Como ver o motivo real quando acontecer de novo

```bash
fly logs -a app2037 | rg "sendText falhou|alerta simulação"
# procure: code=<...> corpo=<...>  (corpo já sanitizado)
```

Inspecionar as falhas no banco (read-only):

```sql
SELECT loja_id, status, attempts, last_error_code, next_attempt_at, created_at
FROM notificacoes_operacionais
WHERE tipo = 'simulacao_humana' AND status <> 'sent'
ORDER BY created_at DESC;
```

Forçar o reprocessamento de **um** dead-letter (⚠️ **reenvia o alerta real ao grupo**,
com a PII daquele cliente — prefira o registro mais recente): resetar
`attempts = 0`, `next_attempt_at = NULL`, `status = 'pending'` no id escolhido; o worker de
outbox (`notificacoes_outbox_job`, ligado no lifespan) reenvia no próximo ciclo e o log
mostra o code classificado.

### Contexto de canais (por que conversas travam)

Cada número de WhatsApp da loja é uma **instância Evolution** = um **canal** (`whatsapp_canais`,
`estado ∈ {pendente, conectado, desconectado, inativo}`). A conversa é amarrada ao canal
por onde entrou; o bot só responde **por aquela instância**. Se o canal está
`desconectado`/`inativo` (ex.: número re-pareado na migração), a conversa fica órfã e o bot
não consegue responder — **nenhum PATCH de estado resolve**; é preciso **reconectar** o
canal (parear por QR em Ajustes na Revy Loja) ou migrar a conversa para um canal ativo.
Multi-WhatsApp/canais existe desde ~2026-07-29 (routing por `canal_id`).

---

## Testes relevantes

- `tests/test_whatsapp_outbound.py` — `EvolutionWhatsAppOutbound.send_text`: sucesso,
  classificação dos codes (`evolution_group_forbidden`, `evolution_target_not_found`,
  `evolution_send_failed`) e **sanitização do log** (CPF/nascimento redigidos, apikey nunca
  vaza). Usa `httpx.MockTransport`.
- `tests/test_solicitacoes_simulacao.py` — fluxo do pedido de simulação humana: qualifica
  lead, pausa bot, enfileira/reenvia alerta e reprocessa dead-letters.
- `tests/test_whatsapp_provider_evolution.py` — provisionamento/estado das instâncias
  (connect/QR, status, logout) sem vazar URL/apikey.
