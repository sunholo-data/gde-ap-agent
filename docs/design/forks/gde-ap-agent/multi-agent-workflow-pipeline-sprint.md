# Multi-Agent Workflow Pipeline — Sprint Plan

**Sprint ID**: WORKFLOW-PIPELINE
**Design Doc**: [multi-agent-workflow-pipeline.md](./multi-agent-workflow-pipeline.md)
**Status**: Ready to Execute
**Created**: 2026-06-03
**Deadline**: 2026-06-05 17:00 PT (competition submission)
**Estimated**: 2.5 days
**Time Available**: ~2 days (tight)

## Sprint Summary

Refactor the AP demo from an LlmAgent-orchestrated pipeline (where the
model decides whether to continue past each stage) to a deterministic
ADK `SequentialAgent` walk where the workflow is *code, not prose*.
`ap-orchestrator` becomes a thin conversational LlmAgent that transfers
once to a new `ap-pipeline` SequentialAgent. The Sequential walks
`[invoice-extractor, ap-validator, ap-poster]` — each specialist owns a
section of the workspace A2UI surface. Two new simulated FastMCP
servers (`vendor-master`, `erp-posting`) ground the validator and
poster, demonstrating MCP integration. Adds `adk-workflow-v1` to the
A2A agent card's `SUPPORTED_EXTENSIONS`.

The result: one user message → seven protocol surfaces light up → four
deterministic stages → zero hallucinated workflow decisions. This is
the submission's protocol-fluency centerpiece.

## Decisions Locked (from design doc)

- **New `metadata.agent_type` field** on `SkillMetadata` — `Literal["llm","sequential"]`, defaults to `"llm"` (backwards compatible)
- **ap-pipeline as a marketplace-visible platform skill** — demonstrates the workflow pattern
- **Intake gate via `before_agent_callback`** on the SequentialAgent — emits friendly "please upload an invoice" `types.Content` when no document is in session state, short-circuits the pipeline per ADK's `_handle_before_agent_callback` contract
- **Card emission moves to ap-poster** — orchestrator no longer owns the Invoice Review Card
- **MCP servers stay in-process** — additional FastMCP mounts (`/mcp/vendor-master`, `/mcp/erp-posting`) on the same Cloud Run service; same trust boundary
- **STAGE_PROGRESS labels emitted from sub-agent `before_agent_callback`** — keeps each label colocated with its agent, survives reordering
- **No feature flag** — structural change ships atomically
- **No frontend code changes expected** — pipeline rail (`APPipelineSteps.tsx`) already matches on `invoice_extractor`/`ap_validator`/`ap_poster` substrings; verification only

## Milestones

### M1 — SequentialAgent factory wiring (~4 hours)

**Scope:** `backend`

- [ ] Add `agent_type: Literal["llm","sequential"] = "llm"` to `SkillMetadata` in [backend/db/models/__init__.py](../../../backend/db/models/__init__.py) with `agentType` camelCase alias
- [ ] Verify the field round-trips through Firestore serialisation (existing alias-handling tests should catch this; add one if not)
- [ ] In [backend/adk/agent.py](../../../backend/adk/agent.py) `create_agent`, branch on `md.agent_type == "sequential"`: build `google.adk.agents.SequentialAgent` with resolved `sub_agents` instead of `LlmAgent`. Reuse the existing sub-skill resolution loop (lines 369-382).
- [ ] Implement `_intake_gate_for(skill_config)` returning a `before_agent_callback` that checks for documents in session state (reuse the existing `_document_loader` state-key convention `app:docs_loaded`). When absent: return `types.Content(parts=[types.Part(text="Please upload or select an invoice document and then ask me to process it.")])`.
- [ ] Implement `_final_progress_for(skill_config)` returning an `after_agent_callback` that emits a STAGE_PROGRESS label (`"Done — invoice processed"`) via the existing `LatencyTracker`
- [ ] Tests in `backend/tests/unit/`:
  - `test_skill_metadata.py::test_agent_type_defaults_to_llm` — pre-existing skills without `agent_type` still parse
  - `test_skill_metadata.py::test_agent_type_sequential_round_trips` — serialise + reload via alias
  - `test_agent_factory.py::test_sequential_agent_built_for_pipeline` — `create_agent` on a sequential fixture returns `SequentialAgent` instance with correct sub-agents
  - `test_agent_factory.py::test_intake_gate_returns_friendly_content_when_no_document` — `before_agent_callback` returns `types.Content` when no doc in session
  - `test_agent_factory.py::test_intake_gate_no_op_when_document_present` — callback returns `None` when doc loaded

