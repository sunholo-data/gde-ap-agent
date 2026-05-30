---
name: aitana-adk-testing
description: >
  How to inspect and verify ADK session state — events, artifacts, traces —
  on the running Aitana v6 backend using the ADK-native HTTP endpoints that
  ship for free with `get_fast_api_app(web=True, ...)`. Load when the user
  asks "are sessions actually being saved?", "where do messages live?",
  "how do I see what the agent saw?", "can I view artifacts the loader
  produced?", "how do I use `adk web` / `adk api_server` against this
  backend?", or is debugging a session that looks empty in the UI but should
  have events. Also load when verifying that `make_document_loader` saved
  the right `doc:{id}.json` artifact, when reproducing a bug from a known
  threadId, or when handing a session over to `adk eval`. Covers the
  app_name / user_id / session_id triple, the agents_dir-vs-APP_NAME quirk
  that makes the dev UI's app picker misleading, and the relationship
  between ADK's canonical store and the Firestore `chat_sessions` mirror.
---

# Aitana v6 — ADK session testing

> **The short version**: events and artifacts are stored *canonically* by
> ADK's `SessionService` + `ArtifactService`. The Firestore
> `chat_sessions` collection is a **metadata mirror only** (title, owner,
> turn count, document ids — for listing and access control). To verify
> what the agent actually saw, hit ADK's session endpoints — they're
> already mounted on our FastAPI app.

## What's stored where

| Concern                              | Lives in                                   | How it gets there                            |
| ------------------------------------ | ------------------------------------------ | -------------------------------------------- |
| User & assistant messages, tool calls, agent state | ADK `SessionService`               | ADK `Runner` appends each event              |
| Document blocks loaded into context  | ADK `ArtifactService`                       | `make_document_loader` saves `doc:{id}.json` |
| Large tool outputs (offloaded)       | ADK `ArtifactService`                       | `_handle_large_output` (callbacks.py)        |
| Title, turn count, owner, documentIds, accessControl | Firestore `chat_sessions/{sessionId}` | `make_session_tracker` + `make_after_agent_response` |
| The session id itself                | Both, joined by `session.id == threadId == ChatSessionIndex.session_id` | HttpAgent generates UUID, backend honours it |

Local dev → both backends are in-memory (process-scoped, lost on
restart). Prod → `VertexAiSessionService` (Agent Engine) for sessions
and `GcsArtifactService` for artifacts. Wiring lives in
[backend/adk/session.py](backend/adk/session.py) — env-var driven via
`AGENT_ENGINE_ID` and `ADK_ARTIFACT_BUCKET`.

## The triple: app_name / user_id / session_id

Every ADK URL needs all three. In v6:

- **`app_name`** = `"aitana_platform"` (constant, set in [backend/adk/agui.py](backend/adk/agui.py) as `APP_NAME`). Do **not** use directory names like `skills` or `tools` that `/list-apps` returns — see the dev UI quirk below.
- **`user_id`** = the authenticated user's Firebase uid. The `ag_ui_adk` wrapper takes it from the request's auth context. Find your own at runtime: `curl http://localhost:1956/api/auth/whoami` (with auth) or check the JWT.
- **`session_id`** = the AG-UI `threadId` = the `?session=` URL param on the chat page = `ChatSessionIndex.session_id` in Firestore. Three names, one value.

## Endpoints that ship for free

`get_fast_api_app(web=True, ...)` mounts every `AdkWebServer` route at
the FastAPI root. Auth is **off** for these — they're a dev/admin
surface. (When you bring `aitana-v6-backend` up in test/prod, decide
whether to leave them open or strip them via a sub-app mount; not
decided yet — flag it during deploy review.)

### Sessions (canonical message store)

```bash
# List session ids for a user
curl http://localhost:1956/apps/aitana_platform/users/<uid>/sessions

# Full session: events + state. THIS is what the agent actually saw.
curl http://localhost:1956/apps/aitana_platform/users/<uid>/sessions/<sessionId> | jq

# Delete a session (in-memory dev only — VertexAI delete is permanent)
curl -X DELETE http://localhost:1956/apps/aitana_platform/users/<uid>/sessions/<sessionId>

# Patch state without running the agent (useful for testing)
curl -X PATCH http://localhost:1956/apps/aitana_platform/users/<uid>/sessions/<sessionId> \
  -H 'Content-Type: application/json' \
  -d '{"state_delta": {"some_key": "some_value"}}'
```

The `events[]` array on the session contains `Event` objects with
`author` (`user`, agent name, or tool name), `content.parts[]`, tool
calls, function responses, and timestamps. This is the source of truth
for what the LLM was sent.

### Artifacts (canonical document/large-output store)

This is how you verify `make_document_loader` did the right thing for a
multi-doc compare:

```bash
# List artifact filenames for a session — expect doc:<id>.json per attached doc
curl http://localhost:1956/apps/aitana_platform/users/<uid>/sessions/<sessionId>/artifacts | jq

# Load one artifact (returns a google.genai.types.Part as JSON)
curl http://localhost:1956/apps/aitana_platform/users/<uid>/sessions/<sessionId>/artifacts/doc:<docId>.json | jq

# Decode the inline_data.data field — it's base64-encoded JSON of the blocks
curl -s '.../artifacts/doc:<docId>.json' \
  | jq -r '.inline_data.data' | base64 -d | jq
```

If the user reports "compared docs but only saw the last", run list
above for that sessionId. **Expect one `doc:<id>.json` per included
tab.** Anything less is a bug.

### Traces (for debugging an event)

