# Sprint Plan: A2A-FILES — Inbound files + org-scoped buckets

## Summary

Two coupled scenarios. **Scenario A**: peer agents (Gemini Enterprise especially) can attach files to A2A `message/send` via `FilePart` — we extract bytes/URIs, upload to ADK_ARTIFACT_BUCKET, mint a `document_id`, and the existing `make_document_loader` callback picks it up. **Scenario B**: each A2A agent registration is bound to a GCS bucket (via Discovery Engine `metadata.gcs_documents_bucket`) and exposes `list_org_documents` / `read_org_document` tools so peers can ask about existing org-scoped documents without uploading anything.

**Duration:** ~1.0 day (~6–8 h wall clock with breathing room)
**Scope:** Backend
**Dependencies:**
- A2A `message/send` bridge implemented in A2A-INVOKE sprint (commits abe9bc9 / 0b2d59e / 5774cb0)
- `a2a-sdk` `FilePart` / `FileWithBytes` / `FileWithUri` schemas verified during design
- `google-adk` `A2aAgentExecutor` + `ExecuteInterceptor` config surface verified during design
- ADK_ARTIFACT_BUCKET already provisioned (production-shared with AG-UI)
**Risk Level:** Medium — Scenario B touches Discovery Engine metadata PATCH (non-standard field) + cross-tenant isolation tests
**Design Doc:** [a2a-file-input.md](./a2a-file-input.md)

## Current Status Analysis

### Recent Velocity (last 2 days)

- 31 commits / 2 days = ~15 commits/day
- 3,902 LOC delta across 31 files
- Whole A2A-INVOKE sprint shipped end-to-end in this window — domain familiarity is high
- Estimated capacity for this sprint: ~750–900 LOC (matches design estimates with the +30% buffer A2A-INVOKE actually consumed)

### Design Change Discovered During Planning — Use ADK's `ExecuteInterceptor` Instead of Subclassing

The design doc proposed subclassing `A2aAgentExecutor` (~120 LOC). Pre-planning verification of the installed ADK package revealed a cleaner extension point: `A2aAgentExecutorConfig.execute_interceptors: list[ExecuteInterceptor]` where `ExecuteInterceptor.before_agent: Callable[[RequestContext], Awaitable[RequestContext]]` is a first-class hook.

→ M1 ships an interceptor (~80 LOC) instead of a subclass. Lower risk on ADK minor bumps; same observable behavior. Design doc and sprint plan reflect this; the design doc's Open Question #1 (executor.execute signature) is now resolved.

### Existing Implementation We Build On

- `backend/protocols/a2a.py` — discovery card (will gain expanded `defaultInputModes`)
- `backend/protocols/a2a_invocation.py` — A2A mount (gains interceptor registration via `A2aAgentExecutorConfig`)
- `backend/adk/callbacks.py` — `make_document_loader` reads `state["document_ids"]` (the **untouched** integration target)
- `backend/skills/templates/ap-orchestrator/SKILL.md` — gains 2 new tools + 1 instruction paragraph (Scenario B)
- ADK_ARTIFACT_BUCKET + Firestore-backed doc registry (production-shared with AG-UI; no new infrastructure)
- 19 passing tests in `test_a2a.py` + `test_a2a_invocation.py` — dense regression net for the bridge

## Proposed Milestones

### Milestone 1 (M1): Scenario A — File extraction via interceptor

**Scope:** backend
**Goal:** A2A `FilePart` (bytes or URI) extracted into `state["document_ids"]` before the runner starts; existing `make_document_loader` does the rest unchanged.
**Estimated:** ~80 LOC interceptor + ~120 LOC validation/upload helpers + ~250 LOC tests = ~450 LOC
**Duration:** ~2.5 hours

**Tasks:**
- [ ] Verify `ExecuteInterceptor.before_agent` signature one more time pre-keyboard (~5 min)
- [ ] Create `backend/protocols/a2a_file_extraction.py` (~200 LOC):
  - [ ] `FileExtractionInterceptor` — a factory returning an `ExecuteInterceptor` with `before_agent` set
  - [ ] `_extract_file_parts(context: RequestContext) -> list[Part]` — walk `context.message.parts`, return only `FilePart`s; needed to know what to strip and what to inject
  - [ ] `_upload_inline_bytes(part: FilePart, *, mime_allowlist, size_limit) -> str` — base64-decode, validate, write `doc:{id}.json` artifact, return document_id
  - [ ] `_register_uri(part: FilePart, *, scheme_allowlist) -> str` — register URI under doc_id, return document_id
  - [ ] `_inject_document_ids_into_state(context, ids: list[str])` — write to session state, preserving existing list
  - [ ] `_validate_file_part(part) -> Optional[str]` — MIME/size/URI-scheme checks; returns error message or None
