# Deployed URLs — Aitana Platform v6

Canonical list of live v6 Cloud Run services, per environment.

Both services are deployed by `cloudbuild.yaml` (multi-container frontend) and
`backend/cloudbuild.yaml` (standalone backend). They are **not** Terraform-
provisioned — Terraform only manages IAM bindings against them. The URLs are
assigned by Cloud Run on first deploy and stay stable unless the service is
deleted and recreated.

## dev

- **Frontend (public, multi-container):** https://aitana-v6-frontend-66pa3y5xnq-ew.a.run.app
  - Main container: `ui:dev` — Next.js 15, listens on 8080 (Cloud Run ingress)
  - Sidecar: `backend:dev` — FastAPI + ADK, listens on 1956
  - Public health checks: `/`, `/api/health`, `/api/proxy/health` (all 200)
- **Backend (IAM-protected, standalone):** resolve with
  ```bash
  gcloud run services describe aitana-v6-backend \
    --project=aitana-multivac-dev --region=europe-west1 \
    --format='value(status.url)'
  ```
  - Needs identity-token auth: `gcloud auth print-identity-token --audiences=$URL`
  - Used by channels (Telegram/email/WhatsApp) and other SA-invoked callers.
- **MCP App sandbox proxy (public):** https://mcp-sandbox-66pa3y5xnq-ew.a.run.app
  - Image: `mcp-sandbox/sandbox:dev` from `infrastructure/mcp-sandbox/`
  - Public smoke: `GET /sandbox.html` → 200 (NOT `/healthz` — Cloud Run's
    GFE intercepts that path for its own probes; user containers never see it)
  - Separate origin from frontend per MCP Apps spec — `allow-same-origin`
    on the inner iframe is only safe when the sandbox is on a different
    origin than the host. See `docs/design/v6.1.0/implemented/mcp-sandbox-separate-origin.md`.
- **MCP map server (public):** https://mcp-ext-apps-map-66pa3y5xnq-ew.a.run.app
  - Image: `mcp-ext-apps-map/server:dev` from `infrastructure/mcp-ext-apps-map/`
    (clones `modelcontextprotocol/ext-apps` at pinned commit `0008d3b7`
    inside the Dockerfile — no vendoring; license MIT upstream)
  - Public smoke: `POST /mcp` with a `tools/list` JSON-RPC body → 200 + SSE
    `event: message data: {"result":{"tools":[{"name":"show-map", ...}]}}`
  - Reached by both: (a) the agent's `McpToolset` (server-side from
    `aitana-v6-backend`); (b) the frontend's MCP Client via the backend
    proxy `/api/proxy/mcp/ext-apps-map` (gated by Firebase auth + per-skill
    allowlist, sprint 1.7 M2B)
  - Bump pinned commit by editing `EXT_APPS_REF` in the Dockerfile.
- **Project:** `aitana-multivac-dev`
- **Region:** `europe-west1`
- **Branch → env:** `dev` branch deploys here via:
  - `trigger-aitana-dev-aitana-v6-frontend` + `trigger-aitana-dev-aitana-v6-backend`
  - `trigger-aitana-dev-mcp-sandbox` (sprint 1.7 M4)
  - `trigger-aitana-dev-mcp-ext-apps-map` (sprint 1.7 M4)

## test

Not yet cut. Will be live once the `test` branch is created and
`trigger-test` / `trigger-test-backend` fire (Terraform already reserves the
triggers — see `multivac-aitana` infrastructure repo).

- **Project:** `aitana-multivac-test`
- **Region:** `europe-west1`
- **Branch:** `test`

## prod

Not yet cut. Same story as `test`.

- **Project:** `aitana-multivac-production`
- **Region:** `europe-west1`
- **Branch:** `prod`

## Vertex AI Agent Engine resources

ADK's `VertexAiSessionService` and `VertexAiMemoryBankService` use a Vertex AI
Agent Engine (a.k.a. Reasoning Engine) resource as the persistence anchor.
The numeric ID is read from the per-project `AGENT_ENGINE_ID` Secret Manager
secret and injected into Cloud Run as an env var. **Bootstrap once per env**
with [`backend/scripts/bootstrap_agent_engine.py`](../../backend/scripts/bootstrap_agent_engine.py)
(idempotent — re-running just prints the existing ID).

| Env  | Display name | Numeric ID            | Region        |
|------|--------------|-----------------------|---------------|
| dev  | `aitana-v6`  | `6224370509212024832` | europe-west1  |
| test | `aitana-v6`  | `6388611158122692608` | europe-west1  |
| prod | `aitana-v6`  | `7741942846147526656` | europe-west1  |

Local laptop dev should set `AGENT_ENGINE_ID=6224370509212024832` in
`backend/.env` so chat history persists to the same Agent Engine the deployed
dev Cloud Run instance uses (same "laptop talks to cloud" pattern as Firebase
Auth and Firestore — relies on ADC credentials).

To re-fetch the value into Secret Manager (if the placeholder ever resurfaces
or someone reseeds with `dummy_value`):

```bash
ENV_PROJECT=aitana-multivac-dev   # or -test / -production
ID=$(GOOGLE_CLOUD_PROJECT=$ENV_PROJECT GOOGLE_CLOUD_LOCATION=europe-west1 \
     uv run python backend/scripts/bootstrap_agent_engine.py)
printf '%s' "$ID" | gcloud secrets versions add AGENT_ENGINE_ID \
  --data-file=- --project=$ENV_PROJECT
```

## How to verify

From a laptop (after `gcloud auth login`):

```bash
./scripts/smoke-deployed.sh              # dev, both services
./scripts/smoke-deployed.sh dev frontend # just the public one
./scripts/smoke-deployed.sh test         # when test is cut
```

In CI, the same checks run automatically as the last step of each cloudbuild
config (`smoke-deployed` in `cloudbuild.yaml`, `smoke-backend` in
`backend/cloudbuild.yaml`). A non-200 from any path fails the build — the
deployment does not silently succeed with a broken sidecar.

## Smoke tests

- [auth-smoke-testing.md](auth-smoke-testing.md) — `/api/auth/whoami`
  round-trip (verifies Firebase custom claims reach the backend)
- [agent-factory-smoke.md](agent-factory-smoke.md) — authenticated
  SSE stream against `/api/skill/{skill_id}/stream` (verifies the
  AGENT-FACTORY sprint output end-to-end)
- [platform-skills.md](platform-skills.md) — platform-owned seed skills
  (`ownerId=aitana-platform`), how the Cloud Build seed step runs, and
  how to verify/re-seed manually
- `/api/buckets` (RESOURCE-ACCESS sprint) — bucket + folder CRUD, IAM-gated
  via Firebase ID token. The smoke step exercises:
  - anon `GET /api/buckets` → 401/403 (auth gate present)
  - authed `GET /api/buckets` → 200 (router mounted, empty list OK)

## Known defect history

- **FE-BRINGUP-1** (2026-04-15) — `/api/proxy/health` 404 on Cloud Run while
  passing locally. Four compounding root causes (sidecar/ingress port
  collision, `BACKEND_URL` → self, `localhost` IPv6 vs uvicorn IPv4, no
  sidecar startup probe). Writeup:
  [incidents/fe-bringup-1-proxy-404.md](incidents/fe-bringup-1-proxy-404.md).
  The smoke step above exists specifically to make this class of bug fail
  loud on the next deploy instead of after-the-fact.
