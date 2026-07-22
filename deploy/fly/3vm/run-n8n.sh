#!/bin/sh
set -eu
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export N8N_USER_FOLDER="${N8N_USER_FOLDER:-/data/n8n}"
mkdir -p "$N8N_USER_FOLDER" 2>/dev/null || true

# Resolve absolute path so supervisord never depends on PATH quirks
if command -v n8n >/dev/null 2>&1; then
  exec "$(command -v n8n)" "$@"
fi
for c in \
  /usr/bin/n8n \
  /usr/local/bin/n8n \
  /usr/lib/node_modules/n8n/bin/n8n \
  /usr/local/lib/node_modules/n8n/bin/n8n
do
  if [ -f "$c" ]; then
    if [ -x /usr/bin/node ]; then
      exec /usr/bin/node "$c" "$@"
    fi
    if [ -x /usr/local/bin/node ]; then
      exec /usr/local/bin/node "$c" "$@"
    fi
    exec "$c" "$@"
  fi
done
echo "n8n binary not found" >&2
command -v node || true
ls -la /usr/bin/n8n /usr/local/bin/n8n 2>/dev/null || true
ls -la /usr/lib/node_modules 2>/dev/null || true
exit 127