**Acceptance:** Targeted unit tests pass. Building an existing `LlmAgent` skill from its template still produces an `LlmAgent` (no regression). Building a fixture with `agent_type: sequential` produces a `SequentialAgent` whose sub_agents list matches `subSkills`. Intake gate emits a `types.Content` only when session state lacks documents.

---

### M2 — Skill template restructuring (~3 hours)

**Scope:** `backend` (template YAML + Python platform_seed verification)

- [ ] Create [backend/skills/templates/ap-pipeline/SKILL.md](../../../backend/skills/templates/ap-pipeline/SKILL.md):
  ```yaml
  ---
  name: ap-pipeline
  description: Deterministic AP processing pipeline (Extract → Validate → Post).
  metadata:
    author: aitana
    version: "0.1"
    agent_type: sequential
    subSkills: [invoice-extractor, ap-validator, ap-poster]
  ---
  (No instruction body — SequentialAgent has no model.)
  ```
- [ ] Rewrite [backend/skills/templates/ap-orchestrator/SKILL.md](../../../backend/skills/templates/ap-orchestrator/SKILL.md):
  - `subSkills: [ap-pipeline]` (was the three specialists)
  - Strip the 80-line Invoice Review Card JSON block
  - New instruction: short — *"You are the AP front door. If the user asks to process or post an invoice, transfer to `ap-pipeline` and let it run. Otherwise answer their question briefly. Never reproduce extracted invoice fields yourself — the pipeline owns that."*
  - Keep `list_documents` in `tools`
- [ ] Move the Invoice Review Card JSON block into [backend/skills/templates/ap-poster/SKILL.md](../../../backend/skills/templates/ap-poster/SKILL.md):
  - Verbatim copy from the existing orchestrator template
  - Update poster instruction: *"Read the validation verdict (session state: `verdict`) and the extracted invoice (session state: `extracted_invoice`). Either post to ERP via `post_to_ledger` (verdict=pass) or open an approval exception via `route_to_approval` (verdict=needs_review). Emit the Invoice Review Card via `send_a2ui_json_to_client`."*
  - Add `send_a2ui_json_to_client` and `erp-posting` MCP server to its `toolConfigs`
- [ ] Add per-specialist `updateComponents` block to [backend/skills/templates/invoice-extractor/SKILL.md](../../../backend/skills/templates/invoice-extractor/SKILL.md):
  - Appends an `extracted_section` Column to the workspace surface (`createSurface` only if not yet created — A2UI is idempotent)
  - Renders vendor, invoice number, line item count
- [ ] Add per-specialist `updateComponents` block to [backend/skills/templates/ap-validator/SKILL.md](../../../backend/skills/templates/ap-validator/SKILL.md):
  - Appends a `validation_section` Column with green/red ticks per check
  - Add `vendor-master` MCP server to its `toolConfigs.mcp_servers`
- [ ] Verify [backend/admin/platform_seed.py](../../../backend/admin/platform_seed.py) picks up the new `ap-pipeline` template on next boot (its existing "iterate templates dir" loop should already handle this)
- [ ] Tests:
  - `tests/unit/test_platform_seed.py::test_ap_pipeline_seed_creates_sequential_skill` — seeding parses the new template and produces a SkillConfig with `agent_type=sequential`
  - `tests/unit/test_platform_seed.py::test_ap_orchestrator_subskills_now_points_to_ap_pipeline` — re-seed of orchestrator updates its `subSkills` to `[ap-pipeline]`

