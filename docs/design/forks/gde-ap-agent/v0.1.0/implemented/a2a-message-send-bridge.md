# A2A `message/send` bridge

**Status**: Implemented
**Priority**: P1 (Medium) — closes the only remaining gap in the Track 3 "discover AND coordinate" criterion
**Estimated**: ~0.5 day implementation + tests + verification
**Scope**: Backend
**Dependencies**:
- A2A spec-compliance fixes already shipped (commits 236fdcb / dbc5856 / 956fafe / 6c2aea4)
- `google-adk` package already installed (verified `google.adk.a2a.utils.agent_to_a2a.to_a2a`)
- `agents-cli register-gemini-enterprise` registration already proven against `multivac-internal-dev` Agentspace app
**Created**: 2026-06-07
**Last Updated**: 2026-06-07 (implemented)
**Upstream-bound**: Yes — every fork on the `ai-protocol-platform` template hits the same six surface decisions. This doc doubles as the upstream PR brief.

## Problem Statement

The deployed agent passes A2A *discovery* end-to-end (card fetched at `/.well-known/agent.json` is spec-compliant, registered as a tool in a Gemini Enterprise Agentspace app, capability negotiation round-trips via `X-A2A-Extensions`) but does **not** implement A2A *invocation*. A peer agent that follows the spec strictly — POST a JSON-RPC `message/send` to the URL the card advertises — gets HTTP 405 because no such endpoint exists.

**Current State (verified by `scripts/simulate-a2a-peer.py` against the live deploy):**
- ✅ `GET /.well-known/agent.json` returns 200 with the full A2A v0.2 card shape
- ✅ `X-A2A-Extensions` round-trips with capability negotiation
- ✅ Card advertises 5 skills with descriptions, IDs, and `streaming: true`
- ✅ Agent registered as `projects/374404277595/.../agents/6125274250691649337` in `multivac-internal-dev` / Agentspace
- ❌ `POST <card.url>` with `{jsonrpc:"2.0", method:"message/send", ...}` → HTTP 405
- ❌ The whole right-hand half of the criterion ("coordinate with other enterprise agents") is unproven

**Impact:**
- **Track 3 submission story**: Discovery is proven. Invocation is the gap; closing it makes "coordinate" a green tick rather than a footnote.
- **Future forks** of the `ai-protocol-platform` template: every fork inherits the gap. Closing it once upstream means every fork ships with strict A2A interop from day one.
- **Real cross-agent workflows**: a peer in the same Agentspace today cannot programmatically invoke this agent through the published A2A surface — it would have to know about our private AG-UI streaming route (`/api/skill/{id}/stream`), defeating the point of A2A.

## Goals

**Primary Goal:** Make `POST <card.url>` (or `<card.url>/a2a`) with a strict A2A v0.2 JSON-RPC `message/send` payload return 200 with a valid `Task` / response object, processed through our existing `Runner` so sessions, observability, and skill behaviour all flow through one path.

**Success Metrics:**
- `scripts/simulate-a2a-peer.py` step 4 ("Attempt strict A2A `message/send`") prints `✓` instead of `⚠ 405`
- A new test in `backend/tests/api_tests/test_a2a_invocation.py` covers JSON-RPC `message/send` end to end against an in-memory runner
- One peer-agent round-trip through Gemini Enterprise (peer agent in the same Agentspace invokes us; we respond) demonstrates the full criterion
- No regression in existing AG-UI streaming behaviour at `/api/skill/{id}/stream`
- ADK Agent Engine session storage continues to track invocations (so chat history and trace continuity hold)

