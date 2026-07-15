#!/usr/bin/env bash
# Sincroniza inventário de slots Playwright no Motor (tabela worker_slots).
#
# Uso:
#   export DATABASE_URL=...   # ou rode dentro da machine do Motor
#   bash deploy/fly/sync-motor-worker-machines.sh santander:MACHINE_ID [fontecred:ID ...]
#
# Não inicia as Machines — só registra IDs allowlist para o orquestrador.
# Crie as Machines paradas no Fly com a mesma imagem e:
#   MOTOR_WORKER_ON_DEMAND=1
#   MOTOR_WORKER_PROVEDOR=santander
#   MOTOR_FANOUT_ENABLED=1
#   restart policy on-failure
#   entrypoint: /srv/scripts/on-demand-worker-entrypoint.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/motor-simulacao"

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 provedor:fly_machine_id [provedor:id ...]" >&2
  exit 1
fi

python - <<'PY' "$@"
import sys
from app.db import SessionLocal
from app.orquestrador import upsert_slot

db = SessionLocal()
try:
    for arg in sys.argv[1:]:
        if ":" not in arg:
            raise SystemExit(f"formato inválido: {arg} (use provedor:machine_id)")
        provedor, mid = arg.split(":", 1)
        provedor = provedor.strip().lower()
        mid = mid.strip()
        slot = upsert_slot(db, provedor=provedor, fly_machine_id=mid)
        print(f"ok {slot.provedor} -> {slot.fly_machine_id} (id={slot.id})")
finally:
    db.close()
PY
