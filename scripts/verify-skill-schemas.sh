#!/usr/bin/env bash
# scripts/verify-skill-schemas.sh — assert platform skills declare the
# structured-input schemas that the Audit View Run-Standalone forms
# need.
#
# Reads the public /api/skills/marketplace endpoint and checks each
# specialist skill (docparse, ap-validator, ap-poster) for a populated
# metadata.structuredInput JSON Schema. The orchestrator is intentionally
# allowed to be schema-less — it has no Run-Standalone form.
#
# This is the verification I wished I had after the AUDIT-VIEW sprint:
# the seed step silently skipped existing skills, so SKILL.md changes
# never reached Firestore. The structural fix lives in
# backend/admin/platform_seed.py; this script catches the regression
# the next time it surfaces (eg. a forked SKILL.md gets stripped, the
# Pydantic alias gets renamed, a deploy hangs without the seed step).
#
# Skip-don't-fail: missing curl or jq => exit 0 with a `skipping…` line.
# Hard fail (exit 1): the live URL responds but specialists are missing
# their schemas — that's the regression we want to catch.
#
# Usage:
#   ./scripts/verify-skill-schemas.sh                            # dev (default)
#   ./scripts/verify-skill-schemas.sh https://your-fork.run.app  # custom URL
#
# Env vars:
#   GDE_AP_URL — backend URL (overrides positional + default)

set -euo pipefail

DEFAULT_URL="https://gde-ap-agent-blqtqfexwa-ew.a.run.app"
URL="${GDE_AP_URL:-${1:-$DEFAULT_URL}}"
URL="${URL%/}"

# Skills that MUST declare structuredInput. Names match SKILL.md `name:` fields.
REQUIRED=(docparse ap-validator ap-poster)

skip() { echo "skipping verify-skill-schemas — $1" >&2; exit 0; }
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; }

command -v curl >/dev/null 2>&1 || skip "curl not on PATH"
command -v jq   >/dev/null 2>&1 || skip "jq not on PATH (brew install jq)"

echo "== verify-skill-schemas =="
echo "URL: ${URL}"

# Fetch the public marketplace once.
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
code=$(curl -sS -o "$TMP" -w '%{http_code}' --max-time 30 "${URL}/api/proxy/api/skills/marketplace") || code=000
if [[ "$code" != "200" ]]; then
    echo "FAIL marketplace endpoint -> ${code}"
    head -c 200 "$TMP" >&2
    exit 1
fi

failed=0
for name in "${REQUIRED[@]}"; do
    # Pull the structuredInput object (or null) for this skill.
    si=$(jq -r --arg n "$name" '
        [ .[] | select(.name == $n) ] as $matches
        | if ($matches | length) == 0 then "MISSING_SKILL"
          elif ($matches[0].skillMetadata.structuredInput // null) == null then "NULL"
          elif ($matches[0].skillMetadata.structuredInput | type) != "object" then "NOT_OBJECT"
          else "OK"
          end
    ' "$TMP")

    case "$si" in
        OK)
            # Sanity: object has at least one `properties` entry.
            prop_count=$(jq -r --arg n "$name" '
                [ .[] | select(.name == $n) ][0].skillMetadata.structuredInput.properties // {} | length
            ' "$TMP")
            ok "${name}: structuredInput populated (${prop_count} properties)"
            ;;
        NULL)
            fail "${name}: structuredInput is null (template not seeded to Firestore — did the deploy seed step run?)"
            failed=1
            ;;
        MISSING_SKILL)
            fail "${name}: skill not in marketplace (purged? renamed?)"
            failed=1
            ;;
        NOT_OBJECT)
            fail "${name}: structuredInput is not a JSON object"
            failed=1
            ;;
        *)
            fail "${name}: unknown state (${si})"
            failed=1
            ;;
    esac
done

echo ""
if [[ $failed -ne 0 ]]; then
    echo "Hint: re-run the platform seed step:"
    echo "  curl -X POST -H \"Authorization: Bearer \$(gcloud auth print-identity-token --audiences=<backend-url>)\" <backend-url>/api/admin/seed-platform-skills"
    echo "Or trigger a fresh deploy."
    exit 1
fi
echo "All ${#REQUIRED[@]} specialists have populated structuredInput schemas."
