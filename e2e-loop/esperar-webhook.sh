#!/bin/bash
# Espera o webhook whatsapp-cloud voltar a responder (nao-404) apos restart.
for i in $(seq 1 16); do
  code=$(curl -sS -o /dev/null -w "%{http_code}" -m 10 "https://n8n2037.fly.dev/webhook/whatsapp-cloud" 2>/dev/null)
  echo "$(date +%H:%M:%S) tent=$i code=$code"
  if [ "$code" != "404" ] && [ -n "$code" ] && [ "$code" != "000" ]; then
    echo "WEBHOOK_PRONTO code=$code"
    exit 0
  fi
  sleep 30
done
echo "WEBHOOK_AUSENTE apos 8min"
exit 1
