#!/usr/bin/env bash
# Confere a memoria real de cada app no Fly.io (nao altera nada).
set -euo pipefail

APPS="portal2037 catalogo2037 motor2037 estoque2037 chatbot2037 n8n2037 evolution2037"

for app in $APPS; do
  echo "=================== $app ==================="
  flyctl scale show -a "$app"
  echo
done
