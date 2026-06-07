# Sprint Plan: A2A-INVOKE — A2A `message/send` Bridge

## Summary

Mount ADK's `to_a2a()` Starlette adapter on our FastAPI at `/a2a`, sharing the existing `Runner` and hand-authored `AgentCard` so peer agents can invoke `ap-orchestrator` via strict A2A v0.2 JSON-RPC. Closes the gap surfaced by `scripts/simulate-a2a-peer.py` (HTTP 405 on `message/send`).

**Duration:** 0.5 day (~4 hours)
**Scope:** Backend
**Dependencies:**
- A2A spec-compliance fixes already shipped (236fdcb / dbc5856 / 956fafe / 6c2aea4)
- `google-adk` already provides `to_a2a`, verified against installed package
**Risk Level:** Low — every API verified against installed source; rollback is `ENABLE_A2A_INVOCATION=false`
**Design Doc:** [a2a-message-send-bridge.md](./a2a-message-send-bridge.md)

## Current Status Analysis

### Recent Velocity (last 3 days)

- 50 commits / 3 days = ~17 commits/day
- 6,549 LOC delta across 61 files
- 7 of last 20 commits are A2A-domain work — high familiarity
- Estimated capacity for this sprint: ~350 LOC (~2 hours of code, ~1.5 hours of tests + verification)

### Existing Implementation We Build On

- `backend/protocols/a2a.py` — discovery card already spec-compliant (`protocolVersion`, `AgentExtension` descriptors, capability negotiation)
- `backend/adk/agent.py` — agent factory + `Runner` builder already exists
- `backend/fast_api_app.py` — Starlette-based FastAPI app, supports `app.mount()`
- `frontend/src/app/.well-known/agent.json/route.ts` — URL rewrite already pulls public origin from request
- 13 passing tests in `tests/api_tests/test_a2a.py` — discovery-side regression net is dense

## Proposed Milestones

### Milestone 1 (M1): Bridge plumbing

**Scope:** backend
**Goal:** `/a2a` mount serves strict A2A JSON-RPC against `ap-orchestrator` via ADK's adapter, sharing our `Runner` and hand-built card.
**Estimated:** ~120 LOC implementation + ~30 LOC card-builder split = ~150 LOC
**Duration:** ~1.5 hours

