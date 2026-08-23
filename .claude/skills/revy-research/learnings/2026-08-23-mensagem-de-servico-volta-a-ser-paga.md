---
gatilho: propor canal de entrada de lead que nao seja anuncio CTWA
produto: chatbot-api
fonte: externo
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# A partir de 01/10/2026 a mensagem de servico volta a ser cobrada

Na WhatsApp Cloud API, todo texto livre que o bot manda dentro da janela de servico foi
gratuito de 01/11/2024 ate **01/10/2026**. Dessa data em diante volta a ser cobrado, a
tarifa de template utilitario. So afeta a API, nao os apps WhatsApp/Business.

**A excecao que salva a Revy:** conversa que nasce de anuncio Click-to-WhatsApp (ou de CTA
no Facebook/Instagram) entra como *free entry point* — continua **gratuita** e a janela e
de **72 horas** em vez de 24. Quem chega pelo numero direto (placa, cartao, Google) passa
a custar por mensagem.

Consequencia de projeto: hoje o funil e todo inbound por CTWA e o custo de servico e zero.
Depois de 01/10/2026 um "fale conosco" no site ou o numero na vitrine deixam de ser
neutros e viram linha de custo. Antes de abrir canal de entrada alternativo, calcule o
custo por mensagem; e ao dimensionar o Modo 2, separe lead CTWA de lead organico na
projecao — a partir de outubro nao sao a mesma coisa.
