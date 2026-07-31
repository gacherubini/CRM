#!/usr/bin/env bash
# Sobe e opera a stack Revy inteira neste computador.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.local.yml"
ENV_FILE="$ROOT_DIR/.env.local"
PROJECT_NAME="revy-local"

die() {
  printf 'erro: %s\n' "$*" >&2
  exit 1
}

random_hex() {
  openssl rand -hex "${1:-24}"
}

fernet_key() {
  openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n'
}

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

create_env() {
  if [[ -f "$ENV_FILE" ]]; then
    return
  fi

  command -v openssl >/dev/null 2>&1 || die "openssl não encontrado"
  umask 077
  {
    printf '# Gerado por ./local.sh. Não versionar.\n'
    printf 'LOCAL_POSTGRES_PASSWORD=%s\n' "$(random_hex 18)"
    printf 'EVOLUTION_API_KEY=%s\n' "$(random_hex 24)"
    printf 'N8N_ENCRYPTION_KEY=%s\n' "$(random_hex 24)"
    printf 'CHATBOT_WEBHOOK_TOKEN=%s\n' "$(random_hex 24)"
    printf 'CHATBOT_API_TOKEN=%s\n' "$(random_hex 24)"
    printf 'ESTOQUE_API_TOKEN=%s\n' "$(random_hex 24)"
    printf 'MOTOR_TOKEN=%s\n' "$(random_hex 24)"
    printf 'MOTOR_METRICS_TOKEN=%s\n' "$(random_hex 24)"
    printf 'MOTOR_ENCRYPTION_KEY=%s\n' "$(fernet_key)"
    printf 'ESTOQUE_OUTBOX_KEY=%s\n' "$(fernet_key)"
    printf 'ESTOQUE_SESSION_SECRET=%s\n' "$(random_hex 32)"
    printf 'PORTAL_SESSION_SECRET=%s\n' "$(random_hex 32)"
    printf 'PORTAL_IDENTITY_HMAC_SECRET=%s\n' "$(random_hex 32)"
    printf 'PORTAL_ENCRYPTION_KEY=%s\n' "$(fernet_key)"
    printf 'REVY_TRAFEGO_SESSION_SECRET=%s\n' "$(random_hex 32)"
    printf 'REVY_TRAFEGO_SERVICE_TOKEN=%s\n' "$(random_hex 24)"
    printf 'LOCAL_STORE_NAME=Moto Center Local\n'
    printf 'LOCAL_STORE_SLUG=moto-center\n'
    printf 'LOCAL_STORE_WHATSAPP=\n'
    printf 'LOCAL_EVOLUTION_INSTANCE=loja-local\n'
    printf 'LOCAL_ADMIN_EMAIL=admin@revy.local\n'
    printf 'LOCAL_ADMIN_NAME=Administrador Local\n'
    printf 'LOCAL_ADMIN_PASSWORD=%s\n' "$(random_hex 10)"
  } >"$ENV_FILE"
  chmod 600 "$ENV_FILE"
  printf 'criado: %s (segredos somente locais)\n' "$ENV_FILE"
}

compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    --file "$COMPOSE_FILE" \
    "$@"
}

check_prerequisites() {
  command -v docker >/dev/null 2>&1 || die "Docker não encontrado"
  docker compose version >/dev/null 2>&1 || die "Docker Compose não encontrado"
  docker info >/dev/null 2>&1 || die "Docker está desligado ou inacessível"
}

bootstrap() {
  printf '\nPreparando loja, usuários e credenciais internas...\n'
  compose exec -T estoque-api python /opt/revy-local/bootstrap.py estoque
  compose exec -T chatbot-api python /opt/revy-local/bootstrap.py chatbot
  compose exec -T motor-api python /opt/revy-local/bootstrap.py motor
  compose exec -T portal python /opt/revy-local/bootstrap.py portal
}

show_urls() {
  local slug
  slug="$(env_value LOCAL_STORE_SLUG)"
  printf '\nServiços locais:\n'
  printf '  Revy Loja:   http://localhost:9000\n'
  printf '  Revy Control:http://localhost:9010\n'
  printf '  Catálogo:    http://localhost:8200/l/%s\n' "$slug"
  printf '  Site:        http://localhost:8088\n'
  printf '  n8n:         http://localhost:5678\n'
  printf '  Evolution:   http://localhost:8080/manager\n'
  printf '  Chatbot API: http://localhost:8001/docs\n'
  printf '  Estoque API: http://localhost:8100/docs\n'
  printf '  Motor API:   http://localhost:8000/docs\n'
}

