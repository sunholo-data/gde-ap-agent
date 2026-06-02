# GDE AP Agent

**Now branded in the UI as `ailang-parse · AP Showcase`** — a live demo of
[ailang-parse](https://www.sunholo.com/ailang-parse) (deterministic invoice
extraction) running inside a Google ADK multi-agent AP pipeline. Part of the
[AILANG](https://ailang.sunholo.com) family. The underlying pipeline is unchanged;
only the visual identity of the deployed app has been rebranded.

Built for the [Google for Startups AI Agents Challenge, Track 3](./SUBMISSION.md). Live demo: https://gde-ap-agent-blqtqfexwa-ew.a.run.app

> Built on the open-source [ai-protocol-platform](https://github.com/sunholo-data/ai-protocol-platform) template (Skills + AG-UI + A2UI + MCP Apps + A2A on Google ADK).
>
> 🚀 **New here?** Start with [**WORKSHOP.md**](./WORKSHOP.md) — clone, set
> `LOCAL_MODE=1`, run `make dev`, working chat UI in under 30 minutes with
> zero GCP credentials.

## AP Agent Pipeline

```
ap-orchestrator (Gemini 2.5 Pro)
    ↓ docparse      — invoice field extraction
    ↓ ap-validator  — grounded validation vs vendor master + POs
    ↓ ap-poster     — post clean or escalate exceptions
```

**Visual features**: Navy+gold AP theme · live pipeline step visualizer · A2UI invoice review card · MCP App vendor globe · MCP App analytics dashboard · per-specialist **Audit View** with live chips, history, structured-input runs, and an `ap-vendor-kg` MCP App showcasing AG-UI + A2UI + MCP Apps together

**One pipeline, four cooperating agents.** Drop an invoice — the orchestrator delegates extraction, validation, and posting, then returns a single audit-ready decision. Each specialist&apos;s work is observable live via the Audit View chip + side panel.

See [SUBMISSION.md](./SUBMISSION.md) for full details and live demo URL.

## Quick Start

### Backend
```bash
cd backend
make install
make dev          # API on port 1956
make playground   # ADK dev UI on port 8501
```

### Frontend
```bash
cd frontend
npm install
npm run dev       # Next.js on port 3000
```

## Deployed-Fork Setup (one-time, per fork)

When forking this repo and deploying to a fresh GCP project, several one-time
infrastructure steps are needed before chat will work. **Skip any of these
and the chat path will return HTTP 500** with cryptic Vertex AI errors.

> **The scripts in this section are stopgaps.** The canonical home for these
> resources is **Terraform in the `multivac-aitana` infrastructure repo** —
> the `_ENABLE_AGENT_ENGINE`, `_PROJECT_ID`, and `_AP_DEMO_BUCKET` substitutions
> already flow through `cloudbuild.yaml` from terraform-managed tfvars, and the
> Reasoning Engine / artifact bucket / demo bucket should follow the same
> pattern. The shell scripts below let you unblock dev today; promote them
> to Terraform modules at the next infra-repo PR window. See script header
> comments for the equivalent Terraform resources.

### 1. Create the Vertex AI Reasoning Engine

ADK's `VertexAiSessionService` needs a Reasoning Engine to namespace chat
sessions. Without it, every `POST /api/skill/{id}/stream` request fails with
`google.genai.errors.ClientError: 400 INVALID_ARGUMENT. Invalid ReasoningEngine
resource name.` ([fast_api_app.py:74](backend/fast_api_app.py#L74)).

```bash
./scripts/create-agent-engine.sh <project-id> us-central1
```

The script is idempotent — re-runs no-op if an engine with `displayName:
gde-ap-agent-sessions` already exists. It populates the `AGENT_ENGINE_ID`
Secret Manager secret with the full resource name
(`projects/{NUM}/locations/{REGION}/reasoningEngines/{ID}`).

Verify the secret holds a real resource name (not `dummy_value`):

```bash
gcloud secrets versions access latest --secret=AGENT_ENGINE_ID --project=<project-id>
```

### 2. Enable the Agent Engine in Cloud Build

Set `_ENABLE_AGENT_ENGINE=true` in the fork's Cloud Build substitutions
(terraform-managed in [cloudbuild.yaml:25](cloudbuild.yaml#L25)). Without
this, the `--set-secrets=AGENT_ENGINE_ID=AGENT_ENGINE_ID:latest` flag is
not injected and the deployed service falls back to in-memory sessions
(chat works, but history is lost on every cold start).

### 3. Create the ADK Artifact Service bucket

ADK's artifact service stores in-session uploads (documents, tool
outputs that need to survive a turn) in a GCS bucket named via
`ADK_ARTIFACT_BUCKET`. Without it, every artifact read/write fails
with `404 ... The specified bucket does not exist.` and the docparse
skill (along with any flow that touches `load_artifacts`) silently
returns no content.

```bash
./scripts/create-artifact-bucket.sh <project-id> <region>
```

The script is idempotent — re-runs only update IAM. It creates
`gs://<project-id>-artifacts` in your Cloud Run region with uniform
bucket-level access + public-access-prevention, and grants the Cloud
Run SA (`sa-gde-ap-agent@<project-id>`) `roles/storage.objectAdmin`.

### 4. Build + deploy the MCP App sandbox

The MCP App sandbox is a **separate Cloud Run service** that serves
each widget's HTML from `infrastructure/mcp-sandbox/artefacts/<name>/index.html`.
Importantly: the main `gde-ap-agent` Cloud Build does **not** rebuild
the sandbox — when you add a new widget (eg. `ap-vendor-kg`), you
must redeploy the sandbox separately, otherwise the iframe inside the
Audit View shows a permanent spinner because the widget HTML returns 404.

```bash
make deploy-mcp-sandbox       # gcloud run deploy --source .
make verify-mcp-artefacts     # asserts each local widget is reachable
```

`verify-mcp-artefacts` walks `infrastructure/mcp-sandbox/artefacts/` and
probes each `${SANDBOX_URL}/artefacts/<name>/index.html`. It fails fast
with an actionable hint when a local widget is missing from the
deployed image — exactly the "I added it but forgot to redeploy" trap
that surfaced as an empty Vendor Knowledge Graph in the validator
Audit View.

### 5. Create the AP-Validator Vertex AI Search datastore

The validator skill uses `VertexAiSearchTool` to ground vendor-master /
PO / approval-policy lookups. Without a datastore at the configured
resource path, every validation call fails with:

```
400 INVALID_ARGUMENT.
tools[0].retrieval.vertex_ai_search.datastore: Invalid Vertex AI datastore resource name
```

```bash
./scripts/create-search-datastore.sh <project-id> eu
```

Defaults to `multivac-internal-dev`/`eu` with id `ds-ap-vendors`.
Idempotent — re-runs no-op on existing datastores. Cloud Build's
substitutions set `DATASTORE_LOCATION=eu`, and the backend's
`_expand_datastore_id` helper turns the bare `ds-ap-vendors` token
in [ap-validator/SKILL.md](backend/skills/templates/ap-validator/SKILL.md)
into the full resource name at agent-build time — no SKILL.md change
needed when re-pointing to a different project (just update
`GOOGLE_CLOUD_PROJECT`).

> The datastore is created with `contentConfig: CONTENT_REQUIRED`
> (structured-documents-required).

Load the demo vendor master (5 vendors, 3 open POs, 3 prior invoices,
3 approval policies — all cross-referenced with the example invoices
in `infrastructure/demo-invoices/`):

```bash
make load-vendor-master
```

Idempotent — `reconciliationMode: INCREMENTAL` upserts each document
by `id`, so re-runs after editing
`infrastructure/demo-vendor-master/generate.py` update the records in
place. The records ground every check the validator does: vendor
approved (Acme GmbH = yes, BlockedCo = no), PO match (PO-2026-0189
for €9,000 from Acme), duplicate detection (prior invoice
INV-2025-187 has the same €9,000 from Acme two months ago), policy
(Cloud Services threshold €10k), tax (DE 19%).

### 6. Seed the demo invoices bucket (optional)

For the Example Invoices sidebar section to populate:

```bash
./infrastructure/demo-invoices/setup-demo-bucket.sh
```

This uploads 9 sample invoices to the `_AP_DEMO_BUCKET` bucket
(`gde-ap-agent-demo-invoices` by default).

### 7. Verify everything works

After a deploy, run the verification scripts:

```bash
make verify-skill-schemas              # platform skills declare structuredInput
GDE_AP_URL=https://your-fork.run.app \
  make verify-audit-view               # full end-to-end audit view check
```

Tail Cloud Run logs to debug deploy issues:

```bash
GCP_PROJECT=<project> ./scripts/tail-logs.sh         # recent errors (1h)
GCP_PROJECT=<project> ./scripts/tail-logs.sh chat    # chat-stream 500s
GCP_PROJECT=<project> ./scripts/tail-logs.sh tail    # live stream
```

### Common bootstrap failures

| Symptom | Cause | Fix |
|---|---|---|
| Chat returns 500, log shows `Invalid ReasoningEngine resource name` | `AGENT_ENGINE_ID` secret is `dummy_value` or missing | Step 1 |
| Specialists show "Skill does not declare metadata.structuredInput" | Platform seed step skipped existing skills (pre-`fa1d150` builds) | Trigger a fresh deploy — the seed step now refreshes template fields |
| MCP App iframe (eg. Vendor Knowledge Graph) shows a permanent spinner | Widget file is in the repo but the sandbox image doesn't include it | `make verify-mcp-artefacts` to confirm; `make deploy-mcp-sandbox` to ship |
| Document load / artifact write fails with `404 ... bucket does not exist` | ADK artifact bucket missing for the project | `make create-artifact-bucket` (Step 3) |
| AP Validator returns `400 INVALID_ARGUMENT ... Invalid Vertex AI datastore resource name` | Vertex AI Search datastore missing | `make create-search-datastore` (Step 5) |
| Example Invoices section shows "No demo files" | `_AP_DEMO_BUCKET` empty or missing IAM grant for the SA | Step 4, or grant `roles/storage.objectViewer` to the Cloud Run SA |
| Audit View chips never light up | AG-UI streaming not reaching the frontend | Check CORS + `/api/proxy/*` route in [frontend/src/app/api/proxy/[...path]/route.ts](frontend/src/app/api/proxy/[...path]/route.ts) |

## API Reference

The backend exposes a self-documenting API:

- **Interactive docs**: http://localhost:1956/docs (Swagger UI — all routes, try them live)
- **OpenAPI JSON**: http://localhost:1956/openapi.json — pipe to `jq '.paths | keys'` to list all routes
- **Skill invocation** (AG-UI streaming): `POST /api/skill/{skill_id}/stream`
- **Bare ADK routes** (dev only): exposed by `get_fast_api_app(web=True)` — use the skill route above in production

> **ADK `app_name` gotcha:** The canonical app name is `aitana_platform` (the `APP_NAME` constant in
> `backend/adk/agui.py`). The dev UI's `/list-apps` historically returned filesystem directory names —
> this version returns the correct `APP_NAME`. Never derive `app_name` from `/list-apps` paths in code;
> always import the `APP_NAME` constant.

## Architecture

```
platform/
├── frontend/     # Next.js 14 + React 18 + AG-UI + A2UI + MCP Apps
├── backend/      # FastAPI + Google ADK
├── cli/          # `aiplatform` CLI
├── docs/         # Design documents
└── firestore.rules
```

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines.

See [docs/design/v5.0.0/migration-to-v6.md](docs/design/v5.0.0/migration-to-v6.md) for the full migration plan.
