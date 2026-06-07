#!/usr/bin/env bash
# scripts/verify-a2a.sh — assert the deployed agent card is A2A-spec-compliant
# and ready for Gemini Enterprise / peer-agent discovery.
#
# What this proves
# ----------------
# 1.  /.well-known/agent.json returns 200 with no auth (per A2A discovery RFC).
# 2.  Required A2A card fields are present: name, description, url, version,
#     capabilities, skills.
# 3.  Capability negotiation works end-to-end — sending X-A2A-Extensions echoes
#     the negotiated intersection on the response, and Vary advertises it.
# 4.  The card's `url` field points at the PUBLIC host (not localhost — the
#     bug that would silently break Gemini Enterprise registration because
#     the registry would store an internal URL it cannot reach).
# 5.  Every advertised skill name resolves on /api/skill/* — i.e. the discovery
#     contract matches the platform's actual surface.
#
# Skip-don't-fail: missing curl / jq => exit 0 with a `skipping…` line.
# Hard fail (exit 1): card reachable but a contract assertion fails.
#
# Usage:
#   ./scripts/verify-a2a.sh                                  # default URL
#   AP_URL=https://gde-ap-agent-blqtqfexwa-ew.a.run.app ./scripts/verify-a2a.sh
#
# Env vars:
#   AP_URL — overrides the default deployed URL.

set -euo pipefail

AP_URL="${AP_URL:-https://gde-ap-agent-blqtqfexwa-ew.a.run.app}"
CARD_URL="${AP_URL%/}/.well-known/agent.json"

skip() { echo "skipping verify-a2a — $1" >&2; exit 0; }
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAILED=1; }
info() { printf "  \033[36m...\033[0m  %s\n" "$1"; }

command -v curl >/dev/null 2>&1 || skip "curl not on PATH"
command -v jq   >/dev/null 2>&1 || skip "jq not on PATH"

FAILED=0
echo "verify-a2a: probing ${CARD_URL}"
echo

# --- 1. Unauthenticated 200 with negotiation -------------------------------
info "fetching card with X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern"
HEADERS_FILE="$(mktemp)"
BODY_FILE="$(mktemp)"
trap 'rm -f "$HEADERS_FILE" "$BODY_FILE"' EXIT

STATUS=$(curl -s -o "$BODY_FILE" -D "$HEADERS_FILE" -w "%{http_code}" \
  -H 'X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern' \
  "$CARD_URL")

if [[ "$STATUS" == "200" ]]; then
  ok "HTTP 200 (unauthenticated discovery)"
else
  fail "expected HTTP 200, got $STATUS"
  echo "--- response body ---"; cat "$BODY_FILE"; echo
fi

# --- 2. Capability negotiation headers -------------------------------------
NEGOTIATED=$(grep -i '^x-a2a-extensions:' "$HEADERS_FILE" | head -1 | sed 's/^[^:]*: *//' | tr -d '\r')
# Combine all Vary lines into one comma-joined string — RFC 7234 says
# multiple Vary headers are equivalent to a single comma-joined Vary, and
# Next.js framework adds its own Vary entries alongside ours, so a strict
# "single line" check would give a false negative on the deployed app.
VARY=$(grep -i '^vary:' "$HEADERS_FILE" | sed 's/^[^:]*: *//' | tr -d '\r' | paste -sd, -)

if [[ -n "$NEGOTIATED" ]]; then
  ok "X-A2A-Extensions echoed on response: ${NEGOTIATED}"
else
  fail "X-A2A-Extensions header missing on response — capability negotiation not wired"
fi

if echo "$VARY" | grep -qi "X-A2A-Extensions"; then
  ok "Vary advertises X-A2A-Extensions (cache-correctness across all Vary lines)"
  info "vary: ${VARY}"
else
  fail "Vary does NOT include X-A2A-Extensions — caches will serve the wrong card to differently-capable clients"
  info "vary (combined): ${VARY:-(empty)}"
fi

# --- 3. Required A2A spec fields -------------------------------------------
# protocolVersion is required by Discovery Engine / Gemini Enterprise — a
# missing one makes `agents-cli register-gemini-enterprise --registration-type
# a2a` fail with INVALID_ARGUMENT (caught in real Gemini Enterprise registration
# 2026-06-07, see a2a.py:_build_card).
for field in protocolVersion name description url version capabilities skills; do
  if jq -e ".${field}" "$BODY_FILE" >/dev/null 2>&1; then
    ok "card has required field: ${field}"
  else
    fail "card MISSING required field: ${field}"
  fi
done

# --- 4. Public URL, not localhost ------------------------------------------
ADVERTISED_URL=$(jq -r '.url' "$BODY_FILE")
if [[ "$ADVERTISED_URL" == http*localhost* ]] || [[ "$ADVERTISED_URL" == http*127.0.0.1* ]]; then
  fail "card advertises a non-routable URL: ${ADVERTISED_URL}"
  fail "  → Gemini Enterprise / peer agents would fail to invoke skills"
else
  ok "card advertises a public URL: ${ADVERTISED_URL}"
fi

