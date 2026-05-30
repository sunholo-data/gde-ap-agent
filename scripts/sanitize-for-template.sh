#!/usr/bin/env bash
#
# sanitize-for-template.sh — produce a public-fork-ready copy of the repo.
#
# Run at fork time only. NOT a routine operation. Produces a copy of the
# repo with Aitana-internal content removed and customer-specific files
# templated. Does NOT modify the current working tree.
#
# Removed:
#   - AgentsCLI_Share/        (NDA — Google preview bundle)
#   - docs/External Fishfood Guide_ Agents CLI (1).pdf  (NDA)
#   - docs/vendor/Fishfood Guide_ Python ADK MCP.pdf     (NDA)
#   - docs/feedback/                                     (private Aitana feedback)
#   - docs/design/v6.0.0/implemented/*-sprint.md         (workflow ephemera)
#   - .claude/state/sprints/                             (sprint state)
#   - .claude/skills/aitana-v6-deploy/                   (Aitana-only deploy ops)
#   - .claude/settings.json paths to /Users/...           (replaced with neutral)
#
# Templated (current value → public template):
#   - Hardcoded project IDs in scripts/dev.sh, backend/Makefile,
#     backend/scripts/_env.py → placeholder "your-project-id"
#   - cloudbuild.yaml + infrastructure/*/cloudbuild.yaml → templated
#
# Usage:
#   bash scripts/sanitize-for-template.sh /path/to/empty-dir [--dry-run]
#
# The target directory must NOT exist (script creates it). Dry-run mode
# prints what would happen without copying anything.

set -euo pipefail

TARGET="${1:-}"
MODE="${2:-apply}"

if [ -z "$TARGET" ]; then
  echo "Usage: $0 /path/to/empty-dir [--dry-run]"
  exit 2
fi

if [ "${MODE}" = "--dry-run" ] || [ "${MODE}" = "-n" ]; then
  DRY=1
else
  DRY=0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
if [ -z "$REPO_ROOT" ]; then
  echo "ERROR: sanitize-for-template.sh must be run inside the platform git repo" >&2
  exit 2
fi

# Refuse to run on a tree that has the public repo's name (paranoia: don't
# overwrite something that already IS the public template).
if [ -f "$REPO_ROOT/.template-fork-target" ]; then
  echo "ERROR: refusing to run inside a tree marked as a fork target" >&2
  exit 2
fi

# Refuse to write into an existing target.
if [ "$DRY" = 0 ] && [ -e "$TARGET" ]; then
  echo "ERROR: target $TARGET already exists. Pick an empty directory." >&2
  exit 2
fi

echo "Sanitize plan (dry-run=$DRY):"
echo "  source: $REPO_ROOT"
echo "  target: $TARGET"
echo

