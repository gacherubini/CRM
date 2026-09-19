---
status: proposed
---

# Áudio do vendedor sai pela Cloud API, fica no volume do bundle e só existe em loja Modo 2

O Atendimento da Loja só envia texto. Não existe outbound de mídia em nenhum
adapter: `CloudWhatsAppOutbound` tem `send_text`, `send_template_button` e
`send_interactive_button` (`chatbot-api/app/whatsapp_outbound.py:223`), e o
`EvolutionWhatsAppOutbound` só tem `send_text` (`whatsapp_outbound.py:106`). Áudio
só existe entrando: o webhook baixa base64 da Evolution e transcreve
(`chatbot-api/app/audio.py:273`). Esta decisão cobre o vendedor gravar a própria
voz no Atendimento e o cliente receber como áudio no WhatsApp.

## Decisão

- O vendedor grava ao vivo no navegador (MediaRecorder). Não há biblioteca de
  áudios prontos nesta fase.
- A gravação sai em `webm/opus` do browser; vira `ogg/opus` no `chatbot-api` com
  `ffmpeg`, que passa a ser dependência do Docker do chatbot.
- O envio usa **só a Cloud API da Meta**. Na Cloud, áudio é dois passos: upload
  multipart em `POST /{phone_number_id}/media` devolve `media_id`, e o envio é
  `POST /{phone_number_id}/messages` com `type: audio` e `id`.
- O microfone só aparece em loja Modo 2. A escolha continua por loja, via
  `outbound_para_loja` (`whatsapp_outbound.py:383`); em loja Modo 1 o mic não é
  oferecido.
- Os bytes ficam no volume `/data` do bundle `app2037`, no mesmo padrão do
  Estoque (`estoque-api/app/config.py:37`). O Chatbot escreve o arquivo e é dono
  da mensagem.
- O Portal fala com o Chatbot por endpoint novo, `POST
  /v1/conversas/{telefone}/audios`, em `multipart/form-data`. O Portal é o gate de
  autenticação e escopo e nunca aceita `instance` ou canal vindos da UI, como já
  vale para o texto (`portal-gestao/app/loja/routes.py:809`).
- O play no workspace passa por rota autenticada. O navegador não recebe token do
  Chatbot; o Portal valida a sessão e repassa, como já faz com as mensagens.
- Enviar áudio pausa o bot e é idempotente por chave, igual ao texto.
- Transcrição é sob demanda, reusando o Whisper do inbound, e fica guardada na
  mensagem.
- Sem expurgo automático nesta fase: o áudio vive enquanto durar a conversa.

## Invariantes

- Todo envio de WhatsApp passa pelo port de provedor do Chatbot (ADR-0001).
- Loja não operacional continua respondendo `423`, e o audio não escapa disso.
- Áudio só sai dentro da janela de 24 h da Cloud. A janela é checada **antes** de
  habilitar o microfone, não depois de gravar.
- Loja Modo 1 não tem microfone. Não há plano de Evolution nesta fase.
- O browser nunca vê token de serviço do Chatbot.
- O payload Portal→Chatbot é multipart, nunca base64.
- `ffmpeg` e `python-multipart` entram em `chatbot-api`, inclusive no
  `requirements` do produto, não só no bundle de deploy.
- Flag de rollout default OFF.

## Consequências

- O volume é single-attach e compartilhado com portal, motor e estoque no mesmo
  bundle. Áudio de conversa enchendo `/data` derruba mais do que o áudio.
- Não há URL assinada nem CDN: o play passa pelo app.
- Migrar para object storage e desenhar expurgo ficam para quando houver HA ou
  disco no limite.
