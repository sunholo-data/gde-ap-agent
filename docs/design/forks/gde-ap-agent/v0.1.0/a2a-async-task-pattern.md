# A2A async task pattern — return early on `message/send`, SSE on `message/stream`

**Status**: Planned
**Priority**: P0 (High) — the GE experience is timeout-bound until this lands; any pipeline >60s is broken from the peer side regardless of how good the backend is
**Estimated**: ~1.0 day across 3 milestones (M1 ~1h observation, M2 ~0.5d async send, M3 ~0.5d SSE — conditional on M1 finding)
**Scope**: Backend
**Dependencies**:
- [A2A `message/send` bridge (implemented)](./implemented/a2a-message-send-bridge.md)
- [A2A file-input + org-scoped buckets (implemented)](./implemented/a2a-file-input.md)
- `a2a.server.request_handlers.DefaultRequestHandler` — handlers exist for `on_message_send`, `on_message_send_stream`, `on_get_task`, `on_cancel_task`, `on_resubscribe_to_task` (verified during design)
- `a2a.server.agent_execution.AgentExecutor` — needs verification on whether `cancel()` cleanly halts a running ADK pipeline
**Created**: 2026-06-08
**Last Updated**: 2026-06-08
**Upstream-bound**: Yes — every fork running ADK agents with non-trivial pipelines hits this exact wall. Folds into the template-PR brief as §8 after implementation.

## Problem Statement

The deployed agent's A2A invocation surface blocks the HTTP response until the full pipeline completes. On 2026-06-08T05:51 UTC the AP pipeline ran ~65s end-to-end (Extract → Validate → Post with MCP grounding for vendor master + ERP). The Next.js / Cloud Run proxy idle timeout dropped the connection before the response could flush. Gemini Enterprise saw a truncated message even though the backend completed cleanly.

**The reflex fix — bump the proxy timeout — does not scale**:
- Cloud Run service-level request timeout maxes at 60 minutes
- Next.js's `experimental.proxyTimeout` would have to track every future deepening of the agent (Loop agents, multi-vendor batch reconciliation, ten-step approval flows)
- Worse, idle timeouts apply per-byte-flush even when the upstream is happily computing — making the timeout a feature of network behaviour not agent latency

**The A2A spec already solves this** with two patterns the platform doesn't currently use:

1. **Async task pattern** (the spec-canonical answer for long tasks): `message/send` returns a `Task` envelope with `state: "submitted"` or `"working"` and a `task_id` IMMEDIATELY. Agent runs in a background task. Peer polls `tasks/get` until status is `completed` / `failed` / `canceled`. Idle timeout doesn't bite because the initial response is fast and each subsequent poll is fast.
2. **Streaming pattern**: `message/stream` (a.k.a. `message/sendSubscribe`) returns an SSE stream. Each `TaskStatusUpdateEvent` or `TaskArtifactUpdateEvent` is a separate write to the connection. The connection stays warm because bytes flow.

Both patterns are first-class in `a2a.server.request_handlers.DefaultRequestHandler` — which our mount already uses. Verified during design: the handler has `on_message_send`, `on_message_send_stream`, `on_get_task`, `on_cancel_task`, and `on_resubscribe_to_task` and tracks `_running_agents: dict[str, asyncio.Task]` + `_background_tasks: set[asyncio.Task]`. The plumbing is **there**; what's broken is the configuration of `on_message_send`'s wait behaviour.

**Current State (verified 2026-06-08T05:51 UTC live traffic):**
- `POST /a2a/` from GE blocked for ~65s while the pipeline ran
- Next.js dropped the connection with `[Error: socket hang up] { code: 'ECONNRESET' }` before the terminal event reached GE
- The backend log shows the full pipeline (vendor-master MCP × 5, erp-posting MCP × 3) completing normally — only the wire connection died
- ADK's `DefaultRequestHandler.on_message_send` currently awaits the producer task to terminal completion before returning the Task

**Impact:**
- **GE UX**: peer sees a truncated answer, retries, hits the same wall — feels broken even though the backend works
- **Submission story**: SUBMISSION.md sells "audit-grade postings out" as an end-to-end experience; right now it's "audit-grade postings, eventually, if Gemini Enterprise stays patient"
- **Future-proofing**: any pipeline deeper than the current 3-specialist sequential (e.g. Loop agents that retry until invariants hold, ParallelAgent fan-out + reduce, human-in-the-loop approval gates) will exceed the proxy timeout. The reflex fix doesn't scale.