```bash
# Spans for an entire session (uses ADK's in-memory exporter)
curl http://localhost:1956/debug/trace/session/<sessionId> | jq

# Per-event detail
curl http://localhost:1956/debug/trace/<eventId>
```

Falls back to OTEL → Cloud Trace in environments where
`otel_to_cloud=true` (any env with ADC).

### Agent invocation (the same path the chat UI uses)

```bash
# Non-streaming
curl -X POST http://localhost:1956/run \
  -H 'Content-Type: application/json' \
  -d '{
    "app_name": "aitana_platform",
    "user_id": "<uid>",
    "session_id": "<existingSessionId>",
    "new_message": {"role": "user", "parts": [{"text": "hi"}]}
  }'

# SSE — events stream as data: <event-json>\n\n
curl -N -X POST http://localhost:1956/run_sse \
  -H 'Content-Type: application/json' \
  -d '{...same as above..., "streaming": true}'
```

Note: the production chat path (`POST /api/skill/{id}/stream`) is a
*different* endpoint that wraps this with skill resolution, auth, and
AG-UI envelope translation. `/run` and `/run_sse` are the bare ADK
paths — useful for isolating "is it ADK or our wrapper".

## The dev UI quirk

`/dev-ui/` is mounted because `web=True`. **But** our `agents_dir =
backend/`, so `/list-apps` enumerates `backend/`'s subdirectories
(`skills`, `tools`, `admin`, …) — none of which are real ADK agents.
The dev UI's app picker shows them anyway and any session you start in
that UI is keyed under one of those names, **not** `aitana_platform`.

Result:
- **Browsing real prod sessions in the dev UI** → broken. The picker
  doesn't show `aitana_platform` because there's no
  `backend/aitana_platform/` directory.
- **Direct API calls with `app_name=aitana_platform`** → work fine.
- **The dev UI is still useful** for one-off agent experiments if you
  scaffold a real agent under `backend/<subdir>/` (won't be wired into
  the chat pipeline, but the runner works).

If you want the dev UI to browse our real sessions, fix would be one
of: (a) restructure so root agent lives under
`backend/aitana_platform/agent.py`, (b) override the agent loader, or
(c) build a thin internal admin UI that calls the same endpoints.
Out of scope until someone needs it.

## ADK CLI commands (local)

```bash
cd backend

# Browser dev UI — same routes as our running server, but isolated
uv run adk web .                         # http://localhost:8000/dev-ui/

# API-only server (no static UI)
uv run adk api_server .                  # http://localhost:8000

# Run an agent in the terminal (works for backend subdirs that ARE real agents)
uv run adk run <subdir>

# Run an evalset (see /adk-eval-guide for evalset shape)
uv run adk eval <subdir> tests/eval/evalsets/<name>.evalset.json
```

`make playground` in `backend/Makefile` is a wrapper for `adk web` on
port 8501. Same dev-UI quirk applies — it lists subdirs, not
`aitana_platform`.

## Common verification recipes

### "Did the multi-doc loader actually save N artifacts?"

```bash
SID=<threadId from URL ?session=>
UID=<your firebase uid>
curl -s http://localhost:1956/apps/aitana_platform/users/$UID/sessions/$SID/artifacts | jq
# expect ["doc:<idA>.json", "doc:<idB>.json", ...]
```

### "Did the session actually persist after I refreshed?"

```bash
curl -s http://localhost:1956/apps/aitana_platform/users/$UID/sessions | jq 'length'
# Compare to Firestore: gcloud firestore documents list chat_sessions ...
# Mismatch == ChatSessionIndex was created but ADK session wasn't (or vice versa).
```

### "What did the agent see for turn 3?"

```bash
curl -s http://localhost:1956/apps/aitana_platform/users/$UID/sessions/$SID \
  | jq '.events[2]'
```

### "Replay a bug from a captured threadId in eval"

```bash
# 1. Capture as eval case
curl -X POST http://localhost:1956/apps/aitana_platform/eval-sets/<set>/add-session \
  -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$UID\",\"session_id\":\"$SID\",\"eval_id\":\"repro-bug-1234\"}"

# 2. Run it
uv run adk eval . tests/eval/evalsets/<set>.evalset.json
```

## Things to remember

- Event order is authoritative. If `events[i].author == "user"` is missing for a turn the user reported, the AG-UI message never got persisted — look at `addMessage` in [useSkillAgent.ts](frontend/src/hooks/useSkillAgent.ts), not the agent.
- `state_delta` events are how callbacks like `make_session_tracker` mutate session state. They show up as events with no content but with `actions.state_delta`.
- The **artifact store and session store have independent `app_name`/`user_id`/`session_id` triples**. They line up because we always pass the same triple, but if you're testing a custom path, check both.
- In prod, `VertexAiSessionService` URLs use the same shape. The endpoint paths are identical. The session ids stay valid across pod restarts; only the in-memory dev backend forgets them.

## See also

- [adk-cheatsheet](../adk-cheatsheet/SKILL.md) — agent / tool / callback API reference
- [adk-eval-guide](../adk-eval-guide/SKILL.md) — evalset schema, `adk eval` workflow
- [aitana-v6-deploy](../aitana-v6-deploy/SKILL.md) — env wiring including `AGENT_ENGINE_ID`
- Backend-side wiring: [backend/adk/session.py](backend/adk/session.py), [backend/adk/agui.py](backend/adk/agui.py), [backend/fast_api_app.py](backend/fast_api_app.py) (`get_fast_api_app(web=True, ...)` is the line that mounts everything above)