**Acceptance:** Re-running `platform_seed` against an empty Firestore produces five AP skills (orchestrator, pipeline, extractor, validator, poster). `ap-orchestrator.subSkills == ["ap-pipeline"]`. `ap-pipeline.subSkills == ["invoice-extractor", "ap-validator", "ap-poster"]`. `ap-pipeline.agent_type == "sequential"`.

---

### M3 — Simulated FastMCP servers (~5 hours)

**Scope:** `backend`

- [ ] Create [backend/protocols/mcp_servers/__init__.py](../../../backend/protocols/mcp_servers/__init__.py) (package init)
- [ ] Create [backend/protocols/mcp_servers/vendor_master.py](../../../backend/protocols/mcp_servers/vendor_master.py):
  ```python
  from mcp.server.fastmcp import FastMCP

  vendor_master_mcp = FastMCP("vendor-master", stateless_http=True, streamable_http_path="/", ...)

  _VENDORS = {
      "acme gmbh": {"vendor_id": "V-1042", "country": "DE", "payment_terms": "NET30", "kyc_status": "verified"},
      "globex industries": {...},
      ...  # 5-8 synthetic vendors covering the demo invoices
  }

  @vendor_master_mcp.tool()
  def lookup_vendor(name: str) -> dict:
      """Look up a vendor by name in the master file..."""

  @vendor_master_mcp.tool()
  def check_duplicate(invoice_number: str, vendor_id: str) -> dict:
      """Check whether this invoice has already been posted..."""
  ```
- [ ] Create [backend/protocols/mcp_servers/erp_posting.py](../../../backend/protocols/mcp_servers/erp_posting.py):
  ```python
  erp_posting_mcp = FastMCP("erp-posting", stateless_http=True, streamable_http_path="/", ...)

  @erp_posting_mcp.tool()
  def post_to_ledger(invoice: dict, gl_code: str, posting_period: str) -> dict:
      """Simulate posting an invoice to the AP ledger..."""
      # Returns {"posting_id": "POST-...", "posted_at": iso8601, "gl_account": ..., "status": "POSTED"}

  @erp_posting_mcp.tool()
  def route_to_approval(invoice: dict, reasons: list[str]) -> dict:
      """Route a needs-review invoice to a finance reviewer's queue..."""
      # Returns {"ticket_id": "APPR-...", "queue": "finance", "sla_hours": 24}
  ```
- [ ] Mount both into [backend/fast_api_app.py](../../../backend/fast_api_app.py) alongside the existing `/mcp` mount:
  ```python
  app.mount("/mcp/vendor-master", vendor_master_mcp.streamable_http_app())
  app.mount("/mcp/erp-posting", erp_posting_mcp.streamable_http_app())
  ```
- [ ] Add Firestore seed entries in [backend/scripts/seed_mcp_servers.py](../../../backend/scripts/seed_mcp_servers.py):
  ```python
  {"name": "vendor-master", "url": f"{base_url}/mcp/vendor-master", "transport": "streamable_http"}
  {"name": "erp-posting",   "url": f"{base_url}/mcp/erp-posting",   "transport": "streamable_http"}
  ```
- [ ] Reference `vendor-master` from `ap-validator/SKILL.md` `tool_configs.mcp_servers`
- [ ] Reference `erp-posting` from `ap-poster/SKILL.md` `tool_configs.mcp_servers`
- [ ] Tool tests in `backend/tests/tool_tests/`:
  - `test_vendor_master_mcp.py::test_lookup_known_vendor_returns_master_data`
  - `test_vendor_master_mcp.py::test_lookup_unknown_vendor_returns_not_found`
  - `test_vendor_master_mcp.py::test_check_duplicate_flags_known_invoice`
  - `test_erp_posting_mcp.py::test_post_returns_posting_id_and_iso_timestamp`
  - `test_erp_posting_mcp.py::test_route_to_approval_emits_ticket_with_sla`
  - All four use FastMCP's in-process test client (no HTTP)

