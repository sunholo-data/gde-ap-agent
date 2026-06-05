# Gemini Enterprise + A2UI Alignment (v0.1.0)

**Status**: Implemented — gap-close shipped 2026-06-02
**Priority**: P0 — Devpost deadline 2026-06-05 17:00 PT
**Reference**: Google Cloud blog — [*A practitioner's guide to Gemini Enterprise and A2UI integration*](https://cloud.google.com/blog/topics/developers-practitioners/guide-to-gemini-enterprise-and-a2ui-integration)
**Related**: [submission-readiness.md](submission-readiness.md) · [SUBMISSION.md](../../../../../SUBMISSION.md) · [docs/talks/ai-ui-protocol-stack.md](../../../../talks/ai-ui-protocol-stack.md)

## Why this doc exists

The blog above is the de-facto official guide that a Track 3 judge will read to evaluate Gemini Enterprise / A2UI submissions. It enumerates the protocol surfaces, security properties, and developer workflow that an A2A-discoverable, GE-renderable agent is expected to expose.

This document is the side-by-side map: every theme the blog calls out, where the GDE AP Agent implements it, and where any spec-alignment gaps were closed for the submission. It exists so a judge — or anyone reviewing the fork — can verify in one read that the codebase lines up with the blog's expectations rather than chasing greps.

## Architecture summary

The GDE AP Agent slots into the four-layer model described in the blog and extends it with two further coordination layers documented in [`docs/talks/ai-ui-protocol-stack.md`](../../../../talks/ai-ui-protocol-stack.md):

| Blog layer | Concern | This project |
|---|---|---|
| L1 — App experience | Where the chat happens | Gemini Enterprise (registered), or the in-repo Next.js frontend (`frontend/`) |
| L2 — Pixel drawing | How components render | Frontend `SurfaceRegistry` (Lit-equivalent React renderer) and Gemini Enterprise's built-in A2UI renderer |
| L3 — Conversation pipeline | Client ↔ agent transport | AG-UI SSE for the in-repo frontend; A2A JSON-RPC for Gemini Enterprise |
| L4 — Data format | What rides on the wire | A2UI v0.9 BasicCatalog messages, MIME `application/json+a2ui` |

Two extra surfaces sit alongside the four-layer stack:

- **A2A discovery** — `/.well-known/agent.json` ([`backend/protocols/a2a.py`](../../../../../backend/protocols/a2a.py)) advertises this agent's public skills and supported A2UI patterns. Used by Gemini Enterprise during registration.
- **MCP Apps sandbox** — separate-origin Cloud Run service (`mcp-sandbox-374404277595.europe-west1.run.app`) hosting iframe artefacts (vendor knowledge graph, AP analytics dashboard). Each artefact wires the spec's `ui/update-model-context` channel back to a fork-side `user_intent` convention — click inside an iframe → host auto-sends the corresponding query as a chat message → orchestrator responds. Postmessage handshake per ADR-013.

## Theme-by-theme map

Each row cites the file/symbol that satisfies the theme. Status: ✅ covered as-shipped · 🔧 closed for this submission · 📝 documented (no code surface).

### Protocol stack & data format

| # | Blog theme | Status | Where |
|---|---|---|---|
| 1 | A2UI is declarative JSON, not HTML/JS | ✅ | A2UI v0.9 BasicCatalog only — [`backend/adk/a2ui.py:75`](../../../../../backend/adk/a2ui.py) (`BasicCatalog.get_config("0.9")`). No `innerHTML` / `dangerouslySetInnerHTML` / script tags anywhere in the emit path. |
| 2 | A2UI rides on A2A / AG-UI / SSE (transport-agnostic) | ✅ | Carried in AG-UI `TOOL_CALL_RESULT` events via [`a2ui-agent-sdk`](https://pypi.org/project/a2ui-agent-sdk/) → ADK → ag-ui-adk → SSE. The same A2UI payload can be re-emitted into A2A JSON-RPC for Gemini Enterprise without re-encoding. |
| 3 | Payloads are MIME-typed `application/json+a2ui` | 🔧 | Closed 2026-06-02. Constant `A2UI_MIME_TYPE` added in [`backend/adk/a2ui.py`](../../../../../backend/adk/a2ui.py); `_SurfaceAwareTool.run_async` now tags every successful payload with `mime_type: "application/json+a2ui"` alongside `validated_a2ui_json`. Frontend / GE renderer can route by MIME instead of inspecting payload shape. |
| 4 | Four-layer separation articulated | ✅ | [`docs/talks/ai-ui-protocol-stack.md`](../../../../talks/ai-ui-protocol-stack.md) — six-layer verification table including the four blog layers plus A2A discovery and MCP Apps sandboxing. |

### Component catalog & negotiation

| # | Blog theme | Status | Where |
|---|---|---|---|
| 5 | Pre-approved component catalog (Card / Text / Button / ChoicePicker / Image / GoogleMap) | ✅ | A2UI v0.9 BasicCatalog hardcoded at [`backend/adk/a2ui.py:75-77`](../../../../../backend/adk/a2ui.py). Invoice Review Card, vendor globe Button, analytics Button, AP pipeline visualizer all render from BasicCatalog components. |
| 6 | Inline pattern (tree + inlined data) | ✅ | Default for `default_surface=None` (chat-bubble). `createSurface` + `updateComponents` only — see [`backend/adk/a2ui.py:99-126`](../../../../../backend/adk/a2ui.py). |
| 7 | Decoupled pattern (tree + separate data model) | ✅ | `default_surface="workspace"` route splits `updateComponents` from `updateDataModel`. The example payload at [`backend/adk/a2ui.py:107-138`](../../../../../backend/adk/a2ui.py) shows the decoupled wire format the Invoice Review Card uses. |
| 8 | `X-A2A-Extensions` request/response header negotiation | 🔧 | Closed 2026-06-02. [`backend/protocols/a2a.py`](../../../../../backend/protocols/a2a.py) now (a) advertises `capabilities.extensions` on the card body, (b) reads `X-A2A-Extensions` on the request, (c) responds with the intersection on the response header, (d) sets `Vary: X-A2A-Extensions` so intermediate caches key on capability. Supported set: `a2ui-v0.9`, `a2ui-basic-catalog-v0.9`, `a2ui-inline-pattern`, `a2ui-decoupled-pattern`, `a2a-v0.2`, `mcp-apps-v1`. |
| 9 | Catalog validation before emit | ✅ | `parse_and_fix` + `A2uiSchemaManager.validate()` from the upstream SDK — wired in the `_SurfaceAwareTool.run_async` super-call at [`backend/adk/a2ui.py:260-261`](../../../../../backend/adk/a2ui.py). Error envelope passes through unaugmented (no surface or MIME leak on failure). |

### A2A discovery & Gemini Enterprise registration

| # | Blog theme | Status | Where |
|---|---|---|---|
| 10 | `/.well-known/agent.json` published as A2A AgentCard | ✅ | [`backend/protocols/a2a.py:agent_card`](../../../../../backend/protocols/a2a.py). 60s `lru_cache` with rotating time-bucket key; invalidated on skill CRUD via [`invalidate_cache()`](../../../../../backend/protocols/a2a.py). |
| 11 | Card schema validates against canonical A2A contract | 🔧 | Closed 2026-06-02. Contract validator `_validate_against_a2a_contract()` added in [`backend/tests/api_tests/test_a2a.py`](../../../../../backend/tests/api_tests/test_a2a.py) — pins required top-level fields, required `capabilities` booleans, non-empty `defaultInputModes` / `defaultOutputModes`, and per-skill `id` / `name` / `description`. Two new pytest cases (`test_agent_card_passes_a2a_contract_with_no_skills`, `…_with_skills`) gate future shape regressions. |
| 12 | `make register-gemini-enterprise` equivalent | ✅ | Documented in [SUBMISSION.md:104-112](../../../../../SUBMISSION.md) — `agents-cli register-gemini-enterprise --skill ap-orchestrator`. Skill itself ships its catalog metadata via the discovery card; registration is a one-shot command from any clone. |
| 13 | Public-only skill exposure (no private leak) | ✅ | `list_marketplace()` filters on `accessControl.type == "public"`. Regression-guarded by `test_agent_card_excludes_private_skills` at [`backend/tests/api_tests/test_a2a.py`](../../../../../backend/tests/api_tests/test_a2a.py). |

### Structured input from widget interactions

| # | Blog theme | Status | Where |
|---|---|---|---|
| 14 | Agent accepts structured JSON from widget clicks (not free text) | ✅ | A2UI client actions POST to `/api/sessions/{id}/surface-action` — [`backend/protocols/a2ui_surface_action_routes.py`](../../../../../backend/protocols/a2ui_surface_action_routes.py). The "Run Standalone" form path uses `POST /api/skill/{id}/structured` validating against each `SKILL.md`'s `metadata.structuredInput` JSON Schema. |
| 15 | Widget interactions feed back into the agent loop | ✅ | Opt-in via `tool_configs.a2ui.allow_surface_context_writes: true`. The `InstructionProvider` chain injects the latest surface snapshot + last action into the next agent prompt — [`backend/adk/a2ui_surface_context.py`](../../../../../backend/adk/a2ui_surface_context.py), [`backend/adk/instruction_provider_chain.py`](../../../../../backend/adk/instruction_provider_chain.py). |

### Streaming & real-time updates

| # | Blog theme | Status | Where |
|---|---|---|---|
| 16 | Incremental A2UI emission | ✅ | A2UI v0.9 wire format ships four message types as an array (`createSurface`, `updateComponents`, `updateDataModel`, `deleteSurface`). Each message rides on its own AG-UI `TOOL_CALL_*` event, so partial renders are visible mid-stream. The pipeline visualizer (`APPipelineSteps.tsx`) is driven by `TOOL_CALL_START/END` events emitted before A2UI flushes. |
| 17 | Mid-stream data updates (e.g. live GoogleMap refresh) | ✅ | `updateDataModel` is independent of `updateComponents`. The vendor globe artefact pushes lat/lng changes via postMessage `ui/update-data` after the initial component tree lands; same pattern works for `updateDataModel` on a persistent workspace surface. |

### Safety & security

| # | Blog theme | Status | Where |
|---|---|---|---|
| 18 | No HTML/JS in the JSON payload (XSS prevention) | ✅ | A2UI BasicCatalog has no scripting surface — all component fields are typed strings/numbers/refs. The validator (theme 9) rejects unknown component types before the payload leaves the agent. |
| 19 | API keys never exposed to the LLM | ✅ | GCP credentials resolved at server start ([`backend/fast_api_app.py:resolve_gcp_credentials`](../../../../../backend/fast_api_app.py)). Gemini API key gated by `GOOGLE_API_KEY` env; startup guard rejects when both Vertex and API-key auth are set so a misconfigured deploy fails loudly, not silently. |
| 20 | Third-party UI sandboxed (cross-origin iframes, restricted permissions) | ✅ | [ADR-013](../../../../adr/ADR-013-mcp-apps-sandbox-profile.md) — `sandbox="allow-scripts allow-forms allow-same-origin allow-popups"` with a separate-origin Cloud Run sandbox service. PostMessage handshake validates `event.source === iframeRef.current?.contentWindow` to reject spoofed messages. |

### Developer workflow

| # | Blog theme | Status | Where |
|---|---|---|---|
| 21 | Reference repo + 5-minute smoke test | ✅ | [SUBMISSION.md](../../../../../SUBMISSION.md) "How to Run This in 5 Minutes (LOCAL_MODE)" — `./scripts/dev-local.sh` boots backend + frontend with a stubbed grounding corpus. Smoke targets: `make cli-selftest-mock`, `make cli-selftest-live`. |
| 22 | Spec references in code | ✅ | `https://a2ui.org/specification/v0_9/basic_catalog.json` in the example payload at [`backend/adk/a2ui.py:111`](../../../../../backend/adk/a2ui.py); A2A spec link at [`backend/protocols/a2a.py:17`](../../../../../backend/protocols/a2a.py); MIME constant cites the blog post URL. |

## What changed for the submission

All three gaps below were closed in a single sweep on 2026-06-02. None touched the AP business logic — they are spec-alignment polish surfaces directly traceable to specific lines of the blog.

### Change 1 — `application/json+a2ui` MIME tag

[`backend/adk/a2ui.py`](../../../../../backend/adk/a2ui.py):

- New module-level constant `A2UI_MIME_TYPE = "application/json+a2ui"` with a comment citing the blog.
- `_SurfaceAwareTool.run_async` now adds `mime_type` to every successful tool result dict, alongside the existing `validated_a2ui_json` (and `surface_id` / `update_mode` when a surface is configured).
- Error envelopes deliberately do NOT carry the MIME tag — a MIME on a failure would mislead any MIME-routing client.

Tests: [`backend/tests/unit/test_a2ui_surface_schema.py`](../../../../../backend/tests/unit/test_a2ui_surface_schema.py)
- `test_run_async_without_surface_omits_surface_keys` updated to assert `mime_type == "application/json+a2ui"`.
- New `test_run_async_with_surface_includes_mime_and_surface_keys`.
- `test_run_async_error_path_preserves_legacy_envelope` extended to assert `mime_type` is absent on errors.

### Change 2 — `X-A2A-Extensions` negotiation

[`backend/protocols/a2a.py`](../../../../../backend/protocols/a2a.py):

- New module constant `SUPPORTED_EXTENSIONS` enumerating the six extensions this agent supports.
- `_parse_client_extensions()` / `_negotiate_extensions()` helpers.
- Card body now includes `capabilities.extensions`.
- `agent_card()` endpoint reads `X-A2A-Extensions` header via `Annotated[str | None, Header(alias=...)]`, replies with the negotiated intersection on the response header, and sets `Vary: X-A2A-Extensions`.

Tests: [`backend/tests/api_tests/test_a2a.py`](../../../../../backend/tests/api_tests/test_a2a.py)
- `test_agent_card_advertises_extensions_on_body`
- `test_agent_card_echoes_full_extensions_when_client_sends_none`
- `test_agent_card_negotiates_extension_intersection`
- `test_agent_card_returns_empty_negotiation_when_no_overlap`

### Change 3 — A2A AgentCard contract test

[`backend/tests/api_tests/test_a2a.py`](../../../../../backend/tests/api_tests/test_a2a.py):

- New `_validate_against_a2a_contract()` helper enforcing the A2A v0.2+ AgentCard required-field set and types — top-level fields, capability booleans, `defaultInputModes` / `defaultOutputModes` non-empty string lists, per-skill `id` / `name` / `description`, absolute `url`.
- `test_agent_card_passes_a2a_contract_with_no_skills` and `..._with_skills` gate the card shape against the contract on every CI run.

The contract is inlined rather than fetched from `a2a-protocol.org` so CI stays hermetic; the field set is a direct mirror of the AgentCard schema published with the A2A reference repo.

## Where a judge can verify each claim

1. **A2A discovery** — `curl https://gde-ap-agent-blqtqfexwa-ew.a.run.app/.well-known/agent.json -H 'X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern' -i` → response header `X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern`, body advertises full `capabilities.extensions`.
2. **A2UI live render** — Open the live demo, type the invoice example from [SUBMISSION.md:14](../../../../../SUBMISSION.md). The Invoice Review Card payload in DevTools → Network → SSE stream shows `mime_type: "application/json+a2ui"` on the tool result.
3. **MCP App sandbox** — Click "🌍 View Vendor on Map" — iframe origin is `mcp-sandbox-374404277595.europe-west1.run.app`, distinct from the main agent origin.
4. **Contract test** — `cd backend && uv run pytest tests/api_tests/test_a2a.py -v` runs all card tests including the contract validator.
5. **MIME tag test** — `cd backend && uv run pytest tests/unit/test_a2ui_surface_schema.py::test_run_async_with_surface_includes_mime_and_surface_keys -v`.

## Non-goals

- Implementing every component the blog mentions (e.g. native Google Maps A2UI component). The vendor globe is intentionally an MCP App artefact, not a BasicCatalog `GoogleMap`, because the workshop demonstrates the iframe sandbox path on the same screen.
- A full A2A task-handler (the `tasks/send` / `tasks/get` JSON-RPC surface). The discovery card is required for registration; task handling is the runtime path Gemini Enterprise invokes via its registered endpoint, and the platform's existing `agui.py` route serves that role under the AG-UI envelope rather than raw A2A JSON-RPC.
- Versioning the A2UI catalog beyond v0.9. The agent advertises `a2ui-basic-catalog-v0.9` exclusively; multi-version negotiation is a follow-up once a v1.0 catalog ships.

## Follow-ups

- Add a `make register-gemini-enterprise` thin wrapper around the documented `agents-cli register-gemini-enterprise` invocation so the workflow matches the blog's command verbatim.
- Vendor an A2A schema snapshot (e.g. `docs/vendor/a2a-agent-card.schema.json`) and validate against it in the contract test instead of the inlined field list. Removes a manual sync risk if the A2A spec extends AgentCard.
- Once Gemini Enterprise publishes a public conformance suite, run it against this card in CI.
