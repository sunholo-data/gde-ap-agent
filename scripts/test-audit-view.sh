#!/usr/bin/env bash
# scripts/test-audit-view.sh — meta-runner for the AUDIT-VIEW feature
# verification loop.
#
# Runs:
#   1. verify-skill-schemas.sh   — Firestore has populated structuredInput
#   2. test-structured-invocation.sh (if AIPLATFORM_ID_TOKEN set)
#                                 — endpoint accepts payload and returns
#                                   the documented shape
#
# Exit 0 when every check passes, 1 on the first hard failure. Both
# sub-scripts use skip-don't-fail for missing preconditions (token,
# tools), so this script also surfaces "skipped" runs without failing.
#
# Usage:
#   ./scripts/test-audit-view.sh
#   AIPLATFORM_ID_TOKEN=<token> ./scripts/test-audit-view.sh
#   GDE_AP_URL=https://my-fork.run.app ./scripts/test-audit-view.sh
#
# Designed to be the one command a reviewer runs to verify the audit
# view end-to-end after merging. Pre-merge CI wires only the schemas
# check (no token); post-deploy smokes wire the full end-to-end probe.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "================================================================"
echo " AUDIT-VIEW verification"
echo "================================================================"

rc=0

if ! "$REPO_ROOT/scripts/verify-skill-schemas.sh"; then
    rc=1
    echo ""
    echo "verify-skill-schemas FAILED — fix this before running the invocation probe."
    exit $rc
fi

echo ""
if [[ -z "${AIPLATFORM_ID_TOKEN:-}" ]]; then
    echo "(skipping structured-invocation probes — set AIPLATFORM_ID_TOKEN to run them)"
    exit 0
fi

"$REPO_ROOT/scripts/test-structured-invocation.sh" || rc=$?

echo ""
echo "================================================================"
if [[ $rc -eq 0 ]]; then
    echo " AUDIT-VIEW verification PASSED"
else
    echo " AUDIT-VIEW verification FAILED"
fi
echo "================================================================"
exit $rc
