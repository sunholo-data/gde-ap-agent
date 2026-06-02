#!/usr/bin/env bash
# scripts/deploy-mcp-sandbox.sh — rebuild + redeploy the MCP App sandbox.
#
# The mcp-sandbox Cloud Run service is SEPARATE from the gde-ap-agent
# backend/frontend service, so a normal `git push` does NOT rebuild it.
# Anyone adding a new artefact (eg. ap-vendor-kg) must run this to ship
# the new HTML into the sandbox image.
#
# Uses `gcloud run deploy --source .` (Buildpacks) — same path the
# existing deploys followed (no terraform-managed cloudbuild.yaml
# substitutions to wrangle).
#
# Usage:
#   ./scripts/deploy-mcp-sandbox.sh                    # default: dev
#   GCP_PROJECT=my-other-project ./scripts/deploy-mcp-sandbox.sh
#
# Env vars:
#   GCP_PROJECT — project id (default: multivac-internal-dev)
#   REGION      — Cloud Run region (default: europe-west1)
#
# After this script finishes, run:
#   ./scripts/verify-mcp-artefacts.sh
# to confirm all expected widgets return 200.

set -euo pipefail

PROJECT="${GCP_PROJECT:-multivac-internal-dev}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-mcp-sandbox}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX_DIR="${REPO_ROOT}/infrastructure/mcp-sandbox"

# Allowed host origins — must match the frontend that embeds the iframe.
# Default lifted from infrastructure/mcp-sandbox/cloudbuild.yaml.
ALLOWED_ORIGINS="${ALLOWED_HOST_ORIGINS:-https://aitana-v6-frontend-66pa3y5xnq-ew.a.run.app,https://gde-ap-agent-blqtqfexwa-ew.a.run.app}"

skip() { echo "skipping deploy-mcp-sandbox — $1" >&2; exit 0; }

command -v gcloud >/dev/null 2>&1 || skip "gcloud not on PATH"
[[ -d "$SANDBOX_DIR" ]] || skip "sandbox source dir not found at $SANDBOX_DIR"

echo "== deploy-mcp-sandbox =="
echo "Project : $PROJECT"
echo "Region  : $REGION"
echo "Service : $SERVICE"
echo "Source  : $SANDBOX_DIR"
echo ""

# List artefacts that should land in the image so the user sees what's
# about to ship. Helps catch the "I added a widget but forgot to commit"
# case before paying for a build.
echo "Artefacts to deploy:"
find "$SANDBOX_DIR/artefacts" -maxdepth 2 -name "index.html" 2>/dev/null \
  | sed "s|$SANDBOX_DIR/artefacts/||;s|/index.html||" \
  | sort \
  | awk '{print "  • " $0}'
echo ""

cd "$SANDBOX_DIR"
# `--set-env-vars` treats commas as key=value delimiters. Use the
# delimiter-override syntax `^@^` so commas inside ALLOWED_HOST_ORIGINS
# (multi-origin lists) survive intact. See `gcloud topic escaping`.
gcloud run deploy "$SERVICE" \
  --source . \
  --project="$PROJECT" \
  --region="$REGION" \
  --allow-unauthenticated \
  --port=8080 \
  --max-instances=3 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars="^@^ALLOWED_HOST_ORIGINS=${ALLOWED_ORIGINS}" \
  --quiet

echo ""
URL=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)' 2>/dev/null)
echo "Deployed: $URL"
echo ""
echo "Verify artefacts with: ./scripts/verify-mcp-artefacts.sh"
