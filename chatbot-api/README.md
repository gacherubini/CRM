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

## CTWA: `origem = meta_ctwa` só para quem veio de anúncio (2026-08-08)

`aplicar_touch_ctwa` separa duas coisas que antes eram uma só:

| | Regra |
|---|---|
| **Gravar o sinal** | **sempre**, sem guard. `ctwa_source_type`, `ctwa_clid`, `meta_ad_id`, `ctwa_codigo` seguem salvos como antes. Nada se perde. |
| **Carimbar `origem`** | só com identificador de anúncio **ou** `ctwa_source_type` em `FAMILIA_ANUNCIO` (`fb_ads`, `ctwa_ad`, `ad`). |

Antes, `ctwa_source_type` **sozinho** já bastava — então `global_search_new_chat` (alguém
digitando o número dentro do WhatsApp) e `click_to_chat_link` (link `wa.me` do site, do
catálogo ou da bio) entravam como lead de anúncio da Meta. Em produção eram 10 leads.

Três detalhes que decidem se a mudança está certa:

- **`casefold` obrigatório.** O valor real em produção é `FB_Ads`, com maiúsculas;
  comparação sensível a caixa classifica 205 leads errado.
- **`canal = whatsapp` ficou fora do guard.** Quem chegou por link direto também chegou
  pelo WhatsApp. Só `origem*` e `ctwa_atribuido_em` dependem de ser anúncio.
- **O guard decide se escreve, nunca apaga.** Lead que veio de anúncio e depois manda
  mensagem por link direto continua `meta_ctwa`.
- **`source_type` desconhecido não carimba**, e é logado uma vez (é enum, não é PII) para
  a lista crescer com evidência. Anúncio de verdade quase sempre traz `clid` ou `ad_id`,
  que já passam pelo guard: falso negativo aqui é barato, falso positivo é o defeito.

**Sem backfill.** Os 10 leads já carimbados ficam como estão — o carimbo antigo
sobrescreveu a origem anterior e não dá para saber qual era. Não faz falta: o painel da
Loja agrupa por `ctwa_source_type`, que está correto nos 10.

`FAMILIA_ANUNCIO` é **duplicação consciente** com o mapa de rótulos em
`portal-gestao/app/loja/sales_overview.py` (produtos diferentes, sem import entre eles).
Mudou aqui, muda lá.

### Tracking pendente com várias conversas no mesmo telefone

`Conversa` é única por `(canal_id, telefone)` com `canal_id` nullable, então o mesmo
cliente tem uma linha **por canal** — a loja tem 7 canais e 492 conversas para 243
identidades. `_vincular_tracking_pendente_ao_lead` pegava a conversa com `.first()`, sem
filtrar canal e sem ordenar, e podia pegar justamente a que não tem
`tracking_pendente_json`.

Agora varre **todas** as conversas do telefone que têm pendente, em `ORDER BY criada_em
ASC`. **Ascendente é obrigatório:** `aplicar_touch_ctwa` só grava os campos `_first`
enquanto estão nulos, então o toque mais antigo precisa chegar primeiro. E o ramo
idempotente do webhook (lead já existe) passou a consumir o pendente em vez de só ler o id
e deixar o anúncio parado na conversa.

⚠️ **Nunca casar lead ↔ `ctwa_auditoria` por telefone mascarado.** `telefone_mascarado`
são `***` + 4 dígitos. Testada contra o dado real em 08/08, a heurística casou o lead de
uma venda com o anúncio de **outro cliente** — DDI/DDD diferentes, 6 últimos diferentes, só
os 4 finais iguais. O aviso está repetido em `scripts/diagnose_ctwa_sinais.py`.

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
