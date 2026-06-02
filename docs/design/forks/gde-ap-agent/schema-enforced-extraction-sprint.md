# Schema-Enforced Extraction — Sprint Plan

**Sprint ID**: SCHEMA-ENFORCE
**Design Doc**: [schema-enforced-extraction.md](./schema-enforced-extraction.md)
**Status**: Ready to Execute
**Created**: 2026-06-02
**Deadline**: 2026-06-05 17:00 PT (competition submission)

## Sprint Summary

Wire `metadata.extraction_schema` from SKILL.md frontmatter to session
state, fire schema-constrained Gemini generation in the existing
`structured_extraction_callback`, validate server-side via
`jsonschema.Draft202012Validator`, and **return a `types.Content` from
the callback** so ADK replaces the agent's prose with the validated
JSON. The three AP specialists (invoice-extractor, ap-validator,
ap-poster) each declare their output contract.

Includes the Gemini 3.x API migration since orchestrator + validator
SKILL.md files already moved to `gemini-3.5-flash` / `gemini-3-flash`
(breaking API change vs 2.x for structured output).

## Decisions Locked (from design doc)

- **Output replacement** over append — downstream consumers JSON.parse
- **Graceful degradation** on schema-violation: surface + log, don't fail
- **`oneOf` flattened** to `action` enum discriminator (Gemini subset)
- **`if/then/else`** in server-side jsonschema enforces conditionals
- **Asymmetric naming**: `structuredInput` / `extractionSchema` — no rename
- **Fail-loud** on Gemini 3-flash preview quota errors (no silent fallback)
- **Per-skill output contract**: ap_invoice, ap_verdict, ap_posting_record

## Milestones

### M1 — SkillMetadata + schema registry (~3 hours)
**Scope:** `backend`

- [ ] Extend `SkillMetadata` Pydantic model with `extraction_schema: str | dict | None`
      field (alias `extractionSchema`) in [db/models/__init__.py](../../../backend/db/models/__init__.py)
- [ ] Add 3 AP schemas to [tools/schemas/__init__.py](../../../backend/tools/schemas/__init__.py):
      `ap_invoice`, `ap_verdict`, `ap_posting_record` (flat action enum, not oneOf)
- [ ] Add `_resolve_schema_ref(value: str | dict | None) -> dict | None` helper
- [ ] Tests: schema registry round-trip, resolver (named / inline / unknown / None),
      ap_posting_record's `if/then/else` enforces `posting_id` when `action="post"`

**Acceptance:** Pydantic accepts both named ref + inline schema, round-trips through
Firestore alias serialisation. Resolver raises on unknown names. New schemas validate
against the Draft 2020-12 metaschema.

---

### M2 — Gemini 3.x API migration + before-agent callback (~3 hours)
**Scope:** `backend`

- [ ] `_extraction_config_for_model(model_id, schema)` in `tools/structured_extraction.py`
      — returns 2.x or 3.x config shape based on family. Branch on `"gemini-3"` prefix
      (semver via `is_gemini_2_or_above` already accepts both)
- [ ] `before_agent_extraction_schema_setter` callback in
      [adk/agent.py](../../../backend/adk/agent.py) — reads `skill_metadata.extraction_schema`,
      writes to `app:extraction_schema` in state; idempotent
- [ ] Compose into existing before-agent chain (after document-loader, before model)
- [ ] Tests: config helper returns correct shape for `gemini-2.5-flash` and
      `gemini-3-flash`; callback sets state when schema set; no-op when None;
      handles unknown name (logged, no crash)

**Acceptance:** Targeted tests pass; agent build doesn't regress for skills without
extraction_schema; skills with extraction_schema have `app:extraction_schema` set in
session state at run start.

---

### M3 — Callback enhancement: enforce, validate, replace (~2.5 hours)
**Scope:** `backend`

- [ ] `structured_extraction_callback` now passes the resolved schema to Gemini
      via `_extraction_config_for_model`
- [ ] Server-side validation: `Draft202012Validator(schema).iter_errors(parsed)`
- [ ] **Return `genai_types.Content`** with the validated JSON text to replace
      the response (per ADK base_agent.py after-agent-callback contract)
