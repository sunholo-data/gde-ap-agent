# GDE AP Agent — Track 3 Submission

**Google for Startups AI Agents Challenge — Track 3: Refactor for Google Cloud Marketplace & Gemini Enterprise**

**Devpost deadline**: 2026-06-05 17:00 PT

---

## Live Demo

**URL:** https://gde-ap-agent-blqtqfexwa-ew.a.run.app
**Video (2 min):** https://www.youtube.com/watch?v=extVYNAX70w
**Devpost:** https://devpost.team/google-cloud-for-startups/projects/18966

**Demo flow:**
1. Type (or upload) an invoice into the **AP Orchestrator** chat: e.g. `"Process this invoice: Vendor: Acme GmbH (Germany), INV-2026-042, €8,500, NET 30, GL 5200-OPEX"`
2. Watch the **4-step pipeline visualizer** animate: Intake → Extract → Validate → Post
3. Watch the three **Audit View chips** in the top nav (DocParse · Validator · Poster) light up live as each specialist runs — latency badges fill in as they complete
4. Click any chip to open the **Audit View side panel** — see that specialist&apos;s input, tool calls, citations, and structured output rendered as an A2UI surface
5. On the Validator Audit View, the embedded **`ap-vendor-kg` MCP App** visualizes the cited vendor record, the matched PO, prior invoices, and the duplicate-detection graph — AG-UI + A2UI + MCP Apps showcased together on one specialist
6. Optionally **Run Standalone** any specialist with a structured input form (no chat box — typed JSON / picker only) to audit its behaviour in isolation
7. The **Invoice Hero Card** renders in the Workbench Invoice tab — vendor + total as visual anchors, ledger-style line items, verdict band tied to validator output
8. Switch to the **MCP App Vendor tab** — the `ap-vendor-kg` knowledge graph shows the validator's grounded references with `LIVE` citation badges. Click any citation row or graph node → an `ui/update-model-context` notification fires → the host auto-sends a follow-up chat query to the agent → the orchestrator answers in the chat. Demonstrates the bidirectional MCP Apps protocol loop end-to-end.
9. Switch to the **MCP App Analytics tab** — invoice aging, top-vendors-by-value, GL-code distribution. Auto-updates from the current pipeline run's emit_* state; the stat tiles and chart cards are clickable, same `user_intent` channel as the KG.

---

## What Was Built