**Tasks:**
- [ ] Split `_build_card()` in `backend/protocols/a2a.py` into `_build_card_dict()` (returns dict; current wire shape) and `_build_card_model()` (returns ADK's `AgentCard` pydantic model). Both share `SUPPORTED_EXTENSION_INFO` as source of truth (~30 LOC delta)
- [ ] Update `_build_card_dict()` to advertise `url = f"{base_url}/a2a"` (~3 LOC)
- [ ] Create `backend/protocols/a2a_invocation.py` exporting `build_a2a_app(agent, runner) -> Starlette` (~80 LOC). Calls `to_a2a(agent, agent_card=_build_card_model(...), runner=runner)`. Document `@a2a_experimental` status on the import.
- [ ] Mount in `backend/fast_api_app.py`: `app.mount("/a2a", build_a2a_app(orchestrator_agent, runner))` gated on `ENABLE_A2A_INVOCATION` env (~12 LOC, plus a startup log line)
- [ ] Smoke-test locally: `curl -X POST localhost:1956/a2a/<adk-path> -d '{"jsonrpc":"2.0",...}'` returns 200 + JSON-RPC envelope

**Files:**
- `backend/protocols/a2a.py` (modify, ~33 LOC delta)
- `backend/protocols/a2a_invocation.py` (new, ~80 LOC)
- `backend/fast_api_app.py` (modify, ~15 LOC delta)

**Acceptance Criteria:**
- [ ] `/a2a/.well-known/agent.json` returns the same card as `/.well-known/agent.json` (both routed through the canonical card source)
- [ ] `POST /a2a/v1/messages` with a valid `message/send` JSON-RPC body returns HTTP 200 + a `Task`-shaped JSON response
- [ ] Existing 13 A2A discovery tests still pass
- [ ] `card.url` ends with `/a2a` when the well-known route is fetched
- [ ] Lint clean: `cd backend && make lint`

**Risks:**
- ADK's `to_a2a` is `@a2a_experimental` → API may differ from docstring. Mitigation: verify shape with `python -c "from google.adk.a2a.utils.agent_to_a2a import to_a2a; help(to_a2a)"` before coding; if signature differs, adjust call site (already verified — to_a2a accepts `agent_card=` and `runner=`)
- ADK's `AgentCard` pydantic model may have slightly different field requirements than our dict (e.g., `defaultInputModes` vs `default_input_modes`). Mitigation: use the introspected signature directly; let pydantic surface mismatches at construction time, not runtime

### Milestone 2 (M2): Auth + tests

**Scope:** backend
**Goal:** Invocation requires Firebase ID token (parity with `/api/skill/{id}/stream`); 4 new tests cover happy path, auth failure, streaming, and the card-URL regression guard.
**Estimated:** ~30 LOC middleware + ~150 LOC tests = ~180 LOC
**Duration:** ~1.5 hours

**Tasks:**
- [ ] Starlette middleware in `backend/protocols/a2a_invocation.py` that runs the existing `get_current_user` Depends-equivalent before delegating to the mounted A2A app. Returns 401 with JSON-RPC error envelope on failure (~30 LOC)
- [ ] `backend/tests/api_tests/test_a2a_invocation.py` (~150 LOC):
  - [ ] `test_a2a_message_send_returns_jsonrpc_response` — POST → 200 + Task envelope with `id`, `status`, `parts`
  - [ ] `test_a2a_message_send_requires_auth` — POST without Bearer → 401 + JSON-RPC error
  - [ ] `test_a2a_send_subscribe_streams_events` — open `message/sendSubscribe`, assert SSE event stream
  - [ ] `test_a2a_card_url_matches_mount` — `_build_card_dict()` advertises `<base>/a2a` (regression guard)
- [ ] Update `tests/api_tests/test_a2a.py` URL assertions for the new `card.url` shape (~5 LOC delta)
- [ ] All 17+ A2A tests green; `make lint && make test-fast`

**Files:**
- `backend/protocols/a2a_invocation.py` (modify, ~30 LOC delta)
- `backend/tests/api_tests/test_a2a_invocation.py` (new, ~150 LOC)
- `backend/tests/api_tests/test_a2a.py` (modify, ~5 LOC delta)

**Acceptance Criteria:**
- [ ] All 4 new A2A invocation tests pass
- [ ] All existing 13 discovery tests still pass (no regression in URL/extension shape)
- [ ] Auth failure path returns a JSON-RPC error envelope, not a 500 or HTML page
- [ ] `make lint` clean + ruff format clean

**Risks:**
- Mounting Starlette middleware on a FastAPI sub-app can be quirky; auth middleware may not see Bearer headers if FastAPI's auth dependency machinery is being bypassed. Mitigation: use Starlette's `BaseHTTPMiddleware` pattern, not FastAPI `Depends`; verify with the explicit-401 test
- A2A `Task` envelope shape may include fields ADK adds that we don't anticipate. Mitigation: assert only the fields documented in the A2A v0.2 spec (`id`, `status`, `parts`); ignore additional fields

### Milestone 3 (M3): Verification + brief update

**Scope:** backend + docs
**Goal:** Probes confirm the gap is closed end-to-end against the live deploy; the upstream template-PR brief gains §5 covering the bridge.
**Estimated:** ~30 LOC probe deltas + ~80 LOC brief addendum = ~110 LOC
**Duration:** ~1 hour

**Tasks:**
- [ ] `scripts/simulate-a2a-peer.py`: Step 4 expects HTTP 200 (replace `⚠ 405` branch with a regression failure path); add a Step 5 that opens `message/sendSubscribe` and prints event names (~30 LOC delta)
- [ ] `scripts/verify-a2a.sh`: add invocation probe section that POSTs a minimal `message/send` to `card.url` and asserts 200 + JSON-RPC envelope (~25 LOC)
- [ ] Deploy to dev (push to `dev` branch, wait for Cloud Build); re-run `verify-a2a.sh` and `simulate-a2a-peer.py` against the live deploy
- [ ] `agents-cli register-gemini-enterprise` re-registration to propagate new `card.url`; confirm console still shows the agent
- [ ] Extend `docs/learnings/template-pr-a2a-spec-compliance.md` with §5 covering the bridge: ADK source citations, mount pattern, auth middleware shape, friction-log entry #25 (~80 LOC)

**Files:**
- `scripts/simulate-a2a-peer.py` (modify, ~30 LOC delta)
- `scripts/verify-a2a.sh` (modify, ~25 LOC delta)
- `docs/learnings/template-pr-a2a-spec-compliance.md` (modify, ~80 LOC delta)
- `cloudbuild.yaml` (modify, set `ENABLE_A2A_INVOCATION=true` for dev, ~2 LOC delta)

**Acceptance Criteria:**
- [ ] `simulate-a2a-peer.py` against live deploy: all 6 steps print `✓`
- [ ] `verify-a2a.sh` against live deploy: all green including new invocation probe
- [ ] Gemini Enterprise re-registration succeeds (idempotent update of existing entry)
- [ ] Template-PR brief §5 written + friction entry #25 ready to paste

**Risks:**
- Cloud Build deploy can take 5–10 minutes; backgrounded watcher means it doesn't block other work but does extend wall-clock time. Mitigation: deploy at the start of M3 so it lands in parallel with brief-writing
- Gemini Enterprise may cache the old `card.url`. Mitigation: re-registration is idempotent and the publish skill says it updates existing entries — confirmed in our earlier round-trips

## Day-by-Day Breakdown

Single-day sprint, ~4 hours wall clock.

### Day 1 — A2A Bridge

| Time | Block | Focus | Checkpoint |
| --- | --- | --- | --- |
| 0:00–1:30 | M1 | Card split, `a2a_invocation.py`, mount + local smoke test | Local `curl` returns 200 from `/a2a/v1/messages` |
| 1:30–3:00 | M2 | Auth middleware, 4 invocation tests, update 1 existing test, lint clean | `make test-fast && make lint` green |
| 3:00–3:30 | M3 setup | Push, wait for deploy (background watcher); update probes in parallel | Deploy lands; live probes green |
| 3:30–4:00 | M3 finish | Re-register with Gemini Enterprise; write template-PR brief §5; commit | Re-registration succeeds; brief §5 committed |

## Quality Gates

After M1:
```bash
cd backend && make lint
curl -X POST localhost:1956/a2a/v1/messages \
  -H "Authorization: Bearer <test-token>" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"hi"}],"messageId":"m1"}}}'
# expect: 200 + Task JSON
```

After M2:
```bash
cd backend && make lint && make test-fast
# expect: 17+ A2A tests green
```

After M3:
```bash
./scripts/verify-a2a.sh && python3 scripts/simulate-a2a-peer.py
# expect: both all-green; simulate steps 1-6 print ✓
```

## Sequencing Risks Called Out

1. **`to_a2a` API stability** — `@a2a_experimental`. Verified against installed `google-adk` during design. If ADK bumps mid-sprint, we re-verify in M1 first 10 minutes; design doc accepts version pinning as the answer.

2. **Card-builder pydantic model field names** — Python convention is snake_case but A2A wire format is camelCase. ADK's `AgentCard` uses camelCase per the introspection we ran. Risk: pydantic alias mismatches when our dict → AgentCard converter runs. Mitigation: pydantic surfaces field-name errors at construction time, not runtime; M1 smoke test catches.

3. **Starlette middleware on a mounted sub-app** — middleware on a `mount` doesn't always see the full request lifecycle the way it would on a root-mounted app. Mitigation: M2 includes an explicit-401 test (`test_a2a_message_send_requires_auth`); if it fails, swap to `Starlette.middleware.base.BaseHTTPMiddleware` on the inner `to_a2a` Starlette app rather than the outer mount.

4. **Existing 13 tests break on URL change** — `_build_card_dict()` now advertises `<base>/a2a`. Tests asserting `card.url == base_url` will fail. Mitigation: M2 explicitly updates `test_a2a.py` URL assertions; this is expected, not a regression.

5. **Deploy + re-registration timing** — Cloud Build takes ~5–10 min. Mitigation: M3 kicks off the deploy first thing, brief-writing fills the wait, re-registration happens last.

6. **Auth dependency in test fixture** — existing `client` fixture in `test_a2a.py` may not inject a valid Bearer token. Mitigation: M2 introduces a `_auth_client` fixture that adds a `Authorization: Bearer <workshop-stub-token>` header; reuse the same stub the existing `/api/skill/*` tests use.

## Validation of 0.5-day Estimate

Comparison against recent A2A work (last 3 days):
- `protocolVersion` fix (dbc5856): ~30 LOC code + ~10 LOC test, shipped in <1 hour including deploy
- `AgentExtension` descriptors (956fafe): ~80 LOC code + ~40 LOC test reshape, shipped in ~1.5 hours
- `verify-a2a.sh` (dfd4e54): ~130 LOC bash, ~30 min
- URL rewrite (236fdcb): ~40 LOC TS, ~30 min

This sprint is approximately the sum of those four pieces (~280 LOC total), so 4 hours wall-clock is consistent with observed velocity in the same code area.

**Conservative buffer:** +30% (1.2 hours) for the experimental-ADK risk = 5.2 hours worst case. Still well within a single working session.
