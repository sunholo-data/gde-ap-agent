#!/usr/bin/env bash
# Creates the AP demo GCS bucket and uploads all demo invoice files.
#
# Usage:
#   ./setup-demo-bucket.sh [gcp-project]
#
# Defaults to multivac-internal-dev. Run once; subsequent runs are idempotent
# (gsutil mb is a no-op if the bucket already exists, and gsutil cp -n skips
# files that are already present).
#
# The app service account (aitana-v6@<project>.iam.gserviceaccount.com) is
# granted Storage Object Viewer on the bucket so the backend can list and
# import files without exposing them publicly.

set -euo pipefail

PROJECT="${1:-multivac-internal-dev}"
BUCKET="gde-ap-agent-demo-invoices"
SA="aitana-v6@${PROJECT}.iam.gserviceaccount.com"
REGION="europe-west1"

echo "→ Project : ${PROJECT}"
echo "→ Bucket  : gs://${BUCKET}"
echo "→ SA      : ${SA}"
echo ""

# 1. Create bucket (idempotent)
if gsutil ls -p "${PROJECT}" "gs://${BUCKET}" &>/dev/null; then
  echo "  ✓ Bucket gs://${BUCKET} already exists — skipping create"
else
  gsutil mb -p "${PROJECT}" -l "${REGION}" -b on "gs://${BUCKET}"
  echo "  ✓ Created gs://${BUCKET}"
fi

# 2. Upload demo files (-n = no-clobber: skip existing files)
echo ""
echo "→ Uploading demo invoice files..."
gsutil -m cp -n \
  acme-gmbh-invoice-2026-042.docx \
  techcorp-uk-expense-report-q2-2026.xlsx \
  nordic-parts-invoice-email-2026.eml \
  batch-invoices-q2-2026.csv \
  apex-consulting-invoice-2026-103.odt \
  ap-approval-thread-inv-042.mbox \
  challenge-complex-docx-sample.docx \
  challenge-merged-cells-spreadsheet.xlsx \
  challenge-email-with-docx-attachment.eml \
  "gs://${BUCKET}/"
echo "  ✓ Files uploaded"

# 3. Grant app SA read access (idempotent via gsutil IAM)
echo ""
echo "→ Granting Storage Object Viewer to ${SA}..."
gsutil iam ch "serviceAccount:${SA}:objectViewer" "gs://${BUCKET}"
echo "  ✓ IAM binding set"

# 4. Verify
echo ""
echo "→ Bucket contents:"
gsutil ls -lh "gs://${BUCKET}/"
echo ""
echo "✅ Demo bucket ready: gs://${BUCKET}"
echo ""
echo "Add to cloudbuild.yaml substitutions:"
echo "  _AP_DEMO_BUCKET: '${BUCKET}'"
