#!/usr/bin/env bash
# scripts/test-structured-invocation.sh — end-to-end probe of the
# Audit View "Run Standalone" endpoint for each specialist.
#
# Posts a known-good payload to /api/skill/{id}/structured for docparse,
# ap-validator, and ap-poster, and asserts a 200 response with the
# expected shape (`text`, `tool_calls`, `duration_ms`).
#
# Catches three regression classes:
#   1. Schema missing (400 structured_input_not_supported)
#   2. Schema rejects valid input (400 structured_input_invalid)
#   3. Endpoint shape changes (missing keys in response)
#
# Skip-don't-fail: no AIPLATFORM_ID_TOKEN => exit 0 with a skip line.
# Hard fail (exit 1): backend reachable but invocation broken.
#
# Usage:
#   AIPLATFORM_ID_TOKEN=<firebase-token> ./scripts/test-structured-invocation.sh
#   AIPLATFORM_ID_TOKEN=<token> ./scripts/test-structured-invocation.sh validator
#
# Env vars:
#   GDE_AP_URL            — backend URL (default: dev demo)
#   AIPLATFORM_ID_TOKEN   — Firebase ID token (required)
#   TEST_DOC_ID           — Firestore parsed_documents id for the
#                           docparse probe (optional; falls back to
#                           a sentinel — docparse will return a
#                           "not found" message but still 200, which
#                           verifies the endpoint+schema work)

set -euo pipefail

DEFAULT_URL="https://gde-ap-agent-blqtqfexwa-ew.a.run.app"
URL="${GDE_AP_URL:-$DEFAULT_URL}"
URL="${URL%/}"
TARGET="${1:-all}"

skip()    { echo "skipping test-structured-invocation — $1" >&2; exit 0; }
ok()      { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
fail()    { printf "  \033[31mFAIL\033[0m %s\n" "$1"; }
section() { echo ""; echo "-- $1 --"; }

command -v curl >/dev/null 2>&1 || skip "curl not on PATH"
command -v jq   >/dev/null 2>&1 || skip "jq not on PATH"

if [[ -z "${AIPLATFORM_ID_TOKEN:-}" ]]; then
    skip "AIPLATFORM_ID_TOKEN not set — required for authenticated POST"
fi

echo "== test-structured-invocation =="
echo "URL: ${URL}"

# Discover specialist skill ids from the public marketplace.
TMP_SKILLS=$(mktemp)
trap 'rm -f "$TMP_SKILLS" /tmp/sti-*.json' EXIT
code=$(curl -sS -o "$TMP_SKILLS" -w '%{http_code}' --max-time 30 \
    "${URL}/api/proxy/api/skills/marketplace") || code=000
if [[ "$code" != "200" ]]; then
    fail "marketplace endpoint -> ${code}"
    exit 1
fi

skill_id_for() {
    jq -r --arg n "$1" '[ .[] | select(.name == $n) ][0].skillId // empty' "$TMP_SKILLS"
}

DOCPARSE_ID=$(skill_id_for docparse)
VALIDATOR_ID=$(skill_id_for ap-validator)
POSTER_ID=$(skill_id_for ap-poster)

probe() {
    local name="$1" skill_id="$2" payload="$3"
    section "${name} (${skill_id})"
    if [[ -z "$skill_id" ]]; then
        fail "${name}: not found in marketplace"
        return 1
    fi
    local out="/tmp/sti-${name}.json"
    local code
    code=$(curl -sS -o "$out" -w '%{http_code}' --max-time 60 \
        -X POST \
        -H "Authorization: Bearer ${AIPLATFORM_ID_TOKEN}" \
        -H "Content-Type: application/json" \
        --data "$payload" \
        "${URL}/api/proxy/api/skill/${skill_id}/structured") || code=000

    case "$code" in
        200)
            local has_text has_tools has_duration
            has_text=$(jq -r 'has("text")' "$out")
            has_tools=$(jq -r 'has("tool_calls")' "$out")
            has_duration=$(jq -r 'has("duration_ms")' "$out")
            if [[ "$has_text" = "true" && "$has_tools" = "true" && "$has_duration" = "true" ]]; then
                local dur tc_count text_len
                dur=$(jq -r '.duration_ms' "$out")
                tc_count=$(jq -r '.tool_calls | length' "$out")
                text_len=$(jq -r '.text | length' "$out")
                ok "${name}: 200 (text=${text_len} chars, tool_calls=${tc_count}, duration=${dur}ms)"
                return 0
            fi
            fail "${name}: 200 but unexpected shape (text=${has_text}, tool_calls=${has_tools}, duration_ms=${has_duration})"
            head -c 400 "$out" >&2; echo "" >&2
            return 1
            ;;
        400)
            local err msg errors
            err=$(jq -r '.detail.error // "unknown"' "$out")
            msg=$(jq -r '.detail.message // "no message"' "$out")
            errors=$(jq -r '.detail.errors // [] | join("; ")' "$out")
            if [[ "$err" = "structured_input_not_supported" ]]; then
                fail "${name}: schema missing in Firestore — run verify-skill-schemas.sh and re-seed"
            else
                fail "${name}: 400 ${err}: ${msg} ${errors}"
            fi
            return 1
            ;;
        401|403)
            fail "${name}: ${code} — Firebase token invalid/expired (refresh AIPLATFORM_ID_TOKEN)"
            return 1
            ;;
        *)
            fail "${name}: HTTP ${code}"
            head -c 400 "$out" >&2; echo "" >&2
            return 1
            ;;
    esac
}

DOCPARSE_PAYLOAD=$(cat <<EOF
{"input": {"document_id": "${TEST_DOC_ID:-sti-probe-no-such-doc}"}}
EOF
)
VALIDATOR_PAYLOAD=$(cat <<'EOF'
{"input": {
  "vendor_name": "Acme GmbH",
  "vendor_id": "V-1042",
  "invoice_number": "INV-2026-042",
  "invoice_date": "2026-05-15",
  "due_date": "2026-06-14",
  "po_reference": "PO-77820",
  "currency": "EUR",
  "line_items": [{"description":"Consulting May","quantity":1,"unit_price":8500,"amount":8500}],
  "subtotal": 8500, "tax": 0, "total": 8500
}}
EOF
)
POSTER_PAYLOAD=$(cat <<'EOF'
{"input": {
  "verdict": "pass",
  "invoice": {"vendor_name": "Acme GmbH","invoice_number": "INV-2026-042","total": 8500,"currency": "EUR"},
  "reasons": []
}}
EOF
)

rc=0
case "$TARGET" in
    docparse)  probe docparse "$DOCPARSE_ID" "$DOCPARSE_PAYLOAD" || rc=$? ;;
    validator) probe ap-validator "$VALIDATOR_ID" "$VALIDATOR_PAYLOAD" || rc=$? ;;
    poster)    probe ap-poster "$POSTER_ID" "$POSTER_PAYLOAD" || rc=$? ;;
    all)
        probe docparse "$DOCPARSE_ID" "$DOCPARSE_PAYLOAD" || rc=1
        probe ap-validator "$VALIDATOR_ID" "$VALIDATOR_PAYLOAD" || rc=1
        probe ap-poster "$POSTER_ID" "$POSTER_PAYLOAD" || rc=1
        ;;
    *) echo "Unknown target: $TARGET (use all|docparse|validator|poster)"; exit 2 ;;
esac

echo ""
[[ $rc -eq 0 ]] && echo "All structured-invocation probes passed." || echo "One or more probes failed."
exit $rc
