#!/usr/bin/env bash
# Deploy Orthonym-Web with docker compose, after asking which OPSIN to use.
#
#   ./deploy.sh
#
# The choice is kept in .env as ORTHONYM_OPSIN (a build arg, backend/Dockerfile),
# so a later plain `docker compose up -d --build` keeps it. The OPSIN main
# choice REMOVES the line instead of writing a commit: the Dockerfile default is
# then used, so a pin bump there is picked up without editing .env.
# After the restart it waits for /api/health to report the OPSIN it asked for.
set -euo pipefail
cd "$(dirname "$0")"

MAIN_PIN=$(sed -n 's/^ARG ORTHONYM_OPSIN=//p' backend/Dockerfile)
MAIN_LABEL="main $(printf '%s' "${MAIN_PIN#main@}" | cut -c1-7)"
current=$(sed -n 's/^ORTHONYM_OPSIN=//p' .env 2>/dev/null | tail -n 1)

echo "OPSIN in .env now: ${current:-not set, so the Dockerfile default ($MAIN_LABEL)}"
echo
echo "Which OPSIN should the site use?"
echo "  1) OPSIN $MAIN_LABEL  (default) reads em-dash adduct names and phane names"
echo "  2) OPSIN 2.9.0        the release, same as 'pip install orthonym' (rollback)"
read -r -p "Choose 1 or 2 [1]: " pick
case "${pick:-1}" in
  1) opsin=""; want=$MAIN_LABEL ;;
  2) opsin=2.9.0; want=2.9.0 ;;
  *) echo "Not 1 or 2. Nothing changed." >&2; exit 1 ;;
esac

read -r -p "Rebuild and restart the stack with OPSIN $want? [y/N]: " ok
case "$ok" in y|Y|yes) ;; *) echo "Nothing changed."; exit 0 ;; esac

# Rewrite .env in place (cat >, not mv, so its owner and mode stay) with every
# other line kept.
touch .env
tmp=$(mktemp)
grep -v '^ORTHONYM_OPSIN=' .env > "$tmp" || true
if [ -n "$opsin" ]; then echo "ORTHONYM_OPSIN=$opsin" >> "$tmp"; fi
cat "$tmp" > .env
rm -f "$tmp"

docker compose up -d --build

# ponytail: polls the loopback port compose publishes; change the URL if the
# backend port binding in docker-compose.yml changes.
echo "Waiting for /api/health to say OK with OPSIN $want ..."
for _ in $(seq 60); do
  health=$(curl -fsS -m 5 http://127.0.0.1:8000/api/health 2>/dev/null || true)
  if printf '%s' "$health" | grep -q '"status":"OK"' \
     && printf '%s' "$health" | grep -q "\"opsin_version\":\"$want\""; then
    echo "Done: $health"
    exit 0
  fi
  sleep 5
done
echo "FAILED: after 5 minutes /api/health says: ${health:-no answer}" >&2
echo "Look at: docker compose ps; docker compose logs backend worker-fast" >&2
exit 1
