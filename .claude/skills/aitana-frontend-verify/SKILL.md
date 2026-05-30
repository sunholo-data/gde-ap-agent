---
name: aitana-frontend-verify
description: >
  How to drive a real Chrome instance via the chrome-devtools MCP to verify
  Aitana v6 frontend changes end-to-end — rendered DOM, console errors,
  /api/proxy network traffic, AG-UI SSE streams, and Firebase auth state.
  Load whenever a frontend change has been made and you need to confirm it
  *actually works* before reporting success, or when debugging behavior that
  static checks (tsc/eslint/vitest) cannot see. Trigger phrases include
  "verify this in the browser", "did the UI change work", "check the
  console", "watch the network panel", "is the SSE stream connecting",
  "click through the chat flow", "screenshot the page", "run lighthouse",
  "is fetchWithAuth being used", "are we getting 401s", "reproduce the bug
  in the browser", "test the threadId/doc-injection/session-delete flow".
  Also load when investigating a UI regression report from the user where
  the description involves something that only manifests at runtime
  (streaming, auth, layout, hydration). Do NOT load for pure static-code
  questions (rename a prop, refactor a hook) — those don't need a browser.
---

# Aitana v6 — frontend verification with chrome-devtools MCP

> **The short version**: chrome-devtools MCP launches a real (headed)
> Chrome and exposes navigate/click/screenshot/network/console tools. Use
> it to close the loop on frontend changes — type-checks pass ≠ feature
> works. The global rule (CLAUDE.md user-level) says "use the feature in a
> browser before reporting the task as complete; if you can't, say so
> explicitly." This skill is how you do that.

## When to use vs. skip

**Use it** for:
- After any UI/UX change — golden path + one edge case before claiming done
- Debugging stateful flows: chat streaming, threadId stability, doc
  injection, session delete, auth handoff, AG-UI events
- Verifying network behavior: `/api/proxy` reaches backend, fetchWithAuth
  attaches the bearer, no 401s, no CORS surprises
- Catching console errors / React warnings / hydration mismatches that
  vitest doesn't see

**Skip it** for:
- Pure refactors with green tests + tsc + lint
- Backend-only changes (use curl + `aitana-adk-testing` instead)
- Anything you'd run against test/prod (the MCP drives a real browser
  with your real auth — keep it on `localhost`)

## Pre-flight checklist

1. **Is the dev server running?** Frontend on `:3456`, backend on
   `:1956` (see `gotcha_gcp_project_env_shadow` — always `make dev` from
   repo root, never raw uvicorn). If not running, start it in a
   background bash and wait for both ports to bind before navigating.
2. **Are you logged in?** The MCP user data dir persists at
   `~/.cache/chrome-devtools-mcp/chrome-profile-stable` so Firebase auth
   from a previous run usually carries over. If `evaluate_script` for
   `localStorage` shows no Firebase IDP token, ask Mark to log in once
   in the headed window — subsequent runs will reuse it.
3. **Localhost only.** Do not point this at v5 (`aitana.sunholo.com`),
   v6 dev/test/prod, or any third-party site without explicit ask.

## Standard verification recipe

For a typical "I changed X in the chat UI, does it work?":

1. `new_page` → `navigate_page` to `http://localhost:3456`
2. `take_snapshot` to confirm the page rendered (look for the document
   workspace or login screen, not a Next.js error overlay)
3. `list_console_messages` — any red errors before you've even
   interacted? That's a regression. Capture and report.
4. Exercise the feature with `click` / `type_text` / `fill_form` /
   `press_key`. Use `wait_for` between steps when the UI streams or
   navigates — don't rely on sleeps.
5. `list_network_requests` — filter mentally for:
   - `/api/proxy/*` — these should be 200/2xx, **not 401**. A 401 here
     almost always means a bare `fetch()` slipped through where
     `fetchWithAuth` was required (see
     `feedback_fetchWithAuth_always`).
   - Long-lived `text/event-stream` connections — the AG-UI SSE channel.
     If you don't see one during a chat send, the stream didn't open.
6. `list_console_messages` again after the interaction — anything new?
7. `take_screenshot` if the change is visual; attach to the report.

