# A2A document support — inbound files + org-scoped buckets

**Status**: Implemented
**Priority**: P1 (Medium) — file-upload-over-A2A is the natural follow-up to the message/send bridge; closes a real Gemini Enterprise use case that hit production within hours of registration
**Estimated**: ~1.0 day implementation + tests + verification (was 0.75 — bumped for the org-bucket mode)
**Scope**: Backend
**Dependencies**:
- [A2A `message/send` bridge](./implemented/a2a-message-send-bridge.md) — landed; this design extends it
- ADK_ARTIFACT_BUCKET already provisioned (used by the AG-UI surface)
- `a2a.types.FilePart` / `FileWithBytes` / `FileWithUri` confirmed in installed `a2a-sdk`
**Created**: 2026-06-08
**Last Updated**: 2026-06-08 (implemented)
**Upstream-bound**: Yes — every fork accepting documents via A2A hits the same six questions

## Problem Statement

The A2A `message/send` bridge handles **text-only** invocations. There are TWO distinct document scenarios peers need today, neither of which works:

**Scenario A — peer sends a fresh document the agent has never seen.** Most common path. On 2026-06-07 22:06:32 UTC, a real Gemini-Enterprise-routed call attempted exactly this and produced a silent failure:

- GE received a user upload (an invoice file in the workspace UI)
- GE's A2A call to our `/a2a` endpoint had only ~2KB extra payload over a text-only call — way too small to carry a `.docx` (~20KB+)
- The agent's pre-turn doc-loader callback logged `doc loader: turn start — document_ids=[] prior loaded=[]`
- The orchestrator answered conversationally because it had no file content to process

**Scenario B — peer asks about a document the org already owns.** A different and complementary need: the agent is registered to org X, org X has a Cloud Storage bucket of pre-loaded documents (vendor master, historical invoices, approval policies, contracts), and a peer in org X asks "what's the spend trend with Acme this quarter?" — the agent should be able to list and read documents from that bucket without the peer having to upload anything. This is RAG-over-an-org-bucket, not file passthrough.

Today there is no convention for "this agent registration is linked to this bucket." Workarounds (env vars baked into the deploy, hard-coded bucket names in skill instructions) don't scale across orgs and they leak across tenants.

**Current State (verified by `gcloud logging read` against the live deploy):**

- ✅ A2A `message/send` text → orchestrator → response works end-to-end (proven in the A2A-INVOKE sprint)
- ✅ Card advertises `defaultInputModes: ["text"]` only — peers correctly conclude this agent doesn't accept files
- ❌ Even when peers attempt file passthrough, our A2A executor has no extraction path for `FilePart` → existing `document_ids` session-state contract
- ❌ The orchestrator's `make_document_loader` callback expects `state["document_ids"]` populated before the runner starts — A2A invocations skip that path entirely
- ❌ AG-UI users (the existing path) get full file handling; A2A users (peers + Gemini Enterprise) don't

**Impact:**

- **Real failure now**: Gemini Enterprise users attempt file uploads, get a non-answer, lose trust in the agent.
- **Track 3 story**: the demo card promises invoice processing — "drop an invoice" is the headline. Without file input via A2A, the promise breaks for any caller that isn't the in-app chat UI.
- **Every fork** of the platform that exposes documents to A2A peers hits the same six surface questions. Solving once upstream means free leverage for every downstream.

## Goals

**Primary Goal:** A peer agent or Gemini Enterprise can do BOTH:

1. **(Scenario A)** Include an A2A `FilePart` (either inline `FileWithBytes` or `FileWithUri`) in `message/send`; the orchestrator's existing doc-loader pipeline sees the document via `state["document_ids"]` and processes it identically to an AG-UI upload.
2. **(Scenario B)** Reference a document the agent already has standing access to via an **org-scoped bucket** linked to the agent registration; a `list_documents` / `read_document` tool the agent already exposes lets the orchestrator answer questions like "summarize this quarter's invoices from Acme" without the peer having to upload anything.

**Success Metrics:**

For Scenario A (inbound file):
- `scripts/simulate-a2a-peer.py` gains Step 7 that POSTs an A2A `message/send` with a `FilePart` carrying an embedded base64 invoice; assertions pass on the resulting Task envelope
- Cloud Run logs show `doc loader: turn start — document_ids=['<minted-id>']` when an A2A FilePart arrives
- A Gemini Enterprise file upload (the failing flow from 22:06:32 UTC on 2026-06-07) produces the same posting decision an AG-UI upload would
- ADK_ARTIFACT_BUCKET grows by 1 artifact per A2A file-bytes invocation; orphan-cleanup remains the same as for AG-UI uploads
- No regression in text-only A2A invocations (every existing test in `test_a2a_invocation.py` still passes)

For Scenario B (org-scoped bucket):
- `scripts/simulate-a2a-peer.py` gains Step 8 that POSTs `message/send` with a text-only query about an existing document and asserts the response references the document's content
- The orchestrator can call a `list_org_documents` tool and get back a list of objects from the agent's linked bucket, scoped to the calling peer's org
- A request without an authenticated org context (or for an agent registration with no linked bucket) gets an empty list and a graceful "no documents available" response — never a 500
- Tenant isolation tested: two registrations pointing at different buckets never see each other's documents

