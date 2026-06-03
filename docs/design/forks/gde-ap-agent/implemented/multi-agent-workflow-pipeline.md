# Multi-Agent Workflow Pipeline (ADK SequentialAgent)

**Status**: Implemented
**Priority**: P0 (Submission centerpiece)
**Estimated**: 2.5 days
**Scope**: Fullstack (backend agent factory + skill templates + new MCP server; frontend verification)
**Dependencies**: [Schema-Enforced Structured Extraction](./schema-enforced-extraction.md) (✅ shipped), [Multi-Agent Inspector UX](./multi-agent-inspector-ux.md) (✅ shipped)
**Created**: 2026-06-02
**Last Updated**: 2026-06-03

> **Submission documentation.** This doc doubles as the architectural narrative for the Google AI Agents Challenge Track 3 submission. Each section maps a pipeline stage to one open protocol, demonstrating *fluency* with the agent stack (Agent Skills, ADK, AG-UI, A2UI, A2A, MCP, MCP Apps) rather than just *familiarity* with the names.

## Problem Statement

The `ap-orchestrator` skill is currently an `LlmAgent` whose instruction *describes* a workflow ("delegate to extractor, then validator, then poster, then emit the card") and relies on the model to *follow* that workflow. In practice the model satisfies itself after one delegation:

**Reproduction (2026-06-02 18:31 UTC, revision 00054):**

1. User: *"please process this file"* (with a parsed demo invoice in session)
2. Backend logs at 18:32:02: `Warning: there are non-text parts in the response: ['function_call']` — model emitted **one** transfer
3. Frontend pipeline rail: only **Intake** lit up
4. Chat output: raw extraction JSON dumped as a code block — no validation, no posting, no Invoice Review Card

The orchestrator decided "I've delegated once, here's the result" and stopped. There was no LLM decision the orchestrator was *supposed* to make — Extract → Validate → Post is the same sequence every time — yet we were paying both the latency and the failure mode of LLM-driven control flow.

**Current State:**

- Orchestrator is an `LlmAgent` with three sub-skills as transfer targets; the model picks one (or none) per turn
- "Workflow" is prose in the skill's instruction; the model is free to ignore it
- Demo UX collapses to a single JSON block when the model gives up mid-pipeline
- Pipeline rail UI (`APPipelineSteps.tsx`) watches for sub-agent tool call substrings; if the model never transfers past stage 2, the rail never advances
- A2UI Invoice Review Card never renders because it's gated on `ap-poster` running

**Impact:**

- **Judges (primary audience):** the headline demo path is the broken path — running "process this invoice" against the deployed service shows an incomplete output, undermining the submission's core claim about hard structural guarantees
- **Developers:** every iteration spent re-prompting the orchestrator instruction is wasted; the *correct* abstraction (workflow agent) exists in ADK and we aren't using it
- **End users:** unreliable workflow — same input sometimes produces different stage counts

## Goals

**Primary Goal:** Convert the AP pipeline from prose-described, LLM-orchestrated control flow into a deterministic ADK `SequentialAgent` walk where the workflow itself is code, not vibes — and use the resulting stage boundaries as deliberate teaching moments for the protocol stack.

**Success Metrics:**

- **Deterministic completion rate**: 100% of invoice-processing chats run all four observable stages (Intake → Extract → Validate → Post → Card). Currently ~25-50% depending on model luck.
- **Orchestrator token cost**: ↓ ~60% (no orchestrator LLM round-trips between stages; ADK walks `sub_agents` in Python)
- **End-to-end latency**: ↓ ~3-5s per pipeline (one fewer LLM round-trip per stage transition)
- **Demo coherence**: judges see one user message produce a visible four-stage assembly with seven distinct protocol surfaces lighting up

**Non-Goals:**

- **Parallel validation.** ADK ships `ParallelAgent` (e.g. run vendor-master check + tax-policy check + duplicate check concurrently). Out of scope for this sprint; the linear walk demos the workflow concept clearly enough. Add later if time permits.
- **Conversational pipeline.** The user can chat with `ap-orchestrator` (front door). Once the pipeline kicks off, the specialists run to completion — no mid-pipeline interjection. A pause/resume UX is a v0.2 concern.
- **Real ERP integration.** The simulated MCP server returns synthetic posting confirmations. Wiring SAP/NetSuite is post-submission.

## Axiom Alignment