- [ ] Capture raw LLM prose in `temp:extraction_raw_response` for debugging
- [ ] On validation failure: log structured line + still emit best-effort JSON
      (graceful degradation per design)
- [ ] Tests: happy path (schema-valid output → callback returns Content), failure
      path (logs violations, doesn't crash), 2.x vs 3.x branches

**Acceptance:** invoice-extractor running end-to-end against a canned
`parsed_documents.blocks` payload returns the schema-valid JSON as its
final text response (verified via `InMemorySessionService` integration test).

---

### M4 — SKILL.md wiring + env vars + verify (~2 hours)
**Scope:** `backend` + `docs`

- [ ] Add `extraction_schema: ap_invoice` to invoice-extractor SKILL.md
- [ ] Add `extraction_schema: ap_verdict` to ap-validator SKILL.md
- [ ] Add `extraction_schema: ap_posting_record` to ap-poster SKILL.md
- [ ] Update [cloudbuild.yaml](../../../cloudbuild.yaml) +
      [backend/cloudbuild.yaml](../../../backend/cloudbuild.yaml) to set
      `EXTRACTION_MODEL=gemini-3-flash`
- [ ] Curl probe: run a one-off `client.aio.models.generate_content` with
      `gemini-3-flash` + `response_format` + `ap_invoice` schema, assert
      schema-valid output before merging
- [ ] Update [SUBMISSION.md](../../../SUBMISSION.md) one paragraph: "Each
      specialist's output is JSON Schema-validated server-side..."

**Acceptance:** `make verify-skill-schemas` still passes; deployed skills
serve `extractionSchema` field in the marketplace response; orchestrator
end-to-end run produces schema-valid output at every step.

---

### M5 — Audit View badge + polish (~1.5 hours, deferrable)
**Scope:** `fullstack`

- [ ] Backend: structured-invocation response gains
      `schema_validation: {enforced: bool, valid: bool, errors: [...]}`
- [ ] Frontend: `StandaloneResultView` renders a "Schema enforced ✓" green
      pill when `enforced && valid`; renders violations prominently when
      `!valid` (replaces "see structured outputs below" with the
      validation errors)
- [ ] Frontend test: pill appears when response carries `schema_validation`
- [ ] AG-UI `STAGE_PROGRESS` event "Validating extraction…"

**Acceptance:** Audit View shows the schema-enforced badge for all three
specialists after this lands.

---

## Pause Points

- **End of M2** — verify before-agent callback wiring isn't double-firing
  + schema is in state when expected
- **End of M3** — manual test of invoice-extractor against demo invoice;
  confirm final text response is schema-valid JSON, not LLM prose
- **End of M4** — full orchestrator dry-run with all 3 specialists; verify
  each output is schema-valid; confirm Gemini 3-flash works (or fall back
  to logging the quota error and switching to 2.5-flash for the demo)

## Risks

- **Gemini 3-flash quota limits in preview tier.** Mitigation: curl probe
  in M4 verifies basic schema enforcement before merging. If quota throttles
  mid-demo, the design's "fail-loud" stance means we'd see the error in
  logs and can swap models in SKILL.md without redeploy (skill_metadata
  refresh path).
- **Vertex AI Gemini 3.x might not be available in europe-west1 yet.**
  Mitigation: structured_extraction.py uses `genai.Client(vertexai=True)`
  which routes to `GOOGLE_CLOUD_LOCATION=europe-west1` by default. If
  3-flash isn't there, override `EXTRACTION_LOCATION=us-central1`.
- **Response replacement might break `_after_agent_response` ordering.**
  The existing composition is `[_after_agent_response,
  structured_extraction_callback]`. If `_after_agent_response` returns
  early on non-None, my replacement won't fire. Need to verify ADK runs
  ALL callbacks in the list and either preserves the first non-None
  return or short-circuits.

## Velocity Baseline

| Metric | Value |
|--------|-------|
| Recent velocity | ~665 LOC/day (matches AUDIT-VIEW baseline) |
| Scope | ~400 LOC backend + ~80 LOC frontend (M5) + ~250 LOC tests |
| Total estimated | 1.75 days |
| Wall-clock target | M1-M4 in one session; M5 follow-up if time |