# --- Paths to delete from the copy ----------------------------------------
DELETE_PATHS=(
  "AgentsCLI_Share"
  "docs/External Fishfood Guide_ Agents CLI (1).pdf"
  "docs/vendor/Fishfood Guide_ Python ADK MCP.pdf"
  "docs/feedback"
  ".claude/state"
  ".claude/skills/aitana-v6-deploy"
  # Aitana-internal ops tooling — has no value to a template forker AND
  # backend/scripts/_env.py contains hardcoded Firebase Web API keys that
  # GitHub's secret scanner (rightly) flags. Even "public" web keys get
  # abused for unauthorized API calls when Google APIs are enabled in the
  # same project. The verify_rules.py + whoami_smoke.py + aiplatform-cli
  # scripts that import _env.py are also Aitana-deployment-specific and
  # have no meaning in a fresh fork.
  "backend/scripts/_env.py"
  "backend/scripts/verify_rules.py"
  "backend/scripts/whoami_smoke.py"
  # Dependents of the deleted scripts above — leaving these in causes
  # ImportError at test collection time on the public template.
  "backend/tests/integration/test_whoami_deployed.py"
  ".claude/skills/aiplatform-cli"
  ".claude/skills/cloud-run-diagnostics"
  # Aitana-internal: this skill documents how to refresh the public
  # template from THIS repo. Forkers of the template never refresh it
  # back upstream — they're downstream consumers, not maintainers. The
  # skill is also where the security-audit regex patterns are documented,
  # which means the patterns themselves trip the audit (an intentional
  # but ironic catch-22 — the gate refuses to ship documentation of
  # itself). Excluding the skill resolves both at once.
  ".claude/skills/aitana-template-publish"
  # Same reasoning as aitana-template-publish: the workshop-publish skill
  # documents how to refresh sunholo-data/build-ai-uis-beyond-chat from
  # docs/workshop/ in THIS repo. Downstream forks never refresh upstream
  # workshop materials — they're attendees of the workshop, not the
  # instructor. The sync script below is excluded for the same reason.
  ".claude/skills/workshop-publish"
  "scripts/refresh-workshop-materials.sh"
  # Platform-side meta only. The workshop repo's actual README is
  # generated from docs/workshop/_workshop-readme.md via the sync script
  # above. _workshop-readme.md is a sync-source meta file — confusing in
  # the public template since the script that consumes it isn't there.
  # docs/workshop/README.md is platform-side orientation that points at
  # the materials repo, which downstream forks don't maintain.
  "docs/workshop/_workshop-readme.md"
  "docs/workshop/README.md"
  # Aitana-internal docs that survived earlier publications. These have
  # no value to a template forker:
  #   - docs/talks/workshop.md walks attendees through "the live Aitana
  #     v6 codebase" with Aitana-specific framing.
  #   - docs/design/v5.0.0/migration-to-v6.md is the v5→v6 historical
  #     migration plan, contains /Users/mark/... path references.
  #   - docs/design/v6.0.0/template-split-strategy.md is the meta-doc
  #     about how Aitana forks this template; reads weird from inside
  #     the template.
  #   - docs/design/v6.0.0/{v6-bringup,tools-porting,v6-implementation}-*
  #     are internal sprint-planning artifacts.
  "docs/talks/workshop.md"
  "docs/design/v5.0.0"
  "docs/design/v6.0.0/template-split-strategy.md"
  "docs/design/v6.0.0/v6-bringup-sprint.md"
  "docs/design/v6.0.0/tools-porting-sprint.md"
  "docs/design/v6.0.0/v6-implementation-roadmap.md"
)

# --- Glob patterns to delete (sprint markdowns) ---------------------------
GLOB_DELETIONS=(
  "docs/design/v6.0.0/implemented/*-sprint.md"
)

if [ "$DRY" = 0 ]; then
  echo "Copying tracked files only (git ls-files — automatically excludes"
  echo "everything in .gitignore: .env, .env.local, build artefacts, etc)..."
  mkdir -p "$TARGET"
  cd "$REPO_ROOT"
  # Use git archive to copy only tracked + uncommitted-staged files. This
  # gives us the exact tree git would push, with no leftover .env, no
  # .pytest_cache, no .DS_Store, no .dev-logs etc — all gitignored paths
  # are naturally excluded.
  git ls-files -z | tar --null --files-from=- -cf - 2>/dev/null | tar -xf - -C "$TARGET"
  cd "$TARGET"
fi

echo
echo "Removing private paths:"
for p in "${DELETE_PATHS[@]}"; do
  echo "  - $p"
  if [ "$DRY" = 0 ] && [ -e "$p" ]; then
    rm -rf -- "$p"
  fi
done

echo
echo "Removing sprint-markdown glob deletions:"
for g in "${GLOB_DELETIONS[@]}"; do
  if [ "$DRY" = 0 ]; then
    # Use shopt to ensure the glob expands; ignore missing matches.
    shopt -s nullglob
    matches=($g)
    shopt -u nullglob
    for m in "${matches[@]}"; do
      echo "  - $m"
      rm -f -- "$m"
    done
  else
    echo "  - $g (glob)"
  fi
done

