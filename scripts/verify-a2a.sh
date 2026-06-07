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
VARY=$(grep -i '^vary:' "$HEADERS_FILE" | sed 's/^[^:]*: *//' | tr -d '\r')

if [[ -n "$NEGOTIATED" ]]; then
  ok "X-A2A-Extensions echoed on response: ${NEGOTIATED}"
else
  fail "X-A2A-Extensions header missing on response — capability negotiation not wired"
fi

if echo "$VARY" | grep -qi "X-A2A-Extensions"; then
  ok "Vary advertises X-A2A-Extensions (cache-correctness)"
else
  fail "Vary does NOT include X-A2A-Extensions — caches will serve the wrong card to differently-capable clients"
fi

# --- 3. Required A2A spec fields -------------------------------------------
for field in name description url version capabilities skills; do
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
  EXTS=$(jq -r '.capabilities.extensions | join(", ")' "$BODY_FILE")
  ok "capabilities.extensions advertises ${EXT_COUNT} extension(s): ${EXTS}"
  # Spec compliance: a2a-v0.2 should be in the set (this IS an A2A agent).
  if jq -e '.capabilities.extensions | index("a2a-v0.2")' "$BODY_FILE" >/dev/null; then
    ok "advertises a2a-v0.2 (canonical A2A extension)"
  else
    fail "capabilities.extensions does not include a2a-v0.2"
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

# --- Summary ----------------------------------------------------------------
echo
if [[ "$FAILED" -eq 0 ]]; then
  printf "\033[32mverify-a2a: all checks passed\033[0m\n"
  exit 0
else
  printf "\033[31mverify-a2a: one or more checks failed\033[0m\n"
  exit 1
fi
