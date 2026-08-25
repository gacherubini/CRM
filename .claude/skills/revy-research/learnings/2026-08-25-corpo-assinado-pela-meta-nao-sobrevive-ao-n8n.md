---
gatilho: bot do Modo 2 fica mudo com audio, imagem ou qualquer midia
produto: n8n
custo: uma noite achando que o pipeline de audio nao existia
fonte: repo
verificado_em: 2026-08-25
---
# O corpo assinado pela Meta nao sobrevive ao `$json.body` do n8n

Em 24/08 o audio no numero do Modo 2 nao teve resposta. Texto respondia normal, na
mesma conversa, com um minuto de diferenca. Tudo o que se costuma culpar estava
certo: workflow `whatsapp-cloud` ativo, webhook POST registrado, volume do n8n em
27%, as tres flags em `1`, `CHATBOT_AUDIO_TRANSCRIPTION_URL` apontando para o Groq
e `processador_de_audio(2)` construindo o processador.

A execucao do audio existia (`wCloudMeta0001` #39241) e parava no `Extrair1`. O que
o `Repassar inbound` recebeu do `/webhook/cloud` foi **`401 {"detail":"assinatura
invalida"}`**.

O no `Meta inbound` tem `rawBody: true`, entao os bytes crus ficam em
`binary.data` — mas o `Repassar inbound` manda `"body": "={{ $json.body }}"`, que e
o corpo **ja parseado**. O n8n re-serializa com `JSON.stringify`, e a Meta assina o
que o `json_encode` do PHP produz, que escapa barra:

    cru  : "mime_type":"audio\/ogg; codecs=opus"
    n8n  : "mime_type":"audio/ogg; codecs=opus"

HMAC sobre bytes diferentes nunca bate, e `assinatura_valida`
(`chatbot-api/app/meta_webhook.py:25`) e fail-closed de proposito.

**Nao e bug de audio — e bug de barra.** Midia sempre carrega `mime_type` e a URL
do `lookaside.fbsbx.com`, entao midia falha 100% das vezes. Texto so passa por
sorte: `"oi"` e o status de entrega nao tinham nenhuma `/`, e voltaram 200 na mesma
janela. Texto com link ou com `s/ entrada` cai igual.

O que enganou: a falha nao deixa rastro em lugar nenhum. Nao entra em `mensagens`,
nao entra em `cloud_evento_falho` (o `registrar_evento_falho` so roda **depois** da
assinatura passar), e a execucao do n8n fica marcada como `success` porque o
`Repassar inbound` tem `neverError: true`. Bot mudo, tudo verde.

Correcao mora no gerador (`n8n/fork_cloud_workflow.py:291`), nunca no JSON —
ver [[2026-08-23-workflow-cloud-e-gerado]]. Encaminhar `binary.data`
(`contentType: binaryData` + `inputDataFieldName: data`, ambos existem no
httpRequest v4.2 instalado) em vez de `$json.body`.

Regra geral: webhook assinado que passa por um intermediario tem de viajar em
**bytes**. Parsear e re-serializar no meio do caminho quebra a assinatura, e quebra
de um jeito que depende do conteudo — o pior tipo de intermitente.