An **Accounts-Payable multi-agent system** that turns an incoming vendor invoice into a trustworthy posting decision with a complete audit trail — built on Google ADK, the Gemini Flash family (3.5 Flash / 3.1 Flash-Lite / 2.5 Flash), and the open-source [`ai-protocol-platform`](https://github.com/sunholo-data/ai-protocol-platform) template.

**No Pro tokens. No LLM at the workflow layer.** The pipeline order is code (ADK `SequentialAgent`), not prose — which removes prompt-injection risk on the routing path and keeps unit cost dominated by Flash-Lite specialists. The headline artifact is five declarative skill files and ~80 lines of wiring:

| Agent | Model | Role |
|---|---|---|
| `ap-orchestrator` | Gemini 3.5 Flash | Entry agent — owns the human handoff and delegates to `ap-pipeline` |
| `ap-pipeline` | *(no model — ADK `SequentialAgent`)* | Deterministic workflow — walks Extract → Validate → Post in code, not prose |
| `invoice-extractor` | Gemini 2.5 Flash | Extraction — turns a raw invoice file into clean, typed fields using `ailang-parse` for structured formats |
| `ap-validator` | Gemini 3.1 Flash-Lite | Grounded validation — checks extracted fields against the vendor master, open POs, and approval policy via Vertex AI Search |
| `ap-poster` | Gemini 3.1 Flash-Lite | Action — posts a clean invoice or escalates with a written audit trail |

---

## Visual + UX Highlights (Competition Polish Sprint)

| Feature | Implementation |
|---------|---------------|
| AP/Finance theme | Parse-blue CSS custom properties + Montserrat display / JetBrains Mono numbers; light-default with dark-mode variants |
| Pipeline step visualizer | `APPipelineSteps.tsx` — live 4-step progress bar driven by AG-UI `STAGE_PROGRESS` events. Session-cumulative (Intake / Extract / Validate / Post stay lit across Q&A turns so the user sees where they are in the pipeline). |
| Invoice Hero Card | `InvoiceHeroCard.tsx` — purpose-built financial card: status-toned accent stripe, vendor name + total as the two typographic anchors, ledger-style line items with totals footer, status-toned verdict band with routing / SLA / audit-citation chips. Fed from merged `app:emitted:invoice` + `verdict` + `posting` state, so it progressively fills in as each specialist completes. |
| AP Analytics Dashboard | MCP App artefact — aging bar with `niceTicks` integer-friendly y-axis, top-vendors horizontal bar, GL-code donut with width-aware legend. Reactivity: pulsing attribution chip showing "Updated by Orchestrator · just now", "Just added by agent" callout summarising the live invoice merge, click any stat tile or chart card to send a chat query (`ui/update-model-context` → `user_intent` → `sendMessage`). |
| Vendor Knowledge Graph MCP App | `ap-vendor-kg` artefact — vendor master record with approval status, prior-invoice nodes, PO edges, "this invoice" highlight. Validator citations with `LIVE` badges that click through to chat queries (vendor_master:V-1042 → "Tell me more about V-1042's history"). Same bidirectional channel as the Dashboard. Mounted both in the workbench Vendor tab AND inside the validator's Audit View. |
| Audit View chips + side panel | `SpecialistChip` row replaces specialist tabs; `InspectorPanel` slides in with animated entrance, renders per-specialist input/tools/output. Each panel shows the **upstream specialist's output as its own input** (Validator's input = Extractor's invoice; Poster's input = invoice + verdict) so judges read the data handoff directly off the audit panel. |
| Structured-input "Run Standalone" | Hand-rolled forms (DocparsePicker / ValidatorJsonForm / PosterVerdictForm) post to `POST /api/skill/{id}/structured`; server validates against `metadata.structuredInput` JSON Schema in each SKILL.md |
| MCP sandbox | Separate-origin Cloud Run service (`mcp-sandbox-374404277595.europe-west1.run.app`) per MCP Apps spec; auto-deploys via conditional Cloud Build step that watches `infrastructure/mcp-sandbox/**` paths |

### Protocol Chain (end-to-end)

```
User uploads an invoice (or picks one from the GCS bucket browser)
   → AG-UI SSE stream fires TOOL_CALL_START per sub-agent (pipeline visualizer advances)
   → SequentialAgent walks Extract → Validate → Post; each specialist
     emits its function-as-schema payload (app:emitted:invoice / verdict / posting)
   → Workbench Invoice tab renders InvoiceHeroCard from merged emit_* state
   → Workbench Vendor tab renders the ap-vendor-kg MCP App showing
     validator citations (vendor_master / open_pos / prior_invoices)
   → User clicks a citation row inside the iframe
   → Artefact posts ui/update-model-context with `{ user_intent: { intent, source, context } }`
   → StaticArtefactFrame forwards the structuredContent to onMcpUserIntent
   → Host auto-sends the intent string as a chat message through the normal sendMessage path
   → Orchestrator responds in the chat → bidirectional protocol loop complete
```

---

## Track 3 Framing

### 1. ADK + Declarative Intent

The entire AP system is defined in five `SKILL.md` files. Each file is a YAML frontmatter block (name, model, tools, `subSkills`) plus a markdown instruction body — no Python pipeline, no orchestration loop, no token counting. ADK handles all of that.

The orchestrator delegates to a single workflow sub-skill, which is itself a `SequentialAgent` with no model:

```yaml
# ap-orchestrator/SKILL.md
subSkills:
  - ap-pipeline

# ap-pipeline/SKILL.md
agentType: sequential   # → google.adk.agents.SequentialAgent
subSkills:
  - invoice-extractor
  - ap-validator
  - ap-poster
```

