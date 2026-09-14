---
gatilho: ver a tela da falha de um driver em prod, ou mapear as chamadas do portal sem abrir o worker
produto: motor-simulacao
custo: screenshot com segredo parado em disco, ou HAR cru com senha e cookies
fonte: repo
verificado_em: 2026-09-13
---
# Print de evento e HAR sanitizado para debugar driver em prod

- **Print sobrevive a reboot do worker** quando vai para o blob do evento
  (migration `0013_evento_screenshot_blob`): `GET
  /v1/simulacoes/{id}/eventos/{id}/print` devolve o binário mesmo com o
  `screenshot_path` morto no rootfs efêmero. `tem_print=true` no evento indica.
- **Busca remota:** motor-api não é pública; vá por dentro do bundle:
  `fly ssh console -a app2037` com script via **stdin**
  (`Get-Content remote.sh | fly ssh console -a app2037 -C 'sh -s'` — `-C`
  complexo quebra no PowerShell, ver learning do stdin). Dentro da VM,
  `$MOTOR_TOKEN` já está no env: `curl 127.0.0.1:8004/...`. Binário volta por
  `base64 -w0`; no log local, descarte a linha `Connecting to...` e decode a
  partir de `/9j/` (JPEG) ou `iVBOR` (PNG).
- **HAR sem tocar no repo:** monkeypatch temporário em
  `PlaywrightBankDriver._new_context_vanilla` somando `record_har_path` +
  `record_har_omit_content=True`, rode o driver, depois **sanitize antes de ler**:
  guarde só host + path sem query, sem headers, sem bodies — HAR cru tem senha do
  portal e cookies. Apague o cru em seguida.
- O que o HAR do Bradesco revelou (exemplo do que procurar): SPA sobre REST
  same-origin, endpoint próprio de `login/captcha/validate` (v3 server-side, sem
  puzzle — sem técnica de bypass aplicável) e RUM Dynatrace + beacon Akamai
  observando a navegação (pacing humano conta; spoofar piora).