## Goals

**Primary Goal:** A peer can invoke a long-running A2A skill and observe the result, regardless of pipeline depth. No HTTP timeout pressure on the response path.

**Success Metrics:**

For M1 (observation):
- We know which A2A method Gemini Enterprise calls (`message/send` vs `message/stream`)
- We know whether GE polls `tasks/get` after a `send` response with `state: working`
- A captured Cloud Logging window from a real GE interaction proves the behaviour (or proves we need to also implement A — sendSubscribe — because GE never polls)

For M2 (async send):
- A live GE upload of `acme-gmbh-invoice-2026-042.docx` returns `state: working + task_id` within 5 seconds (vs current 65s blocking)
- A subsequent `tasks/get` returns `state: completed` with the same final Task body
- `scripts/simulate-a2a-peer.py` Step 7 completes without `ECONNRESET` even when run through the Next.js proxy
- No regression: text-only `message/send` invocations that complete <5s still return inline (we don't force every call into the async dance)

For M3 (SSE, conditional):
- `message/stream` against the deployed mount returns an SSE response with at least 3 incremental `TaskStatusUpdateEvent`s before the terminal event
- Peers using `message/stream` see a streaming experience identical to AG-UI users

**Non-Goals:**
- **Cross-revision task durability.** v1 keeps `InMemoryTaskStore`; if Cloud Run scales out or cold-starts, the new revision doesn't know about tasks the old one was running. Acceptable for the showcase; Firestore-backed TaskStore is a follow-up if forks need it.
- **Push notifications.** The third A2A pattern is server-pushes-to-peer-webhook (`PushNotificationConfig`). Genuinely useful but a different design — peers need their own ingress. Out of scope.
- **Replacing the AG-UI streaming surface.** Frontend continues to use `/api/skill/{id}/stream`; A2A is purely the cross-agent surface.
- **Inventing a custom polling protocol.** Everything is bog-standard A2A v0.2 `tasks/get` / `tasks/cancel` / `tasks/resubscribe`.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | `message/send` returns within milliseconds instead of blocking ~65s — peer immediately gets a task_id and renders "in progress" UI |
| 2 | EARNED TRUST | 0 | No change to citation / confidence paths; the response shape is identical, just streamed differently |
| 3 | SKILLS, NOT FEATURES | 0 | Skills remain the abstraction; A2A peers see the same skill list |
| 4 | RIGHT MODEL, RIGHT MOMENT | 0 | No model routing change |
| 5 | GRACEFUL DEGRADATION | +1 | Cancellation (`tasks/cancel`) for stuck pipelines; pollers that drop continue from `tasks/resubscribe`; if asyncio background task crashes the task is marked `failed` not silently dropped |
| 6 | PROTOCOL OVER CUSTOM | +1 | Adopts A2A v0.2 spec's async task semantics + SSE — no custom polling protocol, no custom streaming format |
| 7 | API FIRST | +1 | A2A peers + AG-UI frontend now have parity: both see streaming progress as events arrive (AG-UI via SSE, A2A via SSE or polling task store) |
| 8 | OBSERVABLE BY DEFAULT | +1 | OTel spans wrap the background task lifetime; `tasks/get` polling visible in BigQuery analytics; backpressure / queue depth becomes a measurable signal |
| 9 | SECURE BY CONSTRUCTION | 0 | No new trust surface; peer must already authenticate to /a2a (M2 middleware shipped). `tasks/cancel` can only affect the calling peer's tasks (per ADK's task_store ownership check) |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | Backend handles async lifecycle; peer just polls or subscribes — no business logic moves client-side |
| | **Net Score** | **+6** | Threshold: >= +4 ✓ |

**Conflict Justifications:** None — no -1 scores.

## Standards Compliance

