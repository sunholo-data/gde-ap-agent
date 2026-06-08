# A2A AILANG-parse integration

**Status**: Planned
**Priority**: P1 (Medium) — closes the "outputs look raw" gap visible in the first live GE upload (2026-06-08); aligns the A2A file path with the SUBMISSION.md narrative ("AILANG Parse extracts deterministically")
**Estimated**: ~0.5 day (1 milestone)
**Scope**: Backend
**Dependencies**:
- [A2A file-input + org-scoped buckets (implemented)](./implemented/a2a-file-input.md) — M1 of A2A-FILES sprint
- `tools/documents/ailang_parse.py:_parse_file_sync` — existing parse helper (verified during design)
- DOCPARSE_API_KEY secret already wired in Cloud Run (used by the AG-UI upload path)
**Created**: 2026-06-08
**Last Updated**: 2026-06-08
**Upstream-bound**: Yes — every fork that wants peer-uploaded files to flow through their parse pipeline hits the same six questions. Doc folds into the template-PR brief as §7 after implementation.

## Problem Statement

The A2A file-input sprint shipped a working FilePart extraction interceptor: peer uploads a `.docx`, the interceptor saves the raw bytes wrapped in a JSON envelope as `doc:{id}.json` artifact, the doc-loader sees the populated `state["document_ids"]` and `app:docs_loaded`, and the agent picks up the artifact. This works end-to-end — verified against a real Gemini Enterprise upload at 2026-06-08T05:51 UTC (Acme GmbH invoice extracted correctly).

**But Gemini parsed the inline bytes via its native multimodal capability**, not via AILANG Parse. The artifact the model receives contains raw base64 inside a generic envelope:

```json
[{
  "kind": "a2a-inline-file",
  "displayName": "acme-gmbh-invoice-2026-042.docx",
  "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "bytesBase64": "UEsDBBQAAAAIA..."
}]
```

The AG-UI upload path produces a fundamentally different artifact: a list of structured `Block` objects (heading / paragraph / table / list / etc.) that ailang-parse extracts deterministically from the file. The orchestrator's prompt and downstream specialists are written assuming this structured shape:

```json
[
  {"type": "heading", "level": 1, "text": "Invoice INV-2026-042"},
  {"type": "paragraph", "text": "Vendor: Acme GmbH (Berlin)..."},
  {"type": "table", "headers": ["Item", "Qty", "Unit", "Amount"], "rows": [...]},
  ...
]
```

**Current State (verified 2026-06-08 live GE traffic):**
- ✅ A2A FilePart extraction interceptor saves an artifact with `state["document_ids"]` + `app:docs_loaded` populated
- ✅ doc-loader correctly skips its Firestore lookup (the `app:docs_loaded` pattern shipped in A2A-FILES M3)
- ✅ Gemini multimodal reads the inline bytes and extracts plausible-looking fields ("Acme GmbH", "INV-2026-042", "€9,817.50")
- ❌ AILANG Parse **never runs** on the uploaded file — the artifact format is raw bytes, not structured blocks
- ❌ Output quality is "raw": the model muddles the structured emit tool calls (Friction 1 returns — malformed function-call-as-Python-source dumped in chat)
- ❌ No way to attach the parsed structure to citations / audit-view / Firestore document_history
- ❌ A2A uploads don't surface in the per-doc Conversations panel like AG-UI uploads do — there's no Firestore record to render from

**Impact:**
- **Demo story**: SUBMISSION.md's headline is "AILANG Parse extracts deterministically". For A2A uploads today, that's literally not happening — it's Gemini multimodal under the hood.
- **Output quality**: GE responses are messy because the model is improvising from base64 bytes rather than typed fields. Less deterministic, more token spend, more "Malformed function call" leaks.
- **Audit / citation**: validator citations reference document-block IDs that don't exist for A2A docs (no parsed blocks). Audit view shows raw envelope, not the structured fields the user can verify.

## Goals

**Primary Goal:** A peer-uploaded A2A FilePart arrives at the orchestrator as the **same structured artifact shape** as an AG-UI upload — a JSON-encoded list of ailang-parse `Block` objects — so the existing prompts, specialists, citations, and audit-view paths all work without per-source branching.

