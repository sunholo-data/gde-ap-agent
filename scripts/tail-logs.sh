#!/usr/bin/env bash
# scripts/tail-logs.sh — pull Cloud Run logs for the GDE AP Agent backend.
#
# Default: recent errors (severity>=ERROR) in the last hour. Pass `tail`
# to stream live, `chat` to filter on chat-stream path errors, or a raw
# Logging filter to override.
#
# Usage:
#   ./scripts/tail-logs.sh                       # recent errors (1h)
#   ./scripts/tail-logs.sh tail                  # live tail
#   ./scripts/tail-logs.sh chat                  # filter chat-stream 500s
#   ./scripts/tail-logs.sh 24h                   # widen lookback
#   ./scripts/tail-logs.sh 'severity>=WARNING'   # custom filter
#
# Env vars:
#   GCP_PROJECT — project id (default: gde-ap-agent)
#   GCP_ACCOUNT — gcloud account to use (default: active)
#   SERVICE     — Cloud Run service name (default: gde-ap-agent)
#
# Requires: gcloud auth with logging.viewer on the target project.
# Skip-don't-fail: missing gcloud / no project access => exit 0 with hint.

set -euo pipefail

PROJECT="${GCP_PROJECT:-gde-ap-agent}"
SERVICE="${SERVICE:-gde-ap-agent}"
ACCT_ARG=""
if [[ -n "${GCP_ACCOUNT:-}" ]]; then
  ACCT_ARG="--account=${GCP_ACCOUNT}"
fi

ARG="${1:-1h}"

skip() { echo "skipping tail-logs — $1" >&2; exit 0; }

command -v gcloud >/dev/null 2>&1 || skip "gcloud not on PATH"

# Resolve mode + filter
case "$ARG" in
  tail|stream)
    echo "== Streaming logs from $PROJECT (service=$SERVICE). Ctrl-C to stop. ==" >&2
    exec gcloud beta logging tail \
      "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE}\"" \
      --project="$PROJECT" $ACCT_ARG \
      --format='value(timestamp,severity,textPayload,jsonPayload.message)'
    ;;
  chat)
    FILTER='resource.type="cloud_run_revision" AND severity>=ERROR AND (textPayload:"500" OR textPayload:"Internal Server Error" OR jsonPayload.message:"500" OR httpRequest.status=500 OR textPayload:"stream_skill" OR textPayload:"process_skill_request")'
    FRESHNESS="2h"
    ;;
  1h|6h|12h|24h|1d|7d)
    FILTER='resource.type="cloud_run_revision" AND severity>=ERROR'
    FRESHNESS="$ARG"
    ;;
  severity*|resource*|http*|json*|text*|labels*|trace*|*\>*|*\<*|*\=*)
    FILTER="resource.type=\"cloud_run_revision\" AND ${ARG}"
    FRESHNESS="1h"
    ;;
  *)
    echo "Unknown arg: $ARG" >&2
    echo "Use: 1h | 24h | tail | chat | <raw Logging filter>" >&2
    exit 2
    ;;
esac

echo "== Logs from $PROJECT (service=$SERVICE, freshness=$FRESHNESS) ==" >&2
echo "Filter: $FILTER" >&2
echo "" >&2

# Add service-label filter so we don't drown in MCP sandbox / frontend noise
FULL_FILTER="${FILTER} AND resource.labels.service_name=\"${SERVICE}\""

OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

if ! gcloud logging read "$FULL_FILTER" \
    --project="$PROJECT" $ACCT_ARG \
    --limit=50 \
    --freshness="$FRESHNESS" \
    --format='value(timestamp,severity,httpRequest.status,httpRequest.requestUrl,textPayload,jsonPayload.message,jsonPayload.exception)' \
    > "$OUT" 2>&1; then
  if grep -q 'PERMISSION_DENIED\|USER_PROJECT_DENIED\|invalid_grant\|not found or deleted' "$OUT"; then
    echo "" >&2
    echo "FAIL — your gcloud account does not have logging.viewer on $PROJECT." >&2
    echo "  Try:   GCP_ACCOUNT=<your-acct> ./scripts/tail-logs.sh $ARG" >&2
    echo "  Or:    gcloud auth login <account-with-access>" >&2
    cat "$OUT" >&2
    exit 1
  fi
  cat "$OUT" >&2
  exit 1
fi

if [[ ! -s "$OUT" ]]; then
  echo "(no matching logs)"
  exit 0
fi

cat "$OUT"