**Non-Goals:**
- **Implementing every A2A v0.2 method from scratch.** We use ADK's `to_a2a()` adapter that ships the full surface (`message/send`, `message/sendSubscribe`, `tasks/get`, `tasks/cancel`, push notifications) — we are bridging, not implementing.
- **One A2A endpoint per skill.** v1 exposes only `ap-orchestrator` via A2A (the conversational entry-point that already routes to the SequentialAgent pipeline). Per-skill A2A mounts are a follow-up if needed.
- **Replacing AG-UI.** The frontend continues to consume the AG-UI stream; A2A is an additional surface for cross-agent invocation only.
- **Auth model overhaul.** A2A invocation mirrors the same Firebase ID token / guest token policy the existing `/api/skill/{id}/stream` route enforces — no new auth scheme.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | `to_a2a` supports `message/sendSubscribe` SSE streaming — first-token latency parity with AG-UI |
| 2 | EARNED TRUST | 0 | No change to citation/confidence path; A2A is a transport, not a content layer |
| 3 | SKILLS, NOT FEATURES | +1 | Skill remains the user-facing abstraction; A2A is the wire format other agents see it through |
| 4 | RIGHT MODEL, RIGHT MOMENT | 0 | Same model routing — A2A just delivers the call to the same `Runner` |
| 5 | GRACEFUL DEGRADATION | +1 | If the bridge fails, discovery still works; existing AG-UI stream unaffected. ADK `to_a2a` returns standard JSON-RPC errors on failure modes |
| 6 | PROTOCOL OVER CUSTOM | +1 | The whole point — replaces the missing surface with the spec-standard JSON-RPC, no custom protocol |
| 7 | API FIRST | +1 | A2A is the cross-agent API; closing this means our skill surface is uniform across web (AG-UI) + cross-agent (A2A) channels |
| 8 | OBSERVABLE BY DEFAULT | +1 | Shares the `Runner`, so OTel traces, BigQuery logging, and Agent Engine session storage all inherit; no observability gap |
| 9 | SECURE BY CONSTRUCTION | +1 | Auth mirrors `/api/skill/{id}/stream`; nothing leaves the GCP project; no new trust boundary |
| 10 | THIN CLIENT, FAT PROTOCOL | 0 | Backend-only change; no client impact |
| | **Net Score** | **+7** | Threshold: >= +4 ✓ |

**Conflict Justifications:** None — no -1 scores.

## Standards Compliance

**Adopts:** A2A protocol v0.2 (via `protocolVersion: "0.2.0"` already on the card; ADK's `to_a2a` defaults to 0.3.0 — we'll keep 0.2.0 for continuity with what Discovery Engine already accepted, and bump in a separate change once we verify 0.3.0 acceptance).

**Adopts:** Google ADK's built-in A2A adapter (`google.adk.a2a.utils.agent_to_a2a.to_a2a`) — no custom JSON-RPC handling. Note ADK's A2A surface is marked `@a2a_experimental`; track upstream API churn.

**Does not invent:** anything. The bridge is glue between two existing standards-compliant components.

## Design

### Overview

Mount ADK's `to_a2a()` Starlette sub-app onto our FastAPI at `/a2a`, passing it our existing `Runner` (so sessions, models, and observability flow through one pipeline) and our hand-authored `AgentCard` (so the extension descriptors, protocolVersion, and skill catalogue we already ship don't get re-derived by ADK's card builder and drift). Update the well-known route's URL rewrite to advertise `https://<host>/a2a` as the invocation target. Wrap the mount with the same Firebase auth dependency the existing `/api/skill/{id}/stream` route enforces.

### Six Surface Decisions

The six questions that need locking in before any keyboard time:

#### 1. URL mount point — **`/a2a` sub-app**

| Option | Pros | Cons | Pick |
| --- | --- | --- | --- |
| Mount at `/a2a` | Clean separation; existing routes untouched; `card.url` clearly points at the A2A surface | Two URL surfaces (`/api/skill/*` for in-app, `/a2a/*` for cross-agent) | ✓ |
| Mount at root | One canonical URL; matches the spec's implicit "card.url IS the JSON-RPC endpoint" reading | Collides with existing routes; can't preserve auth model cleanly | ✗ |
| Sub-domain (`a2a.host`) | Strict isolation | New DNS + cert; overkill for v1 | ✗ |

→ `card.url` becomes `https://<host>/a2a` (was `https://<host>`).