The orchestrator (Gemini 3.5 Flash) is an `LlmAgent` that owns the human handoff and `transfer_to_agent`s into `ap-pipeline`. `ap-pipeline` has **no model** — ADK's `SequentialAgent` walks its `sub_agents` in Python, in order, passing schema-enforced state forward (`ap_invoice` → `ap_verdict` → `ap_posting_record`). No LLM is asked "what comes next" at the workflow level.

→ See [`backend/skills/templates/ap-orchestrator/SKILL.md`](backend/skills/templates/ap-orchestrator/SKILL.md)

### 2. MCP Usage

**Current MCP surface** (in this submission):

- `list_documents` / `get_document_content` / `structured_extraction` — MCP-style tool wrappers in `backend/tools/` used by `invoice-extractor` and `ap-poster` to read invoice artifacts.
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
4. Watch the orchestrator delegate to `ap-pipeline`, which walks `invoice-extractor` → `ap-validator` → `ap-poster` → audit card in the workspace pane.

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
│   ├── ap-orchestrator/SKILL.md   # Entry + human handoff (Gemini 3.5 Flash)
│   ├── ap-pipeline/SKILL.md       # Deterministic workflow (ADK SequentialAgent — no model)
│   ├── invoice-extractor/SKILL.md # Extraction via ailang-parse + Gemini 2.5 Flash multimodal
│   ├── ap-validator/SKILL.md      # Grounded validation via Vertex AI Search (Gemini 3.1 Flash-Lite)
│   └── ap-poster/SKILL.md         # Post xor escalate with audit trail (Gemini 3.1 Flash-Lite)
├── adk/agent.py                   # create_agent() — resolves subSkills at runtime
├── db/local_fixture.py            # LOCAL_MODE fixture (seeds AP bundle)
└── tests/unit/
    └── test_ap_orchestrator_wiring.py  # Wiring regression test (work item 3.1)
docs/design/forks/gde-ap-agent/v0.1.0/
└── submission-readiness.md        # Full gap analysis + sprint plan
```

---

## Gemini Enterprise + A2UI Alignment

This submission lines up with every theme in Google's [practitioner's guide to Gemini Enterprise and A2UI integration](https://cloud.google.com/blog/topics/developers-practitioners/guide-to-gemini-enterprise-and-a2ui-integration). The full theme-by-theme map — protocol stack, component catalog, `X-A2A-Extensions` negotiation, MIME tagging, structured widget input, sandboxing — is documented in [`docs/design/forks/gde-ap-agent/v0.1.0/gemini-enterprise-a2ui-alignment.md`](docs/design/forks/gde-ap-agent/v0.1.0/gemini-enterprise-a2ui-alignment.md). Quick verification:

```bash
# A2A discovery card with capability negotiation
curl https://gde-ap-agent-blqtqfexwa-ew.a.run.app/.well-known/agent.json \
  -H 'X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern' -i
# → response header echoes the negotiated intersection
# → body advertises capabilities.extensions with the full supported set
```

## Built On

- **[Google ADK](https://github.com/google/adk-python)** — agent orchestration, sub-agent delegation, sessions, artifacts
- **[ai-protocol-platform](https://github.com/sunholo-data/ai-protocol-platform)** — open-source platform template (AG-UI, A2UI, MCP, A2A)
- **[ailang-parse](https://ailang.dev)** — deterministic document parsing (<1s, no LLM tokens) for structured invoice formats
- **Gemini 3.5 Flash / 3.1 Flash-Lite / 2.5 Flash** via Vertex AI — entry agent + specialist models (no Pro)
- **Vertex AI Agent Engine** (Reasoning Engine) — managed ADK session service + Memory Bank for cross-session recall via the `load_memory` tool
- **Vertex AI Search** — grounded validation against enterprise knowledge base
- **Google Cloud Run** — backend, frontend, and MCP sandbox deployment target (`europe-west1`)
- **Firebase Auth + Firestore** — auth and skill storage
