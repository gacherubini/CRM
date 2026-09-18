#!/bin/bash
# Oráculo do loop: lê conversa/mensagens/ofertas pela API do chatbot.
# shellcheck shell=bash

_api_token() {
  [ -f "$TOKEN_FILE" ] || { echo "ERRO: sem token. Rode ./provisionar.sh" >&2; return 1; }
  cat "$TOKEN_FILE"
}

# GET autenticado. Imprime corpo; retorna codigo HTTP em stderr-exit.
api_get() { # $1 = path com query
  local token code body
  token="$(_api_token)" || return 1
  body="$(curl -sS -w '\n%{http_code}' -m 20 -H "Authorization: Bearer $token" "$API_BASE$1" 2>/dev/null)"
  code="$(printf '%s' "$body" | tail -n 1)"
  printf '%s' "$body" | sed '$d'
  return "$([ "$code" -ge 200 ] && [ "$code" -lt 300 ] && echo 0 || echo 1)"
}

# Textos de ENTRADA (cliente) criados depois de $1 (ISO UTC). Um por linha.
api_entradas_apos() { # $1 = ISO-8601 UTC
  api_get "/v1/conversas/$GABRIEL_DIGITS/mensagens?instance=$PHONE_NUMBER_ID&after_criada_em=$1&limit=50" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
for m in d.get('mensagens', []):
    if m.get('direcao') == 'entrada' and (m.get('texto') or '').strip():
        print(m['texto'])
"
}

# Textos de SAIDA (bot) criados depois de $1 (ISO UTC). Um por linha.
api_saidas_apos() { # $1 = ISO-8601 UTC
  api_get "/v1/conversas/$GABRIEL_DIGITS/mensagens?instance=$PHONE_NUMBER_ID&after_criada_em=$1&limit=50" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
for m in d.get('mensagens', []):
    if m.get('direcao') == 'saida' and (m.get('texto') or '').strip():
        print(m['texto'])
"
}

api_estado() {
  api_get "/v1/conversas/$GABRIEL_DIGITS/estado?instance=$PHONE_NUMBER_ID" 2>/dev/null
}

api_ofertas() { # $1 = estado (opcional)
  api_get "/v1/ofertas${1:+?estado=$1}" 2>/dev/null
}

api_post() { # $1 = path, $2 = json body (opcional)
  local token code body
  token="$(_api_token)" || return 1
  body="$(curl -sS -w '\n%{http_code}' -m 20 -X POST -H "Authorization: Bearer $token" -H "Content-Type: application/json" -d "${2:-{}}" "$API_BASE$1" 2>/dev/null)"
  code="$(printf '%s' "$body" | tail -n 1)"
  printf '%s' "$body" | sed '$d'
  return "$([ "$code" -ge 200 ] && [ "$code" -lt 300 ] && echo 0 || echo 1)"
}

# Id da oferta aberta para o telefone de teste (vazio se nao houver).
api_oferta_aberta_id() {
  api_ofertas aberta 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
for o in (d if isinstance(d, list) else []):
    tel = ''.join(c for c in str(o.get('telefone_cliente') or '') if c.isdigit())
    if tel.endswith('80336365') and o.get('estado') == 'aberta':
        print(o.get('id') or '')
        break
"
}