#### 2. Card authoring — **pass our `_build_card()` output to `to_a2a(agent_card=...)`**

ADK's `to_a2a` accepts `agent_card: Optional[Union[AgentCard, str]]`. If unset it auto-builds via `AgentCardBuilder`, which would re-derive the card from agent metadata and lose:
- our 7 extension descriptors (a2ui-*, mcp-apps-v1, adk-workflow-v1)
- our `protocolVersion: "0.2.0"` (ADK default is 0.3.0)
- our hand-tuned skill descriptions

→ Pass our card. Add a thin adapter that converts `_build_card()`'s dict output to ADK's `AgentCard` pydantic model. The well-known route keeps serving the dict shape unchanged.

#### 3. Skill selection — **single mount, `ap-orchestrator` only (v1)**

A2A's `message/send` invokes "the agent" — singular. Options:

| Option | Surface | Verdict |
| --- | --- | --- |
| **Single mount, orchestrator only** | `POST /a2a/v1/messages` → orchestrator (already routes to pipeline) | ✓ v1 |
| Per-skill mounts | `POST /a2a/v1/{skill_id}/messages` × 5 | Follow-up if peers ask for direct specialist access |
| Router by `params.message` content | Inspect message, dispatch | Premature; the orchestrator already does this in prose |

→ v1 exposes `ap-orchestrator` only. The orchestrator's existing `transfer_to_agent` to `ap-pipeline` handles specialist routing internally. Per-skill mounts are a follow-up if needed.

#### 4. Streaming overlap with AG-UI — **two surfaces, one runner**

| Surface | URL | Consumer | Protocol |
| --- | --- | --- | --- |
| AG-UI | `/api/skill/{id}/stream` | Frontend (browser, mobile) | AG-UI SSE event protocol |
| A2A | `/a2a/v1/messages:sendSubscribe` | Peer agents, Gemini Enterprise | A2A SSE (`Task` events) |

Both delegate to the same `Runner`. Same model invocations, same OTel traces, same session writes. The wire format differs; the agent's behaviour does not. No collision because the URLs are disjoint.

#### 5. Session model overlap with ADK Agent Engine — **share the same `Runner`**

ADK's `to_a2a(runner=...)` accepts a pre-built `Runner`. Our existing runner already uses `VertexAiSessionService` (when `AGENT_ENGINE_ID` is set) for persistence. Reuse it; A2A invocations become session-equivalent to AG-UI invocations.

A2A's `Task` ID is bound to the ADK session ID (1:1). The card's `capabilities.stateTransitionHistory: False` matches our model: session events are the source of truth, not a task-history list.

#### 6. Auth — **mirror `/api/skill/{id}/stream`**

Discovery (well-known) stays unauthenticated. Invocation (`/a2a/*`) requires the same Firebase ID token / guest token policy the existing skill stream uses. Implementation: a Starlette middleware on the mounted A2A app that runs the same `get_current_user` dependency before delegating to ADK's executor.

Gemini Enterprise's registration captures the agent owner's credentials and re-presents them when routing peer calls — we don't need a separate trust contract for that path.

### Backend Changes

**New file** — `backend/protocols/a2a_invocation.py` (~80 lines):
- Wraps `to_a2a()` with our `Runner` and converted `AgentCard`
- Exposes a `build_a2a_app(orchestrator_agent: BaseAgent, runner: Runner) -> Starlette` factory
- Includes a thin `auth_middleware` wrapping the mount with Firebase token verification

