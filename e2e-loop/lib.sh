# Biblioteca do loop e2e: envio (ponte), espera e asserts (API do chatbot).
# shellcheck shell=bash

e2e_log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG_DIR/loop.log"; }
passou() { printf 'PASSOU %s :: %s\n' "$1" "$2" | tee -a "$LOG_DIR/resultado.log"; }
falhou() { printf 'FALHOU %s :: %s\n' "$1" "$2" | tee -a "$LOG_DIR/resultado.log"; }

e2e_send_text() { # $1 = texto
  openclaw message send --channel whatsapp -t "$CHIP" -m "$1" --json 2>&1 \
    | tee -a "$LOG_DIR/send.log" | tail -n 5
}

e2e_send_media() { # $1 = arquivo, $2 = legenda (opcional)
  if [ -n "${2:-}" ]; then
    openclaw message send --channel whatsapp -t "$CHIP" --media "$1" -m "$2" --json 2>&1 \
      | tee -a "$LOG_DIR/send.log" | tail -n 5
  else
    openclaw message send --channel whatsapp -t "$CHIP" --media "$1" --json 2>&1 \
      | tee -a "$LOG_DIR/send.log" | tail -n 5
  fi
}

_iso_agora() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Espera resposta nova do bot desde $1 (ISO UTC). Textos vao para $2.
e2e_wait_reply() { # $1 = ISO inicio, $2 = arquivo_saida, $3 = timeout (opcional)
  local inicio="$1" out="$2" timeout="${3:-$WAIT_SECS}"
  local fim=$(( $(date +%s) + timeout ))
  : > "$out"
  while [ "$(date +%s)" -lt "$fim" ]; do
    sleep "$POLL_SECS"
    if api_saidas_apos "$inicio" > "$out" 2>>"$LOG_DIR/api.err" && [ -s "$out" ]; then
      return 0
    fi
  done
  return 1
}

assert_contém() { # $1 = arquivo, $2 = padrão (grep -i -E), $3 = id, $4 = detalhe
  if grep -qi -E "$2" "$1"; then passou "$3" "$4"; else falhou "$3" "$4 (sem '$2')"; return 1; fi
}

assert_não_contém() { # $1 = arquivo, $2 = padrão, $3 = id, $4 = detalhe
  if grep -qi -E "$2" "$1"; then falhou "$3" "$4 (achou '$2')"; return 1; else passou "$3" "$4"; fi
}

assert_não_vazio() { # $1 = arquivo, $2 = id, $3 = detalhe
  if [ -s "$1" ]; then passou "$2" "$3"; else falhou "$2" "$3 (sem resposta)"; return 1; fi
}