**Acceptance:** Tool tests pass. `GET /mcp/vendor-master/` and `GET /mcp/erp-posting/` return MCP server metadata (200 OK). `mcp_servers/vendor-master` + `mcp_servers/erp-posting` Firestore entries seeded on deploy.

---

### M4 — A2A extension + observability polish (~2 hours)

**Scope:** `backend`

- [ ] Add `"adk-workflow-v1"` to `SUPPORTED_EXTENSIONS` tuple in [backend/protocols/a2a.py](../../../backend/protocols/a2a.py)
- [ ] Update the extensions docstring to describe the new entry
- [ ] Test: `tests/api_tests/test_a2a_agent_card.py::test_advertises_workflow_extension` — fetch `/.well-known/agent.json`, assert `"adk-workflow-v1"` in `capabilities.extensions`
- [ ] STAGE_PROGRESS labels per sub-agent: in [backend/adk/agent.py](../../../backend/adk/agent.py) (where each LlmAgent is built), attach a `before_agent_callback` that pushes one of:
  - `invoice-extractor`: *"Extracting invoice fields…"*
  - `ap-validator`: *"Validating against vendor master + policy…"*
  - `ap-poster`: *"Posting to AP ledger…"*
  to the existing `LatencyTracker` (the mechanism already used by tool-call STAGE_PROGRESS in `backend/adk/callbacks.py:73`)
- [ ] Test: `tests/unit/test_adk_callbacks.py::test_specialist_emits_stage_progress_label`

**Acceptance:** Agent card response includes `adk-workflow-v1`. Running the pipeline emits three STAGE_PROGRESS events with the expected labels in order. Existing pipeline rail UI tests in `frontend/src/components/chat/__tests__/APPipelineSteps.test.tsx` continue to pass without modification.

---

### M5 — Deploy, verify, and write the judge-path script (~3 hours)

**Scope:** `fullstack` (verification + scripting)

- [ ] Push to dev — Cloud Build auto-deploys (multivac-internal-dev/europe-west1)
- [ ] Wait for revision to roll out (~5-10 min), confirm `gcloud run services describe gde-ap-agent` shows new revision
- [ ] Re-seed Firestore by hitting `POST /api/admin/seed-platform-skills` (or wait for boot-time seed)
- [ ] Re-seed MCP servers: `uv run python scripts/seed_mcp_servers.py` from a local terminal pointed at dev project
- [ ] Create [scripts/verify-judge-path.sh](../../../scripts/verify-judge-path.sh):
  - Curls the deployed `/api/skill/<ap-orchestrator-id>/stream` with "please process invoice INV-2026-042" against a known demo session
  - Parses SSE events; asserts:
    1. At least one `transfer_to_invoice_extractor` tool call event
    2. At least one `transfer_to_ap_validator` tool call event
    3. At least one `transfer_to_ap_poster` tool call event
    4. At least one MCP call event with `server="vendor-master"`
    5. At least one MCP call event with `server="erp-posting"`
    6. Final A2UI `updateDataModel` carries an Invoice Review Card with all required fields populated (vendor, status, total)
  - Exits 0 on success, 1 on missing event with a clear error message
- [ ] Manual verification against deployed dev UI:
  - Pipeline rail advances Intake → Extract → Validate → Post
  - Workspace surface assembles three sections + final card
  - Audit view shows per-agent streaming reasoning + schema-enforced JSON
  - Typing indicator surfaces STAGE_PROGRESS labels
- [ ] Negative test: send "hello" (no doc loaded) — confirm intake gate emits the friendly message without running the pipeline
- [ ] Open a Cloud Trace and confirm one span per sub-agent (`invoke_agent ap_pipeline` → 3× `invoke_agent <specialist>`)
- [ ] Move design doc to `implemented/`: `.claude/skills/design-doc-creator/scripts/move_to_implemented.sh multi-agent-workflow-pipeline`
- [ ] Update SEQUENCE.md to ✅ Implemented status