## Recipe: AG-UI SSE stream sanity

The frontend talks AG-UI directly via `@ag-ui/client` HttpAgent (see
`gotcha_copilotkit_not_agui_native` and `gotcha_agui_protocol_boundary`).
To confirm a stream is healthy:

1. Send a chat message in the UI.
2. `list_network_requests` and find the request whose response
   `Content-Type` is `text/event-stream`.
3. `get_network_request` for that ID — the body should contain
   AG-UI event frames (RUN_STARTED, TEXT_MESSAGE_*, TOOL_CALL_*,
   RUN_FINISHED). No frames = the agent never streamed. Status 200 with
   an immediate close = backend likely returned an error before the
   stream started — check backend logs.

## Recipe: fetchWithAuth audit (live)

CI has `check:auth-fetch` for static cases, but runtime use can still
miss cases where a hook/component constructs a URL conditionally:

1. Navigate, perform the suspected flow.
2. `list_network_requests` → look at every `/api/proxy/*` request.
3. `get_network_request` on each — the request headers must include
   `Authorization: Bearer ...`. Missing header on any proxy request is
   the bug. Identify the calling code, fix to `fetchWithAuth`.

## Recipe: chat-history flow verification

For recent work in this area (threadId stability, doc injection,
session delete) the meaningful checks are:

- **threadId stable across first turn.** Open devtools console with
  `evaluate_script` to inspect the React state or just watch the
  request URL on the second AG-UI call — same threadId as the first.
- **Doc injection.** When a chat is opened with a document attached,
  the first AG-UI request body should already contain the doc as
  context (or the backend should emit a `doc:` artifact event in the
  stream). Confirm via `get_network_request` on the SSE response.
- **Session delete.** Click delete in the sidebar → the row disappears
  from the list, and a `DELETE /api/proxy/sessions/{id}` shows 200/204.
  Reload the page; deleted session should not reappear.

## Tool quick reference

Categories the MCP exposes (full list in upstream README):

- **Navigation**: `navigate_page`, `new_page`, `close_page`,
  `select_page`, `list_pages`, `wait_for`
- **Input**: `click`, `type_text`, `fill`, `fill_form`, `hover`,
  `press_key`, `handle_dialog`, `upload_file`, `drag`
- **Network**: `list_network_requests`, `get_network_request`
- **Console / DOM**: `list_console_messages`, `get_console_message`,
  `take_snapshot`, `evaluate_script`
- **Visual**: `take_screenshot`, `resize_page`, `emulate`
- **Perf**: `performance_start_trace`, `performance_stop_trace`,
  `performance_analyze_insight`, `lighthouse_audit`
- **Memory**: `take_memory_snapshot`

Prefer `take_snapshot` (HTML structure) over `take_screenshot` when you
just need to confirm content — it's cheaper and diff-friendly.

## Gotchas

- **Headed by default.** A real Chrome window opens on Mark's screen.
  That's intentional (lets him watch what you're doing) but don't be
  surprised. There is no `--isolated` flag set, so profile persists.
- **Persistent profile = persistent auth.** Good for not having to log
  in every run. Bad if a test left the app in a weird state. If you
  see stale state, prefer logging out via the UI over killing the
  profile dir — the user may have other state in there.
- **Don't run against test/prod.** The MCP can't tell the difference
  between localhost and a real environment. Real users see your
  traffic. Localhost only unless Mark explicitly says otherwise.
- **Sensitive credentials.** Per upstream docs, the MCP exposes browser
  contents to the model. Don't navigate to anything with secrets that
  aren't already part of this repo's dev flow.
- **One Chrome instance.** Concurrent MCP runs share the same profile.
  Don't launch a second `chrome-devtools-mcp` session in parallel.

## Reporting back

After a verification run, summarize for Mark in this shape:

- **What I exercised**: the flow + steps in 1–2 lines.
- **What worked**: list the positive signals (200 responses, expected
  events, no console errors).
- **What didn't / what I noticed**: anything off — even cosmetic.
- **Screenshot/snapshot**: attach if visual or if a regression.

If the verification failed, **do not claim success**. Report the
failure, propose the fix, and re-verify after the fix.
