#!/usr/bin/env bash
# scripts/bootstrap-gcp-project.sh
#
# Run ONCE per new GCP project before creating Cloud Build triggers.
# Post-2024 GCP projects no longer auto-provision the Cloud Build service
# agent or grant it the permissions it needs — this script does that.
# See docs/ops/gotchas.md for the full explanation.
#
# Usage:
#   ./scripts/bootstrap-gcp-project.sh <project-id> <runtime-sa-email>
#
# Example:
#   ./scripts/bootstrap-gcp-project.sh my-fork-dev \
#     aitana-v6@my-fork-dev.iam.gserviceaccount.com
#
# Prerequisites:
#   - gcloud authenticated as an Owner or Editor of <project-id>
#   - Cloud Build API enabled: gcloud services enable cloudbuild.googleapis.com
#   - Cloud Storage API enabled (for log bucket)

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <project-id> <runtime-sa-email>}"
RUNTIME_SA="${2:?Usage: $0 <project-id> <runtime-sa-email>}"
REGION="${3:-europe-west1}"

echo "==> Bootstrapping Cloud Build for project: ${PROJECT_ID}"
echo "    Runtime SA : ${RUNTIME_SA}"
echo "    Region     : ${REGION}"
echo ""

# 1. Materialize the Cloud Build service agent.
#    Post-2024 projects don't auto-create this; without it, trigger creation
#    fails with an opaque INVALID_ARGUMENT error.
echo "[1/4] Materializing Cloud Build service agent..."
gcloud beta services identity create \
  --service=cloudbuild.googleapis.com \
  --project="${PROJECT_ID}"

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" \
  --format='value(projectNumber)')
CB_SA="service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
echo "      Cloud Build SA: ${CB_SA}"

# 2. Grant the Cloud Build SA permission to impersonate the runtime SA.
#    Required so Cloud Build can deploy Cloud Run services using the
#    runtime SA's identity.
echo "[2/4] Granting Cloud Build SA iam.serviceAccountUser on runtime SA..."
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project="${PROJECT_ID}"

# 3. Create the Cloud Build log bucket (avoids the hardcoded Aitana bucket).
#    The cloudbuild.yaml _LOG_BUCKET substitution defaults to
#    gs://${_PROJECT_ID}-cloudbuild-logs — create that here.
LOG_BUCKET="gs://${PROJECT_ID}-cloudbuild-logs"
echo "[3/4] Creating Cloud Build log bucket: ${LOG_BUCKET}..."
if gcloud storage buckets describe "${LOG_BUCKET}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "      Bucket already exists — skipping."
else
  gcloud storage buckets create "${LOG_BUCKET}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --project="${PROJECT_ID}"
fi

# 4. Grant the Cloud Build SA write access to the log bucket.
echo "[4/4] Granting Cloud Build SA storage.objectCreator on log bucket..."
gcloud storage buckets add-iam-policy-binding "${LOG_BUCKET}" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/storage.objectCreator" \
  --project="${PROJECT_ID}"

echo ""
echo "==> Bootstrap complete."
echo ""
echo "Next steps:"
echo "  1. Register the GitHub repository with Cloud Build v2:"
echo "     gcloud builds repositories create <repo-name> \\"
echo "       --remote-uri=https://github.com/<org>/<repo> \\"
echo "       --connection=<connection-name> \\"
echo "       --project=${PROJECT_ID} --region=${REGION}"
echo "     NOTE: the GitHub account authorizing the connection needs 'admin'"
echo "     on the repository (not just 'push') — see docs/ops/gotchas.md #8."
echo ""
echo "  2. Create the Cloud Build trigger:"
echo "     gcloud builds triggers create github \\"
echo "       --service-account=projects/${PROJECT_ID}/serviceAccounts/${RUNTIME_SA} \\"
echo "       ... (see cloudbuild.yaml for substitutions)"
echo ""
echo "  3. Set channel flags in Terraform substitutions if needed:"
echo "     _ENABLE_ANTHROPIC = true"
echo "     _ENABLE_TELEGRAM  = true  # only if TELEGRAM_BOT_TOKEN secret exists"