# --- Templating: replace hardcoded project IDs ---------------------------
echo
echo "Replacing hardcoded project IDs with 'your-project-id':"
TEMPLATABLE_FILES=(
  "scripts/dev.sh"
  "backend/Makefile"
  "backend/scripts/_env.py"
  "infrastructure/mcp-sandbox/cloudbuild.yaml"
  "infrastructure/mcp-ext-apps-map/cloudbuild.yaml"
  "cloudbuild.yaml"
  "firestore.indexes.json"
)
for f in "${TEMPLATABLE_FILES[@]}"; do
  if [ "$DRY" = 0 ] && [ -f "$f" ]; then
    echo "  - $f"
    # Use a portable sed -i invocation (macOS + Linux divergent on -i syntax).
    sed -i.bak \
      -e 's/aitana-multivac-dev/your-project-id/g' \
      -e 's/aitana-multivac-test/your-project-id-test/g' \
      -e 's/aitana-multivac-production/your-project-id-prod/g' \
      "$f" && rm -f "$f.bak"
  else
    echo "  - $f"
  fi
done

# --- Scrub local user paths from CLAUDE.md + .claude/settings.json -------
# These files reference paths like /Users/mark/dev/... that are useful for
# the original developer but meaningless (and embarrassing) in a public
# template.
echo
echo "Scrubbing local user paths:"

if [ "$DRY" = 0 ] && [ -f "CLAUDE.md" ]; then
  echo "  - CLAUDE.md (remove /Users/mark/... v5/adk-ref/terraform refs)"
  # Delete lines that reference local v5 / adk-ref / multivac-aitana paths.
  # Use a portable in-place sed.
  sed -i.bak \
    -e '/\*\*v5 repo (read-only reference):\*\*/d' \
    -e '/\*\*ADK reference scaffold:\*\*/d' \
    -e '/\*\*Terraform\*\*: `\/Users\/mark/d' \
    -e 's|/Users/mark/dev/aitana-labs/frontend/backend/|<your-v5-source>/|g' \
    -e '/See `\/Users\/mark\/dev\/aitana-labs\/adk-ref\/`/d' \
    "CLAUDE.md" && rm -f "CLAUDE.md.bak"
fi

if [ "$DRY" = 0 ] && [ -f ".claude/settings.json" ]; then
  echo "  - .claude/settings.json (clear additionalDirectories)"
  # Replace the additionalDirectories array contents with an empty array.
  # Python is more reliable than sed for JSON.
  python3 -c "
import json
with open('.claude/settings.json') as f:
    cfg = json.load(f)
if 'permissions' in cfg and 'additionalDirectories' in cfg['permissions']:
    cfg['permissions']['additionalDirectories'] = []
with open('.claude/settings.json', 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
"
fi

# --- Security audit: refuse to finish if Firebase API keys or other
# common secret patterns survived. This is the last line of defence
# before the operator pushes — if it fails, the script exits non-zero
# without writing the fork-target marker, so the operator notices.
if [ "$DRY" = 0 ]; then
  echo
  echo "Security audit (Firebase keys, SA keys, GitHub tokens):"
  leaks=$(grep -rEn 'AIzaSy[A-Za-z0-9_-]{30,}|"private_key":\s*"-----BEGIN|gh[pousr]_[A-Za-z0-9]{36}|sk-[a-zA-Z0-9]{40,}' . 2>/dev/null \
    --include='*.py' --include='*.sh' --include='*.ts' --include='*.tsx' \
    --include='*.json' --include='*.yaml' --include='*.yml' --include='*.md' \
    --include='Makefile' || true)
  if [ -n "$leaks" ]; then
    echo
    echo "FAIL: secret-shaped strings found in sanitized tree:"
    echo "$leaks"
    echo
    echo "Refusing to finish. Add the offending files to DELETE_PATHS or"
    echo "patch the templating step, then re-run."
    exit 3
  fi
  echo "  PASS — no known secret patterns survived sanitization"
fi

# --- Mark the target so future runs refuse to recurse --------------------
if [ "$DRY" = 0 ]; then
  echo "FORK_TARGET" > "$TARGET/.template-fork-target"
fi

echo
echo "Done. Next steps:"
echo "  1. cd $TARGET"
echo "  2. Manually review: README.md, CLAUDE.md (AgentsCLI refs), .claude/settings.json"
echo "  3. Run frontend + backend test suites to confirm the sanitized tree still builds"
echo "  4. git init && git add -A && git commit -m 'Initial public template'"
echo "  5. Push to the new public repo"
