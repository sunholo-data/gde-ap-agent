#!/usr/bin/env bash
# Create a Vertex AI Reasoning Engine for ADK session persistence and store
# its resource name in Secret Manager as AGENT_ENGINE_ID.
#
# Usage:
#   ./scripts/create-agent-engine.sh [project] [region]
#
# Defaults: project=multivac-internal-dev  region=us-central1
#
# After this script runs:
#   1. AGENT_ENGINE_ID secret in Secret Manager is populated with the resource name.
#   2. Set _ENABLE_AGENT_ENGINE=true in the Cloud Build substitutions (terraform.tfvars).
#   3. Push to dev — Cloud Build will inject the secret and enable VertexAiSessionService.
set -euo pipefail

PROJECT="${1:-multivac-internal-dev}"
REGION="${2:-us-central1}"
DISPLAY_NAME="gde-ap-agent-sessions"

echo "Project : ${PROJECT}"
echo "Region  : ${REGION}"
echo ""

# Check for an existing engine to keep this idempotent
EXISTING=$(gcloud ai reasoning-engines list \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --filter="displayName=${DISPLAY_NAME}" \
  --format="value(name)" 2>/dev/null | head -1 || true)

if [[ -n "${EXISTING}" ]]; then
  echo "Reasoning Engine already exists: ${EXISTING}"
  ENGINE_NAME="${EXISTING}"
else
  echo "Creating Reasoning Engine '${DISPLAY_NAME}'..."
  # Create a minimal engine via REST — no Python artifact needed for session-only use.
  TOKEN=$(gcloud auth print-access-token)
  RESPONSE=$(curl -sS -X POST \
    "https://${REGION}-aiplatform.googleapis.com/v1beta1/projects/${PROJECT}/locations/${REGION}/reasoningEngines" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"display_name\": \"${DISPLAY_NAME}\", \"description\": \"ADK session store for GDE AP Agent\"}")

  # The create call is LRO — poll until done
  OPERATION=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
  echo "Waiting for LRO: ${OPERATION}"
  while true; do
    STATUS=$(curl -sS \
      "https://${REGION}-aiplatform.googleapis.com/v1beta1/${OPERATION}" \
      -H "Authorization: Bearer ${TOKEN}")
    DONE=$(echo "${STATUS}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('done', False))")
    if [[ "${DONE}" == "True" ]]; then
      break
    fi
    echo "  still running..."
    sleep 5
  done

  ENGINE_NAME=$(echo "${STATUS}" | python3 -c "import sys,json; print(json.load(sys.stdin)['response']['name'])")
  echo "Created: ${ENGINE_NAME}"
fi

# Numeric ID only (last path segment) — matches the format in .env.example
ENGINE_ID="${ENGINE_NAME##*/}"
echo ""
echo "Engine resource name : ${ENGINE_NAME}"
echo "Engine numeric ID    : ${ENGINE_ID}"

# Populate / update the Secret Manager secret
echo ""
echo "Writing to Secret Manager secret AGENT_ENGINE_ID in project ${PROJECT}..."
echo -n "${ENGINE_NAME}" | gcloud secrets versions add AGENT_ENGINE_ID \
  --project="${PROJECT}" \
  --data-file=-

echo ""
echo "Done. Next steps:"
echo "  1. Set _ENABLE_AGENT_ENGINE=true in multivac/infrastructure/environments/common/terraform.tfvars"
echo "     (under the gde-ap-agent cloud_build substitutions)"
echo "  2. Push the terraform change to origin/dev so Cloud Build picks up the new substitution."
echo "  3. Push to gde-ap-agent dev branch to trigger a deploy — sessions will now persist."
