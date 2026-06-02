# Multi-Agent Inspector UX — Hub Chat + Live Specialist Inspectors

**Status**: Planned
**Priority**: P0 (competition demo differentiator)
**Estimated**: 2.5 days (frontend ~2 days, backend ~0.5 day)
**Scope**: Fullstack (frontend-heavy)
**Dependencies**: Existing `SkillsBar`, `APPipelineSteps`, AG-UI event stream, A2UI workspace surface, MCP Apps sandbox
**Created**: 2026-06-02
**Last Updated**: 2026-06-02

## Problem Statement

The current top nav presents four agents — **AP Orchestrator (HUB)**, **Document Parser**, **AP Validator**, **ERP Poster** — as four peer tabs of equal weight. The only signal that they are not equivalent choices is a small "HUB" badge on the orchestrator. A first-time visitor (and every competition judge) reasonably reads this as "pick one based on your task."

The actual architecture is hub-and-spokes: the orchestrator is the only intended entry point; the three specialists are sub-agents reached via `transfer_to_agent`. Their `SKILL.md` instructions assume orchestrator-provided context ([ap-validator SKILL.md:27-31](../../../backend/skills/templates/ap-validator/SKILL.md#L27-L31): *"You receive a structured invoice from the extraction step"*; [ap-poster SKILL.md:25-26](../../../backend/skills/templates/ap-poster/SKILL.md#L25-L26): *"You receive a validated invoice plus the validator's verdict"*). Invoked standalone via chat, they produce confusing output because the upstream context is missing.

**Current State:**
- 4 peer tabs in [SkillsBar.tsx:66-68](../../../frontend/src/components/navigation/SkillTab.tsx#L66-L68); only the orchestrator is the designed entry point
- The pipeline visualizer ([APPipelineSteps.tsx:7](../../../frontend/src/components/chat/APPipelineSteps.tsx#L7)) is gated to orchestrator messages — specialists have no visualizer when chatted-with directly
- A user who clicks "Document Parser" sees a chat box and a docparse agent that expects a parsed document already in the session — confusing
- Specialists have no observable surface during a real pipeline run beyond a brief `TOOL_CALL_START` event in the AG-UI stream; the user never *sees* what docparse extracted or what the validator grounded against
- A2UI is only used for the final invoice review card; MCP Apps are demo-only buttons (globe, analytics). Neither protocol is wired to the per-agent observability we already have data for.

**Impact:**
- Misrepresents the multi-agent architecture to judges — the *story* of cooperating specialists is undersold
- Specialists score worse than the orchestrator on first-touch because users invoke them without the context they need
- We have rich AG-UI events flowing for each specialist that we don't render anywhere — wasted observability
- The protocol stack (AG-UI / A2UI / MCP Apps) is the technical differentiator for this competition; the UI showcases only one and a half of the three

## Goals

**Primary Goal:** Replace the four-peer-tab layout with a single conversational hub (the orchestrator) plus three live, read-by-default specialist *inspectors* that visibly light up as the pipeline runs and can be opened to view each agent's input, tools used, citations, and structured output — with optional structured-input invocation for audit and demos.

**Success Metrics:**
- Time-to-understand-architecture: a new visitor can describe "what the four agents do together" within 30 seconds of opening the page (subjective demo-script check)
- Live inspector activation latency: a specialist chip transitions to `active` within 200ms of the orchestrator's `TOOL_CALL_START` event
- Standalone-invocation confusion: zero — specialists no longer expose a free-text chat box; invocation is via typed structured forms only
- All three protocols (AG-UI, A2UI, MCP Apps) are visibly demonstrated on the inspector surfaces, not only on the final orchestrator card

**Non-Goals:**
- Removing the specialists from the system — they remain real ADK sub-agents, just not chat surfaces
- Changing the backend orchestration logic (no skill-config changes, no new `transfer_to_agent` semantics)
- Building a generic "agent debugger" — this is a competition-demo polish, scoped to the four AP agents
- Replacing `APPipelineSteps` — it stays; the inspector surface extends it
- Persisting historical inspector state beyond the current session (use the existing ADK session store; no new collection)

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | Inspectors react to AG-UI events in real time (<200ms); no extra latency on hub chat path |
| 2 | EARNED TRUST | +1 | Every specialist's tool calls, citations, and structured output are exposed verbatim — over-trust mitigation |
| 3 | SKILLS, NOT FEATURES | +1 | Reinforces the skill abstraction by making each one individually visible and inspectable |
| 4 | RIGHT MODEL, RIGHT MOMENT | 0 | No model changes |
| 5 | GRACEFUL DEGRADATION | +1 | Inspectors show "idle" empty state when no pipeline is running; structured-invocation form validates before sending |
| 6 | PROTOCOL OVER CUSTOM | +1 | Reuses AG-UI events for state, A2UI for inspector panels, MCP Apps for rich widgets — no new protocol surface |
| 7 | API FIRST | 0 | Mostly frontend; one small backend endpoint for structured specialist invocation |
| 8 | OBSERVABLE BY DEFAULT | +1 | The entire point — turns invisible sub-agent steps into observable, citable surfaces |
| 9 | SECURE BY CONSTRUCTION | 0 | No new data access; structured-invocation goes through existing skill auth |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | Inspector panels are A2UI/AG-UI driven from the backend; the client renders, doesn't decide |
| | **Net Score** | **+7** | Threshold: >= +4 ✅ |

**Conflict Justifications:** None — no axiom scores -1.

## Design

### Overview

Restructure the top of the page so that the AP Orchestrator is the **only conversational tab**, and the three specialists become **live status chips** to its right that double as inspectors. Clicking a chip opens a side-panel **Inspector** rendered as an A2UI surface, showing the last (or live) invocation of that specialist: input, tool calls with citations, structured output. The chip's state (`idle` | `active` | `done` | `error`) is driven by the same AG-UI events that already power `APPipelineSteps`. Each inspector exposes an optional **"Run standalone"** affordance that opens a **structured form**, not a chat box — `docparse` takes a document picker, `ap-validator` takes a JSON invoice (loadable from the last run), `ap-poster` takes a verdict object. One specialist (the validator) hosts an MCP App widget so the protocol trio is demonstrated end-to-end.

### Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  GDE AP Agent · AI-Powered Accounts Payable           [4 AGENTS · LIVE]│
│  ┌──────────────────┐   ┌─────────┐ ┌──────────┐ ┌──────────┐         │
│  │ AP Orchestrator  │   │ Extract │▸│ Validate │▸│   Post   │         │
│  │   [HUB · ACTIVE] │   │ docparse│ │ validator│ │  poster  │         │
│  └──────────────────┘   └────●────┘ └────○─────┘ └────○─────┘         │
│         ▲                     │                                        │
│         │ chat                │ click chip → opens Inspector side panel│
└─────────┼─────────────────────┼────────────────────────────────────────┘
          │                     │
   Main chat (single)     Inspector side panel (A2UI surface)
   - Conversation         ┌────────────────────────────────────┐
   - APPipelineSteps      │ docparse · last invocation         │
   - Invoice Review Card  │  Input: document_id=demo/inv-042   │
     (existing A2UI)      │  Tools used:                       │
                          │   • list_documents (1 hit)         │
                          │   • get_document_content (3.2KB)   │
                          │   • structured_extraction (12 fields)│
                          │  Output (structured):              │
                          │   { vendor: "Acme GmbH", ... }     │
                          │                                    │
                          │  [Run standalone ▾]                │
                          │   ┌───────────────────────────┐    │
                          │   │ Document: [demo/inv-042 ▾]│    │
                          │   │            [Run docparse] │    │
                          │   └───────────────────────────┘    │
                          └────────────────────────────────────┘
```

### Frontend Changes

**New Components:**
- `frontend/src/components/inspector/SpecialistChip.tsx` — renders a chip with `idle | active | done | error` state, icon, name, latency. Replaces the per-specialist `SkillTab` in the top nav.
- `frontend/src/components/inspector/InspectorPanel.tsx` — sliding side panel; hosts the A2UI surface for the selected specialist; remembers last selection per session.
- `frontend/src/components/inspector/RunStandaloneForm.tsx` — disclosure block under each inspector; renders the per-specialist structured form (see below). Never a free-text textarea.
- `frontend/src/components/inspector/forms/DocparsePicker.tsx` — file picker bound to `useDocBrowser`; emits `{document_id}`.
- `frontend/src/components/inspector/forms/ValidatorJsonForm.tsx` — schema-driven form for invoice JSON; "Load from last docparse" button; "Paste JSON" mode behind a tab.
- `frontend/src/components/inspector/forms/PosterVerdictForm.tsx` — two-field form: verdict (`pass` | `needs_review` radio) + reasons array; "Load from last validator" button.
- `frontend/src/hooks/useSpecialistInvocations.ts` — reduces AG-UI event stream into a per-specialist `InvocationState` keyed by tool-call name (`docparse`, `ap-validator`/`ap_validator`, `ap-poster`/`ap_poster`).

**Modified Components:**
- `frontend/src/components/navigation/SkillsBar.tsx` — keep the orchestrator tab; replace the three specialist tabs with a horizontal `SpecialistChip` row that is non-routing by default (clicks open the side panel, do not navigate). Behind a `?devmode=1` URL flag, keep the old peer-tab behavior for development.
- `frontend/src/components/chat/APPipelineSteps.tsx` — keep, but reuse the same `useSpecialistInvocations` state as the chips so they cannot drift out of sync. The vertical step list stays on the orchestrator's bot messages; the chips are the *top-level* live indicator.
- `frontend/src/lib/skillMeta.tsx` — add a `role: "hub" | "specialist"` discriminator; the routing layer reads this so specialists no longer have their own `/chat/{skillId}` route.
- `frontend/src/app/chat/[...path]/page.tsx` — if the URL targets a specialist `skillId` and `?devmode=1` is not set, redirect to `/chat/ap-orchestrator/{sessionId}` and open the matching inspector. This preserves bookmarks without exposing the broken UX.

**State Management:**
- `useSpecialistInvocations(sessionId)` derives state from the AG-UI events already streaming for the current orchestrator run. No new client store; just a `useReducer` over the event stream.
- Selected-inspector state is local to `InspectorPanel` (`useState`); restored from `sessionStorage` so a refresh keeps the user's inspector choice.

**UI/UX:**
- Default landing: orchestrator chat is focused; the three specialist chips are visible and idle.
- During a run: chips light up in order, latency badges fill in (e.g., "1.4s") as `TOOL_CALL_END` events fire.
- Clicking any chip slides the InspectorPanel in from the right (40% width, overlays the document sidebar — sidebar collapses).
- Inside the panel, the most recent invocation is shown first; a small dropdown lets the user scroll back through prior invocations in the same session.
- "Run standalone" is collapsed by default and labeled with a small ⚠ icon — "this specialist expects pre-processed input; results may be lower quality outside the pipeline."

### Backend Changes

**New Endpoints:**
- `POST /api/skill/{skill_id}/structured` — accepts a `{ input: <typed dict>, surface: "inspector" }` body, runs exactly one turn of the named skill agent with the typed input as the user message (serialized as JSON), and streams AG-UI events tagged with `surface: inspector` so the frontend can route them to the panel rather than the main chat. Auth is the same as the existing `/api/skill/{skill_id}/stream` (`skill_processor.process_skill_request` already guards access via `can_access_skill`; see [skill_processor.py:54-64](../../../backend/skills/skill_processor.py#L54-L64)).
  - Input schemas live in the SKILL.md frontmatter as `metadata.structuredInput`, e.g. `{type: "object", properties: {document_id: {type: "string"}}, required: ["document_id"]}`. If absent, the endpoint returns 400. This keeps the schema co-located with the skill definition (PROTOCOL OVER CUSTOM — JSON Schema).

**Modified Endpoints:** None.

**New Services/Modules:**
- `backend/skills/structured_invocation.py` — small module: validate input against `metadata.structuredInput`, serialize as a system-style user message ("Structured input for this run: {...}"), invoke the agent, tag emitted events with `surface: "inspector"`.

**Data Model Changes:**
- Each specialist SKILL.md gains a `metadata.structuredInput` JSON Schema block:
  - `docparse`: `{ document_id: string }`
  - `ap-validator`: full invoice JSON (mirrors `docparse`'s output schema, [docparse SKILL.md:25-36](../../../backend/skills/templates/docparse/SKILL.md#L25-L36))
  - `ap-poster`: `{ verdict: "pass"|"needs_review", invoice: {...}, reasons: [...] }`
- The frontend renders these as schema-driven forms (RJSF or a hand-rolled mini-renderer; lean toward hand-rolled — only three forms).

### API Changes

| Method | Endpoint | Description | Breaking? |
|--------|----------|-------------|-----------|
| POST   | `/api/skill/{skill_id}/structured` | Run a single typed turn of a skill from the inspector panel | No (new) |
| GET    | `/api/skill/{skill_id}` | Already returns `SkillConfig`; will now include `metadata.structuredInput` if defined | No (additive) |

### Protocol Showcase: AG-UI / A2UI / MCP Apps

The inspector surface is intentionally designed to exercise all three protocols, which is the technical story for this competition:

- **AG-UI** — drives the live chip state. The same `TOOL_CALL_START` / `TOOL_CALL_END` events that already feed `APPipelineSteps` ([APPipelineSteps.tsx:19-24](../../../frontend/src/components/chat/APPipelineSteps.tsx#L19-L24)) feed the chip-state reducer. A new event tag (`surface: "inspector"`) lets standalone-invocation events render in the panel only, not in the main chat. Nothing custom — pure AG-UI semantics.

- **A2UI** — each inspector panel is rendered as an A2UI component tree returned by the backend (not hand-rolled React). The panel content is therefore *server-authored* per specialist: docparse's panel emphasizes the extracted-field table, the validator's emphasizes citations + the knowledge-base widget, the poster's emphasizes the posting record or escalation form. A2UI also handles the "scroll back through prior invocations" dropdown as a server-controlled selector. The existing orchestrator A2UI invoice card stays unchanged.

- **MCP Apps** — the validator inspector embeds one new MCP App: **`ap-vendor-kg`**, a small sandboxed iframe widget that visualizes the vendor + PO records that the validator's `ai_search` calls grounded against, with edges to prior invoices for duplicate detection. This re-uses the existing MCP Apps sandbox plumbing (already shipped for the vendor globe + analytics dashboard). The widget reads its props from the validator's tool-call output and is loaded only when the user opens the validator inspector — no extra cost on the hot path. This is the "audit" affordance: a human reviewer can click into the citation, see the actual KB record, and form an opinion.

The protocol trio is therefore demonstrated *together* on a single specialist (the validator), and individually on the others — exactly the showcase a Track 3 judge is scoring.

### CLI Surface

Out of scope for this fork — the `aiplatform` / `aitana` CLI is the upstream's surface. The structured-invocation endpoint is callable via `curl` for debugging without a CLI command; this fork ships no new CLI verbs.

### Architecture Diagram

```
                          User
                            │
                            ▼
              ┌─────────────────────────┐
              │  Orchestrator chat tab  │  ← only conversational surface
              └────────────┬────────────┘
                           │  POST /api/skill/ap-orchestrator/stream
                           ▼
              ┌─────────────────────────┐
              │  AG-UI event stream     │
              └──┬──────────────────────┘
                 │
                 ├──► main chat ──► APPipelineSteps + Invoice Review A2UI card
                 │
                 └──► useSpecialistInvocations
                          │
                          ▼
                     SpecialistChip × 3   (live state)
                          │ click
                          ▼
                ┌──────────────────────┐
                │   InspectorPanel     │  ← A2UI surface
                │  ┌────────────────┐  │
                │  │ last invocation│  │  ← rendered from tool-call event data
                │  └────────────────┘  │
                │  ┌────────────────┐  │
                │  │ MCP App widget │  │  ← validator only: ap-vendor-kg
                │  └────────────────┘  │
                │  ┌────────────────┐  │
                │  │ Run standalone │  │
                │  │ [typed form]   │──┼──► POST /api/skill/{id}/structured
                │  └────────────────┘  │      (single-turn, surface=inspector)
                └──────────────────────┘
```

## Implementation Plan

### Phase 1: Inspector skeleton — read-only (~1 day)
- [ ] Add `useSpecialistInvocations` hook reducing AG-UI events into per-specialist state (~80 LOC)
- [ ] Build `SpecialistChip` component with four visual states (~60 LOC)
- [ ] Build `InspectorPanel` as a side-sliding overlay; mounts to right edge, 40% width (~120 LOC)
- [ ] Modify `SkillsBar`: orchestrator stays a tab; three specialists become chips (~40 LOC delta)
- [ ] Wire `?devmode=1` escape hatch + redirect-to-orchestrator for stale specialist URLs (~30 LOC)
- [ ] Update `skillMeta.tsx` with `role` field (~20 LOC)

### Phase 2: A2UI-rendered inspector content (~0.75 day)
- [ ] Backend: tag inspector-only events with `surface: "inspector"` in the AG-UI stream (~30 LOC in `agui.py` / `stream_agui_events`)
- [ ] Backend: emit a small A2UI component tree per specialist describing input/tools/output (reuse existing `send_a2ui_json_to_client` toolset; no new endpoint) (~120 LOC across three skills, mostly JSON)
- [ ] Frontend: mount the A2UI surface inside `InspectorPanel`, route inspector-tagged events to it (~50 LOC)
- [ ] Frontend: invocation-history dropdown (last N runs in session) (~40 LOC)

### Phase 3: Structured-input invocation (~0.5 day)
- [ ] Backend: `POST /api/skill/{skill_id}/structured` endpoint + `structured_invocation.py` module (~100 LOC + tests)
- [ ] Add `metadata.structuredInput` JSON Schema blocks to the three specialist SKILL.md files (~30 LOC YAML)
- [ ] Frontend: three typed forms — `DocparsePicker`, `ValidatorJsonForm`, `PosterVerdictForm` (~200 LOC total, mostly typed inputs + "Load from last X" buttons)
- [ ] Frontend: wire forms to the structured endpoint; render the response into the inspector via the same A2UI surface (~50 LOC)

### Phase 4: MCP App showcase + polish (~0.25 day)
- [ ] Add `ap-vendor-kg` MCP App: small iframe widget showing vendor + PO + prior-invoice records returned by validator's `ai_search` (~150 LOC HTML/JS in sandbox)
- [ ] Mount the widget inside the validator inspector A2UI tree (~20 LOC)
- [ ] Demo-script polish: update [SUBMISSION.md](../../../SUBMISSION.md) demo flow to highlight the inspector experience; update landing-page copy to "one pipeline, four cooperating agents" (~30 LOC docs)
- [ ] Update [README.md](../../../README.md) screenshot showing chips lit up mid-run

## Migration & Rollout

**Database Migrations:** None — uses existing ADK session store; no Firestore schema changes.

**Feature Flags:**
- `NEXT_PUBLIC_INSPECTOR_UX=1` (default `1` on dev) gates the new chip+inspector layout; `=0` falls back to the existing four-peer-tab layout. Once judged, becomes hard-coded.
- `?devmode=1` URL query flag keeps the legacy specialist-as-chat behavior alive for local debugging without a deploy.

**Rollback Plan:** Single env-var flip to `0` reverts to current UI; no backend rollback needed (the structured endpoint is additive).

**Environment Variables:**
- `NEXT_PUBLIC_INSPECTOR_UX` (frontend, all envs)

## Testing Strategy

### Frontend Tests (Vitest + React Testing Library)
- [ ] `useSpecialistInvocations` reducer: feeds in synthetic AG-UI event streams; asserts chip state transitions for each specialist
- [ ] `SpecialistChip` snapshot tests for each state (`idle`, `active`, `done`, `error`)
- [ ] `InspectorPanel` mounts the A2UI surface; renders mock A2UI tree; click-out closes
- [ ] Three form components: validates against the JSON Schema, disables submit on invalid input, "Load from last X" pre-fills correctly
- [ ] Legacy-URL redirect: `/chat/docparse/abc` without `devmode` redirects to `/chat/ap-orchestrator/abc` with inspector pre-opened

### Backend Tests (pytest)
- [ ] `structured_invocation.py`: schema-valid input runs the agent; invalid input returns 400 with a useful message
- [ ] `/api/skill/{id}/structured` integration test against the three specialists (uses `InMemorySessionService`)
- [ ] Auth: a user without access to a skill receives 403, same as the streaming endpoint

### Manual Testing
- [ ] Run the canned demo prompt (`"Process this invoice: Vendor: Acme GmbH..."`) and verify chips light up in order with sensible latencies
- [ ] Open each inspector mid-run and confirm the A2UI panel shows the live tool calls + citations
- [ ] Open the validator inspector after a real run and verify the `ap-vendor-kg` MCP App widget loads and shows the cited vendor record
- [ ] Run each specialist standalone via its form; verify the inspector receives `surface=inspector` events only (no main-chat pollution)
- [ ] Refresh the page mid-run — chip state recovers from session storage; main chat continues
- [ ] Toggle `NEXT_PUBLIC_INSPECTOR_UX=0`; verify the original four-peer-tab UI returns unchanged

## Security Considerations

- The new `/api/skill/{id}/structured` endpoint reuses `process_skill_request`'s auth path — same Firebase token + `can_access_skill` checks as the streaming endpoint. No new auth surface.
- Structured-input is validated against the skill's declared JSON Schema *before* it reaches the agent prompt; user input cannot smuggle prompt-injection by way of unexpected fields.
- The `ap-vendor-kg` MCP App runs in the existing sandboxed iframe; no new iframe origin, no new postMessage handler.
- A2UI inspector trees are server-authored — the client renders, it does not interpret arbitrary user-supplied component definitions.

## Performance Considerations

- Hot path (the main orchestrator chat) is untouched; inspector state is derived client-side from events the frontend already receives.
- The inspector A2UI tree is emitted as a small payload per specialist invocation (typically <2 KB JSON); cumulative bandwidth impact <10 KB per full pipeline run.
- The `ap-vendor-kg` MCP App is lazy-loaded on first open of the validator inspector — zero cost when not opened.
- No new bundle dependencies (forms are hand-rolled; A2UI surface mount already exists).

## Success Criteria

- [ ] All frontend tests passing (`cd frontend && npm run test:run`)
- [ ] All backend tests passing (`cd backend && uv run pytest tests/`)
- [ ] Lint and typecheck clean (`cd frontend && npm run quality:check:fast`; `cd backend && make lint`)
- [ ] Top nav shows one tab (orchestrator) + three live chips; chips animate during a real demo run
- [ ] Clicking each chip opens the inspector panel with the latest invocation's input, tool calls, citations, and structured output rendered as an A2UI surface
- [ ] Each specialist has a working "Run standalone" form that posts to `/api/skill/{id}/structured` and renders results in the inspector
- [ ] Validator inspector embeds the `ap-vendor-kg` MCP App widget; clicking a citation in the validator output highlights the corresponding KB node
- [ ] Stale specialist-as-chat URLs redirect to the orchestrator with the inspector pre-opened
- [ ] `NEXT_PUBLIC_INSPECTOR_UX=0` reverts to the prior UI
- [ ] [SUBMISSION.md](../../../SUBMISSION.md) demo script updated; [README.md](../../../README.md) screenshot refreshed

## Resolved Decisions

- **Form library**: hand-rolled. Three forms only; RJSF would add ~60 KB for marginal benefit.
- **Naming**: **Audit View** (not Inspector). Reads enterprise-AP for the judges; `ap-` skill prefix aligns. Internal component names keep `Inspector` (e.g., `InspectorPanel`) only where renaming would churn unrelated code; user-visible copy is "Audit View".
- **Panel mode**: persistent side panel, 40% width, document sidebar collapses while open.
- **JSON editing for "Load from last X"**: default read-only; "Edit" toggle opens a plain `<textarea>` with JSON.parse validation on blur. No Monaco — too heavy for the marginal demo benefit.
- **`ap-vendor-kg` data**: stylised mock keyed off the validator's emitted citations. `ai_search` is stubbed in LOCAL_MODE anyway; the widget's job is to demonstrate the protocol surface, not real KG data.

## Open Questions

- None blocking — all design questions resolved above.

## Related Documents

- [Competition Polish Sprint](./competition-polish-sprint.md) — the M1–M6 sprint that shipped the current four-tab UI
- [GCS Bucket Browser](./gcs-bucket-browser.md) — the other P0 design doc currently in flight for the submission
- [Product Axioms](../../../docs/product-axioms.md)
- [SUBMISSION.md](../../../SUBMISSION.md) — competition demo script that this UX feeds into
- [SkillsBar.tsx](../../../frontend/src/components/navigation/SkillsBar.tsx), [SkillTab.tsx](../../../frontend/src/components/navigation/SkillTab.tsx), [skillMeta.tsx](../../../frontend/src/lib/skillMeta.tsx), [APPipelineSteps.tsx](../../../frontend/src/components/chat/APPipelineSteps.tsx) — current implementation that this doc modifies
- AP specialist skills: [ap-orchestrator/SKILL.md](../../../backend/skills/templates/ap-orchestrator/SKILL.md), [docparse/SKILL.md](../../../backend/skills/templates/docparse/SKILL.md), [ap-validator/SKILL.md](../../../backend/skills/templates/ap-validator/SKILL.md), [ap-poster/SKILL.md](../../../backend/skills/templates/ap-poster/SKILL.md)
