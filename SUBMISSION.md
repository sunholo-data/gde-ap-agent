# GDE AP Agent — Track 3 Submission

**Google for Startups AI Agents Challenge — Track 3: Refactor for Google Cloud Marketplace & Gemini Enterprise**

**Devpost deadline**: 2026-06-05 17:00 PT

---

## Live Demo

**URL:** https://gde-ap-agent-blqtqfexwa-ew.a.run.app

**Demo flow:**
1. Select the **AP Orchestrator** skill from the left bar
2. Type (or upload) an invoice: e.g. `"Process this invoice: Vendor: Acme GmbH (Germany), INV-2026-042, €8,500, NET 30, GL 5200-OPEX"`
3. Watch the **4-step pipeline visualizer** animate: Intake → Extract → Validate → Post
4. The **Invoice Review Card** renders in the workspace pane with all fields, verdict, and action
5. Click **🌍 View Vendor on Map** — a rotating 3D canvas globe shows London HQ → vendor location arc
6. Click **📊 AP Analytics** — an inline dashboard shows invoice aging, vendor bar, GL donut

---

## What Was Built

An **Accounts-Payable multi-agent system** that turns an incoming vendor invoice into a trustworthy posting decision with a complete audit trail — built on Google ADK, Gemini 2.5 Pro/Flash, and the open-source [`ai-protocol-platform`](https://github.com/sunholo-data/ai-protocol-platform) template.

The headline artifact is four declarative skill files and ~80 lines of wiring:

| Agent | Model | Role |
|---|---|---|
| `ap-orchestrator` | Gemini 2.5 Pro | Workflow owner — coordinates the three specialists and owns the human handoff |
| `docparse` | Gemini 2.5 Flash | Extraction — turns a raw invoice file into clean, typed fields using `ailang-parse` for structured formats |
| `ap-validator` | Gemini 2.5 Flash | Grounded validation — checks extracted fields against the vendor master, open POs, and approval policy via Vertex AI Search |
| `ap-poster` | Gemini 2.5 Flash | Action — posts a clean invoice or escalates with a written audit trail |

---

## Visual + UX Highlights (Competition Polish Sprint)

| Feature | Implementation |
|---------|---------------|
| AP/Finance theme | Navy+gold CSS custom properties (`--primary: hsl(43 96% 46%)`) |
| Pipeline step visualizer | `APPipelineSteps.tsx` — live 4-step progress bar driven by AG-UI `TOOL_CALL_START/END` events |
| Invoice review card | A2UI v0.9 `updateComponents` tree pushed from `ap-orchestrator/SKILL.md`; renders in workspace pane |
| Vendor geography globe | MCP App artefact — 100% canvas, 50-country lat/lng table, animated arc from London HQ |
| AP analytics dashboard | MCP App artefact — aging bar, vendor bar, GL donut; canvas-only, no CDN |
| MCP sandbox | Separate-origin Cloud Run service (`mcp-sandbox-374404277595.europe-west1.run.app`) per MCP Apps spec |

### Protocol Chain (end-to-end)

```
User types invoice text
   → AG-UI SSE stream fires TOOL_CALL_START per sub-agent (pipeline visualizer advances)
   → ap-orchestrator finishes → calls send_a2ui_json_to_client
   → A2UI createSurface + updateComponents renders Invoice Review Card in workspace
   → User clicks "🌍 View Vendor on Map" Button
   → A2UI action "show_vendor_globe" fires → setGlobeContext state
   → StaticArtefactFrame fetches /artefacts/vendor-globe/index.html from sandbox origin
   → postMessage ui/initialize handshake → ui/update-data push → globe animates to vendor country
```

---

## Track 3 Framing

### 1. ADK + Declarative Intent

The entire AP system is defined in four `SKILL.md` files. Each file is a YAML frontmatter block (name, model, tools, `subSkills`) plus a markdown instruction body — no Python pipeline, no orchestration loop, no token counting. ADK handles all of that.

The orchestrator's `subSkills` declaration:

```yaml
subSkills:
  - docparse
  - ap-validator
  - ap-poster
```

ADK resolves these to `LlmAgent` sub-agents at runtime via the factory in `backend/adk/agent.py`. The orchestrator delegates via ADK's native `transfer_to_agent` mechanism — no hand-rolled routing.

→ See [`backend/skills/templates/ap-orchestrator/SKILL.md`](backend/skills/templates/ap-orchestrator/SKILL.md)

### 2. MCP Usage

**Current MCP surface** (in this submission):

- `list_documents` / `get_document_content` / `structured_extraction` — MCP-style tool wrappers in `backend/tools/` used by `docparse` and `ap-poster` to read invoice artifacts.
- The platform exposes its own MCP server at `/.well-known/agent.json` for A2A discovery, meaning the AP orchestrator is discoverable by other agents.

**Planned MCP surface** (Phase 2, documented):

- `ap-poster/SKILL.md` contains a commented-out `mcp_servers: [ext-ap-erp]` block. Wiring the ERP MCP connector seeds a Firestore `mcp_servers/ext-ap-erp` document and the platform's tool registry activates it. This gives the poster real ERP write-back via MCP without code changes.

### 3. Marketplace + Gemini Enterprise Readiness

**A2A discovery** — The platform already exposes `/.well-known/agent.json`. The AP orchestrator is registerable as a Gemini Enterprise agent via `agents-cli register-gemini-enterprise` (see the `agents-cli-publish` skill).

**Gemini Enterprise registration path**:

```bash
# Dry-run — generates the registration manifest without writing to prod
agents-cli register-gemini-enterprise \
  --skill ap-orchestrator \
  --agent-name "AP Invoice Processor" \
  --dry-run
```

**Marketplace packaging path**:

1. Fork `sunholo-data/ai-protocol-platform` (this repo is already a fork).
2. Run `scripts/bootstrap-gcp-project.sh <project-id> <runtime-sa-email>` to provision Cloud Build infrastructure.
3. Set the Cloud Build substitutions in your trigger (see [Cloud Run deploy](#how-a-buyer-deploys-this)).
4. Push to `main` — the build pipeline deploys backend + frontend to Cloud Run.
5. Seed the Vertex AI Search datastore for grounded validation (see [AP Datastore](#ap-datastore-configuration)).
6. Register with Gemini Enterprise (step above).

---

## How to Run This in 5 Minutes (LOCAL_MODE)

**Prerequisites**: `git`, `uv` (Python), `node` 18+, Google ADC or `GEMINI_API_KEY`.

```bash
git clone https://github.com/sunholo-data/gde-ap-agent
cd gde-ap-agent

# Set your model auth in backend/.env — either:
#   GEMINI_API_KEY=<key from https://aistudio.google.com/apikey>
# or Vertex AI via ADC (gcloud auth application-default login)
echo "VERTEX_PROJECT=<your-project>" >> backend/.env

# Install and start both backend + frontend
cd backend && make install && cd ..
cd frontend && npm install && cd ..
./scripts/dev-local.sh
```

- Backend API: `http://localhost:1956`
- Frontend: `http://localhost:3456` (yellow LOCAL_MODE banner)

Once running:

1. Sign in via the workshop stub identity (LOCAL_MODE — no real auth needed).
2. Pick **ap-orchestrator** from the skills bar.
3. Upload or reference an invoice document.
4. Watch the orchestrator delegate: `docparse` → `ap-validator` → `ap-poster` → audit card in the workspace pane.

In LOCAL_MODE, `vertex_search` is stubbed — the validator runs grounding checks but returns a deterministic fixture response (see [Gap 4 in the submission-readiness doc](docs/design/forks/gde-ap-agent/v0.1.0/submission-readiness.md)). For production grounding, set `AP_DATASTORE_ID` (see below).

---

## How a Buyer Deploys This

### Cloud Run (backend + frontend)

```bash
# 1. Fork this repo to your GitHub org
# 2. Bootstrap GCP infrastructure
./scripts/bootstrap-gcp-project.sh <your-project-id> <sa-email>

# 3. Create a Cloud Build trigger pointing at your fork.
#    Set these substitutions:
#      _PROJECT_ID              = <your-project-id>
#      _REGION                  = europe-west1
#      _SERVICE_NAME            = gde-ap-agent-frontend
#      _ARTIFACT_REGISTRY_REPO_URL_CLIENT = <your-ar-url>
#      _PLATFORM_OWNER_EMAIL    = <admin-email>
#      _ENABLE_ANTHROPIC        = true   (optional: Claude model support)

# 4. Push to main → Cloud Build deploys backend + frontend
git push origin main
```

### AP Datastore Configuration

The `ap-validator` skill uses Vertex AI Search for grounded validation. Set `AP_DATASTORE_ID` to the full resource path:

```bash
# Create the datastore
gcloud alpha discovery-engine data-stores create \
  --project=<your-project> \
  --location=global \
  --collection=default_collection \
  --data-store-id=ds-ap-vendors \
  --display-name="AP Vendor Master" \
  --industry-vertical=GENERIC \
  --solution-types=SOLUTION_TYPE_SEARCH

# Index your vendor master, open POs, and approval policy documents

# Set the env var (or Secret Manager secret) for the backend
export AP_DATASTORE_ID=projects/<your-project>/locations/global/collections/default_collection/dataStores/ds-ap-vendors
```

Update `ap-validator/SKILL.md` to use the full resource path once provisioned:

```yaml
toolConfigs:
  ai_search:
    datastore_id: projects/<your-project>/locations/global/collections/default_collection/dataStores/ds-ap-vendors
```

---

## Repo Structure (AP-relevant)

```
backend/
├── skills/templates/
│   ├── ap-orchestrator/SKILL.md   # Workflow + human handoff (Gemini 2.5 Pro)
│   ├── docparse/SKILL.md          # Extraction via ailang-parse + Gemini multimodal
│   ├── ap-validator/SKILL.md      # Grounded validation via Vertex AI Search
│   └── ap-poster/SKILL.md         # Post xor escalate with audit trail
├── adk/agent.py                   # create_agent() — resolves subSkills at runtime
├── db/local_fixture.py            # LOCAL_MODE fixture (seeds AP bundle)
└── tests/unit/
    └── test_ap_orchestrator_wiring.py  # Wiring regression test (work item 3.1)
docs/design/forks/gde-ap-agent/v0.1.0/
└── submission-readiness.md        # Full gap analysis + sprint plan
```

---

## Built On

- **[Google ADK](https://github.com/google/adk-python)** — agent orchestration, sub-agent delegation, sessions, artifacts
- **[ai-protocol-platform](https://github.com/sunholo-data/ai-protocol-platform)** — open-source platform template (AG-UI, A2UI, MCP, A2A)
- **[ailang-parse](https://ailang.dev)** — deterministic document parsing (<1s, no LLM tokens) for structured invoice formats
- **Gemini 2.5 Pro/Flash** via Vertex AI — orchestrator + specialist models
- **Vertex AI Search** — grounded validation against enterprise knowledge base
- **Google Cloud Run** — deployment target
- **Firebase Auth + Firestore** — auth and skill storage
