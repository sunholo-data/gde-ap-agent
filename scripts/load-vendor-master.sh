#!/usr/bin/env bash
# scripts/load-vendor-master.sh — load the demo vendor master into the
# Vertex AI Search datastore so the AP-validator returns grounded
# results instead of "could not ground" empty citations.
#
# Uses the JSONL produced by infrastructure/demo-vendor-master/generate.py
# (auto-regenerated if missing). Documents are uploaded to a temp prefix
# in the AP demo bucket and imported via Discovery Engine's
# documents:import endpoint with dataSchema=document.
#
# Idempotent: documents are keyed by `id`, so re-imports update in place.
# Bucket prefix uses a stable name so re-runs don't pile up objects.
#
# Usage:
#   ./scripts/load-vendor-master.sh [project] [location] [datastore_id]
#
# Defaults:
#   project=multivac-internal-dev  location=eu  datastore_id=ds-ap-vendors
#
# Env vars:
#   GCS_STAGING_BUCKET — bucket for the import-staging JSONL
#                        (default: ${AP_DEMO_BUCKET:-gde-ap-agent-demo-invoices})
#
# STOPGAP — promote to Terraform in the multivac-aitana infra repo.
# google_discovery_engine_data_store + a follow-up
# google_storage_bucket_object + null_resource for documents:import.
# See create-search-datastore.sh header for the datastore terraform.

set -euo pipefail

PROJECT="${1:-multivac-internal-dev}"
LOCATION="${2:-eu}"
DATASTORE_ID="${3:-ds-ap-vendors}"
STAGING_BUCKET="${GCS_STAGING_BUCKET:-${AP_DEMO_BUCKET:-gde-ap-agent-demo-invoices}}"
STAGING_PREFIX="vendor-master"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JSONL="${REPO_ROOT}/infrastructure/demo-vendor-master/vendor-master.jsonl"

skip() { echo "skipping load-vendor-master — $1" >&2; exit 0; }

command -v gcloud >/dev/null 2>&1 || skip "gcloud not on PATH"
command -v curl   >/dev/null 2>&1 || skip "curl not on PATH"

echo "== load-vendor-master =="
echo "Project       : $PROJECT"
echo "Location      : $LOCATION"
echo "Datastore     : $DATASTORE_ID"
echo "Staging bucket: gs://${STAGING_BUCKET}/${STAGING_PREFIX}"
echo ""

# Generate the JSONL if missing
if [[ ! -f "$JSONL" ]]; then
    echo "Generating $JSONL ..."
    python3 "${REPO_ROOT}/infrastructure/demo-vendor-master/generate.py"
fi

DOC_COUNT=$(wc -l < "$JSONL" | tr -d ' ')
echo "Documents: ${DOC_COUNT}"

# Upload JSONL
GCS_PATH="gs://${STAGING_BUCKET}/${STAGING_PREFIX}/vendor-master.jsonl"
echo "Uploading to ${GCS_PATH}..."
gcloud storage cp "$JSONL" "$GCS_PATH" --project="$PROJECT" --quiet

# Import via Discovery Engine API
case "$LOCATION" in
    global) HOST="https://discoveryengine.googleapis.com" ;;
    *)      HOST="https://${LOCATION}-discoveryengine.googleapis.com" ;;
esac
IMPORT_URL="${HOST}/v1beta/projects/${PROJECT}/locations/${LOCATION}/collections/default_collection/dataStores/${DATASTORE_ID}/branches/0/documents:import"
TOKEN=$(gcloud auth print-access-token)

# `reconciliationMode: INCREMENTAL` upserts on id without wiping the
# datastore — re-runs of this script are safe and update changed records.
BODY=$(cat <<JSON
{
  "gcsSource": {
    "inputUris": ["${GCS_PATH}"],
    "dataSchema": "document"
  },
  "reconciliationMode": "INCREMENTAL"
}
JSON
)

echo "Calling documents:import ..."
IMPORT_OUT=$(mktemp)
trap 'rm -f "$IMPORT_OUT"' EXIT

CODE=$(curl -sS -o "$IMPORT_OUT" -w '%{http_code}' --max-time 60 \
    -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "x-goog-user-project: ${PROJECT}" \
    -H "Content-Type: application/json" \
    -d "${BODY}" \
    "${IMPORT_URL}") || CODE=000

if [[ "$CODE" != "200" ]]; then
    echo "FAIL import returned HTTP ${CODE}:" >&2
    cat "$IMPORT_OUT" >&2
    exit 1
fi

OP=$(python3 -c "import json; print(json.load(open('${IMPORT_OUT}'))['name'])")
echo "Import LRO submitted: ${OP}"
echo "Polling..."

for i in $(seq 1 30); do
    sleep 4
    OP_OUT=$(mktemp)
    curl -sS -o "$OP_OUT" --max-time 30 \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "x-goog-user-project: ${PROJECT}" \
        "${HOST}/v1beta/${OP}"
    DONE=$(python3 -c "import json; d=json.load(open('${OP_OUT}')); print(d.get('done', False))")
    if [[ "$DONE" = "True" ]]; then
        SUCCESS_COUNT=$(python3 -c "import json; d=json.load(open('${OP_OUT}')); print(d.get('metadata',{}).get('successCount','?'))")
        FAILURE_COUNT=$(python3 -c "import json; d=json.load(open('${OP_OUT}')); print(d.get('metadata',{}).get('failureCount','?'))")
        echo "Done. success=${SUCCESS_COUNT}  failure=${FAILURE_COUNT}"
        if [[ "$FAILURE_COUNT" != "0" && "$FAILURE_COUNT" != "?" ]]; then
            echo "Failures detected — full operation:"
            cat "$OP_OUT" >&2
        fi
        rm -f "$OP_OUT"
        exit 0
    fi
    rm -f "$OP_OUT"
    echo "  still importing... (${i})"
done

echo "Import LRO did not complete in 2 minutes. Check manually:"
echo "  curl -H 'Authorization: Bearer \$(gcloud auth print-access-token)' \\"
echo "       -H 'x-goog-user-project: ${PROJECT}' \\"
echo "       ${HOST}/v1beta/${OP}"
exit 1
