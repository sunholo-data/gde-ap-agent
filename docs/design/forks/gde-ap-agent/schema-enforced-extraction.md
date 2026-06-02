# Schema-Enforced Structured Extraction

**Status**: Planned
**Priority**: P0 (the whole app's pitch is structural guarantees)
**Estimated**: 1.75 days (backend-heavy, ~700 LOC + tests; +0.25 day for Gemini 3 API migration)
**Scope**: Backend
**Dependencies**: invoice-extractor SKILL.md (b9814bb), existing `structured_extraction_callback` (already wired into every agent's `after_agent_callback`), Gemini 3.x model availability via Vertex AI
**Created**: 2026-06-02
**Last Updated**: 2026-06-02

## Problem Statement

The AP agent's whole pitch is "structurally validated invoice fields with citations, not vibes". The pipeline currently delivers that ONLY by asking the LLM nicely in the SKILL.md prose to return JSON matching a schema described in markdown. Concretely:

**Current state ([invoice-extractor/SKILL.md](../../../backend/skills/templates/invoice-extractor/SKILL.md), as of b9814bb):**
- The LLM is told *"return your final response as a single JSON object matching the schema below"*
- The schema lives as a code-block in the markdown
- Gemini 2.5 Flash usually follows this. Sometimes it adds a stray sentence or wraps in `\`\`\`json` fences or drops an optional field. The validator/poster downstream then receive `JSONDecodeError` or a missing-key crash.
- We already shipped a `structured_extraction_callback` in [backend/tools/structured_extraction.py](../../../backend/tools/structured_extraction.py) that fires after every agent run, uses Gemini with `response_mime_type: "application/json"`, and stores the result in `temp:extraction_result`. **But nothing sets `app:extraction_schema` in session state, so the callback silently no-ops on every run.** It's a chassis with no engine wired in.
- Hard-fail paths the LLM-driven approach can't catch: optional vs required fields, type coercion (`"8500"` vs `8500`), enum constraints (verdict `"pass"` | `"needs_review"`), nested array item shapes (line items).

**Impact:**
- Three downstream agents (ap-validator, ap-poster, audit-view's standalone form) all assume strictly-shaped JSON; a free-form LLM response breaks them.
- A demo that fails on the third invoice in a row because Gemini chose `"total_amount"` instead of `"total"` ships a worse story than the schema-enforced one.
- The "EARNED TRUST" axiom requires verifiable structure, not "the model usually gets it right."

**Pre-existing infrastructure that's not being used:**
- [`structured_extraction_callback`](../../../backend/tools/structured_extraction.py) — Gemini extraction with `response_mime_type: "application/json"`, already wired as after-agent on every agent.
- [`backend/tools/schemas/__init__.py`](../../../backend/tools/schemas/__init__.py) — registry with 6 pre-defined JSON Schemas including `"invoice"`.
- [`structured_invocation.py`](../../../backend/skills/structured_invocation.py) — already validates structured-input payloads with `jsonschema.Draft202012Validator`; the same validator can run on the output.

## Goals

**Primary Goal:** Declare the extraction schema in `SKILL.md` frontmatter and have the runtime guarantee the agent's final response is JSON Schema-valid. Schema violations are surfaced as typed errors, never silently dropped or returned as malformed JSON.

**Success Metrics:**
- 100% of invoice-extractor runs against the demo invoices produce JSON Schema-valid output (no `JSONDecodeError` / no `KeyError` downstream).
- Zero "the LLM forgot a field" failures in 100 runs of the canned demo flow (currently anecdotally ~5%).
- Per-skill schema declaration: invoice-extractor (output schema = `ap_invoice`), ap-validator (output schema = `ap_verdict`), ap-poster (output schema = `ap_posting_record`). Three skills, three deterministic contracts.
- Server-side validation step adds <50ms p99 on top of the existing Gemini call.

**Non-Goals:**
- Re-architecting `structured_extraction_callback` into a tool the LLM calls. The whole point is determinism — the callback fires unconditionally when a schema is declared, not on the LLM's prompt-following discretion.
- A general-purpose schema authoring UI. Schemas live in SKILL.md frontmatter (inline) or `tools/schemas/__init__.py` (named reference). No frontend editor.
- LOCAL_MODE schema enforcement. The callback uses Gemini Vertex AI; in LOCAL_MODE it short-circuits to a passthrough (today's behaviour preserved).
- Streaming partial JSON via AG-UI. The schema-enforced JSON is the agent's final response — we emit it once, complete.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | 0 | Adds ~one Gemini call + validation; offset by removing retry loops downstream when JSON parsing fails |
| 2 | EARNED TRUST | +1 | The whole point — structurally validated output, citable schema, no hallucinated fields outside the declared shape |
| 3 | SKILLS, NOT FEATURES | +1 | Schema lives in SKILL.md frontmatter — declarative, per-skill, no platform code change to add a new schema |
| 4 | RIGHT MODEL, RIGHT MOMENT | +1 | Uses Gemini's native `responseSchema` (constrained decoding) — model is constrained at generation time, not coerced after the fact |
| 5 | GRACEFUL DEGRADATION | +1 | Validation failure surfaces a typed error with the violator's path; LOCAL_MODE short-circuits; missing schema = today's behaviour (no-op) |
| 6 | PROTOCOL OVER CUSTOM | +1 | JSON Schema (draft 2020-12) + Gemini's native `response_schema` config — no custom format |
| 7 | API FIRST | 0 | Pure backend wiring; the existing `/api/skill/{id}/structured` and `/stream` endpoints automatically benefit |
| 8 | OBSERVABLE BY DEFAULT | +1 | New AG-UI `STAGE_PROGRESS` event "Validating extraction…"; jsonschema errors logged with full violator path; the validated payload appears as the agent's final text message in the existing AG-UI stream |
| 9 | SECURE BY CONSTRUCTION | 0 | No new data access; bounds the LLM's output shape (defensive against prompt injection that tries to widen the response) |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | Schema enforcement is server-side; clients (audit view, orchestrator, validator-as-consumer) just receive validated JSON |
| | **Net Score** | **+7** | Threshold: >= +4 ✅ |

**Conflict Justifications:** None — no axiom scores -1.

## Design

### Overview

Add `metadata.extraction_schema` to the `SkillMetadata` Pydantic model — accepts either a **named reference** (`"invoice"` resolves to `SCHEMAS["invoice"]`) or an **inline JSON Schema object**. A new `before_agent_callback`, composed alongside the existing `_after_agent_response` + `structured_extraction_callback` chain in [`adk/agent.py`](../../../backend/adk/agent.py), reads the resolved schema from skill config and sets `app:extraction_schema` in session state at run start. The existing `structured_extraction_callback` then automatically fires after the agent run, calls Gemini with `response_mime_type: "application/json"` AND `response_schema: <schema>` (Vertex's constrained-decoding), runs the result through `jsonschema.Draft202012Validator` server-side as defence-in-depth, and **replaces the agent's final response** with the validated JSON by returning a `types.Content` from the callback (ADK's `after_agent_callback` contract supports this).

Three new pre-defined schemas land in [`tools/schemas/__init__.py`](../../../backend/tools/schemas/__init__.py): `ap_invoice` (invoice-extractor output), `ap_verdict` (ap-validator output), `ap_posting_record` (ap-poster output). Each specialist's SKILL.md gets one new line: `extraction_schema: ap_invoice` (or matching).

### Backend Changes

**Modified Pydantic model:**
- [`backend/db/models/__init__.py`](../../../backend/db/models/__init__.py) — extend `SkillMetadata`:
  ```python
  extraction_schema: str | dict | None = Field(
      default=None, alias="extractionSchema",
  )
  ```
  Accepts a name (resolved against `SCHEMAS`) or an inline JSON Schema dict. None = no enforcement (today's behaviour).

**New / modified callbacks (composed in `adk/agent.py`):**
- New `before_agent_extraction_schema_setter(callback_context)` — resolves `skill.skill_metadata.extraction_schema` (via `_resolve_schema_ref` helper) and writes it to `callback_context.state["app:extraction_schema"]`. Idempotent.
- Existing `structured_extraction_callback` ([tools/structured_extraction.py](../../../backend/tools/structured_extraction.py)) gets two enhancements:
  1. Pass `response_schema` (the resolved JSON Schema) into the Gemini generate-content config, not just `response_mime_type`. Gemini supports constrained decoding for OpenAPI-subset schemas (verify the schema is OpenAPI-compatible at SKILL.md load time; fall back to mime-type-only when not).
  2. After Gemini returns, run the JSON through `jsonschema.Draft202012Validator`. On failure, log the violator path and either (a) emit a `temp:extraction_validation_error` with the full validator report and let the response flow through (graceful degradation, observable) or (b) replace with a clean error payload `{"error": "schema_violation", "errors": [...]}`. Decision: (a) — surfacing the model's broken output makes debugging easier than swallowing it.
  3. **Return a `genai_types.Content`** with the validated JSON text from the callback so ADK appends it as the final agent response (per `base_agent.py` after-agent-callback contract). This is the critical structural change: today the callback returns `None`, so the agent's prose is the response and the JSON is hidden in state.

**New schema registry entries:**
- [`backend/tools/schemas/__init__.py`](../../../backend/tools/schemas/__init__.py) gains three AP-specific entries matching the prose schemas in the specialist SKILL.md files:
  - `ap_invoice` — vendor_name, vendor_id, invoice_number, invoice_date, due_date, po_reference, currency, line_items (description, quantity, unit_price, amount), subtotal, tax, total. `additionalProperties: false` for strictness.
  - `ap_verdict` — verdict (enum `pass | needs_review`), reasons (array of check/severity/detail/citation objects), citations (array of strings).
  - `ap_posting_record` — action (enum `post | escalate`), invoice (object), posting_id (string, present when action=post), escalation_reason (string, present when action=escalate). Mutually exclusive — defined via `oneOf` shapes.

**SKILL.md updates (3 files):**
- [`invoice-extractor/SKILL.md`](../../../backend/skills/templates/invoice-extractor/SKILL.md) — add `metadata.extraction_schema: ap_invoice`. Prose says "the runtime will validate your response against this schema; fields outside the schema are dropped".
- [`ap-validator/SKILL.md`](../../../backend/skills/templates/ap-validator/SKILL.md) — add `extraction_schema: ap_verdict`.
- [`ap-poster/SKILL.md`](../../../backend/skills/templates/ap-poster/SKILL.md) — add `extraction_schema: ap_posting_record`.

**Schema resolution helper:**
- New `_resolve_schema_ref(value: str | dict | None) -> dict | None` in [`tools/schemas/__init__.py`](../../../backend/tools/schemas/__init__.py):
  - `None` → `None` (no enforcement)
  - `dict` → returned as-is (inline schema)
  - `str` → looked up in `SCHEMAS`; raises `ValueError` on unknown name (caught at agent build time, logged, falls through to None)

### API Changes

| Method | Endpoint | Description | Breaking? |
|--------|----------|-------------|-----------|
| POST | `/api/skill/{skill_id}/structured` | Existing endpoint; response shape **gains** `schema_validation: {valid: bool, errors: [...]}` when the skill declares an extraction schema | No — additive |
| POST | `/api/skill/{skill_id}/stream` | Existing AG-UI stream; gains `STAGE_PROGRESS` events labeled `"Validating extraction…"`; the final `TEXT_MESSAGE_CONTENT` event contains the validated JSON instead of LLM prose | No — additive, downstream consumers already JSON.parse this field |

### Architecture Diagram

```
SKILL.md frontmatter (declarative)
  metadata:
    extraction_schema: ap_invoice   ← short name OR inline JSON Schema
  │
  ▼
backend/skills/skill_config — SkillMetadata Pydantic model parses + persists
  │
  ▼
adk/agent.create_agent(skill, user)
  │  ├─ before_agent_callbacks: [..., set_extraction_schema_in_state]
  │  ├─ tools: [list_documents, get_document_content, ...]
  │  └─ after_agent_callbacks: [_after_agent_response, structured_extraction_callback]
  │
  ▼ agent runs, calls get_document_content(mode="blocks") → sets temp:document_blocks
  │
  ▼ agent's text response (whatever the LLM wrote)
  │
  ▼ structured_extraction_callback fires
  │   │
  │   ├─ Reads app:extraction_schema + temp:document_blocks
  │   ├─ Calls Gemini with response_mime_type=json + response_schema=<schema>
  │   ├─ Validates output via jsonschema.Draft202012Validator
  │   ├─ Logs schema_violations (path + reason) on failure
  │   └─ RETURNS types.Content(validated_json)  ← replaces agent's prose
  │
  ▼ ADK emits TEXT_MESSAGE_CONTENT(validated_json) as the final response event
  │
  ▼ Downstream consumers (audit-view, ap-validator, ap-poster, orchestrator)
    all read deterministic JSON — no more "the LLM forgot a field"
```

### Gemini 3.x / 3.5 model compatibility (BREAKING API change)

The orchestrator + validator SKILL.md files were updated in the same
session as this design (after the doc was first drafted) to point at
**`gemini-3.5-flash`** (ap-orchestrator) and **`gemini-3-flash`**
(ap-validator). Gemini 3.x has a different structured-output API
than 2.x, which the existing
[`structured_extraction.py`](../../../backend/tools/structured_extraction.py)
does not yet support.

**API surface comparison (per ai.google.dev/gemini-api/docs/structured-output):**

| Aspect | Gemini 2.x | Gemini 3.x |
|---|---|---|
| Config key | `response_mime_type: "application/json"` + `response_schema: <schema>` | `response_format: {"text": {"mime_type": "application/json", "schema": <schema>}}` |
| `propertyOrdering` array | **Required for 2.0** (hint to model) | **Ignored** — 3.x handles ordering automatically |
| `oneOf` / `anyOf` | Not in supported subset (silently produces broken output for either family) | Not in supported subset |
| `additionalProperties: false` | Supported | Supported (still our prompt-injection defence) |
| Supported types | string, number, integer, boolean, object, array, null | Same |
| Supported object props | `properties`, `required`, `additionalProperties` | Same |
| Supported string props | `enum`, `format` | Same |
| Supported number props | `enum`, `minimum`, `maximum` | Same |
| Supported array props | `items`, `prefixItems`, `minItems`, `maxItems` | Same |

**ADK model resolution:** `google-adk` 1.31.1 (currently pinned in
[pyproject.toml](../../../backend/pyproject.toml#L18)) already handles
Gemini 3.x via [`is_gemini_2_or_above`](google.adk.utils.model_name_utils.is_gemini_2_or_above)
— it parses the version string semantically and returns `True` for
anything with major >= 2. No ADK upgrade needed; the existing
`adk/agent.py::resolve_model` flow accepts `"gemini-3.5-flash"`
unchanged.

**Implications for this design:**

1. **`structured_extraction.py` config payload must branch on model.**
   The current code calls
   `client.aio.models.generate_content(config={"response_mime_type": "application/json"})`.
   For Gemini 3.x we need
   `config={"response_format": {"text": {"mime_type": "application/json", "schema": <schema>}}}`.
   Add a small `_extraction_config_for_model(model_id, schema)` helper that
   returns the right shape based on `is_gemini_2_or_above` + a
   `"3."` prefix check. Keeps 2.x and 3.x skills coexisting.
2. **Drop `oneOf` from `ap_posting_record`.** The first draft of this
   design used `oneOf` to model the post-vs-escalate split. Neither
   2.x nor 3.x supports `oneOf` in constrained decoding. Flatten to
   a single object with an `action` enum discriminator
   (`"post" | "escalate"`) + optional `posting_id` + optional
   `escalation_reason`. Server-side `jsonschema` validation can
   still enforce the conditional ("posting_id required when
   action=post") via a separate Draft 2020-12 `if/then` clause that
   runs in the validation pass (Draft 2020-12 supports `if/then/else`
   even though Gemini's constrained decoding doesn't).
3. **`propertyOrdering` in `tools/schemas/__init__.py` is harmless
   noise on 3.x but still needed for 2.x callers.** Keep it on the
   existing pre-defined schemas; the new AP schemas can omit it
   since the AP pipeline is now 3.x-only.
4. **Migrate the extraction model default.** `EXTRACTION_MODEL` env
   var (default `gemini-2.5-flash` today) should ride alongside the
   skill model — set to `gemini-3-flash` in cloudbuild.yaml so the
   extraction pass uses the same family the skill agent uses.

### CLI Surface

Out of scope for this fork — the `aiplatform` / `aitana` CLI is the upstream's surface and the schema mechanism is purely declarative (in SKILL.md). A future `aiplatform skill validate <skill-id>` enhancement could lint extraction_schema references against the registry, but that's an upstream concern; for now `make test` + the `aiplatform-cli` skill's curl recipes cover verification.

## Implementation Plan

### Phase 1: Backend wiring (~0.5 day)
- [ ] Extend `SkillMetadata` model with `extraction_schema: str | dict | None` field (~5 LOC + 2 tests)
- [ ] Add `_resolve_schema_ref` helper + 3 new schemas (`ap_invoice`, `ap_verdict`, `ap_posting_record`) in `tools/schemas/__init__.py` (~150 LOC + tests). **`ap_posting_record` uses a flat `action` enum discriminator instead of `oneOf` (per Gemini 3.x subset constraints) — server-side `jsonschema` enforces the conditional via Draft 2020-12 `if/then/else`.**
- [ ] Add `before_agent_extraction_schema_setter` callback in `adk/agent.py`; compose into the existing before-agent chain (~20 LOC)
- [ ] Enhance `structured_extraction_callback` to (a) pass the resolved schema to Gemini via the right config shape for the active model family, (b) validate via jsonschema, (c) return `types.Content` to replace the response (~60 LOC + tests)

### Phase 1b: Gemini 3.x API migration (~0.25 day)
- [ ] Add `_extraction_config_for_model(model_id, schema)` helper that returns either `{response_mime_type, response_schema}` (2.x) or `{response_format: {text: {mime_type, schema}}}` (3.x) based on the model identifier prefix
- [ ] Cover both branches in tests: `test_extraction_config_gemini_25` (existing API), `test_extraction_config_gemini_3` (new API)
- [ ] Update `EXTRACTION_MODEL` env default in cloudbuild.yaml + cloudbuild.yaml (backend) to `gemini-3-flash` so the extraction pass family-matches the skill model
- [ ] Verify with a curl probe before merging that `gemini-3-flash` accepts the new `response_format` payload against `ap_invoice`

### Phase 2: SKILL.md updates + tests (~0.5 day)
- [ ] Add `extraction_schema: ap_invoice` to invoice-extractor SKILL.md; update prose to mention the validator
- [ ] Add `extraction_schema: ap_verdict` to ap-validator SKILL.md
- [ ] Add `extraction_schema: ap_posting_record` to ap-poster SKILL.md
- [ ] Backend tests: schema resolution (named, inline, unknown name, None); before-agent callback sets state; structured_extraction_callback replaces response on success; logs error on validation failure (~120 LOC of tests)
- [ ] Integration test against a canned `parsed_documents.blocks` payload that the AP invoice schema can extract from — asserts the final response is JSON Schema-valid

### Phase 3: Observability + polish (~0.25 day)
- [ ] AG-UI `STAGE_PROGRESS` event `"Validating extraction…"` fired between the Gemini call and the validator pass (per [ttft-instrumentation](../../v6.1.0/ttft-instrumentation.md) pattern)
- [ ] Structured logger line: `extraction.validated skill=<id> schema=<name> errors=<count> duration_ms=<n>`
- [ ] Update [SUBMISSION.md](../../../SUBMISSION.md) one-paragraph mention: "Each specialist's output is JSON Schema-validated server-side — `ap_invoice` for extractor, `ap_verdict` for validator, `ap_posting_record` for poster — making the audit trail structural, not vibes-based."

### Phase 4: Audit View badge (~0.25 day, deferrable to follow-up)
- [ ] Add `schema_enforced: true | false` boolean to the structured-invocation response payload
- [ ] Frontend `StandaloneResultView` renders a "Schema enforced ✓" green pill next to the duration badge when the skill has an extraction_schema declared
- [ ] If validation errors are present, render them prominently above the result (instead of buried) — turns the silent-degradation path into a visible audit moment

## Migration & Rollout

**Database Migrations:** None. The new `extraction_schema` field on `SkillMetadata` defaults to `None`, which is today's behaviour. Existing skill records in Firestore deserialize cleanly (Pydantic ignores unknown serialized fields per `populate_by_name=True`).

**Feature Flags:**
- `EXTRACTION_SCHEMA_ENFORCEMENT=disabled` env var on the backend disables the new before-agent callback wiring, so the system reverts to the prior LLM-prose-following behaviour. Default `enabled`. Off-switch only — no progressive rollout needed because the three specialist SKILL.md files opting in is the rollout.

**Rollback Plan:** Single env-var flip OR remove the `extraction_schema:` line from the SKILL.md and re-seed. The `platform_seed` refresh path (fa1d150) makes the latter a one-deploy revert.

**Environment Variables:**
- `EXTRACTION_SCHEMA_ENFORCEMENT` (default `enabled`) — backend, all envs
- Existing `EXTRACTION_MODEL` (default `gemini-2.5-flash`) — unchanged

## Testing Strategy

### Backend Tests (pytest)
- [ ] `tools/schemas/__init__.py::_resolve_schema_ref` — 4 cases (named lookup, inline dict passthrough, unknown name raises ValueError, None returns None)
- [ ] `tools/schemas/__init__.py` registry — 3 new schemas are valid JSON Schemas (draft 2020-12 metaschema check)
- [ ] `adk/agent.py::before_agent_extraction_schema_setter` — sets `app:extraction_schema` from skill_metadata; no-op when extraction_schema is None; handles inline dict + named ref + unknown name (logged, no crash)
- [ ] `tools/structured_extraction.py::structured_extraction_callback` — happy path: Gemini call mocked, schema-valid output → callback returns `Content` with the validated JSON; failure path: schema-invalid output → returns the original prose + logs violations, doesn't crash
- [ ] Integration test in `tests/integration/test_extractor_schema_enforcement.py`: build the invoice-extractor agent, run it against a canned `parsed_documents.blocks` payload using `InMemorySessionService`, assert the final response is JSON Schema-valid against `ap_invoice`

### Manual / Audit-view E2E
- [ ] Run invoice-extractor "Run Standalone" against demo invoice acme-gmbh-invoice-2026-042; the StandaloneResultView should show JSON exactly matching the `ap_invoice` schema
- [ ] Edit the canned form input to omit `vendor_name`; re-run; verify the schema-violation surface in the panel
- [ ] Run the full orchestrator pipeline; verify ap-validator receives valid `ap_invoice` JSON and emits valid `ap_verdict` JSON

## Security Considerations

- **Bounding LLM output is a defence.** Today a prompt-injected `parsed_documents.blocks` payload could coerce the LLM to return arbitrary JSON — eg. `{"vendor_name": "Acme", "exfiltrated_secret": "..."}` — and downstream consumers might log/forward the unexpected field. `additionalProperties: false` on each schema strips fields not in the contract before they reach the wire.
- **No new data access.** Schema resolution + validation are pure operations on existing in-process data.
- **Validation errors are NOT echoed verbatim to the user-visible audit view** — the validator's error messages can contain reflected portions of the LLM output. We log full reports server-side but the panel surfaces a sanitised "schema_violation: field <path> failed <constraint>" summary.

## Performance Considerations

- **Added cost per run:** one Gemini call (already happens for `structured_extraction_callback` when the schema is set — but currently it's a no-op because the schema is never set) + ~10ms jsonschema validation.
- **Gemini constrained decoding** (`response_schema` config) is roughly equivalent latency to `response_mime_type: json` alone — Google's docs note the schema is applied during decoding, not as a post-pass. Verified for `gemini-2.5-flash`.
- **No new caching needed** — schemas are resolved once at agent build (per session start), not per turn.

## Success Criteria

- [ ] All backend tests passing (`cd backend && make lint && make test-fast`)
- [ ] Lint + typecheck clean (`cd backend && uv run ruff check && uv run ruff format --check`)
- [ ] Frontend tests passing (`cd frontend && npm run test:run`)
- [ ] `SkillMetadata.extraction_schema` field accepts named refs, inline dicts, and None — round-trips through Firestore
- [ ] invoice-extractor, ap-validator, ap-poster SKILL.md files all declare `extraction_schema`
- [ ] Running invoice-extractor standalone via the Audit View "Run Standalone" form produces JSON Schema-valid output that matches `ap_invoice`
- [ ] ap-validator standalone form produces output matching `ap_verdict`
- [ ] ap-poster standalone form produces output matching `ap_posting_record`
- [ ] Orchestrator-driven pipeline completes end-to-end with all three specialists' outputs schema-valid
- [ ] AG-UI stream surfaces `STAGE_PROGRESS "Validating extraction…"` between the model response and the final text-message event
- [ ] Validation failures emit a structured log line `extraction.validation_failed` with skill_id + schema name + violator paths

## Resolved Questions

- **Replace vs append the LLM's response?** Replace, per the design above — downstream consumers (validator/poster) consume the response as JSON and breaking that contract by appending two messages would force them to parse multi-part responses. The LLM's intermediate prose is captured in `temp:extraction_raw_response` for debugging but not surfaced.
- **Schema-violation behaviour?** Surface the broken output + log violations (graceful degradation). Demo-friendly; revisit if drift observed.
- **Does Gemini 2.x/3.x support `oneOf` / `anyOf`?** **No.** Per ai.google.dev/gemini-api/docs/structured-output, neither family includes `oneOf`/`anyOf` in the constrained-decoding subset. **Resolution:** `ap_posting_record` uses a flat `action` enum (`"post" | "escalate"`) + optional `posting_id` + optional `escalation_reason`. Server-side `jsonschema.Draft202012Validator` enforces the conditional ("posting_id required when action=post") via `if/then/else`, which is full Draft 2020-12 and not subject to Gemini's subset.
- **`propertyOrdering` everywhere?** Required for Gemini 2.0, ignored from 2.5 onward, harmless on 3.x. Keep on existing schemas, omit on new AP schemas (AP pipeline is now 3.x-only).

## Open Questions

- **Wire this into the existing structured-input schemas?** The audit view's Run-Standalone form already validates input via `metadata.structuredInput` JSON Schema. Should we rename it to `inputSchema` to mirror the new `outputSchema`/`extraction_schema`? Symmetry would be nice but renaming risks churn — accept asymmetric names (`structuredInput` for input, `extractionSchema` for output) and document the symmetry in the SKILL.md template.
- **Should the extraction model default to the SKILL.md's declared model rather than a separate `EXTRACTION_MODEL` env var?** Today `EXTRACTION_MODEL` is independent of the agent model. Now that the AP pipeline is mixed-family (orchestrator on 3.5, validator on 3-flash, poster TBD), the extraction call should probably use the same family as the skill running it — `_extraction_config_for_model` already needs to branch on family for the API surface, so it might as well pull the model from the skill config too. Worth a 5-minute prototype to decide.
- **Will Gemini 3-flash (preview) be ready by submission deadline?** As of doc date the preview tier may have stricter quotas than 3.5-flash (stable). Have a fallback to `gemini-2.5-flash` on quota errors? Or fail loudly so we know to update the SKILL.md? Lean toward fail-loud — quota silently swapping models defeats the whole "deterministic" pitch.

## Related Documents

- [Multi-Agent Inspector UX](./multi-agent-inspector-ux.md) — defines the Audit View surfaces that will render the schema-enforcement badge
- [Competition Polish Sprint](./competition-polish-sprint.md) — the M1-M6 sprint that shipped the invoice-extractor, ap-validator, ap-poster skills
- [Product Axioms](../../../docs/product-axioms.md) — Axiom #2 EARNED TRUST: "Always show sources. Never present uncertain information with false confidence" — schema enforcement is one mechanism behind this axiom
- AP specialist skills: [invoice-extractor/SKILL.md](../../../backend/skills/templates/invoice-extractor/SKILL.md), [ap-validator/SKILL.md](../../../backend/skills/templates/ap-validator/SKILL.md), [ap-poster/SKILL.md](../../../backend/skills/templates/ap-poster/SKILL.md)
- [`backend/tools/structured_extraction.py`](../../../backend/tools/structured_extraction.py) — the after-agent callback this design wires into action
- [`backend/tools/schemas/__init__.py`](../../../backend/tools/schemas/__init__.py) — the registry getting three new entries