- [ ] Wire into `backend/protocols/a2a_invocation.py` (~10 LOC): construct `A2aAgentExecutorConfig(execute_interceptors=[FileExtractionInterceptor()])`; pass into `A2aAgentExecutor`
- [ ] Extend `_build_card_dict` `defaultInputModes` from `["text"]` to the document-MIME list, with `A2A_AGENT_INPUT_MIME_TYPES` env override (~15 LOC + 1 existing test update)
- [ ] `backend/tests/api_tests/test_a2a_file_input.py` — 6 tests (~250 LOC):
  - [ ] `test_a2a_file_with_bytes_extracted_to_document_id` — POST with embedded base64; assert state gets document_id + artifact bucket has the blob
  - [ ] `test_a2a_file_with_uri_registered` — POST with FileWithUri; assert document_id minted; URI fetched lazily by the loader
  - [ ] `test_a2a_oversized_file_rejected_with_jsonrpc_error` — 26MB FileWithBytes → JSON-RPC error envelope
  - [ ] `test_a2a_unknown_mime_rejected` — `application/x-evil` → rejection
  - [ ] `test_a2a_file_uri_with_disallowed_scheme_rejected` — `file:///etc/passwd` → rejection
  - [ ] `test_a2a_text_only_still_works` — regression guard via the existing FastAPI mount integration test pattern from M2 of A2A-INVOKE
- [ ] Local smoke: `curl -X POST localhost:1956/a2a/ -d '{...FilePart with base64 of demo invoice...}'` → Task with doc context

**Files:**
- `backend/protocols/a2a_file_extraction.py` (new, ~200 LOC)
- `backend/protocols/a2a_invocation.py` (modify, ~10 LOC delta)
- `backend/protocols/a2a.py` (modify, ~15 LOC delta in `_build_card_dict`)
- `backend/tests/api_tests/test_a2a_file_input.py` (new, ~250 LOC)
- `backend/tests/api_tests/test_a2a.py` (modify, ~5 LOC delta for `defaultInputModes`)
- `backend/tests/api_tests/test_a2a_invocation.py` (modify, ~5 LOC delta if any URL/card-shape assertion drifts)

**Acceptance Criteria:**
- [ ] All 6 new tests pass; 19 existing a2a tests still pass; lint + format clean
- [ ] Local curl smoke returns 200 with a Task envelope; logs show `doc loader: turn start — document_ids=['<minted-id>']`
- [ ] Card body advertises at least `application/pdf` + `application/vnd.openxmlformats-officedocument.wordprocessingml.document` in `defaultInputModes`
- [ ] Text-only A2A invocations work identically to today (regression-free)

**Risks:**
- ADK `RequestContext.message` may be a frozen pydantic model; the interceptor would need to clone-and-replace rather than mutate. Mitigation: cover both patterns in the implementation; test asserts the post-interceptor parts list is shorter than the original.
- `FilePart.metadata` shape might differ from what `FileWithBytes` / `FileWithUri` declare. Mitigation: design treats metadata as opaque; we only read `file.bytes` / `file.uri` / `file.mimeType` / `file.name`.
- Cloud Run 32MB request ceiling could clip large base64 uploads. Mitigation: explicit 25MB-decoded limit returns a JSON-RPC error from our middleware *before* Cloud Run terminates the connection.

### Milestone 2 (M2): Scenario B — Org-scoped bucket via registration metadata

**Scope:** backend
**Goal:** Each agent registration carries a `metadata.gcs_documents_bucket`; orchestrator exposes `list_org_documents` and `read_org_document` tools scoped to the calling registration's bound bucket.
**Estimated:** ~100 LOC bucket helpers + ~50 LOC FunctionTool wrappers + ~30 LOC SKILL.md + ~200 LOC tests = ~380 LOC
**Duration:** ~2.5 hours

