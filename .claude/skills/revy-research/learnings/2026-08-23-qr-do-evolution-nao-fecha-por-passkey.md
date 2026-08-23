---
gatilho: parear numero novo no Evolution ou QR que nao conecta
produto: evolution
custo: rollbacks e re-deploys inuteis
---
# QR que nunca fecha e passkey do WhatsApp, nao bug de config

Desde ~jun/2026 o WhatsApp faz rollout de **passkey obrigatoria para autorizar novos
aparelhos** em contas selecionadas. Quando o numero esta marcado, o pareamento trava:
escaneia o QR e nada acontece (ou aparece "continuar no outro dispositivo") e o Evolution
fica gerando QR novo, com `qrcodeCount` subindo sem parar.

**Causa raiz:** o Baileys nao implementa o handshake de passkey/WebAuthn — servidor
headless nao faz assercao biometrica. Atinge todas as libs (Evolution, whatsapp-web.js,
OpenWA), com issues abertas e sem fix. **Nao e a versao do Baileys**: nenhuma versao atual
resolve e rollback nao adianta. A coincidencia de tempo (o dono tinha mexido no Baileys)
enganou o diagnostico em 12/08/2026.

Como distinguir: contas **sem** a exigencia conectam normalmente na mesma instancia e
mesma versao; so as marcadas ficam presas em `connecting`. Nos logs **nao** aparece 401,
405 nem versao defasada — so QR nao consumido.

O que fazer: (1) tentar remover a passkey no telefone (WhatsApp > Ajustes > Conta > Chave
de acesso) e refazer o QR; (2) se for obrigatoria, aquele numero **nao conecta** — use
outro nao-marcado; (3) **parar de re-escanear**, porque reforca o flag de seguranca; (4)
limpar instancias fantasma em `connecting` sem dono, senao a Evolution segue cuspindo QR.
Diagnostico rapido: `fetchInstances` (open vs connecting) e `fly logs -a evolution2037`
procurando `qrcodeCount`.
