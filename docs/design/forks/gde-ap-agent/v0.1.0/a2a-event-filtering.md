# A2A event filtering — stop specialist narration from leaking to peers

**Status**: Planned
**Priority**: P0 (High) — every GE response since 2026-06-08 has shown a wall of specialist intent-narration concatenated with the final verdict. Output looks chaotic; non-deterministic. Until filtered, an A2UI Card on top would render the same wall plus a Card.
**Estimated**: ~0.4 day (1 milestone)
**Scope**: Backend
**Dependencies**:
- [A2A file-input (implemented)](./implemented/a2a-file-input.md) — provides the existing `ExecuteInterceptor` slot
- ADK's `ExecuteInterceptor.after_event` hook — verified during design (returning `None` filters an event out of the executor's event queue)
- The AP-pipeline agent topology — `ap-orchestrator` (LlmAgent) → `ap-pipeline` (SequentialAgent) → [`invoice-extractor`, `ap-validator`, `ap-poster`] (LlmAgents); verified at [backend/adk/agent.py:305](../../../../../backend/adk/agent.py#L305)
**Created**: 2026-06-08
**Last Updated**: 2026-06-08
**Upstream-bound**: Yes — every fork running ADK's `SequentialAgent` over A2A hits the same wall-of-narration problem. Folds into the template-PR brief as §9 after implementation.

## Problem Statement

Three consecutive live GE uploads (2026-06-08T05:51 / 10:11 / 11:56 / 15:27 UTC) have all returned the same shape:

```
Reading the parsed invoice and extracting vendor, line items, and totals.
Validating the extracted invoice against the vendor master and approval policy.
Verdict is needs_review — routing to a finance reviewer.
```

The first two sentences are **intent narration** from the Extract and Validate specialists — Gemini's "thinking-out-loud" preamble before a tool call. ADK's `convert_event_to_a2a_events` (verified by reading `google.adk.a2a.executor.a2a_agent_executor.A2aAgentExecutor.execute`) emits every ADK event in the run through to the A2A event queue, including these intermediate text events. GE concatenates them in the chat bubble.

The peer should see **only the verdict** — the actual deterministic output of the pipeline. The narration is internal-monologue noise that pollutes the bubble and makes the response feel non-deterministic ("Reading the parsed invoice" appears even when there's no parsed invoice).

**Current State (verified 2026-06-08 four times now):**
- ✅ Pipeline runs end-to-end on every A2A turn
- ✅ Verdict is produced by `ap-poster`
- ❌ `invoice-extractor` and `ap-validator` text events leak through to the peer
- ❌ GE bubble shows wall-of-narration
- ❌ Each turn's narration shape varies (Extract sometimes retries with "document not found"), making the output non-deterministic from the peer's perspective

**Impact:**
- **GE UX**: judges/users see noisy internals; the pipeline LOOKS less polished than it actually is.
- **Submission narrative**: "audit-grade postings" promise is undermined by the orchestrator visibly narrating its intent.
- **Blocks A2UI work**: layering a Card on top of the wall would compound the noise, not replace it. Filter first.

## Goals

**Primary Goal:** A2A peers receive only the orchestrator-level and terminal-specialist (`ap-poster`) events. Intermediate `invoice-extractor` and `ap-validator` narration is suppressed.

**Success Metrics:**
- After deploy, a live GE upload returns a single verdict line (e.g. "Verdict is `needs_review` — routing this invoice to ... due to ..."), not the three-line concatenation
- The Extract and Validate specialists' intent narration ("Reading the parsed invoice...", "Validating the extracted invoice...") does NOT appear in the GE bubble
- The in-repo frontend (AG-UI path) behavior is unchanged — AG-UI subscribes to its own event channel, not the A2A one, so this filter only affects A2A peers
- Pipeline tool calls (vendor-master, erp-posting MCP) still get attached as TaskArtifactUpdateEvents for audit (no signal lost on the task)
- All ~37 existing A2A tests stay green + new tests verify the filter

**Non-Goals:**
- **Filtering Extract/Validate output entirely.** Their tool results land in TaskArtifactUpdateEvents for audit; only text-bearing TaskStatusUpdateEvents from these two are dropped.
- **Configurable per-skill drop sets.** v1 hard-codes the AP-pipeline specialist names. Forks with different pipelines can copy the pattern; a config-driven version is a follow-up.
- **A2UI Card emission.** Separate work; only viable after this filter lands.
- **Fixing the "specified document was not found" retry leak in `invoice-extractor`.** Once Extract is filtered, the retry narrative disappears from the peer view; the underlying lookup bug is tracked separately.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | Less wall-of-text in the bubble = the verdict reads instantly instead of after three paragraphs of narration |
| 2 | EARNED TRUST | +1 | Removing chatter that doesn't reflect actual deterministic work lets the verdict itself land; users trust what they understand |
| 3 | SKILLS, NOT FEATURES | 0 | Same skill, same pipeline — only the wire surface changes |
| 4 | RIGHT MODEL, RIGHT MOMENT | 0 | No model routing change |
| 5 | GRACEFUL DEGRADATION | +1 | Filter fails open: any exception in `_after_event` returns the event unchanged, so a broken filter degrades to current behaviour, not silence |
| 6 | PROTOCOL OVER CUSTOM | +1 | Uses ADK's `ExecuteInterceptor.after_event` (returns `None` to drop event); no new format, no custom event type |
| 7 | API FIRST | +1 | A2A wire becomes more spec-aligned: peers see only the events the agent intends to surface as user-visible content, not the executor's internal trace |
| 8 | OBSERVABLE BY DEFAULT | +1 | `logger.warning("a2a event filter: dropped author=%s ...")` per dropped event; cardinality is bounded (3-5 per pipeline turn) |
| 9 | SECURE BY CONSTRUCTION | 0 | No new trust surface; filter runs in the executor's process, same auth boundary |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | Peer doesn't need to know which sub-agents exist or filter their narration client-side — that's the server's job |
| | **Net Score** | **+7** | Threshold: >= +4 ✓ |

**Conflict Justifications:** None.

## Standards Compliance

**Adopts:**
- ADK's `ExecuteInterceptor.after_event(executor_context, a2a_event, adk_event) -> A2AEvent | list[A2AEvent] | None` (verified at `google.adk.a2a.executor.config.ExecuteInterceptor` during design). Returning `None` filters the event out; the docstring states this explicitly.
- A2A v0.2 `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent` types. We filter only TaskStatusUpdateEvents whose `status.message` carries text; artifact updates (tool calls/results) pass through untouched.

**Does not invent:**
- A custom event type, a new MIME, or a per-event metadata convention
- A new interceptor chain or hook system — uses ADK's existing slot

## Design

### Overview

Add a second `ExecuteInterceptor` to the A2A executor's chain whose only purpose is `after_event` filtering. The existing file-extraction interceptor (`make_file_extraction_interceptor`) keeps its `before_agent` hook for FilePart extraction and continues to run first; the new event-filter interceptor runs after every event projection.

```
A2aAgentExecutor.execute
  ├─ Before: file_extraction_interceptor.before_agent  (existing)
  ├─ runner.run_async iterates over ADK events
  │    for each ADK event → convert_event_to_a2a_events → A2A events
  │      ├─ event_filter.after_event(ctx, a2a_evt, adk_evt) → keep | drop  ← NEW
  │      └─ if kept: event_queue.enqueue_event(...)
  └─ (Optional after_agent — not used in v1)
```

### One Surface Decision — what to drop

**Drop**: `TaskStatusUpdateEvent`s whose `status.message` carries text **AND** whose source ADK event's `author` is in `{"invoice-extractor", "ap-validator"}`.

**Keep**:
- All events from `ap-orchestrator`, `ap-pipeline`, `ap-poster`, or the special author `"user"`
- All `TaskArtifactUpdateEvent`s (tool calls/results) regardless of author — these are audit signals attached to the task, not chat content
- All `TaskStatusUpdateEvent`s without text content (state transitions like `submitted`/`working`/`completed`/`failed`)

**Why this shape**:
- The Extract and Validate narration is the documented leak. `ap-poster` produces the actual verdict — must be preserved.
- Tool calls/results need to land for the audit trail (judges can verify the vendor-master + erp-posting MCP calls happened by inspecting task artifacts).
- State events (`submitted`→`working`→`completed`) are how GE knows the task progressed — never filter these.

### Backend Changes

**New file** — `backend/protocols/a2a_event_filter.py` (~80 LOC):
- `_INTERMEDIATE_SPECIALIST_AUTHORS: frozenset[str] = frozenset({"invoice-extractor", "ap-validator"})` — module constant; v1 hard-codes the AP-pipeline specialists
- `_event_has_visible_text(a2a_event) -> bool` — returns True iff the event is a `TaskStatusUpdateEvent` whose `status.message.parts` contains a `kind="text"` part
- `_should_drop(a2a_event, adk_event) -> bool` — combines the rules
- `async def _after_event(executor_context, a2a_event, adk_event) -> A2AEvent | None` — wraps `_should_drop` with fail-open exception handling and a single `logger.warning("a2a event filter: dropped author=%s text=%r", ...)` log line per drop
- `make_event_filter_interceptor() -> ExecuteInterceptor` — returns `ExecuteInterceptor(after_event=_after_event)` with no `before_agent` (composes cleanly with the file-extraction interceptor)

**Modified** — `backend/protocols/a2a_invocation.py` (~5 LOC delta):
- Import `make_event_filter_interceptor`
- Append it to the `execute_interceptors` list passed to `A2aAgentExecutorConfig`. Order: `[file_interceptor, event_filter]` — file extraction first (it runs `before_agent`); event filter runs `after_event` on every projection

**New file** — `backend/tests/api_tests/test_a2a_event_filter.py` (~150 LOC):
- `test_drops_text_event_from_invoice_extractor` — synthesise a `TaskStatusUpdateEvent` with text + an ADK event with `author="invoice-extractor"`; assert `_after_event` returns `None`
- `test_drops_text_event_from_ap_validator` — same but author="ap-validator"
- `test_keeps_text_event_from_ap_poster` — text + author="ap-poster" → unchanged
- `test_keeps_text_event_from_ap_orchestrator` — text + author="ap-orchestrator" → unchanged
- `test_keeps_artifact_update_event_regardless_of_author` — TaskArtifactUpdateEvent + author="invoice-extractor" → unchanged
- `test_keeps_state_only_event_without_text` — `TaskStatusUpdateEvent(state=working)` with no message → unchanged
- `test_fail_open_on_exception` — pass a malformed adk_event; filter returns the event unchanged (no drop on filter error)
- `test_logs_warning_on_drop` — captures the `a2a event filter: dropped` log line via `caplog`

### API Changes

None. Internal change only. Peers see fewer events; the spec-defined event shapes are unchanged.

### Architecture

```
ap-orchestrator (LlmAgent, root)
  └─ subagent: ap-pipeline (SequentialAgent)
       ├─ invoice-extractor   ← Extract specialist (FILTERED text)
       ├─ ap-validator        ← Validate specialist (FILTERED text)
       └─ ap-poster           ← Post specialist (KEPT text — emits the verdict)

A2A wire on every turn (post-filter):
  TaskStatusUpdateEvent(state=submitted)         keep (state-only)
  TaskStatusUpdateEvent(state=working)           keep (state-only)
  [invoice-extractor narration text events]      DROP
  [invoice-extractor tool_calls → artifacts]     keep (audit)
  [ap-validator narration text events]           DROP
  [ap-validator tool_calls → artifacts]          keep (audit)
  [ap-poster text events — verdict]              keep
  [ap-poster tool_calls → artifacts]             keep (audit)
  TaskArtifactUpdateEvent(last_chunk=true)       keep
  TaskStatusUpdateEvent(state=completed)         keep
```

## Implementation Plan

### M1 — Filter + wire + tests (~3 hours)

- [ ] Create `protocols/a2a_event_filter.py` with `_INTERMEDIATE_SPECIALIST_AUTHORS`, helpers, and `make_event_filter_interceptor()` (~80 LOC)
- [ ] Add `event_filter = make_event_filter_interceptor()` then `execute_interceptors=[file_interceptor, event_filter]` in `protocols/a2a_invocation.py` (~5 LOC)
- [ ] Eight tests in `tests/api_tests/test_a2a_event_filter.py` (~150 LOC)
- [ ] `cd backend && make lint && uv run pytest tests/api_tests/test_a2a_*.py -v` all green
- [ ] Push to dev; wait for Cloud Build; live GE upload test — confirm bubble shows only the `ap-poster` verdict line, no Extract/Validate narration
- [ ] Capture before/after transcript pair in `docs/learnings/template-pr-a2a-spec-compliance.md` under §9 — "Filtering intermediate sub-agent narration for clean peer UX"

## Migration & Rollout

**Feature flag:** No new flag — behaviour is a strict subset of current event flow (filters never add, only suppress). To revert: revert the single PR; `execute_interceptors` chain falls back to file-only. Same TaskStore, same orchestrator.

**Rollback Plan:** Revert the single commit. Zero data shape change for sessions in flight; sub-agent events that were being filtered just start flowing through again.

**Environment Variables:** None new. If a follow-up needs configurability, add `A2A_FILTER_AUTHORS=invoice-extractor,ap-validator` (comma list) — but v1 keeps it hardcoded for simplicity.

## Testing Strategy

### Backend Tests (pytest)

- [ ] 8 new tests in `test_a2a_event_filter.py` (above)
- [ ] All ~37 existing A2A tests stay green

### Integration Tests

- [ ] `scripts/simulate-a2a-peer.py` against live deploy — capture the streamed events; confirm Extract/Validate text doesn't appear

### Manual Testing

- [ ] Upload `acme-gmbh-invoice-2026-042.docx` via Gemini Enterprise; bubble shows clean verdict line only
- [ ] Same upload via the in-repo frontend (AG-UI) — Extract/Validate narration STILL shows there because the AG-UI subscription is independent; filter only affects A2A

## Security Considerations

- **No new trust surface.** The filter runs in the same Cloud Run process, same auth boundary.
- **No data exfiltration risk.** Filter only drops events; it never adds or rewrites.
- **Audit completeness preserved.** Tool calls/results land as TaskArtifactUpdateEvents which are NOT filtered. The agent's deterministic work is fully traceable via the task's artifact list.

## Performance Considerations

- **Per-event overhead**: 1 attribute access (`adk_event.author`) + 1 isinstance check + 1 frozenset membership check. ~µs per event. Pipeline emits ~20 events per turn = ~20µs overhead total. Negligible.
- **Memory**: no buffering; filter is pure-functional per event.
- **No additional egress.**

## Success Criteria

- [ ] All backend tests passing
- [ ] Lint + format clean
- [ ] After deploy, live GE upload returns a single-line `ap-poster` verdict (no Extract/Validate narration in the bubble)
- [ ] The "Reading the parsed invoice..." / "Validating the extracted invoice..." text DOES NOT appear in the chat bubble
- [ ] `docs/learnings/template-pr-a2a-spec-compliance.md` gains §9
- [ ] Tool-call audit trail (vendor-master, erp-posting MCP calls) still visible in the task's artifacts list

## Open Questions

- **Are there cases where `ap-poster` emits intent narration too?** Possible — if so the bubble might still feel a little chatty. v1 ships and we observe; if Post also narrates, we extend the filter to a `text_must_be_terminal` rule (drop everything except the final response event from any specialist).
- **Does `ap-orchestrator` ever compose its own wrapping summary text?** Verified during design that the SequentialAgent's last specialist (`ap-poster`) IS the terminal output for AP turns. If a future skill wraps with an orchestrator response on top, that response is from `ap-orchestrator` and would be kept (correct).
- **Should the filter also rewrite tool-result-as-text leaks?** Some specialists may emit tool results as a TextPart instead of a structured artifact. If we observe that pattern, the filter would need to inspect `parts` content. Out of scope for v1.

## Related Documents

- [A2A file-input + org-scoped buckets (implemented)](./implemented/a2a-file-input.md) — provides the `ExecuteInterceptor` slot we extend
- [A2A AILANG Parse integration](./a2a-ailang-parse.md) — separate fix, separate path; both modules can run with no interaction
- [A2A async task pattern](./a2a-async-task-pattern.md) — orthogonal; filter applies regardless of sync/async send
- [Template-PR brief — A2A spec compliance](../../../learnings/template-pr-a2a-spec-compliance.md) — folds in as §9
- Source verified during design: `google.adk.a2a.executor.config.ExecuteInterceptor` (the `after_event` hook with `None` semantics), `google.adk.a2a.executor.a2a_agent_executor.A2aAgentExecutor.execute` (the event-queue path), `backend/adk/agent.py:305` (`_AP_SPECIALIST_STAGE_LABELS` — source of truth for specialist skill names)