**Adopts:**
- **A2A v0.2 spec — async task pattern**: `Task` with `TaskStatus.state` ∈ {`submitted`, `working`, `completed`, `canceled`, `failed`, `rejected`, `input-required`, `auth-required`}; `tasks/get` for polling; `tasks/cancel` for halting; `tasks/resubscribe` for re-attaching to event streams. All defined in `a2a.types.TaskState` (verified during design).
- **A2A v0.2 spec — streaming pattern**: `message/stream` returns SSE; each `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent` is a discrete server-sent event.
- **ADK's `DefaultRequestHandler`**: all four handlers (`on_message_send`, `on_message_send_stream`, `on_get_task`, `on_cancel_task`, `on_resubscribe_to_task`) ship and already track background tasks via `_running_agents` and `_background_tasks`. We don't write new handlers; we configure the existing ones to use the async-send semantics.

**Does not invent:**
- A custom task ID scheme — A2A's UUID conventions apply
- A custom polling response — `Task` envelope per spec
- A custom cancellation method — uses `tasks/cancel`

## Design

### Overview

ADK's `DefaultRequestHandler.on_message_send` currently waits for the producer asyncio task to reach a terminal state before returning. That's the timeout-bound behaviour. The async pattern requires the handler to return a `Task` envelope with `state: working + task_id` as soon as the agent has acknowledged the message (after the first `TaskStatusUpdateEvent`, which fires early per ADK's executor source we already read in M1 of A2A-INVOKE: "for new task, create a task submitted event").

There are three ways to flip this behaviour:

1. **Custom `RequestHandler`** that subclasses `DefaultRequestHandler.on_message_send` to return on first non-`submitted` status update.
2. **Custom `A2aAgentExecutor`** that emits a terminal-shape `Task` envelope after the `submitted` event and continues processing in the background — but that breaks ADK's executor contract.
3. **Hint-driven**: only return early when an env var / per-call config flag says to, so short tasks (text-only chat) still return synchronously. Probably what we want.

(1) + (3) combined gives the cleanest design: a thin subclass of `DefaultRequestHandler` whose `on_message_send` checks a "long-task hint" (env var threshold, or the agent type — `SequentialAgent` is a strong tell), and switches to return-early-with-task_id mode for those.

For `message/stream` the existing `on_message_send_stream` already does the right thing — we just need to verify that ADK's executor actually drives event flow over the queue (some configurations buffer everything until terminal).

### Three Milestones, Sequenced

#### M1 — Observation (~1 hour)

Goal: know GE's actual A2A behaviour before guessing.

Add a logging wrapper around the executor that captures, per request:
- `request.method` — `message/send` vs `message/stream` vs `tasks/get`
- `request.context.message.parts` count + types
- `User-Agent` header
- For follow-up `tasks/get` calls: the original `task_id` so we can correlate

Trigger a real GE upload of `acme-gmbh-invoice-2026-042.docx`. Wait 2-3 minutes. Pull Cloud Logging for the window.

**Outcome decides M2 + M3 priority:**

| Observation | Implication |
| --- | --- |
| GE calls `message/send` and never polls `tasks/get` | M2 is critical (must return early or GE never sees the response); M3 is optional |
| GE calls `message/send` and polls `tasks/get` every N seconds | M2 is the right fix; M3 is nice-to-have for streaming experiences |
| GE calls `message/stream` directly | M3 is critical; M2 might not be needed at all if SSE works |
| GE calls `message/send` but waits 5+ min on the connection | Their proxy is more patient than ours; we still need M2 to remove our wall |

#### M2 — Async `message/send` (~0.5 day)

Goal: `message/send` returns within 2s with `Task(state=working, task_id=<id>)` for any agent invocation that's likely to take >5s.

**Design choice — "likely to take >5s"**: detected by agent shape. The mounted agent is `ap-orchestrator`; it has `subSkills: [ap-pipeline]` and `ap-pipeline` is a `SequentialAgent`. **Any agent whose subSkills contain a workflow agent (Sequential / Loop / Parallel)** runs in async mode. Pure conversational `LlmAgent`s with no workflow sub-agents stay synchronous (fast text responses don't need the round-trip).

**Custom `AsyncOnLongRunRequestHandler(DefaultRequestHandler)`:**

```python
class AsyncOnLongRunRequestHandler(DefaultRequestHandler):
    """Returns early from message/send with Task(state=working) for
    long-running agents. Background task continues and updates the
    TaskStore; peer polls tasks/get for the terminal state.
    """

    def __init__(
        self,
        *args: Any,
        is_long_running: Callable[[RequestContext], bool] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._is_long_running = is_long_running or _default_long_running_detector

    async def on_message_send(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> Message | Task:
        # Build the request context the same way the parent does
        (
            task_manager,
            task_id,
            queue,
            result_aggregator,
            producer_task,
        ) = await self._setup_message_execution(params, context)

        # Caller wants the slow path? Fall back to the parent's blocking
        # behaviour so short conversations stay snappy.
        if not self._is_long_running(_request_context_from(params, context)):
            consumer = EventConsumer(queue)
            producer_task.add_done_callback(consumer.agent_task_callback)
            # … same as parent's tail
            return await self._consume_to_terminal(consumer, result_aggregator)

        # Long path: track the background task and return the current
        # snapshot of the Task envelope (which the executor has already
        # populated with state=submitted/working via the initial
        # TaskStatusUpdateEvent emitted by A2aAgentExecutor).
        self._background_tasks.add(producer_task)
        producer_task.add_done_callback(self._background_tasks.discard)

        # Wait JUST long enough for the executor's initial "submitted"
        # event to land in the TaskStore (max ~50ms).
        await self._wait_for_initial_event(task_id)
        snapshot = await self.task_store.get(task_id)
        if snapshot is None:
            raise ServerError(error=InternalError(message="task_store missed initial event"))
        return snapshot  # Task with state=submitted or working
```

ADK already tracks background tasks; we just don't `await` them. The peer's subsequent `tasks/get` hits `DefaultRequestHandler.on_get_task` which reads the latest snapshot from `self.task_store.get(...)` — the same store the still-running producer task is writing to.

**Default `_default_long_running_detector`:**

```python
def _default_long_running_detector(context: RequestContext) -> bool:
    """Default: any FilePart in the request OR any workflow sub-agent
    in the mounted agent → treat as long-running.

    FilePart is a strong proxy because every file-bearing turn fires the
    AP pipeline (Extract → Validate → Post). The agent shape check covers
    text-only invocations against pipeline agents.
    """
    # Inspect parts
    if context.message and any(
        getattr(p.root, "kind", None) == "file" for p in (context.message.parts or [])
    ):
        return True
    # Inspect the agent — wired via the factory at mount time
    return _MOUNTED_AGENT_HAS_WORKFLOW
```

**Hint env vars** for forks that want to override:
- `A2A_FORCE_ASYNC_SEND=true` — every send returns early
- `A2A_FORCE_SYNC_SEND=true` — every send blocks (current behaviour, useful for debugging)

#### M3 — SSE verification on `message/stream` (~0.5 day, conditional)

`DefaultRequestHandler.on_message_send_stream` already returns an `AsyncGenerator[Event]` — the FastAPI/Starlette mount converts that into an SSE response. The question is whether ADK's executor actually streams events as they happen (each model token → event → SSE write) or buffers everything until terminal completion.

Two-part verification:

1. **Unit test with `httpx.AsyncClient` against an in-process mount**: capture chunked response timing. Assert at least 3 events arrive >500ms apart for a long-running test agent. If they all arrive together, the executor is buffering and we need an `ExecuteInterceptor.after_event` hook to flush.

2. **Live GE test** (if M1 observation shows GE supports stream): invoke the agent via Gemini Enterprise after the deploy; capture Cloud Logging to confirm the response stayed open for the full pipeline duration with bytes flowing every ~10s.

If M1 finds GE doesn't use `message/stream`, M3 is deferred — the M2 async pattern is sufficient for the live GE story. We still ship the verification test as a regression guard.

### Six Surface Decisions

#### 1. Background-task host — **asyncio.create_task() inside the running event loop**

| Option | When it's right | Pick |
| --- | --- | --- |
| **asyncio.create_task() in the request-handler event loop** | Cloud Run min/max instances bounded; tasks last seconds to minutes | ✓ |
| Cloud Tasks / Pub/Sub fanout | Tasks may last >1 hour; need durability across deploy bounces | Future |
| Celery / Sidekiq | Multi-machine queue with priority + retries | Overkill |

→ asyncio. The Cloud Run service is sized for the AP pipeline's ~minute-class durations. If forks scale to ten-minute jobs, switch to Cloud Tasks — a clear migration path documented in the brief.

#### 2. TaskStore persistence — **InMemoryTaskStore for v1; Firestore-backed for follow-up**

| Option | Pros | Cons | Pick |
| --- | --- | --- | --- |
| **InMemoryTaskStore (current)** | Zero new infrastructure; fast | Per-revision; cold start + scale-out drops in-flight tasks | ✓ v1 |
| Firestore-backed TaskStore | Survives revisions, scale-out | Net-new code; Firestore write per event = cost | Follow-up |

→ InMemory v1. The Cloud Run service has `minInstances=1` and `maxInstances=3`; in practice scale-out during a single pipeline run is unlikely. Add `A2A_TASK_STORE=firestore` env var to enable the Firestore path when a fork needs it — but ship the in-memory default.

#### 3. Polling interval guidance — **set `Retry-After` header on Task with `state: working`**

Peers (including GE) should know how often to poll. The A2A spec doesn't define a canonical hint, but HTTP's `Retry-After` is well-understood. We set it to `2` (seconds) on the initial `state: working` response. Peers that honour it ease the load; peers that ignore it just poll more aggressively.

#### 4. Heartbeat — **rely on terminal events; no synthetic heartbeats in v1**

Every time the SequentialAgent transitions to a new sub-agent, the executor emits a `TaskStatusUpdateEvent` with `state: working` (verified by reading ADK's `A2aAgentExecutorImpl` events). Peers polling `tasks/get` see those state updates as natural heartbeats. No synthetic heartbeat-emitter agent needed.

If forks add Loop agents that don't emit per-iteration events, they should configure `A2aAgentExecutor.config.execute_interceptors[].after_event` to emit a heartbeat per iteration.

#### 5. Cancellation — **wire `tasks/cancel` to `producer_task.cancel()`**

A2A's `tasks/cancel` arrives at `DefaultRequestHandler.on_cancel_task`, which calls the executor's `cancel()` method. ADK's `A2aAgentExecutor.cancel()` calls `producer_task.cancel()` on the matching asyncio task. We get cancellation for free as long as we don't swallow `CancelledError` in our background-task tracking.

Test case: launch a 60s pipeline, fire `tasks/cancel` at 5s, assert the asyncio task is cancelled and the TaskStore's `Task.status.state` becomes `canceled`.

#### 6. Backpressure / queue depth — **soft warn at 20 concurrent tasks; hard cap at 50**

Per-revision soft cap (logged warning at 20 active background tasks) and hard reject (HTTP 429 + JSON-RPC error) at 50. Cloud Run's per-container concurrency is 80 by default; we leave headroom for sync invocations. Configurable via `A2A_MAX_CONCURRENT_TASKS`.

### CLI Surface

The platform's `aiplatform a2a` group already has `invoke` and `card`. The async pattern needs polling, cancellation, and resubscription affordances:

```bash
# Returns immediately with a task_id, JSON-formatted
aiplatform a2a invoke <url> --file invoice.docx --async

# Poll the task status
aiplatform a2a task <task-id> --url <agent-url>

# Block until terminal, printing each state transition
aiplatform a2a task <task-id> --url <agent-url> --watch

# Cancel a running task
aiplatform a2a task cancel <task-id> --url <agent-url>

# Re-attach to a streaming task (SSE)
aiplatform a2a task resubscribe <task-id> --url <agent-url>
```

~0.3 day for the four subcommands + httpx calls + tests, slotting under the existing `aiplatform a2a` group.

### Backend Changes

**New file** — `backend/protocols/a2a_async_handler.py` (~120 LOC):
- `AsyncOnLongRunRequestHandler(DefaultRequestHandler)` — subclass with overridden `on_message_send`
- `_default_long_running_detector(context) -> bool` — detector function checking parts + agent shape
- Module-level `_MOUNTED_AGENT_HAS_WORKFLOW` (set at mount time)
- Soft warn + hard cap logic on `_background_tasks` count
- Env-var overrides parsing

**Modified** — `backend/protocols/a2a_invocation.py` (~20 LOC delta):
- Replace `request_handler = DefaultRequestHandler(...)` with `AsyncOnLongRunRequestHandler(...)`
- Detect agent shape (walk `agent.sub_agents` looking for `SequentialAgent` / `LoopAgent` / `ParallelAgent`) and set `_MOUNTED_AGENT_HAS_WORKFLOW`
- Hand a `Retry-After: 2` header via Starlette response middleware on Task-with-working responses

**New file** — `backend/tests/api_tests/test_a2a_async.py` (~250 LOC):
- M1 instrumentation tests (verify logging hooks fire)
- M2 async-send tests:
  - `test_message_send_returns_working_for_workflow_agent` — POST against a SequentialAgent mount, assert response within 2s with `state: submitted/working`
  - `test_message_send_blocks_for_short_chat` — POST against a pure LlmAgent mount, assert blocking behaviour preserved
  - `test_tasks_get_reflects_background_completion` — POST send, poll get 3x at 1s intervals, assert state transitions through `working` → `completed`
  - `test_tasks_cancel_halts_running_pipeline` — POST send long task, fire cancel after 200ms, assert task ends as `canceled`
  - `test_force_async_send_env_var_overrides_detector` — `A2A_FORCE_ASYNC_SEND=true` + short LlmAgent → still async
  - `test_concurrent_tasks_hit_soft_warn_log` — fire 21 invocations, assert log line about backpressure
- M3 streaming tests:
  - `test_message_send_stream_returns_chunked_events` — assert at least 3 events arrive >500ms apart from a multi-step agent
  - `test_resubscribe_reattaches_to_running_task` — POST stream, drop, resubscribe, assert remaining events flow

**Modified** — `cli/aiplatform/commands/a2a.py`:
- Add `task` subcommand group with `get` / `watch` / `cancel` / `resubscribe`
- `invoke --async` flag for return-early semantics

**Modified** — `scripts/simulate-a2a-peer.py`:
- New Step 9 — async send + poll cycle. Assert initial `state: working` arrives <2s; poll to terminal `completed`.

### API Changes

| Method | Endpoint | Description | Breaking? |
|--------|----------|-------------|-----------|
| POST | `/a2a/` `method: message/send` | (modified) Returns `Task(state=working)` early for long-running agents; peer expected to poll | **No** — Task envelope shape is spec-defined; peers already handle `state: working` per A2A v0.2 |
| POST | `/a2a/` `method: tasks/get` | (existing in ADK) Returns latest Task snapshot | No |
| POST | `/a2a/` `method: tasks/cancel` | (existing in ADK) Cancels a running task | No |
| POST | `/a2a/` `method: tasks/resubscribe` | (existing in ADK) Re-attach to an SSE event stream | No |
| POST | `/a2a/` `method: message/stream` | (existing in ADK) SSE-stream events | No |

### Architecture

```
peer / GE
  │
  │ message/send (file or workflow-bound)
  ▼
[Next.js → FastAPI /a2a mount]
  ▼
[AsyncOnLongRunRequestHandler.on_message_send]
  │
  │ Detect long-running:
  │  - FilePart present? YES → async
  │  - Agent has Sequential/Loop/Parallel sub-agent? YES → async
  │  - else: fall through to parent behaviour (sync block)
  │
  ▼ (long-running path)
[Setup execution: build queue, producer_task, task_id]
  │
  ├─→ task_store.save(Task(state=submitted, task_id=<id>))   # ADK does this
  │
  ├─→ asyncio.create_task(producer_task)                      # NOT awaited
  │   ↓
  │   [A2aAgentExecutor executes agent]
  │   ↓
  │   [TaskStatusUpdateEvent(working) → task_store update]
  │   ↓
  │   [Agent completes; TaskStatusUpdateEvent(completed) → task_store update]
  │
  └─→ Return Task(state=working, task_id=<id>) IMMEDIATELY  # <2s
       + Retry-After: 2

  Peer side:
  ─────────
  POST tasks/get(id=<id>)  → Task snapshot from task_store
  POST tasks/get(id=<id>)  → still working
  POST tasks/get(id=<id>)  → Task(state=completed, artifacts=[…])
```

## Implementation Plan

### M1 — Observation (~1 hour)

- [ ] Add logging in `A2AAuthMiddleware` (or a new lightweight middleware) capturing `request.url.path`, `method` (parse JSON-RPC body), `User-Agent`, `task_id` from request body if present (~30 LOC)
- [ ] Deploy; trigger 1× GE upload of `acme-gmbh-invoice-2026-042.docx`; wait 2 minutes for completion (or timeout)
- [ ] Pull Cloud Logging for the window; document observed pattern in `docs/learnings/template-pr-a2a-spec-compliance.md` under a new §8a — "What Gemini Enterprise actually does"
- [ ] Decision point: M2 only, M3 only, or both? Update this design doc + sprint plan accordingly

### M2 — Async `message/send` (~0.5 day, conditional but likely required)

- [ ] Create `backend/protocols/a2a_async_handler.py` with `AsyncOnLongRunRequestHandler` + `_default_long_running_detector` (~120 LOC)
- [ ] Wire into `protocols/a2a_invocation.py`, set `_MOUNTED_AGENT_HAS_WORKFLOW` via the agent factory (~20 LOC delta)
- [ ] Tests in `tests/api_tests/test_a2a_async.py` — six core tests covering detection, blocking fallback, poll-to-completion, cancellation, env-var override, backpressure warn (~250 LOC)
- [ ] CLI `aiplatform a2a task get/watch/cancel/resubscribe` (~120 LOC) + 4 unit tests (~80 LOC)
- [ ] Extend `scripts/simulate-a2a-peer.py` with Step 9 (async send + poll) (~50 LOC)
- [ ] Local smoke: backend on :1957, `aiplatform a2a invoke ... --async` returns task_id <2s; `aiplatform a2a task watch <id>` prints state transitions in real time
- [ ] Deploy; live verification via `verify-a2a.sh` + simulate script against the deployed agent
- [ ] Gemini Enterprise upload test: full pipeline runs cleanly; GE renders the final response without `ECONNRESET`

### M3 — SSE verification on `message/stream` (~0.5 day, conditional on M1)

- [ ] Unit test capturing chunked-response timing on `message/stream` (~80 LOC)
- [ ] If buffering observed, add `ExecuteInterceptor.after_event` flush handler (~50 LOC)
- [ ] CLI `aiplatform a2a stream <url>` for manual streaming inspection (~50 LOC)
- [ ] Update `scripts/simulate-a2a-peer.py` Step 5 to consume the stream properly (we currently treat sendSubscribe as a single response) (~30 LOC)
- [ ] If M1 says GE supports `message/stream`: real GE test
- [ ] Extend `docs/learnings/template-pr-a2a-spec-compliance.md` with §8 covering the async pattern + the streaming pattern + the trade-offs

## Migration & Rollout

**Feature flag:**
- `A2A_ASYNC_SEND=auto` (default) — long-running detector picks; both shapes still work
- `A2A_ASYNC_SEND=force` — every send returns early
- `A2A_ASYNC_SEND=off` — every send blocks (the M2-disabled behaviour for emergency revert)

**Rollback:** flip `A2A_ASYNC_SEND=off` + redeploy. The custom request handler still mounts but behaves identically to the parent `DefaultRequestHandler.on_message_send`.

**Environment Variables:**
- `A2A_ASYNC_SEND` — `auto` (default) / `force` / `off`
- `A2A_MAX_CONCURRENT_TASKS` — soft warn at half this number, hard reject at this number (default 50)
- `A2A_TASK_STORE` — `memory` (default) / `firestore` (follow-up implementation)

**Re-registration with Gemini Enterprise:** none required. The card shape doesn't change.

## Testing Strategy

### Backend Tests (pytest)

- [ ] Six M2 tests in `test_a2a_async.py` (above)
- [ ] Two M3 tests for streaming + resubscribe
- [ ] All ~37 existing a2a tests still green
- [ ] `make lint && make test-fast` both green

### Integration Tests

- [ ] `scripts/simulate-a2a-peer.py` against live deploy with Step 9 (async send + poll cycle)
- [ ] `scripts/verify-a2a.sh` extended to add a Task-watch loop

### Manual Testing

- [ ] Upload `acme-gmbh-invoice-2026-042.docx` via Gemini Enterprise; confirm UI shows final response with no `ECONNRESET` regardless of pipeline length
- [ ] Cancel a long-running task via `aiplatform a2a task cancel`; confirm Cloud Logging shows the asyncio cancellation
- [ ] Fire 25 concurrent invocations; confirm soft-warn log line at 20

## Security Considerations

- **Task ownership**: `tasks/get` / `tasks/cancel` should only succeed for the calling peer's tasks. ADK's `task_store.get()` doesn't enforce ownership by default — add a per-task owner check keyed on the request's `call_context.user.user_name` (which our auth middleware sets when `A2A_INVOCATION_REQUIRE_AUTH=true`).
- **Background task leakage**: a misbehaving peer could trigger many concurrent long-running tasks. The soft-warn + hard-cap pattern is the defence; document the cap in the operator runbook.
- **Cancellation as resource starvation**: peer could DoS by spamming start-then-cancel cycles. Mitigation: rate-limit `message/send` per peer identity (out of scope for v1; documented as a known risk for forks).
- **No new egress.** Background tasks run in the same Cloud Run process; no third-party calls added.

## Performance Considerations

- **Initial response latency** (`message/send` → first Task envelope): target <2s. Limit is how fast ADK's executor emits the `submitted` event after parsing the request — measured at <100ms in M1 of A2A-INVOKE.
- **Polling overhead**: 1 Firestore-read per `tasks/get` (when InMemoryTaskStore is swapped). Peers should respect `Retry-After: 2`. Worst case: 50 concurrent peers polling every second = 50 reads/s = trivial Firestore cost.
- **Background task memory**: each long-running task holds its own asyncio task, event queue, agent state. Estimate 5-10MB per task. At 50 concurrent (the hard cap), ~500MB — well within Cloud Run's 1GB-2GB per-container budget.
- **Cold start impact**: if the Cloud Run instance scales to zero between invocations, the next call pays ~3-5s of cold start. Async send still helps because the cold start happens before the response returns, not on top of a 65s wait.

## Success Criteria

For M1:
- [ ] We have a documented description of GE's behaviour (which method, polls?, latency) committed in the template-PR brief

For M2 (assuming M1 confirms it's needed):
- [ ] `aiplatform a2a invoke ... --async` returns within 2s with a task_id
- [ ] `aiplatform a2a task watch <id>` prints `submitted → working → working → completed` over the pipeline duration
- [ ] Live GE upload of `acme-gmbh-invoice-2026-042.docx` produces a clean final response (no `ECONNRESET`, no truncation)
- [ ] `tasks/cancel` halts a running pipeline within 5s
- [ ] All ~45 backend a2a tests pass; `make lint && make test-fast` clean
- [ ] Soft-warn log fires at 20 concurrent tasks; HTTP 429 at 50

For M3 (conditional):
- [ ] `message/stream` returns a real SSE stream with events flushed individually
- [ ] `tasks/resubscribe` re-attaches mid-flight

## Open Questions

- **Does ADK's `DefaultRequestHandler._setup_message_execution` actually persist the initial submitted Task to the task_store before returning?** If yes, we just need a short wait + `task_store.get(task_id)` to get the snapshot. If no, we need to read off the queue ourselves and reconstruct the Task. M2 starts with a 5-min ADK source dive to confirm.
- **What does GE do on a 429 from `message/send`?** Retry? Surface to user? Black-hole? Worth a deliberate test in M2.
- **Does GE honour `Retry-After`?** Unknown. If yes, we can throttle polling. If no, we get hammered. Either way, harmless to set the header.
- **Per-tenant task isolation**: today we have ONE deployed Cloud Run service that all peers hit. If we go multi-tenant (per-peer task quota), the `_max_concurrent_tasks` needs to be per-peer-identity. Out of scope for v1.

## Related Documents

- [A2A `message/send` bridge (implemented)](./implemented/a2a-message-send-bridge.md) — the M2 + M3 from A2A-INVOKE this design extends
- [A2A file-input + org-scoped buckets (implemented)](./implemented/a2a-file-input.md) — the A2A-FILES sprint this design unblocks (file uploads are exactly the long-running case)
- [A2A AILANG-parse integration (planned)](./a2a-ailang-parse.md) — sibling design; can land before or after this one without coupling
- [Template-PR brief — A2A spec compliance](../../../learnings/template-pr-a2a-spec-compliance.md) — folds in as §8 after implementation
- Source verified during design:
  - `a2a.server.request_handlers.default_request_handler.DefaultRequestHandler` — has `_running_agents: dict[str, asyncio.Task]`, `_background_tasks: set[asyncio.Task]`, `on_message_send`, `on_message_send_stream`, `on_get_task`, `on_cancel_task`, `on_resubscribe_to_task`
  - `a2a.types.TaskState` — values verified: `submitted`, `working`, `input-required`, `completed`, `canceled`, `failed`, `rejected`, `auth-required`, `unknown`
- A2A v0.2 spec: <https://a2aproject.github.io/A2A/v0.2>
