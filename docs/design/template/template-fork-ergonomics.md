# Template Fork Ergonomics

**Status**: Planned  
**Priority**: P0 (was P1 — bumped after gde-ap-agent fork experience)  
**Estimated**: 4d (was 2d — doubled to absorb items #13–#22)  
**Scope**: Backend + Frontend + CLI + Config + Cloud Build + Bootstrap scripts  
**Dependencies**: None  
**Created**: 2026-05-21  
**Last Updated**: 2026-06-02  
**Source items**: #1 #2 #3 #4 #11 #12 (CPH Uni AIPLA upstream feedback); #13–#22 (gde-ap-agent fork, 2026-06-02)

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
- A fresh fork cannot reach a working `/chat` after `git push` without four undocumented one-time bootstrap steps (Agent Engine, ADK artifact bucket, AI Search datastore, MCP sandbox deploy) — each surfaced as a production 4xx/5xx in the gde-ap-agent fork (items #13a–#13d).
- `VertexAiSessionService` is built with `GOOGLE_CLOUD_LOCATION` even though Agent Engine often lives in a different region (e.g. `us-central1` while Cloud Run is `europe-west1`), causing 404s on every chat-start (item #14).
- `cloudbuild.yaml`'s `--set-env-vars` uses comma as the kv-separator, so any list-valued substitution (`ADMIN_SEED_ALLOWED_SAS`, `ALLOWED_HOST_ORIGINS`) silently corrupts the deploy unless the `^|^` / `^@^` delimiter override is used everywhere (item #18).
- Sub-agent wiring forces forks to know generated skill UUIDs even though templates can only know names (item #19).
- The seven default demo skills (`code-assistant`, `general-assistant`, etc.) are opt-out-by-deletion: a fork has to delete eight files to ship a clean skill bundle (item #17).

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

---

## Findings from gde-ap-agent fork (2026-06-02)

Source: a `Track 3` competition fork shipped end-to-end against `multivac-internal-dev`
between 2026-05-30 and 2026-06-02. The list below is every divergence from the
template that traces back to either (a) a 4xx/5xx in production or (b) a feature
the template should arguably ship that this fork had to invent. Each item names the
commit so the upstream owner can read the diff.

### Item #13 — Deployed-fork bootstrap automation

A clean fork cannot reach a working `/chat` after `git push` without four
one-time GCP resource creations. Each surfaced as a swallowed exception. The
template should either auto-provision these in `bootstrap-gcp-project.sh` or
ship a single `bootstrap-deployed-fork.sh`.

| Sub-item | Symptom | Bootstrap script gde-ap-agent had to write |
|---|---|---|
| #13a Vertex Agent Engine | `400 INVALID_ARGUMENT. Invalid ReasoningEngine resource name` on every chat — `AGENT_ENGINE_ID` Secret Manager secret held literal `"dummy_value"` and `fast_api_app.py:74` treats any truthy value as "use Vertex sessions" | [`scripts/create-agent-engine.sh`](../../../scripts/create-agent-engine.sh) (commits `ac8b00d`, `cd74b8c`) |
| #13b ADK artifact bucket | `404 ... The specified bucket does not exist` on every flow that touches `load_artifacts` (document-loader callback, audit view) — bucket name is conventionally `gs://<project>-artifacts` but it's never created | [`scripts/create-artifact-bucket.sh`](../../../scripts/create-artifact-bucket.sh) (commit `59a4428`) |
| #13c Vertex AI Search datastore | `400 ... datastore: Invalid Vertex AI datastore resource name`. Two bugs: datastore didn't exist *and* SKILL.md `datastore_id: ds-ap-vendors` was a bare id that the runtime never expanded to the full `projects/.../dataStores/...` path | [`scripts/create-search-datastore.sh`](../../../scripts/create-search-datastore.sh) + bare-id expansion (commit `20d4b29`) |
| #13d MCP sandbox deploy | Template defaults `_MCP_SANDBOX_URL` to Aitana's live URL (see #12), so MCP Apps either point at someone else's infra or 404. The fork had to deploy its own | [`scripts/deploy-mcp-sandbox.sh`](../../../scripts/deploy-mcp-sandbox.sh) + [`scripts/verify-mcp-artefacts.sh`](../../../scripts/verify-mcp-artefacts.sh) (commit `daecd4e`) |

**Fix:** Either fold all four into `bootstrap-gcp-project.sh` (preferred — single
command), or ship `bootstrap-deployed-fork.sh` with the same four steps and a
`README.md` "Deployed-Fork Setup" section. The fork's "Common bootstrap failures"
table (committed in `cd74b8c`) is the artifact upstream should pull in verbatim
as the inverse-lookup index.

### Item #14 — Region-aware VertexAiSessionService construction

**File:** `backend/adk/sessions.py` (or wherever `get_session_service()` lives)

```python
# Before
service = VertexAiSessionService(
    project=GOOGLE_CLOUD_PROJECT,
    location=GOOGLE_CLOUD_LOCATION,  # europe-west1 (Cloud Run region)
)

# After — parse the region from AGENT_ENGINE_ID if it's a full resource name
def _extract_agent_engine_location(engine_id: str) -> str | None:
    # Matches projects/<p>/locations/<region>/reasoningEngines/<id>
    m = re.match(r"projects/[^/]+/locations/([^/]+)/reasoningEngines/\d+", engine_id)
    return m.group(1) if m else None

agent_region = _extract_agent_engine_location(AGENT_ENGINE_ID) or GOOGLE_CLOUD_LOCATION
service = VertexAiSessionService(project=GOOGLE_CLOUD_PROJECT, location=agent_region)
```

**Why:** Agent Engine isn't available in every Cloud Run region. The fork's
`create-agent-engine.sh` defaults to `us-central1`; the Cloud Run service is in
`europe-west1`. Without this parsing the route hits
`projects/<p>/locations/europe-west1/reasoningEngines/<id>` and Vertex correctly
404s. Apply identical fix to `VertexAiMemoryBankService`. Commit `1801cdb`.

**Bonus:** the same commit fixed a UX bug where the AG-UI route swallowed
`RUN_ERROR` events and the audit view rendered "specialist returned no tool
calls" instead. Worth surfacing `RUN_ERROR` events as a first-class chip state
in the template's protocol layer.

### Item #15 — Bare-id expansion for SKILL.md resource references

**File:** `backend/skills/skill_config.py` (or the toolConfig loader)

When a SKILL.md author writes:

```yaml
toolConfigs:
  ai_search:
    datastore_id: ds-ap-vendors           # bare id — what feels natural
```

the runtime should expand to the full resource path
`projects/<GOOGLE_CLOUD_PROJECT>/locations/<REGION>/collections/default_collection/dataStores/ds-ap-vendors`
before handing to `VertexAiSearchTool`. Today it forwards the bare string and
Vertex rejects it. Same pattern applies to:

- `bucket="demo"` sentinel in `import_gcs_object` (was not resolved before hitting
  GCS — `gs://demo/` crashed; fork fixed in commit `a2d6398`)
- any other `*_id` field in `toolConfigs` that has a canonical resource-path form

Suggest a single `resolve_resource_id(kind, value)` indirection invoked at
config-load time, with `kind` taking values `gcs_bucket`, `vertex_datastore`,
`reasoning_engine`, etc. Commit `20d4b29` shows the bare-id case.

### Item #16 — Idempotent skill-seeder ownership reconciliation

**File:** `backend/admin/platform_seed.py`

A fork that renames `PLATFORM_OWNER_UID` (which it must — see #11 / #17) keeps
the *old* aitana-platform-owned skill rows in Firestore until manually purged.
The fork had to grow two new seeder phases:

1. **Purge stale platform-owner skills** — query for skills whose `ownerUid` is
   the previous platform owner UID and delete them (commits `84a1e18`, `9fb5618`).
2. **Refresh template fields on existing skills** — when a SKILL.md changes
   (displayName, tags, initialMessage) the seeder must update the corresponding
   Firestore document, not just create-if-missing (commit `fa1d150`).

```python
# Add to platform_seed.py after the create-if-missing pass
def reconcile_platform_skills(db, current_owner_uid, previous_owner_uids):
    # Phase 1: purge skills owned by previous platform owners (no orderBy to
    # avoid composite-index requirements during first deploy)
    for prev in previous_owner_uids:
        for doc in db.collection("skills").where("ownerUid", "==", prev).stream():
            doc.reference.delete()

    # Phase 2: refresh template fields on current-owner skills
    for skill_dir in template_skill_dirs():
        meta = read_skill_md_frontmatter(skill_dir)
        ref = db.collection("skills").document(meta["name"])
        ref.set(meta, merge=True)  # merge so user-set fields survive
```

Document `PLATFORM_PREVIOUS_OWNER_UIDS` as a comma-separated env var.

### Item #17 — Default demo skills should be opt-in

**Files:** `backend/skills/templates/{code-assistant,data-extractor,document-analyst,general-assistant,web-researcher,workspace-demo,workspace-demo-interactive}/SKILL.md`

The fork deleted all seven in commit `a42b21f`. The template should ship them
under `backend/skills/templates/demo/` and gate seeding on a
`_INCLUDE_DEMO_SKILLS` Cloud Build substitution / env var
(default `false`). Forks that want them flip one flag; forks that don't, get a
clean slate.

### Item #18 — Cloud Build env-var comma-escaping foot-gun

**File:** `cloudbuild.yaml`

`gcloud run deploy --set-env-vars KEY=VAL,KEY2=VAL2` uses comma as the kv
separator. Any *value* that contains a comma (URL list, SA-allowlist) silently
corrupts the deploy. The fork hit this three times:

- `ADMIN_SEED_ALLOWED_SAS` (commits `9b76b0b`, `9466636`) — fix used `^|^` delimiter override
- `ALLOWED_HOST_ORIGINS` (commit `4cfcaf9`) — fix used `^@^` delimiter override

```yaml
# Before
- '--set-env-vars'
- 'ADMIN_SEED_ALLOWED_SAS=sa1@x.iam,sa2@x.iam,FOO=bar'

# After — use gcloud's delimiter-override syntax (see `gcloud topic escaping`)
- '--set-env-vars'
- '^|^ADMIN_SEED_ALLOWED_SAS=sa1@x.iam,sa2@x.iam|FOO=bar'
```

**Rule for the template:** always use the `^|^` delimiter syntax in
`cloudbuild.yaml`, even when current values happen not to need it. A future
single-value-with-comma will silently break otherwise. Roll into
[`template-cloudbuild-hardening.md`](./template-cloudbuild-hardening.md).

**Related deploy fixes in the same cluster:**
- `--service-account` had to be made explicit on `gcloud run deploy` (commit `48a04a4`)
- Seeder needs a cold-start sleep before its first Firestore write on a fresh service (commit `a95da1f`)

### Item #19 — Sub-agent resolution by skill name, not generated UUID

**File:** `backend/adk/agent.py`

Templates declare sub-agents by name:

```yaml
subSkills:
  - docparse
  - ap-validator
  - ap-poster
```

…but the skill processor receives the *generated UUID* of each skill row. A
fork has no way to write the UUID into its template. The fork added
`skill_config.find_by_name()` + a name-fallback in the sub-agent loop (commit
`dca1323`). Upstream this so all forks can rely on declarative-by-name
`subSkills` and the new `role: "hub" | "specialist"` discriminator (#21)
without per-fork plumbing.

### Item #20 — Empty-string env-var fallback should use `||`, not `??`

**File:** `frontend/src/components/protocols/MCPAppToolCallRouter.tsx` (and
similar)

```ts
// Before — fails when SANDBOX_PROXY_URL is "" (legitimately empty)
const url = process.env.SANDBOX_PROXY_URL ?? "http://localhost:8888";

// After
const url = process.env.SANDBOX_PROXY_URL || "http://localhost:8888";
```

The `??` nullish-coalescing operator does not fall back on the empty string
that `process.env.*` returns when an env var is set-but-empty (common in
container envs that pre-declare all variables). Commit `5be9ae2`. Worth
grepping the entire template for `process\.env\.\w+ ??` and converting to `||`
for env-var defaults. Also worth a typed `env(name, default)` helper that
encodes this once.

### Item #21 — SkillConfig `role: "hub" | "specialist"` discriminator

**File:** `backend/skills/skill_config.py`, `frontend/src/lib/skillMeta.tsx`

The template renders every skill as a peer chat tab, even when the skill's
SKILL.md explicitly assumes orchestrator-provided context (e.g.
`"You receive a structured invoice from the extraction step"`). The fork built
an entire Audit View UX around the missing distinction (see
[`docs/design/forks/gde-ap-agent/multi-agent-inspector-ux.md`](../forks/gde-ap-agent/multi-agent-inspector-ux.md),
commit `4f9267f`).

Adding `role: "hub" | "specialist"` to SKILL.md frontmatter (default `"hub"`
for backward compat) lets the template:

- Route `/chat/<specialist-id>` to the parent hub when `role: specialist` and no `?devmode=1`
- Render specialists as inspector chips next to the hub tab rather than peer tabs
- Use the role to choose between free-text chat and structured-input forms

Pair with the new structured-invocation endpoint
(`POST /api/skill/{id}/structured`, [`backend/skills/structured_invocation.py`](../../../backend/skills/structured_invocation.py),
commit `4f9267f`) — both belong in the template.

### Item #22 — Net-new UI surfaces this fork built that belong in the template

These are not bugs — they are missing capabilities the fork shipped because
any non-trivial demo will need them. Suggest upstreaming each as a `?feature=…`
toggle so the template stays minimal but forks don't reinvent.

| Surface | Files | Commit |
|---|---|---|
| GCS bucket browser (sidebar + backend `gcs_browser` tool + cloudbuild wiring for demo bucket) | [`backend/tools/gcs_browser/`](../../../backend/tools/gcs_browser/) + [`frontend/src/components/doc-browser/GCSFileBrowser.tsx`](../../../frontend/src/components/doc-browser/GCSFileBrowser.tsx) | `06262dc` + `bcb51ac` + `42b8fe6` |
| Multi-agent Audit View (chips + inspector panel + structured-input forms) | [`frontend/src/components/audit/`](../../../frontend/src/components/audit/) | `4f9267f` + `e327dcd` + `e335483` |
| Doc panel view modes (side / focus / collapsed + drag resize) | [`frontend/src/components/doc-browser/`](../../../frontend/src/components/doc-browser/) | `feb4071` |
| Collapsible sidebar accordion w/ per-section toggles | [`frontend/src/components/navigation/Sidebar*`](../../../frontend/src/components/navigation/) | `19995af` |
| `ap-vendor-kg` style data-driven MCP App widget pattern | [`infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html`](../../../infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html) | `4f9267f` |

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
| 7 | Fold all 4 deployed-fork bootstrap scripts into `bootstrap-gcp-project.sh` + add "Deployed-Fork Setup" + "Common bootstrap failures" docs section (#13) | 4h |
| 8 | Region-aware `VertexAiSessionService` + `VertexAiMemoryBankService` construction + surface `RUN_ERROR` in audit view (#14) | 2h |
| 9 | `resolve_resource_id(kind, value)` indirection for bare-id expansion (#15) | 2h |
| 10 | Idempotent seeder reconciliation (purge + refresh phases) + `PLATFORM_PREVIOUS_OWNER_UIDS` (#16) | 2h |
| 11 | Move 7 default skills under `demo/`; gate on `_INCLUDE_DEMO_SKILLS` substitution (#17) | 1h |
| 12 | Audit `cloudbuild.yaml` to use `^|^` delimiter syntax everywhere; explicit `--service-account`; cold-start sleep (#18) | 2h |
| 13 | Sub-agent resolution by name + `role` discriminator (#19, #21) + structured-input endpoint upstream | 4h |
| 14 | Grep template for `process.env.X ??` → `||`; add typed `env()` helper (#20) | 1h |
| 15 | Upstream net-new surfaces as opt-in (`?feature=`) toggles or as ready-to-import components (#22) | 6h |
| 16 | Update tests for all items above | 4h |
| 17 | Update `docs/ops/` + `CLAUDE.md` + `.env.example` + bootstrap-failures table | 2h |

**Total: ~39h ≈ 5d** (over original 2d; matches new 4d estimate plus PR-review buffer).

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
- [ ] A clean fork can run `bootstrap-gcp-project.sh <project> <sa>` and reach a working `/chat` on first deploy without any of the four follow-up bootstrap scripts (#13).
- [ ] Backend with Agent Engine in `us-central1` and Cloud Run in `europe-west1` chats successfully (#14).
- [ ] `SKILL.md` with `datastore_id: <bare-id>` resolves to the full resource path automatically (#15).
- [ ] Renaming `PLATFORM_OWNER_UID` cleans up previously-owned skills on next deploy (#16).
- [ ] `_INCLUDE_DEMO_SKILLS=false` ships zero default skills; `=true` ships the seven demo skills (#17).
- [ ] Adding a comma-bearing value to any `cloudbuild.yaml` env var works without code changes (#18).
- [ ] `subSkills: [name, name]` resolves correctly in a fresh fork without name→UUID plumbing (#19).
- [ ] All instances of `process.env.X ??` for env-var defaults converted to `||` or `env()` helper (#20).
- [ ] SKILL.md with `role: specialist` is no longer reachable via `/chat/<skill-id>` peer URL without `?devmode=1` (#21).
- [ ] All existing tests pass.

## Related Documents

- [local-dev-cli.md](../../v6.1.0/local-dev-cli.md)
- [aitana-template-publish skill](../../../.claude/skills/aitana-template-publish/SKILL.md)
- [template-cloudbuild-hardening.md](./template-cloudbuild-hardening.md) — pairs with #18
- [multi-agent-inspector-ux.md](../forks/gde-ap-agent/multi-agent-inspector-ux.md) — original design for #21/#22 Audit View
- [gde-ap-agent SUBMISSION.md](../../../SUBMISSION.md) — competition fork that surfaced #13–#22
- [SEQUENCE.md](SEQUENCE.md)
