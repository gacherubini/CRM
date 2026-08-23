---
gatilho: reiniciar o n8n2037 ou trocar um secret dele
produto: n8n
custo: mensagens perdidas em horario comercial
fonte: infra
verificado_em: nunca reconferido desde a migracao das memorias (2026-08-23)
---
# Depois do restart o webhook responde 404, e a Evolution nao re-tenta

Reiniciar o `n8n2037` (inclusive por `fly secrets set`, que reinicia) tira o webhook do
ar ate ele se re-registrar. Nesse intervalo o `POST /webhook/whatsapp-ai` responde **404**
(Express generico) e a **Evolution cancela o retry em 404** — as mensagens do intervalo
se perdem, diferente do 500, que ela re-tenta. Reiniciar de novo so zera o relogio.

A janela **nao e fixa**: em 08/08/2026 levou ~6 min, com recuperacao de crash; em
16/08/2026 dois restarts seguidos nao derrubaram o webhook e o registro levou ~40 s.
Trate como risco real, nao como certeza de 6 minutos.

Verificar sem invadir: um POST de corpo vazio no webhook. 404 = ainda ativando; 200 =
registrado (o primeiro no rejeita corpo sem `instance`, entao nao causa efeito nenhum).
`n8n list:workflow --active=true` mostra ativo no banco mesmo enquanto o webhook ainda
nao registrou — nao confie so nele.

Agrupe mudancas de secret e evite restart em horario comercial.