**Acceptance:** `verify-judge-path.sh` exits 0 against deployed dev. All six assertions hold. Manual UI verification matches the design doc's success criteria. Design doc moved to `implemented/`.

---

## Day-by-Day Plan

### Day 1 — 2026-06-03 (today)

- **Morning (~4h):** M1 — SequentialAgent factory wiring + tests
- **Afternoon (~3h):** M2 — Skill template restructuring + platform_seed verification
- **End-of-day target:** M1 + M2 merged on dev. Local backend boots; `make test-fast` green; deploying to dev. ap-orchestrator builds as LlmAgent, ap-pipeline builds as SequentialAgent, agent factory roundtrips both.

### Day 2 — 2026-06-04

- **Morning (~5h):** M3 — Simulated FastMCP servers + tool tests + Firestore seed
- **Afternoon (~2h):** M4 — A2A extension + STAGE_PROGRESS labels
- **End-of-day target:** M3 + M4 merged. Deployed to dev. MCP server tests pass. Pipeline runs end-to-end against a demo invoice.

### Day 3 — 2026-06-05 (deadline day)

- **Morning (~3h):** M5 — Verify against deployed dev, write judge-path script, manual UI verification, move design doc to implemented
- **Afternoon:** Buffer for final demo polish + submission prep
- **17:00 PT:** Submission deadline

## Success Metrics

- All backend tests green: `cd backend && make test-fast`
- All frontend tests green (no expected changes): `cd frontend && npm run test:run`
- Lint + typecheck clean: `make lint` (backend) + `npm run quality:check:fast` (frontend)
- `verify-judge-path.sh` exits 0 against deployed dev
- Manual: pipeline rail advances 4 stages, workspace surface has 3 sections + card, audit view per-agent panes populated
- Cloud Trace: one span per sub-agent (4 spans total per pipeline run)
- Firestore: `mcp_servers/vendor-master`, `mcp_servers/erp-posting` present; `skills/ap-pipeline` present with `agent_type=sequential`

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `SequentialAgent` is `@experimental` in ADK v1.24.1 (config_type marked experimental but the class itself is stable) | Could break on minor ADK upgrade | Pin ADK version in `pyproject.toml`; we use the Python constructor, not the YAML config, so the experimental warning doesn't affect us |
| Sub-agents' `transfer_to_*` events may not reach the AG-UI pipeline rail if ADK's SequentialAgent emits a different event shape than LlmAgent transfers | Pipeline rail stays at Intake | M5 verification catches this; fallback is to add an after-sub-agent hook that emits a synthetic ToolCallState |
| Intake gate triggering on chat messages like "hi" might be surprising — user gets "please upload a document" instead of a chat reply | Bad UX on non-pipeline messages | Front door is the LlmAgent `ap-orchestrator`, not the SequentialAgent — chat lives at the orchestrator, pipeline lives at `ap-pipeline`. Intake gate only fires when user explicitly invokes the pipeline (orchestrator decides to transfer). |
| Demo invoice formats may not parse cleanly through extractor → validator → poster | Pipeline runs but data is garbage | Use the seeded `demo-invoices` bucket invoices that already work end-to-end; smoke-test all 4-6 demo invoices in M5 |
| Two-day deadline is tight if MCP server work takes longer than estimated | Slip past submission | M3 has 5h budget — if it hits 8h, defer `check_duplicate` and skip `route_to_approval`'s SLA logic; keep the demo path working with minimum viable MCP surface |

## Hand-off

After this plan is approved, hand off to `sprint-executor` with sprint ID `WORKFLOW-PIPELINE`.

## Related

- Design doc: [multi-agent-workflow-pipeline.md](./multi-agent-workflow-pipeline.md)
- Prior dependency: [schema-enforced-extraction.md](./schema-enforced-extraction.md) (shipped — provides per-stage structured-output schemas)
- Prior dependency: [multi-agent-inspector-ux.md](./multi-agent-inspector-ux.md) (shipped — provides per-agent audit pane UI)
- Submission deadline: 2026-06-05 17:00 PT (Google AI Agents Challenge Track 3)