**Non-Goals:**
- **Inline binary file response from the agent** — `Task.artifacts[].parts` will continue to carry text/JSON, not file bytes. Outbound files would need a different design.
- **Multi-file batching beyond what `parts[]` already gives us** — A2A's `parts` array is the batching primitive; if a peer sends N FileParts we register N document IDs and the loader processes them in declared order. No new batching protocol.
- **A2A-specific document storage** — files land in the same ADK_ARTIFACT_BUCKET / Firestore-backed doc registry the AG-UI surface uses. No new storage layer.
- **Streaming file uploads** — A2A `message/send` is request/response. A peer that wants to upload a 500MB PDF can do so via base64 inline (the spec doesn't constrain size) but the deploy will hit Cloud Run's 32MiB request limit before us. Multi-part / streaming uploads = future spec, future design doc.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | 0 | Adds an upload + parse step to file-bearing turns; latency dominated by ailang-parse not our bridge code |
| 2 | EARNED TRUST | +1 | Source attribution holds: A2A FilePart → document_id → `doc:{id}.json` artifact → citations on agent output. Documents from A2A are first-class, traceable, and citable like AG-UI uploads |
| 3 | SKILLS, NOT FEATURES | +1 | Skill stays the abstraction; the A2A surface gets equal-weight file input alongside AG-UI |
| 4 | RIGHT MODEL, RIGHT MOMENT | +1 | Reinforces the AILANG-Parse-first path: peer-supplied files run through the same deterministic parser, no LLM tokens on extractable formats |
| 5 | GRACEFUL DEGRADATION | +1 | If file extraction fails, falls back to text-only path with a comprehensible error in the Task response. If the peer sends a URI we can't fetch, the existing orphan-probe drops the doc id and the agent answers from text context |
| 6 | PROTOCOL OVER CUSTOM | +1 | Adopts A2A v0.2 spec's `FilePart` + `FileWithBytes` / `FileWithUri` exactly — no custom file shape |
| 7 | API FIRST | +1 | The API surface (skill request) gains parity across AG-UI and A2A. Channel = transport, not business logic |
| 8 | OBSERVABLE BY DEFAULT | +1 | New OTel span around the A2A FilePart conversion + upload; same BigQuery sink as AG-UI uploads; full content captured per Axiom 8 (data stays inside GCP project) |
| 9 | SECURE BY CONSTRUCTION | 0 | New trust input — file bytes from peer agents. Size limits + MIME allowlist enforced; bytes go straight to ADK_ARTIFACT_BUCKET (inside GCP project, no third-party egress per Axiom 9's privacy boundary). Auth already enforced by the A2A middleware shipped in M2 |
| 10 | THIN CLIENT, FAT PROTOCOL | 0 | Backend-only change; no client impact |
| | **Net Score** | **+7** | Threshold: >= +4 ✓ |

**Conflict Justifications:** None — no -1 scores.

## Standards Compliance

**Adopts:**
- **A2A v0.2 spec** (`a2a.types.FilePart`, `FileWithBytes`, `FileWithUri`) — verified against installed `a2a-sdk` package via `pydantic` model introspection. `FilePart.file` is a union of `FileWithBytes(bytes: str, mimeType: str | None, name: str | None)` and `FileWithUri(uri: str, mimeType: str | None, name: str | None)`.
- **Existing AG-UI document_ids convention** — A2A files end up in the same session-state key `state["document_ids"]` and same artifact format `doc:{id}.json` so `make_document_loader`, `make_document_injector`, and citation rendering all work without per-source branching.
- **Existing ADK Artifact Service** (`get_artifact_service()`) — A2A uploads land via the same `save_artifact` path as AG-UI uploads.

**Does not invent:**
- Custom file part shape (would lose A2A peer interop — strict client like GE would reject it)
- Custom session-state key for A2A documents (would force the loader to read from two places)

## Design

### Overview

Subclass ADK's `A2aAgentExecutor` (or hook into its `request_converter`) to extract A2A `FilePart`s from incoming `message/send` payloads BEFORE the runner starts. For each FilePart:

- **`FileWithBytes`** → base64-decode → upload to ADK_ARTIFACT_BUCKET as `doc:{id}.json` (wrapped in our existing doc-block JSON schema) → mint a document_id → append to session state's `document_ids` list before the agent runs.
- **`FileWithUri`** → register the URI under a document_id → the doc-loader's URI-fetcher (already exists for AG-UI's GCS-browser path) loads it lazily during the turn.

The orchestrator's `before_agent_callback` chain (which already includes `make_document_loader`) then sees `state["document_ids"]` populated and behaves identically to an AG-UI upload. No skill code changes.

### Eight Surface Decisions

Six on Scenario A (inbound file) + two on Scenario B (org-scoped bucket):

#### 1. Card `defaultInputModes` — **extend to include common document MIME types**

| Option | Result | Pick |
| --- | --- | --- |
| **Add specific MIME types** advertised by AILANG Parse + ailang-parse fallback list | Peers know exactly what we accept; correct interop semantics | ✓ |
| Add `"file"` as a catch-all | Not in A2A spec — `defaultInputModes` is a list of MIME types not abstract kinds | ✗ |
| Leave at `["text"]`, accept file parts anyway | Spec-violating; some peers will refuse to send | ✗ |

→ Card now advertises:

```python
"defaultInputModes": [
    "text",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",         # .xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", # .pptx
    "application/vnd.oasis.opendocument.text",   # .odt
    "message/rfc822",                            # .eml
    "text/csv",
],
```

Override per-fork via `A2A_AGENT_INPUT_MIME_TYPES` env var (same pattern as `A2A_AGENT_NAME` / `A2A_AGENT_DESCRIPTION` / `A2A_AGENT_ICON_PATH`).

#### 2. A2A → ADK part converter behavior — **subclass `A2aAgentExecutor`**

ADK's `A2aAgentExecutor.execute` ([introspected in M1]) calls a configured `request_converter` that maps A2A parts to genai parts. By default the converter handles `TextPart` → text and likely drops `FilePart` silently (the M1 failure pattern confirms this).

Options:

| Option | Surface change | Effort | Pick |
| --- | --- | --- | --- |
| **Subclass `A2aAgentExecutor`** with overridden `execute` that pre-processes the request to extract FileParts | Minimal — same mount API | ~30 LOC | ✓ |
| Monkey-patch ADK's converter at module load | Brittle; breaks on ADK minor bumps | ~10 LOC | ✗ |
| Build our own A2A handler from scratch | Loses ADK's runner integration | ~200+ LOC | ✗ |

→ New module `backend/protocols/a2a_file_extraction.py` exporting `A2aFileExtractingExecutor(A2aAgentExecutor)`. Overrides `execute(context, event_queue)` to:

1. Walk `context.message.parts` extracting any `FilePart`
2. For each FilePart, dispatch on `file` shape:
   - `FileWithBytes` → `_upload_inline_bytes(part)` → returns document_id
   - `FileWithUri` → `_register_uri(part)` → returns document_id
3. Inject the list of new document_ids into `state["document_ids"]` (merging with any existing list — A2A turns are idempotent like AG-UI turns)
4. Delegate to `super().execute(context, event_queue)` with the part-list rewritten to exclude FileParts (since the docs are now in session state where the loader expects them)

#### 3. Document-loader integration — **session-state injection (the existing contract)**

The fork already has a tested, observable pipeline that fires on `state["document_ids"]`. Two integration points to evaluate:

| Option | Where the document_ids land | Existing tests cover | Pick |
| --- | --- | --- | --- |
| **Session-state injection** before runner starts | `state["document_ids"]` (existing) | All `make_document_loader` paths | ✓ |
| New callback hooked into `before_agent_callback` for A2A only | New A2A-specific callback | None; would need new tests | ✗ |

→ Injection at the executor layer, NOT a new callback. The `make_document_loader` callback gets the doc IDs through its existing path — no skill code change, no new behaviour at runtime, and the existing observability (the `doc loader: turn start —` log line we read in this morning's debug) starts showing populated IDs for A2A turns.

#### 4. Auth on file bytes — **peer-trusted at v1; MIME validation only**

The A2A invocation surface is auth-gated by `A2AAuthMiddleware` (shipped in M2 of the message/send sprint). Once a peer is past the gate, they're treated as trusted for the purposes of file content. The bridge enforces:

| Check | Enforced at | Action on fail |
| --- | --- | --- |
| MIME type in allowlist | A2aFileExtractingExecutor on receive | Reject the FilePart; surface in JSON-RPC error envelope |
| Size <= 25 MB per file | A2aFileExtractingExecutor on receive | Reject; surface in error envelope |
| Total request <= 32 MB (Cloud Run limit) | Cloud Run pre-routing | 413 status, no body |
| No URI-bytes shenanigans (no `file:///` URIs) | URI scheme allowlist on FileWithUri | Reject; only `https://`, `gs://` allowed |

No content scanning at v1 (no ClamAV, no LLM-based extraction-then-rescan). Content lands in ADK_ARTIFACT_BUCKET which is inside the GCP project (Axiom 9 privacy boundary holds). Forks that need stricter validation can subclass `A2aFileExtractingExecutor.validate_file_part`.

#### 5. Size limits — **25 MB per file, configurable; align with ADK_ARTIFACT_BUCKET defaults**

Inline bytes via `FileWithBytes` carries a base64 string — that's ~33% overhead, so a 25 MB file → ~33 MB base64 → over Cloud Run's 32 MB request limit. The effective limit:

- Per `FileWithBytes`: **25 MB** decoded (configurable via `A2A_FILE_MAX_BYTES`)
- Per `FileWithUri`: no size cap at the FilePart level (the URI fetcher applies its own limit when actually loading)
- Total request size: **32 MB** (enforced by Cloud Run, not by us)

The 25 MB default matches ailang-parse's documented sweet spot for sync extraction. Forks running large-document workloads can:
- Raise `A2A_FILE_MAX_BYTES` (and accept the Cloud Run 32 MB ceiling)
- Or instruct peers to send `FileWithUri` referencing a GCS object (no inline cap)

#### 6. Back-compat for text-only invocations — **strictly additive**

Every existing test in `test_a2a_invocation.py` must still pass with the new executor. The implementation:

- Subclass `A2aAgentExecutor` rather than wholesale replacing
- If the incoming message has no FilePart, the new code path is a no-op (`if not file_parts: return await super().execute(...)`)
- All existing test fixtures (text-only POSTs) continue to exercise the unchanged path
- Card field changes (`defaultInputModes`) are additive — `"text"` stays first in the list

#### 7. Org-scoped bucket — config carried on the **agent registration**, surfaced as a **bucket-backed tool**

The org-scoped bucket is associated with the **A2A agent registration**, not with the deploy. A single deployed binary may be registered to multiple Gemini Enterprise apps (one per tenant), each with its own bucket. The card itself stays generic — bucket binding lives at the registration record level.

| Option | Where the bucket is configured | Tenant isolation | Pick |
| --- | --- | --- | --- |
| **Per-registration via Discovery Engine record** + agent reads the binding on each turn | `agent_record.metadata.gcs_documents_bucket` (custom metadata field, PATCHed at registration) | Per-registration (1 bucket per agent ID); peer's calling agent ID is in the request context | ✓ |
| Per-deploy env var (`A2A_AGENT_DOCUMENT_BUCKET`) | `cloudbuild.yaml` | None (one bucket per deploy across all tenants) — leaks data | ✗ |
| Per-skill metadata in `SKILL.md` | `metadata.gcs_documents_bucket` in the skill | One bucket per skill regardless of caller — same leak | ✗ |
| Per-user via Firebase claims | User JWT | Works for AG-UI; A2A peers don't carry Firebase identity | ✗ |

→ **Per-registration via Discovery Engine custom metadata**. At registration time, the operator can pass a bucket binding via a new CLI flag (`--documents-bucket gs://acme-orgX-docs/`); the agents-cli PATCHes that into the agent record's metadata. At turn time, the orchestrator's `before_agent_callback` reads the calling agent's registration metadata, scopes any document-listing tool calls to that bucket. Buckets are addressed by full `gs://bucket-name/optional-prefix/` so a single shared bucket can serve multiple agents via path prefix isolation.

Implementation pieces:
- New module `backend/protocols/a2a_org_bucket.py` exporting:
  - `get_bound_bucket(agent_resource_name: str) -> str | None` — looks up the registration record's `metadata.gcs_documents_bucket`
  - `list_documents_in_bucket(bucket: str, prefix: str = "") -> list[dict]` — returns metadata for objects (name, size, mimeType, time_created)
  - `read_document_from_bucket(bucket: str, name: str) -> dict` — fetches + parses via ailang-parse, returns the same doc-block JSON the AG-UI loader produces
- Two new ADK `FunctionTool`s exposed on `ap-orchestrator`'s tool list:
  - `list_org_documents(prefix: Optional[str]) -> list[dict]` — bucket-scoped to the registration; empty list if no binding
  - `read_org_document(name: str) -> dict` — reads a named doc into the same `doc:{id}.json` artifact shape; the existing doc-loader and citation rendering work on it without modification

The orchestrator's instruction body gains one paragraph: "If the user asks about existing organizational data (vendor history, past invoices, policies), use `list_org_documents` to find candidates and `read_org_document` to load the one you need before answering. If `list_org_documents` returns empty, answer from text context only."

#### 8. Tenant isolation for the org-scoped bucket — **defence in depth via three independent checks**

A single deploy serving multiple tenants must guarantee that peer A's registration cannot read peer B's bucket. Three checks all have to fail before a leak happens:

1. **Registration metadata** — only the bucket bound to the calling agent_resource_name is consulted; the lookup is keyed on the agent record, not free-form user input. Bypassing this means tampering with the calling agent's identity inside Discovery Engine.
2. **GCS IAM** — the Cloud Run service account is granted `roles/storage.objectViewer` on each bound bucket explicitly; no wildcard grants. If an operator misconfigures the binding to point at a bucket the SA can't read, the tool returns `[]` rather than 500 — but it also can't read it.
3. **Skill-level guard** — `list_org_documents`'s before_tool_callback verifies the bucket arg matches the registration's bound bucket. Refuses any call where the bucket doesn't match.

The defence-in-depth is overkill for v1's two-registration scope but is the natural shape for forks that scale to dozens of tenant registrations on one deploy. Document the IAM grant pattern in the deployment guide.

### Backend Changes

**New file** — `backend/protocols/a2a_file_extraction.py` (~120 LOC) — Scenario A:
- `A2aFileExtractingExecutor(A2aAgentExecutor)` — subclass with file-extraction logic
- `_upload_inline_bytes(part: FilePart) -> str` — base64-decode → write `doc:{id}.json` artifact → return document_id
- `_register_uri(part: FilePart) -> str` — register URI under a doc registry key → return document_id
- `_validate_file_part(part: FilePart) -> Optional[str]` — MIME + size + URI-scheme checks; returns error message if invalid, None if OK
- `_inject_document_ids(context, new_ids: list[str]) -> None` — write to session state preserving existing list

**New file** — `backend/protocols/a2a_org_bucket.py` (~100 LOC) — Scenario B:
- `get_bound_bucket(agent_resource_name: str) -> str | None` — fetch the registration record from Discovery Engine, read `metadata.gcs_documents_bucket`. 60s LRU cache keyed by agent_resource_name (same TTL as the discovery card cache).
- `list_documents_in_bucket(bucket_uri: str, prefix: str = "") -> list[dict]` — GCS LIST against the bound bucket; returns object metadata (name, size, mimeType, time_created)
- `read_document_from_bucket(bucket_uri: str, name: str) -> str` — fetch object → parse via ailang-parse → write `doc:{id}.json` artifact → return document_id
- `_assert_bucket_matches_registration(bucket_uri: str, agent_resource_name: str)` — the skill-level guard called by both functions

**New file** — `backend/tools/org_documents.py` (~50 LOC) — the ADK FunctionTool wrappers:
- `list_org_documents(prefix: Optional[str]) -> list[dict]` — wraps `list_documents_in_bucket` with the calling agent's binding lookup
- `read_org_document(name: str) -> dict` — wraps `read_document_from_bucket`; minted document_id is appended to `state["document_ids"]` so the existing loader picks up the artifact

**Modified** — `backend/protocols/a2a_invocation.py`:
- Swap `A2aAgentExecutor(runner=runner)` → `A2aFileExtractingExecutor(runner=runner)` (~3 LOC delta)
- No other change to the mount; the auth middleware, the card, the lifespan workaround all still work

**Modified** — `backend/protocols/a2a.py`:
- Extend `_build_card_dict`'s `defaultInputModes` from `["text"]` to the document-MIME list (with `A2A_AGENT_INPUT_MIME_TYPES` env override)
- Add the same expansion to `defaultOutputModes`? **No** — output is still `["text"]` (per Non-Goals: no file response from agent in v1)

**Modified** — `backend/skills/templates/ap-orchestrator/SKILL.md`:
- Add `list_org_documents` and `read_org_document` to the `tools:` list
- Add a short instruction paragraph: "When the user asks about existing organizational data, first try `list_org_documents` to discover what's available before deciding to extract from peer-supplied uploads."

**New test** — `backend/tests/api_tests/test_a2a_file_input.py` (~250 LOC) — Scenario A:
- `test_a2a_file_with_bytes_extracted_to_document_id` — POST with embedded base64 invoice; assert session state gets a document_id and the artifact bucket gains a `doc:{id}.json` blob
- `test_a2a_file_with_uri_registered` — POST with a `FileWithUri`; assert document_id minted; URI fetched lazily by the loader
- `test_a2a_oversized_file_rejected_with_jsonrpc_error` — POST with a 26 MB FileWithBytes; assert JSON-RPC error envelope with size message
- `test_a2a_unknown_mime_rejected` — POST with `application/x-evil`; assert rejection
- `test_a2a_file_uri_with_disallowed_scheme_rejected` — POST with `file:///etc/passwd`; assert rejection
- `test_a2a_text_only_still_works` — regression guard: existing text-only test patterns still pass through the new executor

**New test** — `backend/tests/api_tests/test_a2a_org_bucket.py` (~200 LOC) — Scenario B:
- `test_list_org_documents_returns_objects_from_bound_bucket` — fixture binds an agent to a fake bucket; assert list returns the expected objects
- `test_list_org_documents_empty_when_no_binding` — unbound agent gets `[]` and no error
- `test_read_org_document_loads_into_artifact` — `read_org_document(name)` produces a `doc:{id}.json` artifact and appends to `state["document_ids"]`
- `test_org_bucket_lookup_is_cached_per_agent_resource_name` — repeated calls within 60s don't hit Discovery Engine twice
- `test_cross_tenant_bucket_access_denied` — agent A bound to bucket X cannot read bucket Y even if name is leaked; `_assert_bucket_matches_registration` raises
- `test_missing_bucket_iam_returns_empty_not_500` — bound bucket exists but SA lacks read perms; list returns `[]` with a logged warning, not a 500

**Modified** — `scripts/simulate-a2a-peer.py`:
- Add a Step 7 (Scenario A) that base64-encodes `infrastructure/demo-invoices/acme-gmbh-invoice-2026-042.docx` and POSTs it as a FilePart; assert the response Task contains a real validation outcome (not the "I'd need to see the document" fallback)
- Add a Step 8 (Scenario B) that POSTs a text-only message asking about a known existing document in the demo bucket; assert the response references the document's content (proving `list_org_documents` + `read_org_document` fired)

**Modified** — `scripts/verify-a2a.sh`:
- Extend the invocation probe to assert `defaultInputModes` includes at least one non-text MIME type
- Add a "FilePart accepted" probe that sends a tiny base64 string with `mimeType: text/plain` and asserts the agent acknowledges file context (not full upload; just shape verification)
- Optionally probe `list_org_documents` directly via a tool-call payload if the deploy advertises a bound bucket — skip cleanly when no binding is configured

### CLI Surface

The platform's `aiplatform` CLI is the developer-facing test harness for A2A invocations. Currently `aiplatform` has `auth`, `skills`, etc. but no A2A-specific subcommand. **Add one in this sprint** so future forks don't have to curl JSON-RPC by hand:

```bash
# Probe an A2A endpoint with a text message — proxy for the existing simulate-a2a-peer.py
aiplatform a2a invoke <url> --text "Process this invoice..."

# Drop a file (Scenario A) — base64-encodes locally + POSTs as FilePart
aiplatform a2a invoke <url> --file infrastructure/demo-invoices/acme-gmbh-invoice-2026-042.docx

# Both at once
aiplatform a2a invoke <url> --text "Look at this" --file invoice.docx

# Inspect the org bucket binding (Scenario B) — what does this registration see?
aiplatform a2a bucket show <agent-resource-name>

# Bind a bucket at registration time (or after)
aiplatform a2a bucket bind <agent-resource-name> --bucket gs://orgX-documents/

# JSON output for scripting
aiplatform a2a invoke <url> --file invoice.docx --json
```

~0.35 day for both `invoke` and `bucket` subcommands + httpx calls + unit tests mocking the POST/PATCH. Slots under `aiplatform a2a` for future expansion (e.g., `a2a register`, `a2a list-skills`).

### API Changes

| Method | Endpoint | Description | Breaking? |
|--------|----------|-------------|-----------|
| GET    | `/.well-known/agent.json` | `defaultInputModes` extended from `["text"]` to include document MIMEs | **No** — additive; peers ignoring unknown entries (none would, but spec-compliant ones don't reject) |
| POST   | `/a2a` (and `/a2a/`) | Now extracts `FilePart`s from `message.parts[]`; rest of behavior unchanged | **No** — additive |

The Discovery Engine validator may re-flag the card after the MIME-list expansion (new entries to schema-validate). Plan to re-register with Gemini Enterprise after deploy to verify.

### Architecture

```
Peer agent (Gemini Enterprise, A2A peer, etc.)
   │
   │ POST /a2a {parts: [TextPart, FilePart(bytes=base64 invoice)]}
   ▼
[Next.js rewrite at /a2a/* → 127.0.0.1:1956]
   ▼
[FastAPI /a2a mount → A2AAuthMiddleware → A2AStarletteApplication]
   ▼
[A2aFileExtractingExecutor]
   │
   │ 1. Walk parts; pull FileParts out
   │ 2. For each FilePart:
   │      - validate (MIME, size, URI scheme)
   │      - bytes  → base64-decode → save artifact doc:{id}.json
   │      - uri    → register under doc_id in URI registry
   │      - mint document_id
   │ 3. Write document_ids to session state
   │ 4. Rewrite message.parts to drop FileParts
   ▼
[super().execute() → ADK Runner with the cleaned message]
   ▼
[before_agent_callback chain]
   │ — make_document_loader reads state["document_ids"] (the existing path)
   │ — load_artifacts_tool injects doc content into the model
   ▼
[ap-orchestrator → ap-pipeline → Extract → Validate → Post]
   ▼
[A2A response: Task with text artifacts back to peer]
```

## Implementation Plan

### Phase 1 — Scenario A: file extraction (~0.35 day)
- [ ] Verify ADK's `A2aAgentExecutor.execute` signature against the installed package (~5 min introspection)
- [ ] Create `backend/protocols/a2a_file_extraction.py` with the executor subclass (~120 LOC)
- [ ] Swap the executor in `backend/protocols/a2a_invocation.py` (~3 LOC)
- [ ] Extend `_build_card_dict` `defaultInputModes` + env override (~10 LOC + 1 test update)
- [ ] `backend/tests/api_tests/test_a2a_file_input.py` — 6 tests (~250 LOC)
- [ ] Smoke-test locally: `curl -X POST localhost:1956/a2a/ -d '{...FilePart with base64...}'` returns Task with the doc context observed by the agent

### Phase 2 — Scenario B: org-scoped bucket (~0.35 day)
- [ ] Create `backend/protocols/a2a_org_bucket.py` (~100 LOC): bucket lookup + LIST/READ + tenant-isolation guard
- [ ] Create `backend/tools/org_documents.py` (~50 LOC): the two FunctionTool wrappers
- [ ] Add `list_org_documents` + `read_org_document` to `ap-orchestrator/SKILL.md`'s tools list (~5 LOC + instruction paragraph)
- [ ] `backend/tests/api_tests/test_a2a_org_bucket.py` — 6 tests (~200 LOC)
- [ ] PATCH the agent registration record on dev with `metadata.gcs_documents_bucket = gs://gde-ap-agent-demo-invoices/` so the dev deploy has a binding to test against
- [ ] All ~12 new tests green; existing 19 a2a tests still pass; `make lint` + `make test-fast` clean

### Phase 3 — Probe + CLI + deploy + verify (~0.3 day)
- [ ] Extend `scripts/simulate-a2a-peer.py` with Step 7 (Scenario A) + Step 8 (Scenario B) — ~60 LOC delta
- [ ] Extend `scripts/verify-a2a.sh` for both scenarios (~30 LOC delta)
- [ ] Add `aiplatform a2a invoke <url> --file <path>` subcommand (~80 LOC)
- [ ] Add `aiplatform a2a bucket bind/show` subcommands (~50 LOC)
- [ ] Deploy to dev; re-run probes against the live deploy
- [ ] Re-register with Gemini Enterprise so the new `defaultInputModes` propagates
- [ ] Trigger a real file upload via Gemini Enterprise console; confirm via Cloud Run logs that the doc-loader sees a populated `document_ids` (Scenario A)
- [ ] Ask Gemini Enterprise a question about an existing demo invoice in `gs://gde-ap-agent-demo-invoices/` without uploading anything; confirm the agent finds it via `list_org_documents` and answers (Scenario B)
- [ ] Update [`docs/learnings/template-pr-a2a-spec-compliance.md`](../../../learnings/template-pr-a2a-spec-compliance.md) with §6 covering both modes for upstream forks

## Migration & Rollout

**Feature flag:**
- New env var `ENABLE_A2A_FILE_INPUT` (default `false`). When false, the executor falls back to the M1 base behavior — file parts are silently dropped, exactly the same outcome as today. When true, the file-extraction path activates.
- Set to `true` in `cloudbuild.yaml` for dev once test suite is green. Promote to prod with the standard branch-deploy pattern.

**Rollback Plan:**
- Single-line env var flip `ENABLE_A2A_FILE_INPUT=false` + redeploy → executor falls back to text-only A2A. The auth middleware, card, and existing text invocations stay unaffected.
- If the card's expanded `defaultInputModes` causes a peer to reject the card (unlikely — additive), `A2A_AGENT_INPUT_MIME_TYPES=text` env override restores the v1 shape.

**Environment Variables:**
- `ENABLE_A2A_FILE_INPUT` — `true` to extract file parts (Scenario A), `false` to skip. Default false.
- `ENABLE_A2A_ORG_BUCKET` — `true` to expose `list_org_documents` / `read_org_document` tools (Scenario B), `false` to skip. Default false.
- `A2A_AGENT_INPUT_MIME_TYPES` — comma-separated MIME list for `defaultInputModes`. Default: the canonical doc-format list (see §1 above).
- `A2A_FILE_MAX_BYTES` — per-file decoded byte limit. Default `26214400` (25 MB).
- No new secrets. The IAM grant on each bound bucket is set per-bucket via `gcloud storage buckets add-iam-policy-binding` and is **not** carried as an env var (no wildcard bucket access).

**Re-registration with Gemini Enterprise:**
- After deploy, `agents-cli register-gemini-enterprise` to propagate the new card.
- Friction 28 caveat from the message/send sprint applies — manually delete the pre-file-input agent record and PATCH the new icon.uri (the well-known curl recipes in the template-PR brief still apply).

## Testing Strategy

### Backend Tests (pytest)
- [ ] `test_a2a_file_input.py` — 6 new tests
- [ ] `test_a2a.py` updated for new `defaultInputModes` shape
- [ ] `test_a2a_invocation.py` — all 6 existing tests still pass (regression guard for back-compat)
- [ ] `make test-fast` green; specifically the doc-loader unit tests in `test_session_callbacks.py` still pass — the loader path is unchanged

### Integration Tests
- [ ] `scripts/verify-a2a.sh` Step 7 (file accepted) against live deploy
- [ ] `scripts/simulate-a2a-peer.py` Step 7 against live deploy — assert the orchestrator's response shows real invoice processing not a fallback

### Manual Testing
- [ ] Drop the canonical demo invoice (`acme-gmbh-invoice-2026-042.docx`) via the Gemini Enterprise workspace UI; confirm the agent answers with extracted fields + verdict
- [ ] Drop an oversized file (>25 MB) via Gemini Enterprise; confirm rejection produces a user-visible error in the workspace UI rather than a silent fallback
- [ ] Drop an unknown MIME (e.g. raw `.bin`); confirm rejection
- [ ] Send a `FileWithUri` pointing at a public HTTPS-hosted invoice; confirm the agent fetches and processes it

## Security Considerations

- **Trust boundary** (Axiom 9): file bytes from peer agents land directly in ADK_ARTIFACT_BUCKET inside the GCP project. No third-party egress; same trust posture as AG-UI uploads.
- **MIME validation**: enforced server-side regardless of `Content-Type` headers. Peer-claimed `mimeType` on `FileWithBytes` is treated as advisory; the loader will re-detect from the bytes.
- **URI scheme allowlist**: `FileWithUri.uri` must be `https://` or `gs://`. Reject `file://`, `data:`, etc. to prevent local-file-read or in-memory-bomb attacks.
- **Size limits**: 25 MB per file (configurable); 32 MB total request enforced by Cloud Run.
- **No content scanning at v1**: forks needing virus scan can subclass `validate_file_part` to inject ClamAV / Cloud DLP. Documented as a fork extension point.
- **Auth**: unchanged from the M2 middleware — `A2A_INVOCATION_REQUIRE_AUTH` gates all of `/a2a/*` except the well-known card.

## Performance Considerations

- **Latency overhead per file**: base64 decode + GCS write (~100ms for a typical invoice). Comparable to AG-UI upload path.
- **Memory**: peer-supplied file bytes held in memory transiently during decode + upload. Worst case 25 MB per file; with the 32 MB total cap, a peer cannot OOM the service via this path.
- **Streaming throughput**: A2A `message/sendSubscribe` continues to stream Task updates as before; file extraction adds a one-time per-turn cost not a per-event one.
- **No cache**: each turn re-uploads the same file if the peer keeps sending it. Forks needing dedupe can hash on receive and reuse existing document_ids. Out of scope for v1.

## Success Criteria

Scenario A:
- [ ] All backend tests passing (`cd backend && make test-fast`)
- [ ] Lint + format clean (`cd backend && make lint`)
- [ ] `scripts/simulate-a2a-peer.py` Step 7 returns a Task whose text mentions extracted invoice fields (vendor, total, PO match) — not a fallback message
- [ ] A real Gemini Enterprise file upload completes — Cloud Run logs show `doc loader: turn start — document_ids=['<minted-id>']` instead of `document_ids=[]`
- [ ] `agents-cli register-gemini-enterprise` re-registration succeeds with the new `defaultInputModes`

Scenario B:
- [ ] `scripts/simulate-a2a-peer.py` Step 8 returns a Task whose text references real content from the bound bucket's demo invoices
- [ ] PATCHing `metadata.gcs_documents_bucket` onto the dev agent record makes the binding take effect within the 60s cache window
- [ ] A peer asking the agent (via Gemini Enterprise) "what invoices do we have from Acme?" gets back a list referencing real bucket contents, no upload needed
- [ ] Tenant isolation manual check: bind two agent records on the same deploy to different buckets; confirm each can only see its own

Both:
- [ ] CLI commands `aiplatform a2a invoke ... --file ...` and `aiplatform a2a bucket bind/show ...` work end-to-end against the live deploy
- [ ] `docs/learnings/template-pr-a2a-spec-compliance.md` gains §6 covering both modes for upstream forks
- [ ] No regression in the existing A2A text-only path (every existing test still green; manual probe still works)

## Open Questions

- **ADK `A2aAgentExecutor.execute` signature** — needs introspection to confirm the `context` object's mutability around `message.parts`. If parts are frozen, the executor rewrites become a clone-and-replace pattern rather than mutate-in-place. M1 of the sprint resolves.
- **GE file-upload conversion behaviour** — does Gemini Enterprise actually emit `FileWithBytes` or does it convert uploads to GCS URIs internally and send `FileWithUri`? We'll know from Cloud Run logs once the bridge is live. Both paths are designed for; the question is which fires in practice.
- **Multi-tenant doc registry** — if peer A's upload mints document_id `abc` and peer B then sends a `FileWithUri` referencing the same id, do they share state? Today AG-UI scopes doc IDs per session — A2A inherits the same scope because document_ids live on the session. Verify via test.
- **Output modes vs spec** — A2A spec lets `defaultOutputModes` advertise non-text formats. Today we send text artifacts. Should we add `application/json` to indicate the structured payloads we sometimes emit? Probably yes in a follow-up; not in scope for v1.

## Related Documents

- [A2A `message/send` bridge (implemented)](./implemented/a2a-message-send-bridge.md) — the M1+M2+M3 sprint this extends
- [A2A `message/send` bridge sprint plan](./implemented/a2a-message-send-bridge-sprint.md)
- [Template-PR brief — A2A spec compliance](../../../learnings/template-pr-a2a-spec-compliance.md) — the upstream PR brief this design folds into as §6 after implementation
- [Gemini Enterprise + A2UI Alignment](./gemini-enterprise-a2ui-alignment.md)
- ADK source verified during design: `google.adk.a2a.executor.a2a_agent_executor.A2aAgentExecutor`, `google.adk.a2a.converters.request_converter` (the path we override)
- a2a-sdk verified during design: `a2a.types.FilePart`, `FileWithBytes`, `FileWithUri`, `DataPart`
- A2A v0.2 spec: <https://a2aproject.github.io/A2A/v0.2>
- Existing doc-loader pipeline: `backend/adk/callbacks.py:make_document_loader` — the integration target
