#!/usr/bin/env bash
# scripts/create-logs-bucket.sh — create the OTEL GenAI completions
# bucket (LOGS_BUCKET_NAME) and grant the Cloud Run SA write access.
#
# Without this, every model call generates a background error trace:
#   FileNotFoundError: https://storage.googleapis.com/upload/storage/v1/
#     b/<project>-aitana-v6-logs/o?name=completions/...jsonl
# because opentelemetry-util-genai's completion-hook uploads prompts +
# system_instructions + tool_definitions to GCS for observability.
# Chat still works (the hook runs in a background thread), but error
# logs flood and you lose model-call observability.
#
# Idempotent: re-runs no-op if the bucket already exists.
#
# STOPGAP — promote to Terraform in the multivac-aitana infra repo:
#
#   resource "google_storage_bucket" "aitana_v6_logs" {
#     name                        = "${var.project_id}-aitana-v6-logs"
#     project                     = var.project_id
#     location                    = var.region
#     uniform_bucket_level_access = true
#     public_access_prevention    = "enforced"
#     lifecycle_rule {
#       action { type = "Delete" }
#       condition { age = 30 }  # OTEL completion logs are debug-grade
#     }
#   }
#   resource "google_storage_bucket_iam_member" "logs_writer" {
#     bucket = google_storage_bucket.aitana_v6_logs.name
#     role   = "roles/storage.objectAdmin"
#     member = "serviceAccount:sa-gde-ap-agent@${var.project_id}.iam.gserviceaccount.com"
#   }
#
# Usage:
#   ./scripts/create-logs-bucket.sh [project] [region]
#
# Defaults: project=multivac-internal-dev  region=europe-west1
#
# After this script runs:
#   1. gs://<project>-aitana-v6-logs exists with uniform bucket-level access
#   2. The Cloud Run SA (sa-gde-ap-agent@<project>) has
#      roles/storage.objectAdmin on the bucket
#   3. LOGS_BUCKET_NAME env var on the deployed service already points
#      at this name (set by cloudbuild.yaml).

set -euo pipefail

PROJECT="${1:-multivac-internal-dev}"
REGION="${2:-europe-west1}"
SERVICE_SA="${SERVICE_SA:-sa-gde-ap-agent@${PROJECT}.iam.gserviceaccount.com}"
BUCKET="${LOGS_BUCKET_NAME:-${PROJECT}-aitana-v6-logs}"

skip() { echo "skipping create-logs-bucket — $1" >&2; exit 0; }

command -v gcloud >/dev/null 2>&1 || skip "gcloud not on PATH"

echo "== create-logs-bucket =="
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
echo "Done. Verify with the next chat turn — OTEL FileNotFoundError traces"
echo "should stop appearing in:"
echo "  ./scripts/tail-logs.sh 'severity>=ERROR'"