**Tasks:**
- [ ] Confirm Discovery Engine accepts a top-level `metadata` field on the agent record (curl PATCH + GET; if it doesn't, fall back to a `description`-encoded JSON marker — design doc to be amended) (~5 min)
- [ ] Create `backend/protocols/a2a_org_bucket.py` (~100 LOC):
  - [ ] `get_bound_bucket(agent_resource_name: str) -> str | None` — Discovery Engine GET on the agent record, read `metadata.gcs_documents_bucket`. 60s LRU cache (same TTL as the card cache).
  - [ ] `list_documents_in_bucket(bucket_uri: str, prefix: str = "") -> list[dict]` — GCS LIST against the bound bucket; return name/size/mimeType/timeCreated
  - [ ] `read_document_from_bucket(bucket_uri: str, name: str) -> str` — GCS GET → ailang-parse → write `doc:{id}.json` artifact → return document_id
  - [ ] `_assert_bucket_matches_registration(bucket_uri: str, agent_resource_name: str)` — skill-level guard
- [ ] Create `backend/tools/org_documents.py` (~50 LOC):
  - [ ] `list_org_documents(prefix: Optional[str] = None, tool_context: ToolContext) -> list[dict]` — look up calling agent's binding via `tool_context`; call `list_documents_in_bucket`; return `[]` on no binding (graceful degradation)
  - [ ] `read_org_document(name: str, tool_context: ToolContext) -> dict` — same binding lookup; call `read_document_from_bucket`; append minted document_id to `state["document_ids"]`
- [ ] Add both tools to `backend/skills/templates/ap-orchestrator/SKILL.md` `tools:` list (~5 LOC delta)
- [ ] Add a short instruction paragraph to the orchestrator's prompt body (~5 LOC delta)
- [ ] `backend/tests/api_tests/test_a2a_org_bucket.py` — 6 tests (~200 LOC):
  - [ ] `test_list_org_documents_returns_objects_from_bound_bucket` — fixture binds an agent to a fake bucket; assert list returns expected objects
  - [ ] `test_list_org_documents_empty_when_no_binding` — unbound → `[]`, no error
  - [ ] `test_read_org_document_loads_into_artifact` — `read_org_document(name)` produces `doc:{id}.json` + appends to `state["document_ids"]`
  - [ ] `test_org_bucket_lookup_is_cached_per_agent_resource_name` — repeated calls within 60s don't hit Discovery Engine twice
  - [ ] `test_cross_tenant_bucket_access_denied` — agent A bound to bucket X cannot read bucket Y even if name is leaked; `_assert_bucket_matches_registration` raises
  - [ ] `test_missing_bucket_iam_returns_empty_not_500` — bound bucket exists but SA lacks read perms; list returns `[]` with logged warning, not 500
- [ ] PATCH the live dev agent record (the working one in `multivac-internal-dev` from A2A-INVOKE) with `metadata.gcs_documents_bucket = gs://gde-ap-agent-demo-invoices/`; verify GET returns it (~5 min)

**Files:**
- `backend/protocols/a2a_org_bucket.py` (new, ~100 LOC)
- `backend/tools/org_documents.py` (new, ~50 LOC)
- `backend/skills/templates/ap-orchestrator/SKILL.md` (modify, ~10 LOC delta)
- `backend/tests/api_tests/test_a2a_org_bucket.py` (new, ~200 LOC)

**Acceptance Criteria:**
- [ ] All 6 new bucket tests pass; 19 existing a2a tests still pass; 6 file-input tests from M1 still pass
- [ ] `list_org_documents` returns `[]` when called on an unbound registration; doesn't 500
- [ ] Cross-tenant isolation test verifies that agent A's bound bucket is the only one its tool calls can read
- [ ] Lint + format clean

**Risks:**
- **Discovery Engine custom metadata field acceptance** — the design doc assumes `metadata.gcs_documents_bucket` is allowed. If the Discovery Engine schema rejects custom fields, fall back to encoding the binding in `agent.description` (e.g., a trailing `<binding gs://...>` marker) — ugly but works. Mitigation: 5-minute pre-flight curl at the top of M2.
- **Tool context not carrying `agent_resource_name`** — ADK tool callbacks receive `tool_context` which has session metadata but might not have the A2A registration ID. Mitigation: the M1 interceptor also stashes `agent_resource_name` into `state["a2a:agent_resource_name"]`; the tool reads from there.
- **Cross-tenant fixture complexity** — needs two simultaneous registrations in test fixtures. Mitigation: use `monkeypatch` to stub `get_bound_bucket` returning different values per agent_resource_name; no real Discovery Engine calls in unit tests.
- **`list_org_documents` returning thousands of objects** — pagination not in v1. Mitigation: hard cap of 100 objects (configurable via `A2A_ORG_BUCKET_LIST_LIMIT` env var); document the cap in the tool's docstring (so the orchestrator knows to use `prefix` for large buckets).

### Milestone 3 (M3): Probes + CLI + deploy + verify

**Scope:** backend + CLI + ops
**Goal:** Both scenarios verified end-to-end against live deploy; CLI ships for ergonomic testing; upstream brief gets §6.
**Estimated:** ~60 LOC probe extensions + ~130 LOC CLI + ~120 LOC brief additions = ~310 LOC
**Duration:** ~2.5 hours

**Tasks:**
- [ ] Extend `scripts/simulate-a2a-peer.py`:
  - [ ] Step 7 (Scenario A): base64-encode `infrastructure/demo-invoices/acme-gmbh-invoice-2026-042.docx`, POST as FilePart, assert Task contains extracted fields (~40 LOC delta)
  - [ ] Step 8 (Scenario B): POST text-only "what invoices do we have from Acme?" assert response references bucket contents (~20 LOC delta)
- [ ] Extend `scripts/verify-a2a.sh`:
  - [ ] Assert `defaultInputModes` contains at least one non-text MIME type (~5 LOC)
  - [ ] FilePart-accepted probe with a tiny base64 + `text/plain` (~15 LOC)
  - [ ] Optional bucket probe (skip cleanly if no binding) (~10 LOC)
- [ ] Add `aiplatform a2a invoke <url> --file <path>` Click subcommand (~80 LOC):
  - [ ] base64-encode locally; POST JSON-RPC; pretty-print Task or output `--json`
  - [ ] Unit test mocking the POST
- [ ] Add `aiplatform a2a bucket bind/show <agent-resource-name>` (~50 LOC):
  - [ ] `show` does a Discovery Engine GET and prints the metadata
  - [ ] `bind --bucket gs://...` does a PATCH with `metadata.gcs_documents_bucket`
  - [ ] Unit tests mocking both
- [ ] Push to dev; wait for Cloud Build to deploy
- [ ] PATCH the dev agent record's binding to `gs://gde-ap-agent-demo-invoices/`
- [ ] Re-run `verify-a2a.sh` + `simulate-a2a-peer.py` against live deploy; both green
- [ ] Re-register with Gemini Enterprise (so the expanded `defaultInputModes` propagates) — delete pre-update agent + PATCH new icon per Friction 28
- [ ] Manual GE test: upload `acme-gmbh-invoice-2026-042.docx` via Gemini Enterprise console; confirm Cloud Run logs show `doc loader: turn start — document_ids=['<minted-id>']`
- [ ] Manual GE test: ask "what invoices do we have from Acme?" without uploading; confirm response references real bucket content
- [ ] Update `docs/learnings/template-pr-a2a-spec-compliance.md` with §6 (Scenario A + Scenario B), ~120 LOC

**Files:**
- `scripts/simulate-a2a-peer.py` (modify, ~60 LOC delta)
- `scripts/verify-a2a.sh` (modify, ~30 LOC delta)
- `cli/aiplatform/a2a.py` (new, ~130 LOC)
- `cli/tests/test_a2a_cli.py` (new, ~80 LOC)
- `docs/learnings/template-pr-a2a-spec-compliance.md` (modify, ~120 LOC delta)
- `cloudbuild.yaml` (modify, set `ENABLE_A2A_FILE_INPUT=true` + `ENABLE_A2A_ORG_BUCKET=true`, ~3 LOC)

**Acceptance Criteria:**
- [ ] `simulate-a2a-peer.py` Steps 1-8 all green against live deploy
- [ ] `verify-a2a.sh` all green
- [ ] `aiplatform a2a invoke` CLI works end-to-end
- [ ] Real GE file upload propagates to the doc-loader (verified in logs)
- [ ] Real GE bucket-asking flow returns content-referencing response (verified manually)
- [ ] Template brief §6 written; ready to hand to upstream agent

**Risks:**
- **Cloud Build deploy timing** — usually 5-8 min; backgrounded watcher means no time loss but adds wall-clock. Mitigation: kick off deploy first thing in M3 to parallelize with CLI work.
- **`aiplatform a2a invoke` httpx streaming** — POST with a large file body might need explicit `httpx.Client(timeout=60)` to avoid premature disconnect. Mitigation: test with 5MB invoice first; bump timeout if needed.
- **GE manual tests rely on user intervention** — can't fully script. Mitigation: M3 success criteria explicitly call out which checks are "manual" so we're honest about coverage.

## Day-by-Day Breakdown

Single-day sprint, ~7-8 hours wall clock.

### Day 1 — A2A files + buckets

| Time | Block | Focus | Checkpoint |
| --- | --- | --- | --- |
| 0:00–2:30 | M1 | Interceptor + file extraction + 6 tests | Local curl smoke returns 200 with doc context observed |
| 2:30–5:00 | M2 | Org-bucket helpers + tools + SKILL.md + 6 tests | `make lint && make test-fast` green (31 a2a-area tests total) |
| 5:00–5:30 | M3 setup | Push, background deploy watcher, start CLI work | Deploy in flight; CLI subcommand stubs in place |
| 5:30–7:00 | M3 finish | CLI complete, brief §6 written, live probes green, re-register with GE | Both GE manual tests pass; sprint commit + finalize |

## Quality Gates

After M1:
```bash
cd backend && make lint
curl -X POST localhost:1956/a2a/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"file","file":{"bytes":"<base64-of-tiny-doc>","mimeType":"application/pdf","name":"test.pdf"}}],"messageId":"m1"}}}'
# expect: 200 + Task JSON; logs show doc_loader picked up the minted id
```

After M2:
```bash
cd backend && make lint && make test-fast
# expect: 31+ a2a tests green
```

After M3:
```bash
./scripts/verify-a2a.sh && python3 scripts/simulate-a2a-peer.py
# expect: both all-green; 8 simulate steps print ✓
```

## Sequencing Risks Called Out

1. **ADK `ExecuteInterceptor` API stability** — `@a2a_experimental` like the rest of `google.adk.a2a.*`. We verified the dataclass shape during planning. Mitigation: pin `google-adk` version; if a minor bump breaks the interceptor signature, the design still works with subclassing as the fallback (same logic, different attachment).

2. **Discovery Engine custom metadata field** — design assumes `metadata.gcs_documents_bucket` PATCHes cleanly. Need a 5-min curl pre-flight at the top of M2 to confirm. If rejected, fall back to encoding the binding in agent description (ugly; documented).

3. **`tool_context` carrying `agent_resource_name`** — M2's tools need to know which registration is calling them. ADK's `tool_context` carries session metadata but may not have A2A peer identity. Mitigation: M1's interceptor stashes `agent_resource_name` into `state["a2a:agent_resource_name"]`; M2's tools read from there.

4. **Cross-tenant isolation test fixture complexity** — needs two simultaneous registrations in test fixtures. Mitigation: monkeypatch `get_bound_bucket` per agent_resource_name; no real Discovery Engine calls in unit tests.

5. **Friction 28 strikes again on re-registration** — every re-register creates a new agent ID. Mitigation: M3 explicitly lists the manual delete + icon PATCH as part of the deploy step (same recipe as A2A-INVOKE M3).

6. **Card schema validation in Discovery Engine** — expanded `defaultInputModes` might re-flag the card. Mitigation: M3's re-registration step explicitly tests this; if rejection, env override `A2A_AGENT_INPUT_MIME_TYPES=text` restores the v1 shape.

7. **`list_org_documents` pagination** — buckets with thousands of objects. Mitigation: hard 100-object cap (configurable); document the cap in tool docstring so the model uses `prefix`.

## Validation of 1.0-day Estimate

Comparison against A2A-INVOKE sprint (most recent A2A-area work):
- A2A-INVOKE estimated 440 LOC, actual 680 LOC (+55%)
- A2A-FILES estimated ~1,140 LOC across all three milestones
- Recent commits average ~125 LOC/commit; this sprint is roughly 9-10 commits

Specific comparison to similar past work:
- M2 of A2A-INVOKE (auth middleware + 6 tests): ~200 LOC, ~1.5h actual → M1 here (interceptor + 6 tests) is similar shape at ~450 LOC, scaling to ~2.5h
- M3 of A2A-INVOKE (deploy + brief): ~320 LOC, ~1h actual → M3 here adds CLI (~130 LOC more) so ~2.5h

**Conservative buffer:** +30% for the `@a2a_experimental` interceptor risk + Discovery Engine custom metadata uncertainty = ~10h worst case. Still bounded in a single working day.
