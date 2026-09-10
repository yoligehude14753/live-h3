#!/usr/bin/env bash
# run_orchestrator.sh — start the queue + dispatcher.
# Reads worker URLs from config/orchestrator.env (see .example).
set -euo pipefail

CONFIG="${1:-./config/orchestrator.env}"
[ -f "$CONFIG" ] || { echo "missing $CONFIG (copy from config/orchestrator.env.example)" >&2; exit 1; }
# shellcheck disable=SC1090
source "$CONFIG"

[ -n "${WORKER_URLS:-}" ] || { echo "WORKER_URLS is empty in $CONFIG" >&2; exit 1; }

echo "[orchestrator] workers:"
IFS=',' read -ra URLS <<< "$WORKER_URLS"
for u in "${URLS[@]}"; do
  printf '  - %s  ' "$u"
  if curl -sf --max-time 3 "$u/system_stats" >/dev/null; then
    echo "OK"
  else
    echo "UNREACHABLE (will be skipped until healthy)"
  fi
done

# The orchestrator itself is a small service: accept jobs, shard frame ranges,
# POST /prompt to idle workers, collect terminal receipts, assemble output.
# Implement against the contract in docs/architecture.md; nothing here is
# host-specific — workers are just URLs.
echo "[orchestrator] ready on :${ORCHESTRATOR_PORT:-8300}"
echo "[orchestrator] implement dispatcher per docs/architecture.md (queue + /prompt + receipts)"
