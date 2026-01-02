#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8766}"
CNAME="${CNAME:-tests}"
ANAME="${ANAME:-smoke_hello}"

hr() { echo; echo "============================================================"; }
say() { echo; echo ">>> $*"; }

say "BASE=$BASE  CNAME=$CNAME  ANAME=$ANAME"
hr

say "GET /health"
curl -sS "$BASE/health"; echo
hr

say "GET /containers"
curl -sS "$BASE/containers"; echo
hr

say "POST /containers (create, may fail if exists)"
curl -sS -X POST "$BASE/containers" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$CNAME\",\"description\":\"smoke container\"}"; echo
hr

say "GET /containers (check description from metadata)"
curl -sS "$BASE/containers"; echo
hr

say "POST /containers/$CNAME/start (may fail if already running)"
curl -sS -X POST "$BASE/containers/$CNAME/start"; echo
hr

say "GET /containers/$CNAME/vnc_url (optional)"
curl -sS "$BASE/containers/$CNAME/vnc_url"; echo
hr

say "POST /automations/save (writes DB + exports script)"
cat > /tmp/auto.json <<JSON
{
  "name": "$ANAME",
  "description": "smoke test",
  "container": "$CNAME",
  "vars": [],
  "steps": [
    {
      "label": "notify",
      "action": "notify",
      "enabled": 1,
      "note": "",
      "params": [
        {"key":"title","type":"str","value":"AUTOMATR"},
        {"key":"msg","type":"str","value":"smoke hello"}
      ],
      "clauses": []
    },
    {
      "label": "sleep",
      "action": "sleep",
      "enabled": 1,
      "note": "",
      "params": [
        {"key":"seconds","type":"float","value":"0.2"}
      ],
      "clauses": []
    }
  ]
}
JSON

curl -sS -X POST "$BASE/automations/save" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/auto.json; echo
hr

say "GET /automations"
curl -sS "$BASE/automations"; echo
hr

say "GET /automations/$ANAME"
curl -sS "$BASE/automations/$ANAME"; echo
hr

say "GET /actions/check (wrapper public vs DB distinct)"
curl -sS "$BASE/actions/check"; echo
hr

say "POST /containers/$CNAME/run"
curl -sS -X POST "$BASE/containers/$CNAME/run" \
  -H "Content-Type: application/json" \
  -d "{\"automation\":\"$ANAME\"}"; echo
hr

hr
say "GET /containers/$CNAME (single container detail)"
curl -sS "$BASE/containers/$CNAME"; echo
hr

say "GET /automations/$ANAME/graph (canonical editor shape)"
curl -sS "$BASE/automations/$ANAME/graph"; echo
hr

say "POST /containers/$CNAME/stop_auto"
curl -sS -X POST "$BASE/containers/$CNAME/stop_auto"; echo
hr

say "POST /containers/$CNAME/clear_stop"
curl -sS -X POST "$BASE/containers/$CNAME/clear_stop"; echo
hr

say "POST /containers/$CNAME/restart"
curl -sS -X POST "$BASE/containers/$CNAME/restart"; echo
hr

say "DELETE /automations/$ANAME"
curl -sS -X DELETE "$BASE/automations/$ANAME"; echo
hr

say "POST /containers/$CNAME/stop"
curl -sS -X POST "$BASE/containers/$CNAME/stop"; echo
hr

say "DONE"
