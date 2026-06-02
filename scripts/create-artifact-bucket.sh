#!/usr/bin/env bash
# scripts/create-artifact-bucket.sh — create the ADK Artifact Service
# bucket and grant the Cloud Run SA write access.
#
# Without this, every call that touches ADK artifacts (eg. document
# ingest, in-session uploads via ADK's artifact_service) hits:
#   404 GET https://storage.googleapis.com/storage/v1/b/<project>-artifacts/...
#   "The specified bucket does not exist."
#
# Idempotent: re-runs no-op if the bucket already exists.
#
# STOPGAP — promote to Terraform in the multivac-aitana infra repo:
#
#   resource "google_storage_bucket" "adk_artifacts" {
#     name                        = "${var.project_id}-artifacts"
#     project                     = var.project_id
#     location                    = var.region
#     uniform_bucket_level_access = true
#     public_access_prevention    = "enforced"
#   }
#   resource "google_storage_bucket_iam_member" "adk_artifacts_writer" {
#     bucket = google_storage_bucket.adk_artifacts.name
#     role   = "roles/storage.objectAdmin"
#     member = "serviceAccount:sa-gde-ap-agent@${var.project_id}.iam.gserviceaccount.com"
#   }
#
# Usage:
#   ./scripts/create-artifact-bucket.sh [project] [region]
#
# Defaults: project=multivac-internal-dev  region=europe-west1
#
# After this script runs:
#   1. gs://<project>-artifacts exists with uniform bucket-level access
#   2. The Cloud Run SA (sa-gde-ap-agent@<project>) has
#      roles/storage.objectAdmin on the bucket
#   3. ADK_ARTIFACT_BUCKET env var on the deployed service already points
#      at this name (set by cloudbuild.yaml).

set -euo pipefail

PROJECT="${1:-multivac-internal-dev}"
REGION="${2:-europe-west1}"
SERVICE_SA="${SERVICE_SA:-sa-gde-ap-agent@${PROJECT}.iam.gserviceaccount.com}"
BUCKET="${ADK_ARTIFACT_BUCKET:-${PROJECT}-artifacts}"

skip() { echo "skipping create-artifact-bucket — $1" >&2; exit 0; }

command -v gcloud >/dev/null 2>&1 || skip "gcloud not on PATH"

echo "== create-artifact-bucket =="
echo "Project : ${PROJECT}"
echo "Region  : ${REGION}"
echo "Bucket  : gs://${BUCKET}"
echo "SA      : ${SERVICE_SA}"
echo ""

if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT}" >/dev/null 2>&1; then
    echo "Bucket already exists — checking IAM binding..."
else
    echo "Creating bucket gs://${BUCKET} in ${REGION}..."
    gcloud storage buckets create "gs://${BUCKET}" \
        --project="${PROJECT}" \
        --location="${REGION}" \
        --uniform-bucket-level-access \
        --public-access-prevention
fi

echo ""
echo "Granting roles/storage.objectAdmin on the bucket to ${SERVICE_SA}..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member="serviceAccount:${SERVICE_SA}" \
    --role=roles/storage.objectAdmin \
    --project="${PROJECT}" \
    --quiet >/dev/null

echo ""
echo "Done. Verify the bucket env on Cloud Run:"
echo "  gcloud run services describe gde-ap-agent --project=${PROJECT} --region=${REGION} --format=export | grep ADK_ARTIFACT_BUCKET"
