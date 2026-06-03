#!/usr/bin/env bash
# scripts/verify-judge-path.sh — WORKFLOW-PIPELINE M5 end-to-end check.
#
# The "judge path" is the demo flow we want bullet-proofed before
# submission to the Google AI Agents Challenge (Track 3):
#
#   1. User opens deployed dev → /chat/@gde-ap-agent/ap-orchestrator
#   2. Uploads or selects a demo invoice
#   3. Says "please process this invoice"
#   4. Pipeline rail advances Intake → Extract → Validate → Post
#   5. Workspace pane renders the Invoice Review Card
#
# Two layers of verification:
#
#   - **Unauthenticated** (always runs): the service is reachable and
#     the Cloud Run revision in the multivac-internal-dev project is
#     newer than the WORKFLOW-PIPELINE landing commit.
#
#   - **Authenticated** (runs only when AIPLATFORM_ID_TOKEN is set):
#     hits the proxied /api/skills endpoints to verify that the
#     ap-pipeline skill exists with agent_type=sequential, that
#     ap-orchestrator.subSkills points to it, and that the MCP server
#     references are wired into the validator + poster.
#
# Per-tool MCP behaviour, A2A extension advertisement, and per-specialist
# STAGE_PROGRESS labels are covered by the unit-test suite (backend
# make test-fast — 1463 tests). The live AG-UI stream + workspace card
# are verified by the manual UI checklist this script prints at the end.
#
# Exit 0 on success, 1 on first failure.
#
# Usage:
#   ./scripts/verify-judge-path.sh                # dev (default)
#   AIPLATFORM_ID_TOKEN=<token> ./scripts/verify-judge-path.sh  # + API checks
#   GDE_AP_URL=https://my-fork.run.app ./scripts/verify-judge-path.sh

set -euo pipefail

ENV="${1:-dev}"

case "$ENV" in
  dev)
    DEFAULT_URL="https://gde-ap-agent-blqtqfexwa-ew.a.run.app"
    GCP_PROJECT="multivac-internal-dev"
    GCP_REGION="europe-west1"
    SERVICE_NAME="gde-ap-agent"
    ;;
  test|prod)
    DEFAULT_URL=""
    GCP_PROJECT=""
    ;;
  *) echo "Unknown env: $ENV (use dev|test|prod)"; exit 2 ;;
esac

URL="${GDE_AP_URL:-$DEFAULT_URL}"
if [[ -z "$URL" ]]; then
  echo "FAIL: no URL configured for env=$ENV; set GDE_AP_URL"
  exit 1
fi

echo "================================================================"
echo " WORKFLOW-PIPELINE judge-path verification"
echo "   env: $ENV"
echo "   url: $URL"
echo "================================================================"

rc=0
passed=0
failed=0
skipped=0

pass()   { echo "PASS  $1"; passed=$((passed + 1)); }
fail()   { echo "FAIL  $1"; failed=$((failed + 1)); rc=1; }
skip()   { echo "SKIP  $1"; skipped=$((skipped + 1)); }

# -----------------------------------------------------------------
# 1. Frontend reachable
# -----------------------------------------------------------------
echo ""
echo "-- 1. Frontend reachable --"
http_code=$(curl -s -o /dev/null -w "%{http_code}" "$URL/" || echo "000")
if [[ "$http_code" == "200" ]]; then
  pass "GET / -> 200"
else
  fail "GET / -> $http_code (expected 200)"
fi

# -----------------------------------------------------------------
# 2. Cloud Run revision contains the WORKFLOW-PIPELINE commits
# -----------------------------------------------------------------
echo ""
echo "-- 2. Deployed revision --"
if ! command -v gcloud >/dev/null 2>&1; then
  skip "gcloud not on PATH, can't inspect Cloud Run revision"
elif [[ -z "$GCP_PROJECT" ]]; then
  skip "no GCP project configured for env=$ENV"
else
  latest_rev=$(gcloud run services describe "$SERVICE_NAME" \
    --project="$GCP_PROJECT" --region="$GCP_REGION" \
    --format='value(status.latestReadyRevisionName)' 2>/dev/null || echo "")
  if [[ -z "$latest_rev" ]]; then
    fail "could not resolve latest revision for $SERVICE_NAME"
  else
    pass "Latest revision: $latest_rev"
    # The revision name embeds a serial number — confirm it's >= the
    # WORKFLOW-PIPELINE landing baseline (rev 54 = M2). M5 verification
    # expects the current build to be > rev 54.
    # Strip leading zeros so bash arithmetic doesn't parse as octal
    rev_num=$(echo "$latest_rev" | grep -oE '[0-9]+' | head -1 | sed 's/^0*//')
    rev_num="${rev_num:-0}"
    if [[ "$rev_num" -ge 55 ]]; then
      pass "Revision number $rev_num >= 55 (WORKFLOW-PIPELINE baseline)"
    else
      fail "Revision number $rev_num < 55 — WORKFLOW-PIPELINE build hasn't landed"
    fi
  fi
