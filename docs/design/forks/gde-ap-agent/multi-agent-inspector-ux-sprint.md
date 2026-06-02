# Multi-Agent Inspector UX — Sprint Plan

**Sprint ID**: AUDIT-VIEW
**Design Doc**: [multi-agent-inspector-ux.md](./multi-agent-inspector-ux.md)
**Status**: Ready to Execute
**Created**: 2026-06-02
**Deadline**: 2026-06-05 17:00 PT (competition submission)

## Sprint Summary

Replace the four-peer-tab top nav with one orchestrator chat tab plus three live **Audit View** chips for the specialists. Chips light up from existing AG-UI events. Clicking a chip opens a persistent side panel rendered as an A2UI surface, showing the latest invocation and offering structured-input-only "Run standalone". The validator panel embeds a new `ap-vendor-kg` MCP App widget so all three protocols (AG-UI / A2UI / MCP Apps) are showcased side-by-side.

## Decisions Locked

- **Naming**: "Audit View" for user-visible copy; component names keep `Inspector*` where renaming is churn.
- **Forms**: hand-rolled (no RJSF).
- **Panel**: persistent, 40% width, sidebar collapses while open.
- **JSON edit**: plain `<textarea>` + JSON.parse on blur; no Monaco.
- **`ap-vendor-kg`**: stylised mock keyed off validator citations.

## Milestones

### M1 — Audit View skeleton: chips + panel + state hook (~5 hours)
**Scope:** `frontend`

- [ ] `frontend/src/lib/skillMeta.tsx` — add `role: "hub" | "specialist"` on each meta entry
- [ ] `frontend/src/hooks/useSpecialistInvocations.ts` — reducer over AG-UI tool-call events → `{docparse, ap_validator, ap_poster: InvocationState}` per session
- [ ] `frontend/src/components/audit/SpecialistChip.tsx` — chip with `idle | active | done | error` states, latency badge, icon
- [ ] `frontend/src/components/audit/InspectorPanel.tsx` — sliding 40% side panel; `sessionStorage` for last selection; close button
- [ ] `frontend/src/components/navigation/SkillsBar.tsx` — keep orchestrator tab; replace specialist tabs with chip row that opens the panel (no nav)
- [ ] `frontend/src/app/chat/[...path]/page.tsx` — legacy `/chat/docparse/{sid}` URLs redirect to orchestrator with chip pre-selected (unless `?devmode=1`)
- [ ] `NEXT_PUBLIC_INSPECTOR_UX` env flag gates the whole change

**Acceptance:** chips visible; clicking opens panel with a "no invocations yet" empty state; flag `=0` reverts.

---

### M2 — A2UI-rendered Audit View content (~3 hours)
**Scope:** `fullstack`

- [ ] Backend: `backend/adk/audit_view.py` — helper that builds a per-specialist A2UI tree from the last tool-call result; reuses `send_a2ui_json_to_client` semantics
- [ ] Backend: orchestrator post-processing taps the existing event stream and emits `surface: "audit-view"` A2UI updates per specialist as their `TOOL_CALL_END` fires
- [ ] Frontend: route `surface=audit-view` events into the matching specialist's A2UI surface (not the main workspace)
- [ ] Frontend: in `InspectorPanel`, mount the A2UI surface and add a "history" dropdown for last 5 invocations from `sessionStorage`

**Acceptance:** after a real demo run, opening each chip shows that specialist's input/tools/output as an A2UI card.

---

### M3 — Structured-input "Run standalone" (~3 hours)
**Scope:** `fullstack`

- [ ] Backend: `backend/skills/structured_invocation.py` — validates body against `metadata.structuredInput`, runs one agent turn with input serialised as the user message, tags events `surface=audit-view`
- [ ] Backend: `POST /api/skill/{skill_id}/structured` route in `backend/skills/routes.py`; same auth as `/stream`
- [ ] Add `metadata.structuredInput` JSON Schema to docparse / ap-validator / ap-poster SKILL.md
- [ ] Frontend: `RunStandaloneSection.tsx` — disclosure block in `InspectorPanel`, picks form by skill id
- [ ] Frontend: `forms/DocparsePicker.tsx` — uses existing `useDocBrowser`; emits `{document_id}`
- [ ] Frontend: `forms/ValidatorJsonForm.tsx` — "Load from last docparse" pre-fill + `<textarea>` + JSON.parse validation
- [ ] Frontend: `forms/PosterVerdictForm.tsx` — verdict radio + reasons list + "Load from last validator"
- [ ] Backend tests: `tests/api_tests/test_structured_invocation.py` — valid input runs, invalid input → 400, 403 on no-access

**Acceptance:** each specialist's form posts to `/structured` and renders results in its Audit View.

---

### M4 — MCP App `ap-vendor-kg` + demo polish (~2 hours)
**Scope:** `fullstack`

- [ ] `infrastructure/mcp-apps/ap-vendor-kg/index.html` — stylised vendor-KG widget (sandboxed iframe, reads citations via postMessage)
- [ ] Register widget in MCP Apps registry (mirror the existing vendor-globe + analytics pattern)
- [ ] Validator A2UI tree mounts the widget when citations are present
- [ ] Update [SUBMISSION.md](../../../SUBMISSION.md) demo script (3-line edit highlighting the Audit View flow)
- [ ] Update [README.md](../../../README.md) one-liner: "one pipeline, four cooperating agents"

**Acceptance:** opening the validator Audit View after a run shows the KG widget with cited vendor highlighted.

---

## Pause Points

- **End of M1** — visual review of chip placement, latency badge styling, panel slide animation
- **End of M3** — manual test of all three forms before MCP App work
- **End of M4** — full demo dry-run

## Risks

- **Event stream tagging in M2**: AG-UI events flow through `stream_agui_events`; adding a `surface` field requires care so existing main-chat rendering is untouched. Mitigation: tag only the *new* A2UI events emitted from `audit_view.py`, not raw `TOOL_CALL_*` events.
- **Form pre-fill state**: "Load from last docparse" requires the frontend to remember the last structured output per specialist. Use `sessionStorage['ap-audit-last-output:{skill_id}']`; populated by `useSpecialistInvocations`.
- **LOCAL_MODE compatibility**: validator's `ai_search` is stubbed locally. `ap-vendor-kg` must render usefully against stubbed citations — checked in M4.

## Velocity Baseline

| Metric | Value |
|--------|-------|
| Recent velocity | ~665 LOC/day (matches GCS-BROWSER baseline) |
| Scope | ~1300 LOC frontend, ~250 LOC backend, ~200 LOC HTML/JS widget |
| Total estimated | 2.5 days |
| Wall-clock target | Finish M1-M3 in one session, M4 next session |
