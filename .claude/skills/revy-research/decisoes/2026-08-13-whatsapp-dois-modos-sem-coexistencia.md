---
decidido: 2026-08-13
nao_reproponha: coexistencia por vendedor (echo de mensagem / historico) no lugar dos dois modos
---
# WhatsApp: dois modos por loja, e a coexistencia foi descartada

Diante da passkey do WhatsApp, que impede o Evolution de parear numeros marcados, o dono
escolheu **dois modos por loja, um XOR o outro**, no Revy Control:

- **Modo 1** — Baileys mais grupo, o legado, que aceita passkey em numeros ja pareados ou
  nao marcados.
- **Modo 2** — central Cloud API **so-bot**: um numero central por loja na API oficial; o
  bot atende e simula, e distribui por **rodizio em ordem** (template com botao). O
  vendedor pega e fala com o cliente do **proprio WhatsApp**, ou seja, **nenhum numero de
  vendedor pareia com bot** e a passkey nao os afeta.

A alternativa de **coexistencia por vendedor** (via echo de mensagens e historico) foi
**descartada**, nao adiada. Nao re-propor.

Spec canonica: `docs/referencia-viva/specs/2026-08-12-whatsapp-dois-modos-design.md`.