show_credentials() {
  create_env
  printf 'Login local (Portal e Control):\n'
  printf '  e-mail: %s\n' "$(env_value LOCAL_ADMIN_EMAIL)"
  printf '  senha:  %s\n' "$(env_value LOCAL_ADMIN_PASSWORD)"
  printf '\nEvolution Manager:\n'
  printf '  API key: %s\n' "$(env_value EVOLUTION_API_KEY)"
  printf '\nOs tokens entre serviços continuam ocultos em %s.\n' "$ENV_FILE"
}

doctor() {
  local failures=0
  local label url
  local checks=(
    "Revy Loja|http://localhost:9000/health/ready"
    "Revy Control|http://localhost:9010/health/ready"
    "Catálogo|http://localhost:8200/health/ready"
    "Site|http://localhost:8088/"
    "n8n|http://localhost:5678/healthz"
    "Evolution|http://localhost:8080/"
    "Chatbot API|http://localhost:8001/health/ready"
    "Estoque API|http://localhost:8100/health/ready"
    "Motor API|http://localhost:8000/health/ready"
  )

  printf '\nDiagnóstico HTTP:\n'
  for item in "${checks[@]}"; do
    IFS='|' read -r label url <<<"$item"
    if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; then
      printf '  ok     %s\n' "$label"
    else
      printf '  falhou %s (%s)\n' "$label" "$url"
      failures=$((failures + 1))
    fi
  done

  if (( failures > 0 )); then
    printf '\n%s serviço(s) não responderam; use ./local.sh logs.\n' "$failures"
    return 1
  fi
  printf '\nTudo respondeu corretamente.\n'
}

import_workflow() {
  check_prerequisites
  create_env

  local source="$ROOT_DIR/n8n/workflow-ai-nao-salvos.json"
  [[ -f "$source" ]] || die "workflow não encontrado: $source"

  local prepared
  prepared="$(mktemp "${TMPDIR:-/tmp}/revy-workflow.XXXXXX")"
  trap 'rm -f "${prepared:-}"' RETURN

  sed \
    -e "s|__EVOLUTION_KEY__|$(env_value EVOLUTION_API_KEY)|g" \
    -e "s|__CHATBOT_TOKEN__|$(env_value CHATBOT_API_TOKEN)|g" \
    -e "s|__CHATBOT_WEBHOOK_TOKEN__|$(env_value CHATBOT_WEBHOOK_TOKEN)|g" \
    "$source" >"$prepared"

  compose cp "$prepared" n8n:/tmp/workflow-local.json
  compose exec -T --user root n8n chown node:node /tmp/workflow-local.json
  compose exec -T --user root n8n chmod 600 /tmp/workflow-local.json
  if ! compose exec -T n8n n8n import:workflow --input=/tmp/workflow-local.json; then
    compose exec -T --user root n8n rm -f /tmp/workflow-local.json || true
    return 1
  fi
  compose exec -T --user root n8n rm -f /tmp/workflow-local.json
  compose restart n8n
  printf '\nWorkflow importado inativo. Abra http://localhost:5678, configure a credencial Gemini e ative-o.\n'
}

up() {
  check_prerequisites
  create_env
  printf 'Construindo e iniciando a stack local...\n'
  compose up --detach --build --wait --wait-timeout 600
  bootstrap
  show_urls
  show_credentials
  doctor || true
  printf '\nPara acompanhar: ./local.sh logs\n'
  printf 'Guia completo: deploy/local/README.md\n'
}

usage() {
  cat <<'EOF'
Uso: ./local.sh [comando]

  up               cria/configura e sobe tudo (padrão)
  down             desliga sem apagar dados
  restart          reinicia os serviços
  status           mostra o estado dos contêineres
  logs [serviço]   acompanha logs de tudo ou de um serviço
  doctor           testa os endpoints locais
  urls             mostra os endereços
  credentials      mostra o login local e a chave da Evolution
  workflow         importa o template no n8n (ainda exige Gemini)
  help             mostra esta ajuda
EOF
}

command_name="${1:-up}"
case "$command_name" in
  up)
    up
    ;;
  down)
    create_env
    compose down
    ;;
  restart)
    check_prerequisites
    create_env
    compose restart
    ;;
  status)
    create_env
    compose ps
    ;;
  logs)
    check_prerequisites
    create_env
    shift || true
    compose logs --follow --tail=200 "$@"
    ;;
  doctor)
    doctor
    ;;
  urls)
    create_env
    show_urls
    ;;
  credentials)
    show_credentials
    ;;
  workflow)
    import_workflow
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