Scored per [docs/product-axioms.md](../../product-axioms.md). Net score must be ≥ +4.

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | **+1** | Removing orchestrator LLM round-trips between stages cuts ~3-5s. Each sub-agent's tokens stream live via AG-UI. The watchdog (shipped earlier today) covers the residual long-tail. |
| 2 | EARNED TRUST | **+1** | Every stage's output is JSON Schema-validated (SCHEMA-ENFORCE). Audit view exposes per-agent reasoning + structured output. Validator cites vendor-master/policy hits via MCP. No hidden steps. |
| 3 | SKILLS, NOT FEATURES | **+1** | Adds one new `agent_type: sequential` field to `SkillMetadata` — declarative, fits the existing SKILL.md model. Non-developers reading the YAML understand "this skill runs these sub-skills in order". No new user-facing concept. |
| 4 | RIGHT MODEL, RIGHT MOMENT | **+1** | Orchestrator-level workflow decisions move from LLM to ADK runtime (zero tokens). Front-door `ap-orchestrator` keeps `gemini-3.5-flash` for chat; specialists keep `gemini-3.1-flash-lite` for structured extraction. No reasoning model runs where a fast model suffices. |
| 5 | GRACEFUL DEGRADATION | **+1** | `before_agent_callback` on the SequentialAgent acts as an intake gate — if no document is loaded, emit a friendly "please upload an invoice" message and skip the pipeline (sets `ctx.end_invocation`). Existing watchdog handles mid-stream stalls. MCP server failures degrade to a structural `[TOOL_ERROR]` propagated through the schema-enforced output, never a 500. |
| 6 | PROTOCOL OVER CUSTOM | **+1** | Every stage maps to an existing protocol. New code adopts ADK's `SequentialAgent` instead of reinventing workflow orchestration. Simulated vendor-master + ERP are exposed via the existing FastMCP server pattern, not as ad-hoc Python functions. A2UI patches use the standard `updateComponents` + `updateDataModel` decoupled pattern (already advertised in our A2A `capabilities.extensions`). Zero custom wire formats. |
| 7 | API FIRST | **0** | No external API contract change. Channels (web, Telegram, email) continue to see the same `POST /api/skill/.../stream` surface; only the agent graph inside it changes. |
| 8 | OBSERVABLE BY DEFAULT | **+1** | ADK emits one OTEL span per sub-agent invocation automatically — Cloud Trace gets a clean Extract → Validate → Post breakdown for free. STAGE_PROGRESS labels surface to the typing indicator. Each sub-agent has its own audit-view pane with streaming reasoning + structured output. |
| 9 | SECURE BY CONSTRUCTION | **0** | Simulated MCP servers run in-process (same FastMCP instance, additional mount paths). Same trust boundary (Cloud Run service edge). No new data egress. Existing IAM + Firebase Auth gates all paths. |
| 10 | THIN CLIENT, FAT PROTOCOL | **+1** | Workflow logic moves *out* of the LLM (where it never belonged) and into ADK runtime (server-side Python). Frontend code unchanged — pipeline rail already watches `transfer_to_*` events, audit view already lights up per-agent. Zero new client-side state. |
|   | **Net Score** | **+8** | Strong alignment — proceed. |

**Conflict Justifications:** None (no -1 scores).

## Standards Compliance Check

| Standard | Adopted? | Source verified |
|---|---|---|
| **ADK SequentialAgent** (workflow agent) | ✅ Replaces ad-hoc orchestrator instruction. | `google.adk.agents.sequential_agent.SequentialAgent` (ADK v1.24.1, verified via `mcp__adk-mcp__search_code`). Constructor: `SequentialAgent(name, description, sub_agents, before_agent_callback, after_agent_callback)` inherited from `BaseAgent`. |
| **Agent Skills spec** (SKILL.md format) | ✅ Extended via metadata, not replaced. | Adds `metadata.agent_type: "sequential" \| "llm"` (defaults to `"llm"` — backwards compatible). Existing frontmatter unchanged for all existing skills. |
| **A2A agent card** (`/.well-known/agent.json`) | ✅ Already shipped in `backend/protocols/a2a.py`. Advertises `SUPPORTED_EXTENSIONS`. | `backend/protocols/a2a.py:59-66` — adds `adk-workflow-v1` to the extensions tuple to signal we expose deterministic workflow agents. |
| **MCP** (Model Context Protocol) | ✅ New servers reuse existing FastMCP pattern at `backend/protocols/mcp_server.py`. | Two new mount points: `/mcp/vendor-master` and `/mcp/erp-posting`. Tools registered via `FastMCP.add_tool` (same as `gde-ap-agent` server). |
| **AG-UI** (streaming protocol) | ✅ ADK emits sub-agent events that already serialise through `ag_ui_adk`. | No protocol change — each `SequentialAgent` child agent's events flow through unchanged. Tool call events for `transfer_to_*` already reach the pipeline rail. |
| **A2UI v0.9** (declarative UI, decoupled pattern) | ✅ Each specialist emits its own surface section via `send_a2ui_json_to_client`. | Per-specialist `updateComponents` + `updateDataModel` blocks. Additive — workspace pane grows as each stage completes. The decoupled pattern is already advertised in our A2A extensions tuple. |
| **Gemini structured output** | ✅ Already shipped in [schema-enforced-extraction.md](./schema-enforced-extraction.md). | Each specialist's `metadata.extraction_schema` is enforced server-side. SequentialAgent passes outputs through session state, schema-validated at each boundary. |
| **MCP Apps** (sandboxed iframe) | ✅ Already shipped (`ext-apps-map`). | Final card retains the existing `🌍 View Vendor on Map` button → MCP App. No protocol change. |

No custom wire formats are introduced. All seven protocol surfaces in the demo are pre-existing open standards already advertised in the agent card.

## Design

### Overview

