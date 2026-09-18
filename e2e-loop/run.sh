#!/bin/bash
# Loop e2e: roda os cenarios em ordem, para no primeiro vermelho.
# Uso: CHIP="+55..." ./run.sh [T1|T2|...]   (sem arg roda tudo)
# RESTRICAO: a memoria do agente (n8n, chave instance:telefone) sobrevive ao
# reset do banco. Rode a suite INTEIRA de uma vez apos `fly apps restart n8n2037`
# + esperar-webhook.sh, e nao mude setup (seed/catalogo/config) no meio.
set -u
E2E_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./config.sh
. "$E2E_DIR/config.sh"
mkdir -p "$LOG_DIR"
# shellcheck source=./lib.sh
. "$E2E_DIR/lib.sh"
# shellcheck source=./api.sh
. "$E2E_DIR/api.sh"
# shellcheck source=./cenarios.sh
. "$E2E_DIR/cenarios.sh"

chmod +x "$E2E_DIR"/*.sh
e2e_log "inicio loop e2e chip=$CHIP log=$LOG_DIR"
e2e_log "ponte: $(openclaw channels status 2>/dev/null | grep -i whatsapp | head -n 1)"

# Sem audio por ordem do dono (18/09): T3/T3b/T4 pausados, texto primeiro.
# Ordem com simulacao antes do handoff (jornada dinheiro primeiro).
TODOS="T1_abertura T2_barra T5_catalogo T6_estoque T8_simulacao T7_handoff T9_imagem T10_followup T11_injection"
ALVOS="$TODOS"
if [ "$#" -gt 0 ]; then
  ALVOS=""
  for a in "$@"; do
    case "$a" in
      T1) ALVOS="$ALVOS T1_abertura";; T2) ALVOS="$ALVOS T2_barra";;
      T3) ALVOS="$ALVOS T3_audio_pergunta";; T3b) ALVOS="$ALVOS T3b_audio_nome";;
      T4) ALVOS="$ALVOS T4_audio_silencio";; T5) ALVOS="$ALVOS T5_catalogo";;
      T6) ALVOS="$ALVOS T6_estoque";; T7) ALVOS="$ALVOS T7_handoff";;
      T8) ALVOS="$ALVOS T8_simulacao";; T9) ALVOS="$ALVOS T9_imagem";;
      T10) ALVOS="$ALVOS T10_followup";; T11) ALVOS="$ALVOS T11_injection";;
      *) e2e_log "cenario desconhecido: $a"; exit 2;;
    esac
  done
fi

VERMELHOS=0
for t in $ALVOS; do
  e2e_log "=== $t ==="
  if ! "$t"; then
    VERMELHOS=$((VERMELHOS + 1))
    e2e_log "PARADA no primeiro vermelho: $t"
    break
  fi
done

e2e_log "=== resumo ==="
sort "$LOG_DIR/resultado.log" | tee -a "$LOG_DIR/loop.log"
[ "$VERMELHOS" -eq 0 ]
