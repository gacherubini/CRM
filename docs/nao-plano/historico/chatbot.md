# Histórico — Chatbot API

Contexto que saiu de `chatbot-api/README.md`.

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

## Tracking pendente com várias conversas no mesmo telefone

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

## Colisão de 4 dígitos no telefone mascarado (08/08)

`telefone_mascarado` em `ctwa_auditoria` são `***` + 4 dígitos. Testada contra o dado real,
a heurística de casar lead ↔ auditoria por esse campo casou o lead de uma venda com o
anúncio de **outro cliente** — DDI/DDD diferentes, 6 últimos diferentes, só os 4 finais
iguais. Qualquer atribuição saída daí é receita inventada. O aviso está repetido em
`scripts/diagnose_ctwa_sinais.py`.

## Alerta de simulação ao grupo de estoque — erro do Evolution desmascarado

Antes, um `sendText` que falhava só guardava o code genérico `evolution_send_failed` e
descartava o corpo real do Evolution — cegava o diagnóstico. `app/whatsapp_outbound.py`
passou a **classificar** a falha num code durável e a **logar o corpo real sanitizado**
(apikey removida; dígitos longos — CPF/telefone/nascimento — redigidos como `[num]`, pois
o texto do alerta contém PII e o provedor pode ecoá-lo). Nenhum corpo bruto é persistido.

Ver `chatbot-api/README.md` → "Alerta de simulação falhando" para a tabela de códigos e o
procedimento de diagnóstico, que continua sendo operação corrente.
