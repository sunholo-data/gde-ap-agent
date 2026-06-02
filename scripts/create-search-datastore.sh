#!/usr/bin/env bash
# scripts/create-search-datastore.sh — create the Vertex AI Search
# datastore that backs the ap-validator's grounding.
#
# Without this, ap-validator runs fail with:
#   400 INVALID_ARGUMENT. The GenerateContentRequest proto is invalid:
#   tools[0].retrieval.vertex_ai_search.datastore:
#   [FIELD_INVALID] Invalid Vertex AI datastore resource name
#
# Bare ids (eg. "ds-ap-vendors" in SKILL.md) are now expanded by the
# backend (search_agent._expand_datastore_id), so the SKILL.md value
# stays a short token. This script creates the datastore the expansion
# points at: gs://<DATASTORE_ID> at location eu, content config
# CONTENT_REQUIRED_NO_CONTENT (structured metadata-only — a real
# vendor master loader is a follow-up).
#
# Idempotent: re-runs no-op if the datastore already exists.
#
# Usage:
#   ./scripts/create-search-datastore.sh [project] [location]
#
# Defaults: project=multivac-internal-dev  location=eu
#
# STOPGAP — promote to Terraform in the multivac-aitana infra repo:
#
#   resource "google_discovery_engine_data_store" "ap_vendors" {
#     project           = var.project_id
#     location          = "eu"
#     data_store_id     = "ds-ap-vendors"
#     display_name      = "AP Vendor Master"
#     industry_vertical = "GENERIC"
#     solution_types    = ["SOLUTION_TYPE_SEARCH"]
#     content_config    = "CONTENT_REQUIRED"
#   }

set -euo pipefail

PROJECT="${1:-multivac-internal-dev}"
LOCATION="${2:-eu}"
DATASTORE_ID="${DATASTORE_ID:-ds-ap-vendors}"
DISPLAY_NAME="${DISPLAY_NAME:-AP Vendor Master}"

skip() { echo "skipping create-search-datastore — $1" >&2; exit 0; }

command -v gcloud >/dev/null 2>&1 || skip "gcloud not on PATH"
command -v curl   >/dev/null 2>&1 || skip "curl not on PATH"

echo "== create-search-datastore =="
echo "Project       : $PROJECT"
echo "Location      : $LOCATION"
echo "Datastore ID  : $DATASTORE_ID"
echo "Display name  : $DISPLAY_NAME"
echo ""

TOKEN=$(gcloud auth print-access-token --account="$(gcloud config get-value account)" 2>/dev/null || true)
[[ -n "$TOKEN" ]] || skip "could not mint access token (gcloud auth login)"

# Discovery Engine API has region-specific endpoints — `global` uses the
# bare host, while `eu`/`us` need a regional prefix. Mismatch returns:
#   400 INVALID_ARGUMENT: The current endpoint can only serve traffic
#   from "global" region, but got "eu" region from the API request.
case "$LOCATION" in
    global) HOST="https://discoveryengine.googleapis.com" ;;
    *)      HOST="https://${LOCATION}-discoveryengine.googleapis.com" ;;
esac
BASE="${HOST}/v1beta/projects/${PROJECT}/locations/${LOCATION}/collections/default_collection/dataStores"
GET_URL="${BASE}/${DATASTORE_ID}"

# Idempotency check
STATUS=$(curl -sS -o /tmp/csd-get -w '%{http_code}' --max-time 30 \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "x-goog-user-project: ${PROJECT}" \
    "${GET_URL}") || STATUS=000
if [[ "$STATUS" = "200" ]]; then
    NAME=$(python3 -c "import json; print(json.load(open('/tmp/csd-get'))['name'])" 2>/dev/null || echo "?")
    echo "Datastore already exists: ${NAME}"
    rm -f /tmp/csd-get
    echo ""
    echo "Done. SKILL.md datastore_id can stay as short form (\"${DATASTORE_ID}\")."
    exit 0
fi
rm -f /tmp/csd-get

# Create
echo "Creating datastore '${DATASTORE_ID}' (display: '${DISPLAY_NAME}')..."
CREATE_URL="${BASE}?dataStoreId=${DATASTORE_ID}"
BODY=$(cat <<JSON
{
  "displayName": "${DISPLAY_NAME}",
  "industryVertical": "GENERIC",
  "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
  "contentConfig": "CONTENT_REQUIRED"
}
JSON
)

CREATE_STATUS=$(curl -sS -o /tmp/csd-create -w '%{http_code}' --max-time 60 \
    -X POST \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "x-goog-user-project: ${PROJECT}" \
    -H "Content-Type: application/json" \
    -d "${BODY}" \
    "${CREATE_URL}") || CREATE_STATUS=000

if [[ "$CREATE_STATUS" = "200" || "$CREATE_STATUS" = "201" ]]; then
    OP=$(python3 -c "import json; print(json.load(open('/tmp/csd-create'))['name'])" 2>/dev/null || echo "?")
    echo "Create LRO submitted: ${OP}"
    # Poll briefly — datastore creation usually finishes in <30s
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 3
        OP_STATUS=$(curl -sS --max-time 30 -H "Authorization: Bearer ${TOKEN}" \
            -H "x-goog-user-project: ${PROJECT}" \
            "${HOST}/v1beta/${OP}")
        DONE=$(python3 -c "import json,sys; print(json.load(open('/tmp/poll'))[\"done\"])" 2>/dev/null \
            || python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('done', False))" "$OP_STATUS" 2>/dev/null \
            || echo "False")
        if [[ "$DONE" = "True" ]]; then
            echo "Datastore ready."
            break
        fi
        echo "  still creating..."
    done
else
    echo "Create returned HTTP ${CREATE_STATUS}:" >&2
    cat /tmp/csd-create >&2
    rm -f /tmp/csd-create
    exit 1
fi
rm -f /tmp/csd-create

FULL="projects/${PROJECT}/locations/${LOCATION}/collections/default_collection/dataStores/${DATASTORE_ID}"
echo ""
echo "Datastore : ${FULL}"
echo ""
echo "SKILL.md needs:"
echo "    ai_search:"
echo "      datastore_id: ${DATASTORE_ID}"
echo "(the backend search_agent expands bare ids using GOOGLE_CLOUD_PROJECT + DATASTORE_LOCATION)"
