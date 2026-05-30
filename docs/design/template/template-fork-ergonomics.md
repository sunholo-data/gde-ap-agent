# Template Fork Ergonomics

**Status**: Planned  
**Priority**: P1  
**Estimated**: 2d  
**Scope**: Backend + Frontend + CLI + Config  
**Dependencies**: None  
**Created**: 2026-05-21  
**Last Updated**: 2026-05-21  
**Source items**: #1 #2 #3 #4 #11 #12 (CPH Uni AIPLA upstream feedback)

## Problem Statement

Every downstream fork of `sunholo-data/ai-protocol-platform` hits a cluster of friction
points caused by Aitana-specific values baked into the template's code. A fork can't use
the CLI seeder, must manually override the owner email, runs with an MCP sandbox URL
pointing at Aitana's infrastructure, and sees `aitana://` hardwired into protocol
identifiers that cannot be rebranded without touching source.

**Current State:**

- `backend/scripts/seed_skills.py` has a hardcoded `DISPLAY_NAMES` / `TAGS` / `INITIAL_MESSAGES` dict listing only the five inherited demo skills. Adding a new skill template means it seeds with falsy defaults (item #1).
- Same file pins the GCP project via `pin_project_for_env("dev")`, making the seeder unusable in any project other than `aitana-multivac-dev` (item #2).
- `backend/admin/platform_seed.py` defaults `PLATFORM_OWNER_EMAIL` to `platform@aitanalabs.com`; a fork that forgets to set the env var ships skills owned by Aitana (item #3).
- The CLI package, binary, and per-env default URLs all hardcode Aitana branding — `aiplatform`, `aitanalabs.com`, `aitana-multivac-*` (item #4).
- "Aitana" appears in dev-page titles, doc comments, a `__aitanaTransport` internal field, the `aitana://` citation URI scheme, and an `aitana skill create` CLI example (item #11).
- `_MCP_SANDBOX_URL` defaults to `https://mcp-sandbox-66pa3y5xnq-ew.a.run.app/sandbox.html` — a live Aitana Cloud Run service (item #12).

**Impact:**

- Any fork that relies on the command-line seeder (`seed_skills.py`) gets broken or Aitana-branded output.
- A fork that forgets `PLATFORM_OWNER_EMAIL` ships with skills that reference Aitana's identity.
- The `aitana://` URI is a load-bearing protocol identifier that shows up in `InlineCitation`, making it visible to users as a brand marker.
- The MCP sandbox URL ships broken-by-default: it works only while Aitana keeps that service running and only Aitana-hosted content can use it.

## Goals

**Primary Goal:** Any downstream fork should be able to run the template out-of-the-box
without patching Aitana-specific values, and should get loud errors (not silent wrong
defaults) when required configuration is missing.

**Success Metrics:**
- `seed_skills.py` works correctly for a skill not in the original five without touching the dict.
- `PLATFORM_OWNER_EMAIL` unset in a non-LOCAL_MODE env causes a startup failure with a clear message, not a silent wrong owner.
- A fork that sets `PLATFORM_SEED_PROJECT` in env can run the CLI seeder against its own GCP project.
- `_MCP_SANDBOX_URL` substitution defaults to an empty string; if no override is set the feature degrades gracefully (MCP Apps disabled, not misconfigured).
- The `aitana://` URI scheme and `__aitanaTransport` field name are sourced from a single constant in `branding.ts` / `branding.py` so a fork can rebrand in one file.

**Non-Goals:**
- Full rebrand automation (scaffolding, search-and-replace tooling) — that is a separate template-init concern.
- Changing the `aiplatform` binary name in the Aitana product itself — the rename only affects how the template packages the CLI.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | 0 | No request-path changes |
| 2 | EARNED TRUST | 0 | |
| 3 | SKILLS, NOT FEATURES | +1 | Skills become more portable across forks |
| 4 | RIGHT MODEL, RIGHT MOMENT | 0 | |
| 5 | GRACEFUL DEGRADATION | +1 | Fail-loud > silent wrong default; MCP sandbox degrades to disabled |
| 6 | PROTOCOL OVER CUSTOM | +1 | Removing brand-custom URI hardcoding |
| 7 | API FIRST | 0 | |
| 8 | OBSERVABLE BY DEFAULT | +1 | Startup validation surfaces mis-config early |
| 9 | SECURE BY CONSTRUCTION | 0 | |
| 10 | THIN CLIENT, FAT PROTOCOL | 0 | |
| | **Net Score** | **+4** | Meets threshold |

## Design

### Item #1 — Seed skills from SKILL.md frontmatter

**File:** `backend/scripts/seed_skills.py`

Replace the `DISPLAY_NAMES` / `TAGS` / `INITIAL_MESSAGES` dicts with a frontmatter read:

```python
# Before (closed dict)
DISPLAY_NAMES = {"ai-search": "AI Search", "code-assistant": "Code Assistant", ...}

# After (read from SKILL.md metadata)
import yaml, pathlib

def _read_skill_md_meta(skill_dir: pathlib.Path) -> dict:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {}
    text = skill_md.read_text()
    # Extract YAML frontmatter between --- fences
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    return {}
```

`displayName`, `tags`, and `initialMessage` are already defined in SKILL.md frontmatter
(per the Agent Skills spec). The dict is then unnecessary; delete it.

### Item #2 — Replace project pin with env-var / ADC

**File:** `backend/scripts/seed_skills.py` line 36, `backend/scripts/_env.py`

```python
# Before
pin_project_for_env("dev")

# After — read from env, fall back to ADC's project
import os
project = os.environ.get("PLATFORM_SEED_PROJECT") or _gcp_project_from_adc()
if project:
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
```

Add `PLATFORM_SEED_PROJECT` to the template's `.env.example` with a comment:
```
# Override the GCP project used by seed_skills.py.
# Defaults to GOOGLE_CLOUD_PROJECT / ADC project.
PLATFORM_SEED_PROJECT=
```

Remove `pin_project_for_env` from `_env.py` if its only callers are the seeder; otherwise
make it accept an explicit project arg.

### Item #3 — Fail-loud when PLATFORM_OWNER_EMAIL is unset

**File:** `backend/admin/platform_seed.py`

```python
# Before
PLATFORM_OWNER_EMAIL = os.environ.get("PLATFORM_OWNER_EMAIL", "platform@aitanalabs.com")

# After
_raw = os.environ.get("PLATFORM_OWNER_EMAIL", "")
if not _raw:
    if LOCAL_MODE:
        _raw = f"platform@localhost"  # acceptable stub for local dev
    else:
        raise RuntimeError(
            "PLATFORM_OWNER_EMAIL is required in non-LOCAL_MODE. "
            "Set it to the platform admin email for this deployment."
        )
PLATFORM_OWNER_EMAIL = _raw
```

Add `PLATFORM_OWNER_EMAIL` to `cloudbuild.yaml` substitutions with a `_PLATFORM_OWNER_EMAIL`
substitution default of `""` so Cloud Build deploys still get a useful error rather than
silently using the Aitana fallback.

### Item #4 — CLI brand de-coupling

**Files:** `cli/pyproject.toml`, `cli/aiplatform/http.py`

The binary name stays `aiplatform` in Aitana's own product (it was renamed from `aitana`
once already). For the template, the fix is:

1. Move `_DEFAULT_URLS` from a hardcoded dict to a `cli/config.yaml` file read at startup,
   with `AIPLATFORM_API_URL_*` env-var overrides already documented:

```yaml
# cli/config.yaml (ships in the template; forks override the values)
environments:
  local:  http://localhost:1956
  dev:    ""   # set AIPLATFORM_API_URL_DEV
  test:   ""   # set AIPLATFORM_API_URL_TEST
  prod:   ""   # set AIPLATFORM_API_URL_PROD
```

2. Remove the docstring sentence that says *"Brand and backend remain Aitana Labs /
   aitana-multivac-*"* — it signals downstream is second-class.

3. Add a note to `cli/README.md` explaining how to rename the binary in a fork via
   `pyproject.toml` `[project.scripts]`.

### Item #11 — Aitana brand strings in code

**Files to change:**

| File | Current | Fix |
|------|---------|-----|
| `frontend/src/components/chat/InlineCitation.tsx:9,62` | `aitana://` URI scheme | Read from `branding.ts` constant `CITATION_SCHEME` |
| `frontend/src/app/dev/mcp-apps/passive/page.tsx:43` | `__aitanaTransport` field | Read from `branding.ts` constant `TRANSPORT_FIELD` |
| `frontend/src/app/skills/new/page.tsx:10` | `aitana skill create` CLI example | Change to generic `aiplatform skill create` |
| `frontend/src/app/dev/mcp-apps/page.tsx:12` | "Aitana MCP Apps" title | Generic "MCP Apps" |
| `frontend/src/app/dev/rich-media/page.tsx:80,125,127` | fixture filename + display text | Generic names |
| `frontend/src/types/skill.ts:5` | doc comment | Remove brand reference |

**`branding.ts` addition:**

```ts
// frontend/src/lib/branding.ts  (new file, forks edit this one place)
export const CITATION_SCHEME = process.env.NEXT_PUBLIC_CITATION_SCHEME ?? "inline-citation";
export const TRANSPORT_FIELD = `__${process.env.NEXT_PUBLIC_APP_SLUG ?? "platform"}Transport`;
```

The `aitana://` URI is the highest-priority fix because it appears in user-visible content
(citation chips in chat). The others are internal-only but still confusing for fork authors.

### Item #12 — MCP sandbox URL default

**File:** `cloudbuild.yaml`

```yaml
# Before
substitutions:
  _MCP_SANDBOX_URL: 'https://mcp-sandbox-66pa3y5xnq-ew.a.run.app/sandbox.html'

# After
substitutions:
  _MCP_SANDBOX_URL: ''   # Set to your deployed mcp-sandbox URL; blank = MCP Apps disabled
```

In `backend/config.py` / wherever `MCP_SANDBOX_URL` is consumed:

```python
MCP_SANDBOX_URL = os.environ.get("MCP_SANDBOX_URL", "")
MCP_APPS_ENABLED = bool(MCP_SANDBOX_URL)
```

Frontend reads `NEXT_PUBLIC_MCP_SANDBOX_URL`; if blank, `MCPAppToolCallRouter` renders a
"MCP Apps not configured" stub instead of a broken iframe.

### CLI Surface

No new commands. The config.yaml approach lets `aiplatform --env` work unchanged.

## Implementation Plan

| Step | Description | Effort |
|------|-------------|--------|
| 1 | Replace DISPLAY_NAMES/TAGS/INITIAL_MESSAGES dicts with frontmatter read (#1) | 2h |
| 2 | Replace `pin_project_for_env` with `PLATFORM_SEED_PROJECT` env-var (#2) | 1h |
| 3 | Add startup validation for `PLATFORM_OWNER_EMAIL` (#3) | 1h |
| 4 | Move `_DEFAULT_URLS` to `cli/config.yaml`; remove brand docstring (#4) | 2h |
| 5 | Add `branding.ts` + wire `CITATION_SCHEME` + `TRANSPORT_FIELD` (#11) | 2h |
| 6 | Set `_MCP_SANDBOX_URL` default to `''`; add `MCP_APPS_ENABLED` guard (#12) | 1h |
| 7 | Update tests for all six changes | 2h |
| 8 | Update `docs/ops/` + `CLAUDE.md` + `.env.example` | 1h |

**Total: ~12h ≈ 1.5d** (within 2d estimate, leaving buffer for PR review).

## Testing Strategy

- **`test_seed_skills.py`** — add a fixture skill outside the five-skill list; assert display name, tags, and initial message are read correctly from its SKILL.md.
- **`test_platform_seed.py`** — assert startup raises `RuntimeError` when `PLATFORM_OWNER_EMAIL` is unset and `LOCAL_MODE=false`.
- **`test_branding.ts`** — snapshot test for `CITATION_SCHEME` default and env-override.
- **`test_mcp_apps_disabled.tsx`** — render `MCPAppToolCallRouter` with empty `MCP_SANDBOX_URL`; assert stub rendered, not broken iframe.
- Manual smoke: fork the template locally; run seeder without any Aitana-specific env vars; verify clean output.

## Success Criteria

- [ ] `seed_skills.py` with a sixth skill template correctly seeds display name, tags, and initial message from its SKILL.md frontmatter.
- [ ] `seed_skills.py` run with `PLATFORM_SEED_PROJECT=my-project` targets the correct GCP project.
- [ ] Backend startup in non-LOCAL_MODE with `PLATFORM_OWNER_EMAIL` unset exits with a useful error message.
- [ ] `_MCP_SANDBOX_URL` blank → `MCPAppToolCallRouter` renders a graceful "not configured" state.
- [ ] `InlineCitation` uses `CITATION_SCHEME` from `branding.ts`; no `aitana://` literal in the component.
- [ ] All existing tests pass.

## Related Documents

- [local-dev-cli.md](../../v6.1.0/local-dev-cli.md)
- [aitana-template-publish skill](../../../.claude/skills/aitana-template-publish/SKILL.md)
- [SEQUENCE.md](SEQUENCE.md)