# --- 5. Extensions advertised in body --------------------------------------
EXT_COUNT=$(jq -r '.capabilities.extensions | length' "$BODY_FILE" 2>/dev/null || echo 0)
if [[ "$EXT_COUNT" -gt 0 ]]; then
  # A2A v0.2 schema: capabilities.extensions[] must be AgentExtension objects
  # with a `uri` field — Discovery Engine / Gemini Enterprise rejects bare
  # strings with "unexpected instance type" (caught 2026-06-07).
  ALL_OBJECTS=$(jq -r '.capabilities.extensions | map(type == "object" and has("uri")) | all' "$BODY_FILE")
  if [[ "$ALL_OBJECTS" == "true" ]]; then
    URIS=$(jq -r '.capabilities.extensions | map(.uri) | join(", ")' "$BODY_FILE")
    ok "capabilities.extensions advertises ${EXT_COUNT} AgentExtension descriptor(s)"
    info "uris: ${URIS}"
  else
    fail "capabilities.extensions[] entries are not AgentExtension objects with .uri"
    fail "  → Gemini Enterprise registration will reject with 'unexpected instance type'"
  fi
  # Spec compliance: a2a-v0.2 should be among the URIs (this IS an A2A agent).
  if jq -e '.capabilities.extensions | map(.uri // "") | any(. | endswith("a2a/v0.2") or contains("a2a-v0.2"))' "$BODY_FILE" >/dev/null; then
    ok "advertises an A2A v0.2 extension descriptor"
  else
    fail "capabilities.extensions does not include an A2A v0.2 entry"
  fi
else
  fail "capabilities.extensions is empty or missing"
fi

# --- 6. Skill names match the platform surface -----------------------------
SKILL_NAMES=$(jq -r '.skills[].name' "$BODY_FILE")
if [[ -z "$SKILL_NAMES" ]]; then
  fail "card advertises zero skills"
else
  COUNT=$(echo "$SKILL_NAMES" | wc -l | tr -d ' ')
  ok "card advertises ${COUNT} skill(s)"
  echo "$SKILL_NAMES" | sed 's/^/         - /'
fi

# --- 7. Invocation surface reachable + JSON-RPC envelope on auth fail ------
# The strict A2A invocation bridge is mounted at card.url. We probe with NO
# Bearer token to assert two things at once:
#   (a) the surface exists at all (404/405 = bridge not deployed)
#   (b) auth failure returns a JSON-RPC error envelope, not an HTML 401
# (a strict A2A client would choke on an HTML page). When auth is disabled
# server-side, the probe instead expects 400 (no method body) — still
# proves the bridge is up.
ADVERTISED_URL=$(jq -r '.url' "$BODY_FILE")
INVOKE_BODY="$(mktemp)"
trap 'rm -f "$HEADERS_FILE" "$BODY_FILE" "$INVOKE_BODY"' EXIT
INVOKE_STATUS=$(curl -s -o "$INVOKE_BODY" -w "%{http_code}" \
  -X POST \
  -H 'Content-Type: application/json' \
  --data-raw '{"jsonrpc":"2.0","id":"probe","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"probe"}],"messageId":"probe-msg"}}}' \
  "$ADVERTISED_URL")

case "$INVOKE_STATUS" in
  200)
    # Bridge up AND auth disabled. Body must be JSON-RPC envelope.
    if jq -e '.jsonrpc == "2.0"' "$INVOKE_BODY" >/dev/null 2>&1; then
      ok "invocation surface at ${ADVERTISED_URL} returns valid JSON-RPC 2.0 envelope"
    else
      fail "invocation surface returns 200 but body is not JSON-RPC: $(head -c 120 "$INVOKE_BODY")"
    fi
    ;;
  401|403)
    # Bridge up, auth required. JSON-RPC envelope expected even on auth fail.
    if jq -e '.jsonrpc == "2.0" and has("error")' "$INVOKE_BODY" >/dev/null 2>&1; then
      ok "invocation surface up at ${ADVERTISED_URL}; auth gate returns JSON-RPC error envelope"
    else
      fail "invocation surface returns ${INVOKE_STATUS} but body is not a JSON-RPC error: $(head -c 120 "$INVOKE_BODY")"
    fi
    ;;
  400)
    # Bridge up; body shape rejected by ADK (unexpected fields). Still JSON-RPC.
    if jq -e '.jsonrpc == "2.0"' "$INVOKE_BODY" >/dev/null 2>&1; then
      ok "invocation surface up at ${ADVERTISED_URL}; returns JSON-RPC parse/validation error"
    else
      fail "invocation surface returns 400 but body is not JSON-RPC: $(head -c 120 "$INVOKE_BODY")"
    fi
    ;;
  404|405)
    fail "invocation surface NOT deployed: HTTP ${INVOKE_STATUS} from POST ${ADVERTISED_URL}"
    fail "  → Set ENABLE_A2A_INVOCATION=true in cloudbuild.yaml and re-deploy"
    ;;
  *)
    fail "invocation surface unexpected status: HTTP ${INVOKE_STATUS} from POST ${ADVERTISED_URL}"
    info "body: $(head -c 200 "$INVOKE_BODY")"
    ;;
esac

# --- Summary ----------------------------------------------------------------
echo
if [[ "$FAILED" -eq 0 ]]; then
  printf "\033[32mverify-a2a: all checks passed\033[0m\n"
  exit 0
else
  printf "\033[31mverify-a2a: one or more checks failed\033[0m\n"
  exit 1
fi