**Modified** — `backend/protocols/a2a.py`:
- Split `_build_card()` into `_build_card_dict()` (current behaviour, returns dict for the well-known JSON response) and `_build_card_model()` (returns ADK's `AgentCard` pydantic model for `to_a2a`)
- Both share the same `SUPPORTED_EXTENSION_INFO` source of truth
- `_build_card_dict()` advertises `url = f"{base_url}/a2a"` (the invocation surface), not the bare base URL

**Modified** — `backend/fast_api_app.py`:
- Import `build_a2a_app` and the orchestrator agent + runner from the existing agent factory
- `app.mount("/a2a", build_a2a_app(orchestrator, runner))` after the existing FastAPI routes register
- Log at startup which agent is exposed

**Modified** — `frontend/src/app/.well-known/agent.json/route.ts`:
- `publicOrigin(req)` is fine as-is; the backend now advertises `<origin>/a2a` in `card.url` directly
- No frontend code change needed beyond what's already shipped

**New test** — `backend/tests/api_tests/test_a2a_invocation.py`:
- `test_a2a_message_send_returns_jsonrpc_response`: POST a `message/send` JSON-RPC payload, assert 200 + valid `Task` envelope with `id`, `status`, `parts`
- `test_a2a_message_send_requires_auth`: POST without token → 401
- `test_a2a_send_subscribe_streams_events`: open `message/sendSubscribe`, assert SSE events flow
- `test_a2a_card_url_matches_mount`: assert `card.url` ends with `/a2a` (regression guard for the well-known rewrite)

**Modified** — `scripts/simulate-a2a-peer.py`:
- Step 4 now expects HTTP 200 — change the `⚠ 405` branch to a regression failure
- Add a Step 5 that calls `message/sendSubscribe` and prints the streamed event names

**Modified** — `scripts/verify-a2a.sh`:
- Add an invocation probe: POST a `message/send` to `card.url` with a minimal payload, assert HTTP 200 + JSON-RPC envelope

### API Changes

| Method | Endpoint | Description | Breaking? |
|--------|----------|-------------|-----------|
| POST   | `/a2a/v1/messages` (or whatever path `to_a2a` mounts) | A2A `message/send` JSON-RPC | No (new) |
| POST   | `/a2a/v1/messages:sendSubscribe` | A2A streaming SSE | No (new) |
| GET    | `/a2a/v1/tasks/{task_id}` | Task status polling | No (new) |
| POST   | `/a2a/v1/tasks/{task_id}:cancel` | Task cancellation | No (new) |
| GET    | `/.well-known/agent.json` | (modified) `card.url` now points at `/a2a` not root | **Yes** — peers reading the OLD card after registration won't auto-update, but they re-fetch on each discovery so the change propagates within one round-trip |

The exact A2A path layout under `/a2a` is whatever ADK's `to_a2a` defines — we don't pick those URLs, the adapter does. We'll document the actual paths in the success-criteria after implementation.

### Architecture

```
Peer agent (Gemini Enterprise, A2A peer, etc.)
   │
   │ 1. GET /.well-known/agent.json
   ▼
[Next.js well-known route]
   │ → proxies to backend /.well-known/agent.json
   ▼
[FastAPI /.well-known/agent.json] ←── card.url = https://host/a2a
   │
   │ 2. POST /a2a/v1/messages  (jsonrpc message/send)
   ▼
[FastAPI /a2a mount]
   │ → auth middleware (Firebase ID token)
   ▼
[ADK to_a2a Starlette app]
   │ → A2aAgentExecutor
   ▼
[Existing Runner]  ←── shared with /api/skill/{id}/stream
   │
   ├── Vertex AI Agent Engine (sessions)
   ├── Gemini / Vertex AI (model)
   ├── Vertex AI Search (grounding)
   └── OTel → Cloud Trace + BigQuery
```

## Implementation Plan

### Phase 1 — Bridge plumbing (~0.3 day)
- [ ] Add `_build_card_model()` to `backend/protocols/a2a.py` returning ADK's `AgentCard` pydantic model, sharing source of truth with `_build_card_dict()` (~30 LOC)
- [ ] Update `_build_card_dict()` to advertise `url = base_url + "/a2a"` (~5 LOC, plus update tests)
- [ ] Create `backend/protocols/a2a_invocation.py` exporting `build_a2a_app(agent, runner) -> Starlette` (~80 LOC)
- [ ] Mount in `backend/fast_api_app.py` (~10 LOC, gated on a feature flag for safe rollback)

### Phase 2 — Auth + tests (~0.15 day)
- [ ] Starlette middleware that runs the existing `get_current_user` against the request before delegating to ADK's executor (~30 LOC)
- [ ] `backend/tests/api_tests/test_a2a_invocation.py` — 4 tests as listed above (~150 LOC)
- [ ] Update `backend/tests/api_tests/test_a2a.py:_build_card` assertions for the new `card.url` shape (~5 LOC)
- [ ] All 17+ A2A tests green; ruff check + ruff format clean

### Phase 3 — Verification + brief update (~0.05 day)
- [ ] `scripts/simulate-a2a-peer.py`: Step 4 expects 200; add Step 5 for `sendSubscribe`
- [ ] `scripts/verify-a2a.sh`: add invocation probe
- [ ] Deploy to dev; re-run `simulate-a2a-peer.py` against the live deploy; capture transcript
- [ ] Update [`docs/learnings/template-pr-a2a-spec-compliance.md`](../../../learnings/template-pr-a2a-spec-compliance.md) with the bridge as the fourth template-PR item

## Migration & Rollout

**Feature flag:**
- New env var `ENABLE_A2A_INVOCATION` (default `false`). When false, `/a2a` is not mounted and behaviour is identical to today.
- Set to `true` in `cloudbuild.yaml` for dev once the test suite is green. Promote to test then prod with the standard branch-deploy pattern.

**Rollback Plan:**
- Set `ENABLE_A2A_INVOCATION=false` (no env-var change needed if it's already a flag default-false rollout) and redeploy. The `/a2a` mount disappears; discovery and AG-UI unaffected.
- If the well-known card already advertises `<host>/a2a`, peers will get 404 on invocation — degraded but not catastrophic. To fully revert, also revert the `_build_card_dict()` URL rewrite. Both reverts are single-line.

**Environment Variables:**
- `ENABLE_A2A_INVOCATION` — `true` to mount, `false` to skip. Set in Cloud Build substitutions per environment.
- No new secrets. Reuses `AGENT_ENGINE_ID`, Firebase project credentials, etc.

**Re-registration with Gemini Enterprise:**
- After deploy, re-run `agents-cli register-gemini-enterprise --registration-type a2a ...` so the GE registration picks up the new `card.url`. Idempotent per the publish skill — "Agent already registered" is not an error and the command updates the existing entry.

## Testing Strategy

### Backend Tests (pytest)
- [ ] `test_a2a_invocation.py` (4 new tests, see above)
- [ ] `test_a2a.py` updated assertions for `card.url` ending in `/a2a`
- [ ] All existing 13 A2A tests still pass (no regression in discovery/negotiation/extension shape)

### Integration Tests
- [ ] `scripts/verify-a2a.sh` against the live deploy — `Vary` correct, descriptors correct, invocation returns 200
- [ ] `scripts/simulate-a2a-peer.py` against the live deploy — all 6 steps print `✓`

### Manual Testing
- [ ] Re-register with Gemini Enterprise; confirm console still shows the agent with the updated `card.url`
- [ ] Open the Agentspace UI; invoke the agent through Gemini Enterprise's own routing (the part we couldn't verify before because we had no invocation endpoint); capture transcript
- [ ] Confirm session shows up in Agent Engine session list with the A2A-generated task ID

## Security Considerations

- **Auth boundary**: invocation requires the same Firebase ID token / guest token as `/api/skill/{id}/stream`. Same middleware runs first; ADK's executor never sees an unauthenticated request.
- **Data egress**: zero new. ADK's `to_a2a` runs inside the GCP project; sessions go to Agent Engine; OTel goes to Cloud Trace + BigQuery (all internal per Axiom #9). No new external trust relationships.
- **Input validation**: A2A's JSON-RPC envelope is shape-validated by ADK's pydantic models; malformed payloads return JSON-RPC errors not 500s.
- **Prompt injection**: A2A payloads land in the same `Runner` as AG-UI payloads. The same agent-instruction injection defences apply (no new attack surface from the bridge itself; A2A peers are no more trusted than web users).
- **Push notifications**: ADK's `to_a2a` accepts a `push_config_store=` parameter. v1 uses the default in-memory store (no external webhook posts). If forks later enable push, they must add a webhook allow-list per Axiom #9.

## Performance Considerations

- **Latency overhead of the bridge**: one extra pydantic validation per request; sub-ms. ADK's executor sits between the wire and our `Runner` and runs the same model invocation we'd run from AG-UI. Expected first-token latency parity with AG-UI (Axiom #1).
- **Memory**: the in-memory push-config store grows with active push subscriptions. If we enable push at scale, swap for Firestore-backed store.
- **Bundle size**: zero impact (backend-only change, no frontend code).
- **Cache behaviour**: the A2A invocation path is `Cache-Control: no-store` by design (JSON-RPC over POST). The discovery path's `Vary: X-A2A-Extensions` correctness (already shipped in 6c2aea4) is unchanged.

## Success Criteria

- [ ] All backend tests passing (`cd backend && make test-fast`)
- [ ] Lint + format clean (`cd backend && make lint`)
- [ ] `scripts/verify-a2a.sh` against deployed dev — all green
- [ ] `scripts/simulate-a2a-peer.py` step 4 returns HTTP 200 with a valid JSON-RPC `Task` envelope
- [ ] `agents-cli register-gemini-enterprise` re-registration succeeds (card URL update propagates)
- [ ] One Agentspace-mediated peer invocation completes (manual test, transcript captured)
- [ ] `docs/learnings/template-pr-a2a-spec-compliance.md` extended with §5 covering this bridge
- [ ] No regression in `/api/skill/{id}/stream` AG-UI behaviour (manual: load the workbench chat, run an invoice through the pipeline, audit chips light up)

## Open Questions

- **ADK `to_a2a` is `@a2a_experimental`**: how stable is the API shape? Plan: pin a known-working `google-adk` version in `pyproject.toml`; revisit on ADK minor bumps.
- **`protocolVersion` 0.2.0 vs 0.3.0**: ADK's `AgentCard` defaults to `"0.3.0"`; Discovery Engine accepted our 0.2.0. We'll keep 0.2.0 in v1 for continuity. Confirm Discovery Engine accepts 0.3.0 in a follow-up; bump as a separate, single-line change.
- **A2A `Task` vs ADK session lifecycle**: ADK sessions persist via Agent Engine; A2A `Task` is normally a short-lived envelope. Verify there's no double-billing or duplicate session creation when `to_a2a` opens its own runner — solved by passing our pre-built `Runner` (already in the design), but confirm in tests.
- **Per-skill A2A mounts**: do peers actually want direct specialist access (e.g., "call ap-validator standalone via A2A"), or is orchestrator-only sufficient? Decision deferrable until a peer asks.

## Related Documents

- [Gemini Enterprise + A2UI Alignment](./gemini-enterprise-a2ui-alignment.md) — the broader theme-by-theme alignment with Google's practitioner's guide
- [Submission readiness](./submission-readiness.md) — original Track 3 sprint plan
- [Devpost form answers](./devpost-form-answers.md) — Q4/Q5 reference the A2A path explicitly
- [Template-PR brief — A2A spec compliance](../../../learnings/template-pr-a2a-spec-compliance.md) — the upstream PR brief this design doc folds into as a fourth section
- [Template-protocols friction log](../../../learnings/template-protocols-friction.md) — Friction 22/23/24 already cover the discovery-side bugs; this doc adds Friction 25 (the invocation bridge) after implementation
- ADK source verified during design: `google.adk.a2a.utils.agent_to_a2a.to_a2a`, `google.adk.a2a.executor.a2a_agent_executor.A2aAgentExecutor`, `google.adk.a2a.utils.agent_card_builder.AgentCardBuilder`
- A2A v0.2 spec: <https://a2aproject.github.io/A2A/v0.2>
