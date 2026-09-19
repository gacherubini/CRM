# Config do loop e2e Revy (WhatsApp real -> loja teste).
# Uso: export CHIP="+55..." ; ./run.sh
# Token da API: ./provisionar.sh (uma vez, apos fly auth login da conta Revy).
: "${CHIP:?exporte CHIP com o E.164 do chip da loja teste}"
GABRIEL="+5551980336365"
# Identidade que a Meta enxerga: ela entrega `from` SEM o 9 (555180336365).
# Tudo que le conversa (API/dbq) usa este; o envio continua para o CHIP.
GABRIEL_DIGITS="555180336365"
LOJA_SLUG="teste"
PHONE_NUMBER_ID="1356659367525459"
API_BASE="${API_BASE:-https://app2037.fly.dev}"
E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_FILE="$E2E_DIR/.token"
LOG_DIR="$E2E_DIR/logs/run-$(date +%Y%m%d-%H%M%S)"
WAIT_SECS=150
POLL_SECS=10
# T8: o "Peguei" e o unico passo que so o aparelho do vendedor faz.
T8_PEGUEI_SECS="${T8_PEGUEI_SECS:-300}"