fi

# -----------------------------------------------------------------
# 3. Authenticated structural checks (only when token is provided)
# -----------------------------------------------------------------
echo ""
echo "-- 3. Skill structure (API, requires AIPLATFORM_ID_TOKEN) --"

if [[ -z "${AIPLATFORM_ID_TOKEN:-}" ]]; then
  skip "AIPLATFORM_ID_TOKEN not set — skipping authenticated API checks"
  skip "  to enable: AIPLATFORM_ID_TOKEN=\$(gcloud auth print-identity-token --audiences=\"$URL\") ./scripts/verify-judge-path.sh"
else
  auth_hdr="-H 'Authorization: Bearer $AIPLATFORM_ID_TOKEN'"

  fetch_skill() {
    local slug="$1"
    # Output: response body if 2xx, empty string on any error/non-2xx
    curl -fsS \
      -H "Authorization: Bearer $AIPLATFORM_ID_TOKEN" \
      "$URL/api/proxy/api/skills/by-slug/gde-ap-agent/$slug" 2>/dev/null || echo ""
  }

  # ap-pipeline
  pipe_resp=$(fetch_skill "ap-pipeline")
  if [[ -z "$pipe_resp" ]]; then
    fail "ap-pipeline skill not reachable (auth ok? deploy ok?)"
  else
    if echo "$pipe_resp" | grep -qE '"agentType"[[:space:]]*:[[:space:]]*"sequential"|"agent_type"[[:space:]]*:[[:space:]]*"sequential"'; then
      pass "ap-pipeline.agent_type == sequential"
    else
      fail "ap-pipeline.agent_type != sequential"
      echo "    body[:300]: $(echo "$pipe_resp" | head -c 300)…"
    fi
    if echo "$pipe_resp" | grep -qE '"subSkills"[[:space:]]*:[[:space:]]*\[[[:space:]]*"invoice-extractor"[[:space:]]*,[[:space:]]*"ap-validator"[[:space:]]*,[[:space:]]*"ap-poster"[[:space:]]*\]'; then
      pass "ap-pipeline.subSkills == [invoice-extractor, ap-validator, ap-poster]"
    else
      fail "ap-pipeline.subSkills not in Extract → Validate → Post order"
    fi
  fi

  # ap-orchestrator
  orc_resp=$(fetch_skill "ap-orchestrator")
  if [[ -z "$orc_resp" ]]; then
    fail "ap-orchestrator skill not reachable"
  elif echo "$orc_resp" | grep -qE '"subSkills"[[:space:]]*:[[:space:]]*\[[[:space:]]*"ap-pipeline"[[:space:]]*\]'; then
    pass "ap-orchestrator.subSkills == [ap-pipeline]"
  else
    fail "ap-orchestrator.subSkills != [ap-pipeline]"
  fi

  # ap-validator references vendor-master
  val_resp=$(fetch_skill "ap-validator")
  if [[ -z "$val_resp" ]]; then
    fail "ap-validator skill not reachable"
  elif echo "$val_resp" | grep -q '"vendor-master"'; then
    pass "ap-validator references vendor-master MCP server"
  else
    fail "ap-validator does NOT reference vendor-master MCP server"
  fi

  # ap-poster references erp-posting
  pos_resp=$(fetch_skill "ap-poster")
  if [[ -z "$pos_resp" ]]; then
    fail "ap-poster skill not reachable"
  elif echo "$pos_resp" | grep -q '"erp-posting"'; then
    pass "ap-poster references erp-posting MCP server"
  else
    fail "ap-poster does NOT reference erp-posting MCP server"
  fi
fi

# -----------------------------------------------------------------
echo ""
echo "================================================================"
echo " Summary: $passed passed, $failed failed, $skipped skipped"
echo "================================================================"

if [[ $rc -eq 0 ]]; then
  cat <<'TIP'

Static structural checks passed. The remaining judge-path verification
is MANUAL (visual) — open the deployed URL and:

  1. Pick the ap-orchestrator chat from the marketplace
  2. Select a demo invoice from the GCS browser pane
  3. Say "please process this invoice"
  4. CONFIRM the pipeline rail advances Intake → Extract → Validate → Post
  5. CONFIRM the workspace pane renders an Invoice Review Card with vendor,
     invoice #, total, verdict, and action buttons
  6. CONFIRM the audit view shows per-agent streaming reasoning +
     schema-enforced JSON for each specialist
  7. CONFIRM the typing indicator shows "Extracting invoice fields…",
     "Validating against vendor master + policy…", and "Posting to AP
     ledger…" labels during the respective stages
  8. NEGATIVE: with no document loaded, ask "process this invoice" and
     CONFIRM the intake gate's friendly "please upload" message appears
     without running the pipeline

If any of the above fails, capture the session_id and inspect Cloud Trace
for the four expected spans:
  invoke_agent ap_pipeline → 3x invoke_agent <specialist>
TIP
fi
exit $rc
