#!/bin/sh
set -eu
for c in /usr/bin/caddy /usr/local/bin/caddy; do
  if [ -x "$c" ]; then
    exec "$c" "$@"
  fi
done
echo "caddy not found" >&2
ls -la /usr/bin/caddy /usr/local/bin/caddy 2>/dev/null || true
exit 127
