#!/usr/bin/env bash
# Gemeo do secrets.ps1, para o Mac.
#
# GitHub Secret e via de mao unica: `gh secret set` escreve e nada le de volta.
# Por isso este script grava SEMPRE nos dois lados na mesma chamada — o
# .env.local (que roda na sua maquina) e o GitHub (que roda no CI).
#
#   ./deploy/ci/secrets.sh set MOTOR_BRADESCO_SENHA
#   ./deploy/ci/secrets.sh push
#   ./deploy/ci/secrets.sh list
#   ./deploy/ci/secrets.sh check
set -euo pipefail

REPO="${REPO:-gacherubini/CRM}"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
# ENV_LOCAL=... na frente do comando aponta para outra arvore. So precisa disso
# rodando de um worktree, ja que o .env.local fica fora do git.
ENV_LOCAL="${ENV_LOCAL:-$RAIZ/motor-simulacao/.env.local}"

# Nao sao segredo: sao os parametros da simulacao de teste. Vao para
# `gh variable`, que da para ler e editar na interface do GitHub.
VARIAVEIS="MOTOR_BROWSER_HEADLESS MOTOR_WARM_SESSION MOTOR_SCREENSHOT_DIR
MOTOR_STORAGE_STATE_DIR PROBE_PLACA PROBE_VALOR PROBE_UF PROBE_PRAZOS
PROBE_ENTRADA PROBE_CATEGORIA"

eh_variavel() {
  for v in $VARIAVEIS; do [ "$v" = "$1" ] && return 0; done
  return 1
}

conferir_gh() {
  command -v gh >/dev/null || { echo "gh CLI nao encontrado: brew install gh" >&2; exit 1; }
  gh auth status >/dev/null 2>&1 || { echo "gh nao autenticado: gh auth login" >&2; exit 1; }
}

enviar() {
  local nome="$1" valor="$2"
  # Pelo stdin, nunca por argumento: argumento aparece no `ps`.
  if eh_variavel "$nome"; then
    printf '%s' "$valor" | gh variable set "$nome" --repo "$REPO"
    echo "  GitHub variable $nome  (visivel na UI)"
  else
    printf '%s' "$valor" | gh secret set "$nome" --repo "$REPO"
    echo "  GitHub secret   $nome  (escrita so)"
  fi
}

gravar_env_local() {
  local nome="$1" valor="$2" tmp
  tmp="$(mktemp)"
  umask 077
  if [ -f "$ENV_LOCAL" ] && grep -qE "^[[:space:]]*${nome}[[:space:]]*=" "$ENV_LOCAL"; then
    # awk em vez de sed -i: o valor pode conter / e & sem aviso.
    awk -v n="$nome" -v v="$valor" '
      $0 ~ "^[[:space:]]*"n"[[:space:]]*=" { print n"="v; next }
      { print }
    ' "$ENV_LOCAL" > "$tmp"
  else
    [ -f "$ENV_LOCAL" ] && cat "$ENV_LOCAL" > "$tmp" || : > "$tmp"
    printf '%s=%s\n' "$nome" "$valor" >> "$tmp"
  fi
  mv "$tmp" "$ENV_LOCAL"
  chmod 600 "$ENV_LOCAL"
  echo "  .env.local      $nome"
}

nomes_locais() {
  [ -f "$ENV_LOCAL" ] || return 0
  grep -vE '^[[:space:]]*#' "$ENV_LOCAL" \
    | grep -oE '^[A-Z][A-Z_0-9]*=' \
    | tr -d '=' \
    | grep -E '^(MOTOR|PROBE|MOTRIX)_' \
    | sort -u
}

nomes_remotos() {
  {
    gh secret list --repo "$REPO" --json name --jq '.[].name'
    gh variable list --repo "$REPO" --json name --jq '.[].name'
  } | grep -E '^(MOTOR|PROBE|MOTRIX)_' | sort -u
}

case "${1:-help}" in

  set)
    NOME="${2:?uso: $0 set NOME_DA_VARIAVEL}"
    conferir_gh
    NOME="$(printf '%s' "$NOME" | tr '[:lower:]' '[:upper:]')"
    if eh_variavel "$NOME"; then
      read -r -p "novo valor para $NOME: " VALOR
    else
      read -r -s -p "novo valor para $NOME (nao aparece na tela): " VALOR
      echo
    fi
    [ -n "$VALOR" ] || { echo "valor vazio, nada foi gravado" >&2; exit 1; }
    gravar_env_local "$NOME" "$VALOR"
    enviar "$NOME" "$VALOR"
    echo "$NOME atualizado nos dois lugares."
    ;;

  push)
    conferir_gh
    [ -f "$ENV_LOCAL" ] || { echo "nao achei $ENV_LOCAL" >&2; exit 1; }
    N=0
    while IFS= read -r nome; do
      valor="$(grep -E "^[[:space:]]*${nome}[[:space:]]*=" "$ENV_LOCAL" | head -1 | cut -d= -f2-)"
      [ -n "$valor" ] || continue
      enviar "$nome" "$valor"
      N=$((N + 1))
    done < <(nomes_locais)
    echo "$N variaveis enviadas ao GitHub."
    ;;

  list)
    conferir_gh
    echo
    echo "SECRETS (valor nao pode ser lido; a data responde 'de quando e essa senha')"
    gh secret list --repo "$REPO"
    echo
    echo "VARIABLES (valor visivel)"
    gh variable list --repo "$REPO"
    ;;

  check)
    conferir_gh
    LOCAIS="$(nomes_locais || true)"
    REMOTOS="$(nomes_remotos || true)"
    echo "local:  $(printf '%s\n' "$LOCAIS" | grep -c . || true) variaveis"
    echo "GitHub: $(printf '%s\n' "$REMOTOS" | grep -c . || true) variaveis"
    SO_LOCAL="$(comm -23 <(printf '%s\n' "$LOCAIS") <(printf '%s\n' "$REMOTOS") || true)"
    SO_REMOTO="$(comm -13 <(printf '%s\n' "$LOCAIS") <(printf '%s\n' "$REMOTOS") || true)"
    if [ -n "$SO_LOCAL" ]; then
      echo
      echo "So no .env.local (o CI nao tem):"
      printf '  %s\n' $SO_LOCAL
      echo "  corrija com: $0 push"
    fi
    if [ -n "$SO_REMOTO" ]; then
      echo
      echo "So no GitHub (sua maquina nao tem):"
      printf '  %s\n' $SO_REMOTO
      echo "  o valor nao da para baixar; regrave com: $0 set <NOME>"
    fi
    if [ -z "$SO_LOCAL" ] && [ -z "$SO_REMOTO" ]; then
      echo
      echo "Os dois lados tem os mesmos nomes."
    fi
    ;;

  *)
    cat <<'AJUDA'
secrets.sh - credenciais dos portais de banco, nos dois lados de uma vez

  set <NOME>   pede o valor (senha nao aparece na tela) e grava no .env.local
               E no GitHub, na mesma chamada
  push         manda tudo que ja esta no .env.local para o GitHub (bootstrap)
  list         lista o que existe no GitHub e QUANDO cada um mudou
  check        compara os nomes dos dois lados e mostra o que falta onde

Rotacao de senha expirada:
  ./deploy/ci/secrets.sh set MOTOR_BRADESCO_SENHA
AJUDA
    ;;
esac