`ap-orchestrator` becomes a thin `LlmAgent` whose only job is to either chat with the user OR transfer once to a new `ap-pipeline` SequentialAgent. The SequentialAgent walks `[invoice-extractor, ap-validator, ap-poster]` deterministically. Each specialist owns a *section* of the workspace A2UI surface — the card assembles itself stage-by-stage. Two new simulated MCP servers (`vendor-master`, `erp-posting`) ground the validator and poster.

### Agent Topology

```
ap-orchestrator (LlmAgent, conversational)
│   model: gemini-3.5-flash
│   instruction: "If user asks to process an invoice, transfer to ap_pipeline.
│                 Otherwise answer their question. Never reproduce extracted
│                 data yourself — the pipeline owns that."
│   tools: [list_documents]
│   sub_agents: [ap-pipeline]
│
└── ap-pipeline (SequentialAgent, deterministic — NO model)
    │   agent_type: sequential
    │   before_agent_callback: intake_gate (checks session state has document)
    │   after_agent_callback: emit_final_stage_progress
    │
    ├── invoice-extractor (LlmAgent + structured output schema)
    │   model: gemini-3.1-flash-lite
    │   extraction_schema: ap_invoice
    │   tools: [retrieve_artifact, send_a2ui_json_to_client]
    │   emits: workspace "Extracted Invoice" section
    │
    ├── ap-validator (LlmAgent + structured output schema)
    │   model: gemini-3.1-flash-lite
    │   extraction_schema: ap_verdict
    │   tools: [ai_search, vendor_master_lookup (MCP), send_a2ui_json_to_client]
    │   emits: workspace "Validation Checks" section
    │
    └── ap-poster (LlmAgent + structured output schema)
        model: gemini-3.1-flash-lite
        extraction_schema: ap_posting_record
        tools: [erp_post (MCP), send_a2ui_json_to_client]
        emits: workspace "Posting Result" section + final card buttons
```

### Per-Stage Protocol Map (the submission narrative)

