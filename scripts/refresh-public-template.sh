#!/usr/bin/env bash
#
# refresh-public-template.sh — propagate changes from Aitana-Labs/platform
# to the public template at sunholo-data/ai-protocol-platform.
#
# The template is GENERATED, not maintained — every refresh produces a
# new "Initial public template" history rather than tracking commits 1:1
# with this repo. This is intentional:
#   - Attendees who used "Use this template" get a clean repo, no
#     surprising upstream history
#   - We don't need to worry about merge conflicts or branch tracking
#   - Force-push is the right answer; the template's value is its
#     current-state, not its history
#
# How it works:
#   1. Run sanitize-for-template.sh into a scratch dir
#   2. Init fresh git history (single commit referencing source SHA)
#   3. Force-push to sunholo-data/ai-protocol-platform main
#   4. Clean up scratch dir
#
# Anything that depends on the template ALREADY has its own git history
# from the moment they clicked "Use this template" — the force-push only
# affects the template repo itself, not any downstream copies.
#
# Usage:
#   bash scripts/refresh-public-template.sh
#   bash scripts/refresh-public-template.sh --dry-run   # generate but don't push

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

DRY=0
if [ "${1:-}" = "--dry-run" ] || [ "${1:-}" = "-n" ]; then
  DRY=1
fi

SOURCE_SHA="$(git rev-parse --short HEAD)"
SOURCE_BRANCH="$(git symbolic-ref --short -q HEAD || echo detached)"
TARGET_REMOTE="https://github.com/sunholo-data/ai-protocol-platform.git"
SCRATCH="$(mktemp -d -t ai-protocol-platform-refresh-XXXXXX)"

echo "Refresh plan:"
echo "  source repo   : $REPO_ROOT"
echo "  source branch : $SOURCE_BRANCH @ $SOURCE_SHA"
echo "  target remote : $TARGET_REMOTE"
echo "  scratch dir   : $SCRATCH"
echo "  dry-run       : $DRY"
echo

# Refuse to refresh from a dirty tree — the template should always come
# from a clean, committed state in Aitana-Labs/platform.
if [ -n "$(git status --porcelain)" ]; then
  echo "ERROR: working tree has uncommitted changes. Commit or stash first." >&2
  exit 2
fi

# Step 1: sanitize
echo "=== Step 1: sanitize ==="
bash scripts/sanitize-for-template.sh "$SCRATCH/tree"

# Step 2: init git history
echo
echo "=== Step 2: init fresh git history ==="
cd "$SCRATCH/tree"
git init -b main -q
git add -A
git -c user.email=github@markedmondson.me -c user.name=Mark commit -m "$(cat <<EOF
Refresh public template from Aitana-Labs/platform $SOURCE_SHA

Regenerated via scripts/refresh-public-template.sh on $(date -u +%Y-%m-%d).

This is a fresh-history snapshot of the latest Aitana-Labs/platform state
sanitized for public consumption. Existing forks/template-instances are
unaffected — they have their own histories from the moment they cloned.

A protocol-native AI assistant platform on Google ADK. Start with
WORKSHOP.md — clone, set LOCAL_MODE=1, run make dev, working chat UI in
under 30 minutes with zero GCP credentials.

Licensed under Apache 2.0. See LICENSE + CONTRIBUTING.md.
EOF
)" >/dev/null

echo "  committed: $(git rev-parse --short HEAD)"
echo "  files    : $(git ls-files | wc -l | tr -d ' ')"

if [ "$DRY" = 1 ]; then
  echo
  echo "Dry-run done. Inspect $SCRATCH/tree then delete it. Not pushed."
  exit 0
fi

# Step 3: force-push
echo
echo "=== Step 3: force-push to $TARGET_REMOTE ==="
git remote add origin "$TARGET_REMOTE"
git push --force origin main

# Step 4: clean up
echo
echo "=== Step 4: clean up ==="
cd "$REPO_ROOT"
rm -rf "$SCRATCH"
echo "  removed $SCRATCH"

echo
echo "Done. Template refreshed at https://github.com/sunholo-data/ai-protocol-platform"
echo "Source SHA: $SOURCE_SHA"
