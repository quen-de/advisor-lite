#!/usr/bin/env bash
set -euo pipefail
base="http://localhost:8080/api"
for i in $(seq 1 30); do curl -fsS "$base/healthz" >/dev/null 2>&1 && break || sleep 2; done
curl -fsS "$base/healthz" | grep -q '"ok"'
chat_id=$(curl -fsS -X POST "$base/chats" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
# Leave no TestModel artifacts behind: the db volume is shared with dev runs.
trap 'curl -fsS -X DELETE "$base/chats/$chat_id" >/dev/null || true' EXIT
reply=$(curl -fsS -N -X POST "$base/chats/$chat_id/messages" \
  -H 'content-type: application/json' -d '{"content":"What do I hold?"}')
echo "$reply" | grep -q 'event: delta'
echo "$reply" | grep -q 'event: sources'
echo "$reply" | grep -q 'event: done'
curl -fsS "$base/chats/$chat_id/exchanges" | grep -q 'What do I hold?'
echo "SMOKE OK"
