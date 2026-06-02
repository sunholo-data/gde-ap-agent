#!/usr/bin/env bash
# scripts/verify-mcp-artefacts.sh — assert every artefact in the local
# repo has a matching index.html reachable on the deployed sandbox.
#
# Catches the "I added a widget locally but forgot to redeploy the
# sandbox" regression — the one that surfaced as an empty Vendor
# Knowledge Graph panel in the validator Audit View.
#
# Discovery: walks ${REPO_ROOT}/infrastructure/mcp-sandbox/artefacts/
# (ignoring _template) and probes each against the live sandbox URL.
# Expects HTTP 200 on /artefacts/<name>/index.html.
#
# Skip-don't-fail: missing curl / no sandbox URL => exit 0 with a
# `skipping…` line. Hard fail (exit 1): sandbox reachable but one or
# more artefacts return non-200.
#
# Usage:
#   ./scripts/verify-mcp-artefacts.sh                              # default
#   SANDBOX_URL=https://mcp-sandbox-...a.run.app ./scripts/verify-mcp-artefacts.sh
#
# Env vars:
#   SANDBOX_URL — explicit sandbox URL (overrides auto-discovery)
#   GCP_PROJECT — gcloud project for auto-discovery (default: multivac-internal-dev)
#   REGION      — Cloud Run region (default: europe-west1)
#   SERVICE     — service name (default: mcp-sandbox)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTEFACTS_DIR="${REPO_ROOT}/infrastructure/mcp-sandbox/artefacts"

skip() { echo "skipping verify-mcp-artefacts — $1" >&2; exit 0; }
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; }

command -v curl >/dev/null 2>&1 || skip "curl not on PATH"
[[ -d "$ARTEFACTS_DIR" ]] || skip "artefacts dir not found at $ARTEFACTS_DIR"

URL="${SANDBOX_URL:-}"
if [[ -z "$URL" ]]; then
    if command -v gcloud >/dev/null 2>&1; then
        URL=$(gcloud run services describe "${SERVICE:-mcp-sandbox}" \
            --project="${GCP_PROJECT:-multivac-internal-dev}" \
            --region="${REGION:-europe-west1}" \
            --format='value(status.url)' 2>/dev/null || true)
    fi
fi
[[ -n "$URL" ]] || skip "SANDBOX_URL unset and gcloud could not resolve mcp-sandbox URL"
URL="${URL%/}"

echo "== verify-mcp-artefacts =="
echo "Sandbox: $URL"

# Walk artefacts/*/index.html, skipping the _template starter directory.
# Use `while read` (bash 3-compatible) rather than mapfile so macOS's
# stock /bin/bash 3.2 doesn't choke.
LOCAL_ARTEFACTS=()
while IFS= read -r line; do
    LOCAL_ARTEFACTS+=("$line")
done < <(
    find "$ARTEFACTS_DIR" -maxdepth 2 -name "index.html" \
        ! -path "*/_template/*" \
        2>/dev/null \
        | sed "s|$ARTEFACTS_DIR/||;s|/index.html||" \
        | sort
)

if [[ ${#LOCAL_ARTEFACTS[@]} -eq 0 ]]; then
    skip "no artefacts found locally — nothing to verify"
fi

# Probe /sandbox.html first to confirm the service is reachable —
# distinguishes "sandbox down" from "artefact missing" in the report.
sb_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "${URL}/sandbox.html") || sb_code=000
if [[ "$sb_code" != "200" ]]; then
    fail "/sandbox.html -> ${sb_code} — sandbox itself unreachable"
    echo "  Redeploy: ./scripts/deploy-mcp-sandbox.sh"
    exit 1
fi
ok "/sandbox.html -> 200 (service alive)"
echo ""

failed=0
for name in "${LOCAL_ARTEFACTS[@]}"; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
        "${URL}/artefacts/${name}/index.html") || code=000
    if [[ "$code" = "200" ]]; then
        ok "${name} -> 200"
    else
        fail "${name} -> ${code} (in repo but missing from deployed sandbox)"
        failed=1
    fi
done

if [[ $failed -ne 0 ]]; then
    echo ""
    echo "One or more artefacts are missing from the deployed sandbox."
    echo "Fix: ./scripts/deploy-mcp-sandbox.sh (rebuilds + redeploys with current artefacts/)"
    exit 1
fi

echo ""
echo "All ${#LOCAL_ARTEFACTS[@]} local artefacts are reachable on the deployed sandbox."