**Success Metrics:**
- After deploy, a live GE upload of `acme-gmbh-invoice-2026-042.docx` produces:
  - A Cloud Run log line `AILANG Parse: parsed gs://... in <N>ms` (proves parse ran)
  - The `doc:{id}.json` artifact contains `[{"type": "heading", ...}, {"type": "paragraph", ...}, ...]` — not `[{"kind": "a2a-inline-file", "bytesBase64": "..."}]`
- The orchestrator's emit-tool call shape stabilises — no more "Malformed function call" leaks in the live transcript (or at least drops by ~80% relative to the 2026-06-08T05:51 transcript)
- A2A-uploaded docs appear in the AG-UI Document Conversations panel alongside AG-UI uploads (depends on Decision #2; can be deferred)
- AG-UI uploads keep working bit-identically — `scripts/verify-judge-path.sh` (chat-side smoke test) stays green
- All 1492 existing backend tests pass + new tests added for the parse path

**Non-Goals:**
- **Replace Gemini multimodal entirely.** Gemini natively supports many formats ailang-parse doesn't; the fallback path stays. This design just routes via ailang-parse FIRST, with Gemini as fallback (per Decision #3).
- **Per-org bucket parse (Scenario B from the parent sprint).** That path already uses `read_document_from_bucket` which downloads, but doesn't yet route through ailang-parse either. Same fix would apply but lands as a follow-up — keeping this sprint focused.
- **Frontend changes.** No new UI, no per-doc renderer changes. The artifact format alignment means the existing AG-UI rendering code works on A2A docs without modification.
- **Multi-tenant binding.** Out of scope (covered by §6 anti-pattern in the template brief).

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | 0 | Adds 1–3s per uploaded file for the parse step; A2A invocations already run ~65s end-to-end for the full AP pipeline so the relative impact is <5% |
| 2 | EARNED TRUST | +1 | Structured blocks let citations point at specific block IDs the user can verify against the source; raw-bytes envelope has no such handle |
| 3 | SKILLS, NOT FEATURES | +1 | A2A and AG-UI uploads now hit the same skill path identically; no source-specific branching in skill instructions |
| 4 | RIGHT MODEL, RIGHT MOMENT | +1 | Deterministic extraction (ailang-parse) replaces LLM-multimodal-as-OCR for the formats it supports — exactly the "no LLM tokens where deterministic processing exists" play |
| 5 | GRACEFUL DEGRADATION | +1 | Parse failure falls back to current bytes-only artifact, with a synthetic note in the response so the agent knows; deploy-wide DOCPARSE_API_KEY missing leaves the path unset and skips parse — neither case 500s |
| 6 | PROTOCOL OVER CUSTOM | 0 | Uses existing ailang-parse + the existing AG-UI artifact shape; no new format invented |
| 7 | API FIRST | +1 | The skill API is now identical between channels (AG-UI upload via REST POST, A2A FilePart via JSON-RPC `message/send`) — channel parity strengthens |
| 8 | OBSERVABLE BY DEFAULT | +1 | New log line `AILANG Parse: parsed <name> in <N>ms` per A2A upload; OTel span around parse-call wraps consistently with the existing upload path |
| 9 | SECURE BY CONSTRUCTION | 0 | No new trust surface — peer bytes already land in our process via M1's validation; parse runs over a tempfile in the same isolation boundary |
| 10 | THIN CLIENT, FAT PROTOCOL | 0 | Backend-only; zero frontend impact |
| | **Net Score** | **+6** | Threshold: >= +4 ✓ |

**Conflict Justifications:** None — no -1 scores.

## Standards Compliance

**Adopts:**
- **AG-UI artifact shape** (the existing `doc:{id}.json` block-list format used by `make_document_loader` + `load_artifacts_tool`) — verified by reading `backend/adk/callbacks.py:296-323` during design
- **AILANG Parse `parse_file(tmp_path, output_format="blocks")`** — verified the function exists at `backend/tools/documents/ailang_parse.py:331-346` via `_parse_file_sync(tmp_path, output_format)`
- Same `_run_parse` shape `(status, blocks, parsed_ms, parse_error)` used by AG-UI uploads so future log queries and tests can use one mental model

**Does not invent:**
- A new artifact shape (would force every downstream consumer — doc-loader, audit view, citations — to branch on source)
- A new parse pipeline (ailang-parse already exists, is already wired, already has secrets)
- Custom MIME handling — the `is_supported` check from `tools/documents/ailang_parse.py:170` covers the dispatch

## Design

### Overview

In `protocols/a2a_file_extraction.py:_save_inline_bytes_as_artifact`, after the raw-bytes envelope is constructed but BEFORE it's written to the artifact_service, try to parse the bytes via ailang-parse. If parse succeeds, replace the envelope with the structured-blocks shape. If parse fails or the MIME isn't supported (e.g. raw `.txt`), fall through to the current bytes-only envelope. Either path produces a usable `doc:{id}.json` artifact; the structured path is the happy case.

The doc-loader's `app:docs_loaded` pre-population from M3 stays in place — same behaviour, just with a richer artifact body underneath.

### Six Surface Decisions

#### 1. Inline-bytes parse path — **tempfile + existing `_parse_file_sync`**

| Option | Effort | Reuse | Pick |
| --- | --- | --- | --- |
| **Tempfile + `_parse_file_sync(tmp_path)`** | ~10 LOC | Reuses existing helper verbatim | ✓ |
| Upload bytes to a temp GCS path + call `parse_gcs_file(gs_url)` | ~30 LOC | Reuses AG-UI upload pipeline | ✗ — round-trip latency, GCS lifecycle cleanup |
| Add a new `parse_bytes(data, mime)` helper to `ailang_parse.py` | ~25 LOC + DocParse SDK call signature lookup | Cleanest API surface long-term | Maybe (follow-up) |

→ Write bytes to `tempfile.NamedTemporaryFile(suffix=ext)`, call `_parse_file_sync(tmp_path, output_format="blocks")`, return its `ParseOutcome`. Tempfile cleanup via `try/finally` around the call. ~10 LOC.

#### 2. Firestore record for A2A uploads — **deferred to follow-up**

| Option | Effort | Value | Pick |
| --- | --- | --- | --- |
| **No Firestore record (ephemeral, session-scoped)** | 0 LOC | A2A uploads stay session-bound — fine for v1 | ✓ |
| Store in `parsed_documents` with `source: "a2a"` tag | ~50 LOC + UI filter logic | A2A docs surface in per-doc Conversations panel | Follow-up |

→ Skip Firestore. A2A uploads remain session-scoped artifacts. If a peer wants persistence, they use the org-scoped bucket path (Scenario B from the parent sprint). The follow-up "A2A docs in Conversations panel" is a separate UX concern with its own tradeoffs — out of scope.

#### 3. Parse failure / unsupported MIME — **fall back to bytes-only envelope**

| Failure mode | Behaviour |
| --- | --- |
| MIME not in ailang-parse's deterministic set (e.g. `.txt`, `image/png`) | Skip parse step → bytes-only envelope → Gemini multimodal reads natively (current behaviour) |
| ailang-parse SDK returns `ok=False` (corrupt file, format error) | Log warning, fall back to bytes-only envelope |
| DOCPARSE_API_KEY unset (LOCAL_MODE without parse secret) | Log info, fall back to bytes-only envelope — same as AG-UI path's `preview_only` outcome |
| Tempfile write fails (disk full) | Fall back to bytes-only envelope, log error |

In all fallback cases the existing v1 behaviour applies. A synthetic message in the response (extending the existing `rejected` list machinery in the interceptor) tells the model "AILANG Parse couldn't structure this file; reading raw" so the response acknowledges the degraded path. Failure is non-fatal.

#### 4. Parse latency budget — **1–3s acceptable; document the math**

Measured from the existing AG-UI path: typical invoice DOCX parses in 800-1500ms; 10MB PDF in 2-4s. A2A invocations already run ~65s for the full Extract → Validate → Post pipeline (verified live 2026-06-08T05:51), so a 1-3s parse add is <5% of total wall clock. No timeout adjustments needed.

The parse call happens INSIDE the interceptor's `before_agent` hook, so it blocks the runner start. Could move parse to a background task that the doc-loader awaits, but the synchronous path is simpler and the latency is bounded. v1 keeps it synchronous.

#### 5. Artifact size — **cap at the existing 25MB FilePart limit**

The interceptor already enforces a 25MB cap on `FileWithBytes` (configurable via `A2A_FILE_MAX_BYTES`). Parsed blocks are typically 5-30% the size of source bytes (text extraction without binary embedded media), so the parsed artifact is always smaller than the raw envelope. No new cap needed.

Edge case: a DOCX with embedded images may produce blocks that include image references but not the image bytes themselves. Those references are preserved as URLs back to the original artifact if we keep the raw bytes secondary, OR dropped if we don't. For v1: **drop embedded media from parsed blocks**. The model gets text + structure; the image is lost from this turn. If a peer needs full-fidelity image extraction, they upload via AG-UI which has the multi-block image storage. Documented as a known limitation.

#### 6. Test fixture — **monkeypatch `_parse_file_sync`**

Three test patterns matching A2A-FILES M1's:

1. **Happy path** — monkeypatch `_parse_file_sync` to return canned `ParseOutcome(content=[{"type": "heading", ...}], ok=True)`; assert the saved artifact JSON contains the canned blocks
2. **Parse failure** — monkeypatch to return `ParseOutcome(ok=False, error="...")`; assert artifact falls back to the bytes-only envelope; assert a `rejected` note is added
3. **Unsupported MIME** — pass a `text/plain` part; assert no parse attempt is made (deterministic-format check); assert artifact is the bytes-only envelope

No real ailang-parse / DocParse SDK calls in unit tests. Integration coverage already exists via the live deploy + scripts/simulate-a2a-peer.py.

### Backend Changes

**Modified** — `backend/protocols/a2a_file_extraction.py`:
- New helper `_parse_bytes_to_blocks(decoded: bytes, mime_type: str, name: str) -> tuple[list, int, str | None]` (~25 LOC):
  - Map `mime_type` to a sensible suffix (`.docx`, `.pdf`, `.xlsx`, …) for the tempfile
  - Write `decoded` to a `tempfile.NamedTemporaryFile(delete=False, suffix=ext)`
  - Call `_parse_file_sync(tmp_path, output_format="blocks")`
  - Clean up tempfile in `finally`
  - Returns `(blocks, parsed_ms, error_message_or_None)`
- Modified `_save_inline_bytes_as_artifact` to call `_parse_bytes_to_blocks` first; if blocks returned, save THOSE as the artifact (same shape AG-UI's doc-loader writes); else fall back to current bytes envelope (~20 LOC delta)
- Log line `AILANG Parse (A2A): parsed <name> in <ms>ms (<N> blocks)` on success; `AILANG Parse (A2A): fallback to bytes envelope: <reason>` on failure

**Modified** — `backend/tests/api_tests/test_a2a_file_input.py`:
- Update `test_a2a_file_with_bytes_extracted_to_document_id` to assert the artifact is the **structured-blocks shape**, not the raw envelope (after monkeypatching `_parse_file_sync` to return canned blocks) (~10 LOC delta)
- New `test_a2a_file_parse_fallback_on_parser_error` — monkeypatch parse failure; assert bytes-envelope fallback + rejected-note (~30 LOC)
- New `test_a2a_file_unsupported_mime_skips_parse` — POST `text/plain` part; assert no parse attempt; assert bytes envelope (~25 LOC)
- Existing fallback tests (oversized, unknown MIME) unchanged — they short-circuit before the parse step

No other files modified. The doc-loader (`make_document_loader`), session injection (`_inject_document_ids`), and `app:docs_loaded` skip pattern all keep working — they don't care what the artifact body shape is.

### API Changes

No external API changes. The card's `defaultInputModes` stays the same 11-MIME list. The `/a2a` endpoint contract stays the same. Only the SHAPE OF THE ARTIFACT inside the session changes.

### Architecture

```
peer / GE
  → /a2a (mount)
    → A2aAgentExecutor (force_new_version=True)
      → FileExtractionInterceptor.before_agent(context)
        │
        ├── for each FilePart in context.message.parts:
        │     ├── validate (MIME, size, URI scheme)        # unchanged
        │     ├── decode base64 → bytes                    # unchanged
        │     │
        │     ├── NEW: _parse_bytes_to_blocks(bytes, mime) → ParseOutcome
        │     │     ├── write bytes to NamedTemporaryFile (suffix from MIME)
        │     │     ├── call _parse_file_sync(tmp_path, output_format="blocks")
        │     │     └── return blocks OR fallback marker
        │     │
        │     ├── if blocks: artifact = json.dumps(blocks)            # AG-UI shape
        │     │   else:      artifact = json.dumps([bytes_envelope]) # current v1 shape
        │     │
        │     ├── save_artifact(doc:{id}.json, artifact)
        │     ├── mint document_id, append to state["document_ids"]
        │     └── append document_id to state["app:docs_loaded"]    # unchanged
        │
        └── strip FileParts from context.message.parts             # unchanged
      → ADK runner → orchestrator → ap-pipeline (Extract → Validate → Post)
```

## Implementation Plan

### M1 — Parse integration + tests (~3 hours)

- [ ] Read `tools/documents/ailang_parse._parse_file_sync` one more time pre-keyboard to confirm signature + import path (~5 min)
- [ ] Add `_parse_bytes_to_blocks(decoded, mime_type, name) -> tuple[list, int, str | None]` to `protocols/a2a_file_extraction.py` (~30 LOC)
- [ ] Add the MIME → suffix mapping (~10 LOC; reuse the same map as `_DEFAULT_INPUT_MIME_TYPES`)
- [ ] Modify `_save_inline_bytes_as_artifact` to call `_parse_bytes_to_blocks` first, branch on result (~20 LOC delta)
- [ ] Log lines on both success and fallback (~5 LOC)
- [ ] Update 1 existing test + add 2 new tests in `test_a2a_file_input.py` (~65 LOC)
- [ ] Local smoke test against `localhost:1957` with `aiplatform a2a invoke --file ...`: artifact should show parsed-blocks shape in Cloud Logging
- [ ] `cd backend && make lint && make test-fast` both green
- [ ] Push to dev; wait for Cloud Build; re-run live test against deployed agent; verify Cloud Run logs show `AILANG Parse (A2A): parsed ...` line

### Verification + brief update (~1 hour)

- [ ] Re-run `scripts/simulate-a2a-peer.py` against live deploy — Step 7 should print structured-field extraction in the response, not raw-bytes-decoded text
- [ ] Manual GE test: upload `acme-gmbh-invoice-2026-042.docx` via the GE workspace UI; confirm the agent's response references structured fields cleanly; capture the new transcript and compare to the 2026-06-08T05:51 baseline (look for: no "Malformed function call" leak; clean emit-tool calls)
- [ ] Extend `docs/learnings/template-pr-a2a-spec-compliance.md` with §7 covering this work (parse integration, fallback path, tempfile pattern) — ~80 LOC

## Migration & Rollout

**Feature flag:** No new flag. Behaviour is purely additive — when parse succeeds, artifact is better; when parse fails, artifact is same as today. The existing `ENABLE_A2A_FILE_INPUT` flag still gates the whole interceptor.

**Rollback Plan:** Revert the single PR. The interceptor falls back to the bytes-envelope shape; no data shape change for sessions in flight.

**Environment Variables:** No new env vars. `DOCPARSE_API_KEY` already required for the AG-UI parse path; the A2A path uses the same secret. Forks without DOCPARSE_API_KEY just stay on the bytes-envelope shape (graceful degradation).

## Testing Strategy

### Backend Tests (pytest)

- [ ] Updated `test_a2a_file_with_bytes_extracted_to_document_id` — assert artifact has the structured-blocks shape when parse succeeds
- [ ] New `test_a2a_file_parse_fallback_on_parser_error` — monkeypatch parse to return `ok=False`; assert bytes-envelope fallback + rejected-note appended
- [ ] New `test_a2a_file_unsupported_mime_skips_parse` — `text/plain` doesn't even attempt parse; bytes envelope only
- [ ] All 1492 existing backend tests stay green; especially `test_a2a_*.py` files

### Integration Tests

- [ ] `scripts/simulate-a2a-peer.py` Step 7 against live deploy — capture the agent's response text; confirm it references vendor/invoice/total cleanly (the live baseline before this fix had the same fields but with "raw" framing)

### Manual Testing

- [ ] Upload `acme-gmbh-invoice-2026-042.docx` via Gemini Enterprise workspace UI; confirm the new transcript is cleaner than the 2026-06-08T05:51 transcript
- [ ] Upload a PDF; confirm parse runs (vs `.docx`)
- [ ] Upload a `.txt`; confirm parse is skipped (text not in ailang-parse's deterministic set); response is unchanged

## Security Considerations

- **No new trust surface.** The peer bytes already land in our process via M1's validated path. The parse step just reads them; tempfile lives in `/tmp` inside the same Cloud Run container.
- **Tempfile cleanup.** `try/finally` around the parse call to delete the tempfile even on parse errors. Use `delete=False` + manual `os.unlink` in finally rather than the `NamedTemporaryFile` context manager so the file is readable from the subprocess `_parse_file_sync` uses (some OS quirks make NamedTemporaryFile with `delete=True` invisible across calls).
- **DOCPARSE_API_KEY** is the same secret the AG-UI path uses. Cloud Run service account already grants `secretmanager.versions.access` on it; no new IAM.
- **No data egress.** Parse runs inside our GCP project (DocParse SDK is in the AILANG family; verify it's hitting `*.sunholo.com` not a third-party).

## Performance Considerations

- **Latency add per uploaded file**: 1–3s for typical invoices, up to ~5s for a 10MB PDF. <5% of the existing 65s full-pipeline wall clock.
- **Memory**: tempfile + bytes in memory transiently; same magnitude as the existing FilePart validation step. Peak ≈ 50MB for the largest allowed file.
- **No cache**: each turn re-parses the same file if the peer keeps re-uploading it. Forks with deduplication needs can hash-on-receive (future).
- **OTel**: wrap `_parse_bytes_to_blocks` in a span so parse latency is independently traceable from the agent invocation cost.

## Success Criteria

- [ ] All backend tests passing (`cd backend && make test-fast`)
- [ ] Lint + format clean (`cd backend && make lint`)
- [ ] Local smoke (`aiplatform a2a invoke --file ...` against `localhost:1957`) shows the `doc:{id}.json` artifact containing `[{"type": "heading", ...}, ...]` shape — not the bytes envelope
- [ ] Cloud Run logs after deploy: a per-A2A-upload line `AILANG Parse (A2A): parsed <name> in <Nms> (<count> blocks)`
- [ ] Live GE upload of `acme-gmbh-invoice-2026-042.docx` produces a response that references structured fields cleanly (manual visual check vs the 2026-06-08T05:51 baseline; no "Malformed function call" raw-Python leak in the captured transcript)
- [ ] `docs/learnings/template-pr-a2a-spec-compliance.md` gains §7

## Open Questions

- **Does AILANG Parse's `_parse_file_sync` handle non-extension hint?** The DocParse SDK might infer format from content sniffing OR require the tempfile suffix to match. Verify in the M1 task by passing a `.docx` byte stream with `.bin` suffix and observing behaviour. If it requires the suffix, our MIME→suffix mapping must be airtight.
- **Should we ALSO hash the bytes and check for an existing parse?** Useful for dedup if the peer repeatedly re-sends the same invoice in different chat turns. Probably not — A2A turns are stateless from the peer's perspective. v1 keeps it simple.
- **OTel span granularity**: emit a single `a2a.parse_bytes` span, or one per FilePart in the message? Multi-file uploads aren't common in practice (most peers send one file per turn); single span keeps the trace tidy.

## Related Documents

- [A2A file-input + org-scoped buckets (implemented)](./implemented/a2a-file-input.md) — the parent sprint this extends
- [Template-PR brief — A2A spec compliance](../../../learnings/template-pr-a2a-spec-compliance.md) — folds in as §7
- [Original SUBMISSION.md](../../../../SUBMISSION.md) — the "AILANG Parse extracts deterministically" claim this design makes true for A2A uploads
- Source verified during design: `backend/tools/documents/upload.py:_run_parse` (the AG-UI parse path), `backend/tools/documents/ailang_parse.py:_parse_file_sync` (the helper this design reuses), `backend/adk/callbacks.py:296-323` (the doc-loader's artifact shape contract)