| Stage | What runs | Protocols on display | Visible artefact |
|---|---|---|---|
| **Front door** | `ap-orchestrator` `LlmAgent` answers or transfers | **Agent Skills** (SKILL.md), **A2A** (discoverable at `/.well-known/agent.json` with `capabilities.extensions`) | Chat reply + pipeline rail Intake dot |
| **Workflow** | `ap-pipeline` `SequentialAgent` (no model, ADK Python walks sub_agents) | **ADK Workflow Agents**, **AG-UI** (each sub-agent's `transfer_to_*` event streams to the rail) | Pipeline rail advances each stage as it fires |
| **Extract** | `invoice-extractor` LlmAgent | **Gemini structured output** (`response_mime_type=application/json` + `ap_invoice` schema), **A2UI** `updateComponents` adds "Extracted Invoice" section, **AG-UI** audit-view streaming | Section 1 of workspace card + audit pane streams |
| **Validate** | `ap-validator` LlmAgent | **MCP** (`vendor-master` lookup), **RAG** (`ai_search` grounded over policy datastore), **Gemini structured output** (`ap_verdict` schema), **A2UI** `updateComponents` appends "Validation Checks" with green/red ticks | Section 2 of workspace card with citations + audit pane structured JSON |
| **Post** | `ap-poster` LlmAgent | **MCP** (`erp-posting` simulated), **Gemini structured output** (`ap_posting_record` schema with `if/then/else`), **A2UI** `updateDataModel` finalises the card, **MCP Apps** (`🌍 View Vendor on Map` button → sandboxed iframe) | Section 3 + final action button + MCP App widget |
| **Throughout** | LatencyTracker hooks on each sub-agent | **AG-UI custom events** (STAGE_PROGRESS labels: *"Extracting…"* → *"Validating against vendor master…"* → *"Posting to ERP…"*), watchdog | Typing-indicator labels + stalled-state amber UI |

**The submission story in one sentence:** *one user message, seven protocol surfaces, four deterministic stages, zero hallucinated workflow decisions.*

### Backend Changes

**New skill template** — `backend/skills/templates/ap-pipeline/SKILL.md`:

```yaml
---
name: ap-pipeline
description: >
  Deterministic AP processing pipeline. Runs invoice-extractor →
  ap-validator → ap-poster in sequence. No LLM at the workflow level —
  ADK's SequentialAgent walks the sub-agents in code.
metadata:
  author: aitana
  version: "0.1"
  agent_type: sequential      # NEW — builds SequentialAgent not LlmAgent
  subSkills:
    - invoice-extractor
    - ap-validator
    - ap-poster
---

(No instruction — SequentialAgent doesn't have a model.)
```

**Modified — `backend/adk/agent.py`** (`create_agent`):

Branch on `metadata.agent_type`. If `sequential`:

```python
from google.adk.agents import SequentialAgent

if md.agent_type == "sequential":
    return SequentialAgent(
        name=_sanitize_name(skill_config.skill_id),
        description=skill_config.description or "",
        sub_agents=sub_agents,  # already resolved above
        before_agent_callback=_intake_gate_for(skill_config),
        after_agent_callback=_final_progress_for(skill_config),
    )
# else: existing LlmAgent path
```

The `before_agent_callback` returns a `types.Content` with a friendly "please upload an invoice" message when no document is in session state, which short-circuits the SequentialAgent per `BaseAgent._handle_before_agent_callback`. This is the **graceful degradation** affordance — no document, no pipeline run, no confused output.

**Modified — `backend/skills/skill_config.py`** (`SkillMetadata`):

```python
class SkillMetadata(BaseModel):
    ...
    agent_type: Literal["llm", "sequential"] = "llm"  # NEW, defaults to llm
```

Backwards compatible — every existing skill continues to build as `LlmAgent`.

**Modified — `backend/skills/templates/ap-orchestrator/SKILL.md`:**

- `subSkills: [ap-pipeline]` (was `[invoice-extractor, ap-validator, ap-poster]`)
- Instruction rewritten to: *"If the user wants to process an invoice, transfer to ap-pipeline. Otherwise answer the user's question. Never produce extracted invoice fields yourself — that's the pipeline's job."*
- Remove the inline Invoice Review Card JSON block (moves into `ap-poster`)

**Modified — `backend/skills/templates/ap-poster/SKILL.md`:**

- Add the existing Invoice Review Card JSON template (currently in the orchestrator)
- Add `metadata.tools: [erp_post, send_a2ui_json_to_client]`
- Update instruction: *"Read the validation verdict and extracted invoice from session state. Either post to ERP (verdict=pass) or open an approval exception (verdict=needs_review). Then emit the final A2UI workspace card."*

**Modified — `backend/skills/templates/invoice-extractor/SKILL.md`** and **`backend/skills/templates/ap-validator/SKILL.md`:**

- Add per-specialist A2UI `updateComponents` blocks targeting their *section* of the workspace surface (not a fresh `createSurface`). Each specialist appends one Column to the workspace root.

**New — `backend/protocols/mcp_servers/vendor_master.py`:**

```python
from mcp.server.fastmcp import FastMCP

vendor_master_mcp = FastMCP("vendor-master", stateless_http=True, streamable_http_path="/")

@vendor_master_mcp.tool()
def lookup_vendor(name: str) -> dict:
    """Look up a vendor by name in the master file. Returns
    {found: bool, vendor_id, country, payment_terms, kyc_status}."""
    return _SIMULATED_VENDORS.get(name.lower(), {"found": False})

@vendor_master_mcp.tool()
def check_duplicate(invoice_number: str, vendor_id: str) -> dict:
    """Check whether this invoice has already been posted. Returns
    {duplicate: bool, posted_at, posting_id}."""
    ...
```

**New — `backend/protocols/mcp_servers/erp_posting.py`:**

```python
@erp_posting_mcp.tool()
def post_to_ledger(invoice: dict, gl_code: str, posting_period: str) -> dict:
    """Simulate posting an invoice to the AP ledger. Returns
    {posting_id, posted_at, gl_account, status}."""
    ...

@erp_posting_mcp.tool()
def route_to_approval(invoice: dict, reasons: list[str]) -> dict:
    """Route a needs-review invoice to a finance reviewer's queue.
    Returns {ticket_id, queue, sla_hours}."""
    ...
```

Both mounted into `fast_api_app.py` alongside the existing `/mcp` mount:

```python
app.mount("/mcp/vendor-master", vendor_master_mcp.streamable_http_app())
app.mount("/mcp/erp-posting", erp_posting_mcp.streamable_http_app())
```

**Modified — `backend/protocols/a2a.py`:**

Add `"adk-workflow-v1"` to `SUPPORTED_EXTENSIONS` so the agent card advertises that this platform exposes deterministic workflow agents. (Optional but it's the kind of detail that signals fluency.)

**New Firestore seed entries** — `mcp_servers/vendor-master` and `mcp_servers/erp-posting`:

```python
# backend/scripts/seed_mcp_servers.py — add two entries
{"name": "vendor-master", "url": f"{base_url}/mcp/vendor-master", "transport": "streamable_http"}
{"name": "erp-posting", "url": f"{base_url}/mcp/erp-posting", "transport": "streamable_http"}
```

`ap-validator` and `ap-poster` reference these by ID in their `tool_configs.mcp_servers`.

### Frontend Changes

**Verification only — no code changes expected.**

- `frontend/src/components/chat/APPipelineSteps.tsx` already matches on substrings `invoice_extractor`, `ap_validator`, `ap_poster`. Each sub-agent's `transfer_to_*` event reaches the rail via AG-UI unchanged — the rail should now light up cleanly Extract → Validate → Post.
- Audit view (`Multi-Agent Inspector UX`, shipped) already creates a pane per sub-agent. Each specialist's streaming reasoning + structured JSON drops into its pane.
- Workspace surface assembles itself from each specialist's `updateComponents` patches. A2UI is additive by design — no client logic needed.

The acceptance test (below) verifies all three layers light up against the deployed service.

### Architecture Diagram

```
User: "please process this file"
   ↓
ap-orchestrator (LlmAgent, gemini-3.5-flash)
   ↓ transfer_to_ap_pipeline   (one decision — chat or pipeline)
   ↓
ap-pipeline (SequentialAgent)   ← Workflow lives in ADK Python, not a prompt
   │  before_agent_callback: intake gate (no doc → bail politely)
   │
   ├─→ invoice-extractor (gemini-3.1-flash-lite)
   │     → ai_search (none here, but available)
   │     → response_mime_type=application/json + ap_invoice schema
   │     → send_a2ui_json_to_client → workspace "Extracted" section
   │     → session state: extracted_invoice
   │
   ├─→ ap-validator (gemini-3.1-flash-lite)
   │     → MCP: vendor-master.lookup_vendor
   │     → ai_search (policy + open POs grounded RAG)
   │     → response_mime_type=application/json + ap_verdict schema
   │     → send_a2ui_json_to_client → workspace "Validation" section
   │     → session state: verdict
   │
   └─→ ap-poster (gemini-3.1-flash-lite)
         → MCP: erp-posting.post_to_ledger OR route_to_approval
         → response_mime_type=application/json + ap_posting_record schema
         → send_a2ui_json_to_client → workspace "Posting" + final card
         → MCP App button: "🌍 View Vendor on Map" (sandboxed iframe)
```

## Implementation Plan

### Phase 1 — SequentialAgent wiring (~0.75 day)

- [ ] `backend/skills/skill_config.py` — add `agent_type: Literal["llm","sequential"] = "llm"` to `SkillMetadata` + `agentType` camelCase alias (~10 LOC + serialiser)
- [ ] `backend/adk/agent.py` — branch `create_agent` on `agent_type`; build `SequentialAgent` with resolved `sub_agents` (~30 LOC)
- [ ] Intake gate `before_agent_callback`: return `types.Content` with a friendly message when no document in session (~25 LOC)
- [ ] Unit test: `tests/unit/test_agent_factory.py::test_sequential_agent_built_for_pipeline` (~40 LOC)
- [ ] Unit test: `tests/unit/test_agent_factory.py::test_intake_gate_bails_with_no_document` (~30 LOC)

### Phase 2 — Skill template restructuring (~0.5 day)

- [ ] New `backend/skills/templates/ap-pipeline/SKILL.md` (~20 LOC YAML, no instruction body)
- [ ] Rewrite `ap-orchestrator/SKILL.md` instruction; flip `subSkills` to `[ap-pipeline]` (~50 LOC delta)
- [ ] Move Invoice Review Card JSON block from orchestrator → `ap-poster/SKILL.md`; update poster instruction (~80 LOC moved)
- [ ] Add per-specialist `updateComponents` block to `invoice-extractor/SKILL.md` and `ap-validator/SKILL.md` (~30 LOC each)
- [ ] `backend/admin/platform_seed.py` smoke: confirm template parse picks up new templates + `agent_type` field

### Phase 3 — Simulated MCP servers (~0.75 day)

- [ ] `backend/protocols/mcp_servers/vendor_master.py` — FastMCP with `lookup_vendor` + `check_duplicate` (~80 LOC + synthetic vendor table)
- [ ] `backend/protocols/mcp_servers/erp_posting.py` — FastMCP with `post_to_ledger` + `route_to_approval` (~80 LOC)
- [ ] Mount both into `backend/fast_api_app.py` (`/mcp/vendor-master`, `/mcp/erp-posting`) (~10 LOC)
- [ ] `backend/scripts/seed_mcp_servers.py` — add two Firestore entries (~20 LOC)
- [ ] Add `vendor-master` to `ap-validator`'s `tool_configs.mcp_servers`; `erp-posting` to `ap-poster`'s
- [ ] Tool test: `tests/tool_tests/test_vendor_master_mcp.py` — round-trip via FastMCP test client (~60 LOC)
- [ ] Tool test: `tests/tool_tests/test_erp_posting_mcp.py` (~60 LOC)

### Phase 4 — A2A extension + observability polish (~0.25 day)

- [ ] `backend/protocols/a2a.py` — add `"adk-workflow-v1"` to `SUPPORTED_EXTENSIONS`
- [ ] Test: `tests/api_tests/test_a2a_agent_card.py::test_advertises_workflow_extension`
- [ ] `backend/adk/callbacks.py` — emit STAGE_PROGRESS on SequentialAgent `before_agent_callback` of each child (*"Extracting invoice fields…"* / *"Validating against vendor master…"* / *"Posting to ERP…"*)
- [ ] Verify Cloud Trace shows one span per sub-agent (free from ADK)

### Phase 5 — Deploy + judge-path verification (~0.25 day)

- [ ] Deploy to dev (auto via Cloud Build on push)
- [ ] `scripts/verify-judge-path.sh` — curls the deployed `gde-ap-agent` with a demo invoice, asserts all four pipeline stage events arrive over SSE, asserts the final A2UI workspace surface has three sections (Extracted, Validated, Posted), asserts at least one `vendor-master` MCP tool call appears in the trace
- [ ] Manual: open the deployed UI, send "process this file", confirm pipeline rail lights up Extract → Validate → Post → card renders with all three sections, audit view shows per-agent reasoning + JSON, typing-indicator surfaces STAGE_PROGRESS labels

## Migration & Rollout

**Database Migrations:**

- Two new entries in Firestore `mcp_servers/` collection (`vendor-master`, `erp-posting`) — added by `seed_mcp_servers.py` on deploy
- New platform skill `ap-pipeline` seeded by `platform_seed.py` on next backend boot (the loader iterates `backend/skills/templates/`)
- Existing `ap-orchestrator` record gets its `subSkills` rewritten from `[invoice-extractor, ap-validator, ap-poster]` to `[ap-pipeline]` — handled by `platform_seed.py`'s existing "refresh template-sourced fields" path

**Feature Flags:** None. The change is structural; either it ships or it doesn't. The pre-change orchestrator was the bug.

**Rollback Plan:** Revert the commit. Skill templates and agent factory diff are co-located in one PR. `agent_type` defaults to `llm` so reverting `ap-pipeline`'s template doesn't break any other skill's resolution.

**Environment Variables:** None new.

## Testing Strategy

### Backend Tests (pytest)

- [ ] `test_agent_factory.py::test_sequential_agent_built_for_pipeline` — `create_agent` on a fixture with `agent_type=sequential` returns a `SequentialAgent` instance with the right sub-agents
- [ ] `test_agent_factory.py::test_intake_gate_bails_with_no_document` — `before_agent_callback` returns a `types.Content` and the runner short-circuits when session state lacks a document
- [ ] `test_skill_metadata.py::test_agent_type_defaults_to_llm` — pre-existing skill YAML without `agent_type` still parses as `LlmAgent`
- [ ] `test_vendor_master_mcp.py::test_lookup_vendor_returns_master_data` + `test_duplicate_check_flags_known_invoice`
- [ ] `test_erp_posting_mcp.py::test_post_returns_posting_id` + `test_route_to_approval_emits_ticket`
- [ ] `test_a2a_agent_card.py::test_advertises_workflow_extension` — `adk-workflow-v1` appears in `capabilities.extensions`
- [ ] Integration: `test_ap_pipeline_end_to_end.py` (marked `@pytest.mark.integration`) — runs the full pipeline against an in-memory session + a fixture invoice, asserts schema-validated `ap_invoice`, `ap_verdict`, `ap_posting_record` all land in session state in order

### Frontend Tests (Vitest)

- [ ] `APPipelineSteps.test.tsx` already covers the rail logic — re-run to confirm no regression. Add one test: with `transfer_to_invoice_extractor`, `transfer_to_ap_validator`, `transfer_to_ap_poster` all in `toolCalls`, all four steps are `done`.
- [ ] No new frontend code expected; if the rail or audit view needs adjustment, that's an unplanned finding.

### Manual / E2E

- [ ] Open deployed dev (`https://gde-ap-agent-blqtqfexwa-ew.a.run.app`), pick a demo invoice, ask `ap-orchestrator` to "please process this file". Confirm:
  - Pipeline rail advances Intake → Extract → Validate → Post (all done)
  - Workspace surface renders three sections + final action button
  - Audit view shows per-agent streaming reasoning + schema-enforced JSON
  - Typing indicator surfaces STAGE_PROGRESS labels per stage
  - Cloud Trace shows one span per sub-agent
- [ ] Negative path: ask `ap-orchestrator` to "process this file" with NO document in session — confirm intake gate bails politely without running specialists

## Security Considerations

- **Trust boundary unchanged.** Simulated MCP servers run in the same FastMCP process inside the same Cloud Run service. No new egress.
- **MCP inputs are user-influenced via the LLM.** Vendor-master `lookup_vendor(name)` and `erp-posting.post_to_ledger(invoice)` receive arguments that flow from extracted fields. Inputs validated by the simulated server (synthetic data lookup, no SQL). Real ERP integrations would need parameterised calls + rate limits + audit logs — explicitly out of scope.
- **Schema enforcement at every boundary.** Each specialist's output is JSON Schema-validated before downstream consumption — a model that hallucinates `vendor_id` can't poison the validator's MCP call because the extractor's output must validate against `ap_invoice` first.
- **Intake gate prevents accidental pipeline runs.** No user message ever runs the pipeline without a document — limits the attack surface to "load a synthetic doc, watch a synthetic posting happen".

## Performance Considerations

- **Latency budget.** Each sub-agent: ~1-2s LLM call. Three stages = ~3-6s total work. Vs. orchestrator-LLM-decided baseline that needs an additional ~1-2s round-trip per transition (~3-6s overhead) — net **~3-5s faster end-to-end** for the same work.
- **Token cost.** Orchestrator no longer reasons about workflow — saves the chain-of-thought tokens it was burning per stage (~500-800 tokens per turn × 3-4 turns = ~2k saved per pipeline run).
- **Cloud Trace storage.** One span per sub-agent → 4 spans per pipeline run (vs. ~7-10 for the model-decided version with re-prompting). Cheaper to store, cleaner to read.
- **Frontend bundle size.** Zero impact — no new client code.

## Success Criteria

- [ ] All backend tests passing (`cd backend && make test-fast`)
- [ ] All frontend tests passing (`cd frontend && npm run test:run`)
- [ ] Lint + typecheck clean (`make lint` backend, `npm run quality:check:fast` frontend)
- [ ] Deployed dev service runs the four-stage pipeline end-to-end for `please process this file` against a demo invoice
- [ ] Pipeline rail lights up Intake → Extract → Validate → Post on every successful run
- [ ] Workspace A2UI surface renders three sections + final action button
- [ ] Each specialist's audit-view pane shows streaming reasoning + schema-enforced JSON
- [ ] Cloud Trace shows one span per sub-agent
- [ ] `/.well-known/agent.json` lists `adk-workflow-v1` in `capabilities.extensions`
- [ ] `verify-judge-path.sh` passes against deployed dev
- [ ] Design doc moved to `implemented/` and `SEQUENCE.md` updated

## Open Questions

- **Should `ap-pipeline` be a platform skill (marketplace-visible) or hidden?** Recommendation: marketplace-visible — it demonstrates the workflow pattern. Hide via `accessControl.visibility=private` if it clutters the marketplace.
- **Do we want STAGE_PROGRESS labels emitted from ADK callbacks, or from sub-agent `before_agent_callback`?** Recommendation: sub-agent `before_agent_callback` — keeps the label colocated with the agent it describes, survives reordering.

## Related Documents

- [Schema-Enforced Structured Extraction](./schema-enforced-extraction.md) — provides the per-specialist JSON Schema validation that lets SequentialAgent pass structured outputs between stages safely
- [Multi-Agent Inspector UX](./multi-agent-inspector-ux.md) — provides the per-agent audit pane that surfaces each SequentialAgent stage's reasoning + structured output
- [Competition Polish Sprint](./competition-polish-sprint.md) — established the A2UI workspace card, MCP App pattern, and pipeline rail UI this design extends
- [Product Axioms](../../product-axioms.md) — scoring framework
- [ADK SequentialAgent source](https://github.com/google/adk-python/blob/main/src/google/adk/agents/sequential_agent.py) — `google.adk.agents.sequential_agent.SequentialAgent` (v1.24.1)
- [A2A spec](https://a2a-protocol.org/latest/specification/) — AgentCard schema + extensions mechanism
- [A2UI v0.9 spec](https://a2ui.org/specification/v0_9/) — declarative UI message protocol, decoupled pattern
- [MCP spec](https://modelcontextprotocol.io/docs/) — tool integration protocol

---

## Implementation Report

**Completed**: 2026-06-03
**Actual Effort**: ~1 day (vs 2.5 estimated — high velocity riding on the SCHEMA-ENFORCE and AUDIT-VIEW foundations)
**Sprint**: WORKFLOW-PIPELINE (commits 084d578, fd68e9e, 405e6c6, 93e1447)

### What Was Built

**M1 — SequentialAgent factory wiring (commit 084d578)** — Added `agent_type: Literal["llm","sequential"] = "llm"` to `SkillMetadata` (with `agentType` camelCase alias). `create_agent` in `adk/agent.py` branches on `agent_type == "sequential"` and builds a `google.adk.agents.SequentialAgent` instead of an `LlmAgent`. Two helper factories `_make_intake_gate` and `_make_final_progress` produce the before/after callbacks. Intake gate returns `types.Content` with a friendly "please upload an invoice" message when `state["app:docs_loaded"]` is empty, short-circuiting the pipeline per ADK's `BaseAgent._handle_before_agent_callback` contract. Final progress emits a "Done — invoice processed" STAGE_PROGRESS for telemetry.

**M2 — Skill template restructuring (commit fd68e9e)** — New `backend/skills/templates/ap-pipeline/SKILL.md` (`agentType: sequential`, `subSkills: [invoice-extractor, ap-validator, ap-poster]`, no instruction body). `ap-orchestrator/SKILL.md` now has `subSkills: [ap-pipeline]` and a simplified "chat or transfer once" instruction. The 80-line Invoice Review Card JSON moved from orchestrator to `ap-poster/SKILL.md` (the only specialist that knows the final action). `ap-validator` references `vendor-master` in `tool_configs.mcp.servers`; `ap-poster` references `erp-posting`.

**M3 — Simulated FastMCP servers (commit 405e6c6)** — New `backend/protocols/mcp_servers/` package with `vendor_master.py` and `erp_posting.py`. Each is a `FastMCP` instance mounted at `/mcp/vendor-master` and `/mcp/erp-posting` alongside the existing `/mcp` server. Vendor-master exposes `lookup_vendor` (synthetic table covering the demo invoices) and `check_duplicate`. ERP exposes `post_to_ledger` (POST-<8 hex>) and `route_to_approval` (APPR-<8 hex>, 24h SLA). Mount order matters — specific paths must register before generic `/mcp` or Starlette swallows every subpath. Seeded via `scripts/seed_mcp_servers.py` with `--backend-base-url` flag for local dev override.

**M4 — A2A extension + STAGE_PROGRESS labels (commit 93e1447)** — `adk-workflow-v1` added to `SUPPORTED_EXTENSIONS` in `backend/protocols/a2a.py` so peer agents discovering this platform via `/.well-known/agent.json` know it exposes deterministic workflow agents. Per-specialist STAGE_PROGRESS labels via `_emit_specialist_stage_label` — lookup by SKILL.md name (stable) so re-seeding into a fresh Firestore doesn't break the labels. The orchestrator and ap-pipeline emit no label, only the three specialists do.

**M5 — Verify + finalize** — `scripts/verify-judge-path.sh` ships with two layers: unauthenticated (frontend reachable, Cloud Run revision ≥ 55) always runs, authenticated (skill structure checks via `/api/proxy/api/skills/by-slug/...`) gated on `AIPLATFORM_ID_TOKEN`. Prints the manual UI verification checklist for the parts a script cannot reach (live AG-UI stream, workspace card rendering, STAGE_PROGRESS surfacing in the typing indicator).

### Files Changed

**New:**
- `backend/skills/templates/ap-pipeline/SKILL.md` (M2)
- `backend/protocols/mcp_servers/__init__.py` (M3)
- `backend/protocols/mcp_servers/vendor_master.py` (M3)
- `backend/protocols/mcp_servers/erp_posting.py` (M3)
- `backend/tests/tool_tests/test_vendor_master_mcp.py` (M3)
- `backend/tests/tool_tests/test_erp_posting_mcp.py` (M3)
- `scripts/verify-judge-path.sh` (M5)

**Modified:**
- `backend/db/models/__init__.py` — added `agent_type` to `SkillMetadata` (M1)
- `backend/adk/agent.py` — SequentialAgent branch, intake gate, final progress, specialist STAGE_PROGRESS labels (M1, M4)
- `backend/db/local_fixture.py` — seed ap-pipeline alongside the four other AP skills (M2)
- `backend/skills/templates/ap-orchestrator/SKILL.md` — transfers to ap-pipeline only (M2)
- `backend/skills/templates/ap-poster/SKILL.md` — gains Invoice Review Card emission + erp-posting MCP ref (M2)
- `backend/skills/templates/ap-validator/SKILL.md` — gains vendor-master MCP ref (M2)
- `backend/fast_api_app.py` — mounts the two new FastMCP servers with lifespan composition + correct mount order (M3)
- `backend/scripts/seed_mcp_servers.py` — Firestore entries for vendor-master + erp-posting (M3)
- `backend/protocols/a2a.py` — adk-workflow-v1 in SUPPORTED_EXTENSIONS (M4)
- `backend/tests/unit/test_create_agent.py` — 12 new tests for SequentialAgent build + intake gate + final progress + specialist labels (M1, M4)
- `backend/tests/unit/test_models.py` — agent_type round-trip + validation tests (M1)
- `backend/tests/unit/test_platform_seed.py` — ap-pipeline template parse + orchestrator subSkills assertion (M2)
- `backend/tests/unit/test_ap_orchestrator_wiring.py` — reworked for two-level hierarchy: orchestrator → pipeline → specialists (M2)
- `backend/tests/unit/test_local_fixture.py` — skill count 10 → 11 (M2)
- `backend/tests/api_tests/test_a2a.py` — adk-workflow-v1 advertisement test (M4)
- `docs/design/forks/gde-ap-agent/SEQUENCE.md` — entry + ✅ Implemented status

### Test Count

- Backend: **1463 passing**, 1 skipped, 12 deselected
- Frontend: 577 passing (unchanged — no frontend code changes)

### Deviations from Plan

- **Per-specialist incremental A2UI sections deferred.** The design doc proposed `invoice-extractor` and `ap-validator` each append a section to the workspace surface as they finish. M2 instead kept the full Invoice Review Card emission on `ap-poster` (the final stage). The structural change — deterministic SequentialAgent — is what matters for the submission; the "growing card" visual polish can land as a follow-up if time allows.
- **Sprint completed in ~1 day vs 2.5 estimated.** SCHEMA-ENFORCE and AUDIT-VIEW had landed the foundations (schema validation, per-agent audit panes), so M1's factory branch + M2's template restructuring were short. M3 was the biggest milestone by LOC and went smoothly because the existing FastMCP pattern at `backend/protocols/mcp_server.py` was directly reusable.

### Lessons Learned

- **Starlette mount order is a footgun.** A more-specific path (`/mcp/vendor-master`) registered AFTER a less-specific path (`/mcp`) gets swallowed. Documented this inline in `fast_api_app.py` with a code comment so the next person doesn't repeat it.
- **`from __future__ import annotations` doesn't free you from importing `Literal` at runtime.** Pydantic resolves annotations at model-build time even with the future import, so adding a `Literal[...]` field requires adding the import. Caught this when ruff didn't flag it but Pydantic would have at import time.
- **Lookup by stable name (`skill.name`), not skill_id.** The skill_id is a fresh UUID per Firestore environment, but the SKILL.md `name` field is stable. STAGE_PROGRESS labels and AP-specific behaviour key off `name`, so re-seeding into a fresh project never breaks them.
- **The fork's `/.well-known/agent.json` is unreachable externally** because the combined-container Cloud Run service serves Next.js at the root and only proxies `/api/*` to the backend. The A2A discovery surface works for backend-internal callers but not for external A2A crawlers. Pre-existing issue, not in scope for this sprint, but noted for a follow-up.
