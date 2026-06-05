# MCP Apps Interaction Pass — Sprint Plan

**Sprint ID**: MCP-INTERACT
**Design Doc**: [mcp-apps-interaction-pass.md](./mcp-apps-interaction-pass.md)
**Status**: Ready to Execute
**Created**: 2026-06-05
**Target wall-clock**: 1.5 days; M1–M3 in one session, M4 follow-up

## Sprint Summary

Cut the Vendor Globe (decorative, no information density). Promote the
Vendor KG into the workbench Vendor tab so the most interesting MCP App
stops being buried in the validator audit view. Wire click→chat
round-trips on both remaining artefacts (KG + Dashboard) using the
vendored spec's `ui/update-model-context` channel verbatim, with a
fork-side `user_intent` convention layered on top. Auto-send routes the
intent through the normal `sendMessage` path; the agent reacts via its
standard chat loop.

Result: 2 MCP Apps with strong bidirectional stories instead of 3
one-way visualisations.

## Decisions Locked (from design doc)

- **Drop the globe entirely** — no archive, no flag. Files deleted, frontend mount deleted, `show_vendor_globe` references stripped from SKILL.md and `handleAction`
- **Same artefact, two mounts** — `ap-vendor-kg` renders in both the workbench Vendor tab AND the validator audit view; payload shape identical so artefact code stays single-source
- **Wire format: `ui/update-model-context` with `structuredContent: { user_intent: { intent, source, context } }`** — spec-compliant message type; `user_intent` is a fork-side host-routing convention, not a protocol extension
- **Auto-send intent as chat message** — same `sendMessage` path as typed text; visible in chat log; trust posture acknowledged as demo-only (production would route to draft input)
- **No backend changes for the bidirectional loop** — host short-circuits the iframe payload locally; the full spec'd `ui/update-model-context → ADK session state → next-turn prompt` path is future work
- **No new SKILL.md backend wiring** — only stripping the dropped globe references

## Milestones

### M1 — Drop the Vendor Globe (~2 hours)
**Scope:** `frontend` + `infrastructure` + `backend skills`

- [ ] Delete `infrastructure/mcp-sandbox/artefacts/vendor-globe/` (entire dir)
- [ ] Delete `frontend/src/components/workspace/VendorGlobePanel.tsx`
- [ ] In [page.tsx](../../../frontend/src/app/chat/[...path]/page.tsx): remove `globeContext` state, the `show_vendor_globe` branch in `handleAction`, the `globeContext` prop on `APWorkbench`, and the legacy non-AP globe slot
- [ ] In `APWorkbench`: drop globe-related badge effect; Vendor tab content is replaced in M2
- [ ] In `ap-orchestrator/SKILL.md`, `ap-validator/SKILL.md`, `invoice-extractor/SKILL.md`: grep + remove `show_vendor_globe` / "show vendor on map" references
- [ ] In [scripts/deploy-mcp-sandbox.sh](../../../scripts/deploy-mcp-sandbox.sh) or `make verify-mcp-artefacts`: drop the globe URL from probe list (find the artefact registration)
- [ ] Tests: typecheck + lint must pass with all references removed

**Acceptance:** `npm run quality:check:fast` clean; grep for `vendor-globe`/`VendorGlobePanel`/`show_vendor_globe` returns nothing outside the design docs.

---

### M2 — Vendor KG in the workbench Vendor tab (~2 hours)
**Scope:** `frontend`

- [ ] Move `VendorKgPanel` import / verify it can mount in the workbench (currently inspector-only)
- [ ] In `APWorkbench` Vendor tab: mount `VendorKgPanel` fed by the already-computed `emittedInvoicePayload` (vendor + audit_citations_csv)
- [ ] Empty-state copy: "Process an invoice — the vendor knowledge graph will populate with the validator's grounded references."
- [ ] Keep the validator audit-view mount unchanged (regression check)
- [ ] If `VendorKgPanel` currently reads its payload from the InspectorPanel's `record.resultContent`, factor the payload extraction into a small helper so both mounts share it

**Acceptance:** Open AP, process an invoice, switch to the workbench Vendor tab — KG renders with vendor + citations. Open the validator audit view — KG also renders with the same data. No regression on the validator's existing mount.

---

### M3 — Bidirectional click→chat (~4 hours)
**Scope:** `infrastructure` (artefact HTML/JS) + `frontend`

- [ ] In [ap-vendor-kg/index.html](../../../infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html): add click handlers on citation rows (`vendor_master:*`, `open_pos:*`, `prior_invoices`) and graph nodes (vendor, prior-invoice); each handler sends a `ui/update-model-context` notification with `structuredContent: { user_intent: { intent: "...", source: "vendor_kg", context: {...} } }`
- [ ] Add `cursor: pointer` + hover styling on clickable elements only
- [ ] In [ap-dashboard/index.html](../../../infrastructure/mcp-sandbox/artefacts/ap-dashboard/index.html): same for the four interactive surfaces — Exceptions tile, Top Vendors row, aging-band bar, GL donut slice
- [ ] In [VendorKgPanel.tsx](../../../frontend/src/components/workspace/VendorKgPanel.tsx) and [APDashboardPanel.tsx](../../../frontend/src/components/workspace/APDashboardPanel.tsx): add `onUserIntent?: (intent: string, context?: Record<string, unknown>) => void` prop; pattern-match on the `user_intent` shape in their existing `onUpdate` (or `ui/update-model-context`) handlers; call `onUserIntent` when matched
- [ ] In `APWorkbench`: add `onMcpUserIntent?: (intent: string, context?: Record<string, unknown>) => void` prop; thread to both panels (workbench mount + InspectorPanel mount for KG)
- [ ] In `page.tsx`: pass `onMcpUserIntent={(text) => void sendMessage(text, { documentIds: includedDocIds, resumedSession: enteredViaResume })}` to `APWorkbench`
- [ ] Also thread `onMcpUserIntent` through `InspectorPanel` → `VendorKgPanel` for the audit-view mount

**Acceptance:** Manual: click each interactive surface in both artefacts; confirm the chat receives the corresponding auto-sent message and the orchestrator responds. Round-trip < 5 seconds.

---

### M4 — Layout polish + workshop notes (~2 hours, deferrable)
**Scope:** `infrastructure` + `docs`

- [ ] Tighten `ap-dashboard/index.html` so it fits 480px workbench width without clipping (smaller donut radius, narrower legend, optional column collapse below 520px)
- [ ] In `ap-vendor-kg/index.html`: verify clickable hover affordances are obvious (especially on dark mode)
- [ ] Append a Friction 19 entry to [docs/learnings/template-protocols-friction.md](../../../docs/learnings/template-protocols-friction.md): *"MCP Apps without an interactive return path read as 'just an iframe'. The 5-line addition of a click→`ui/update-model-context` handler turns the protocol into a story."*
- [ ] Update [SUBMISSION.md](../../../SUBMISSION.md) (if present) demo flow: add a "click in the MCP App" step
- [ ] After M3 ships: redeploy the mcp-sandbox service (`make deploy-mcp-sandbox`) — sandbox doesn't auto-deploy on git push (Friction 14)

**Acceptance:** Dashboard renders cleanly at 480–600px workbench widths. Friction 19 documented. Sandbox redeploy verified by hitting a deployed iframe and clicking through.

---

## Pause Points

- **End of M1** — full grep for any stale globe references in code, docs, scripts; confirm the page still renders the AP demo without errors (Vendor tab will be empty since M2 hasn't landed)
- **End of M2** — manual smoke test of the workbench Vendor tab on a fresh AP run + a resumed session (both should show the KG with the right data)
- **End of M3** — manual end-to-end test: process an invoice, click each interactive surface in both artefacts, verify auto-send + agent response chain

## Risks

- **Sandbox redeploy gap (Friction 14).** Artefact HTML changes don't deploy on a `git push` — `make deploy-mcp-sandbox` is a separate manual step. M3 click handlers won't work on the deployed demo until the sandbox redeploys, even if the frontend changes are live. Mitigation: explicitly call out the redeploy in M4 acceptance and verify via a deployed-URL probe before declaring done.
- **`VendorKgPanel` payload extraction may not factor cleanly.** Currently the panel reads `record.resultContent` (validator's tool-call output as a JSON string). The workbench mount has `emittedInvoicePayload` (already-parsed object). The two shapes differ. Mitigation: M2's "factor into a helper" step explicitly designs the unified input; if the shapes are too different, the panel accepts an optional `payload` prop alongside the existing `record` prop, and one mount uses one path while the other uses the other. Acceptable as a stopgap.
- **Click→chat auto-send during an in-flight pipeline.** If the user clicks a KG citation while the agent is mid-run (`isLoading=true`), the `sendMessage` call will be rejected (the chat input is disabled in that state). Mitigation: gate `onMcpUserIntent` on `!isLoading` in the page-level handler; if loading, swallow silently and log in dev. No UI signal to the user — the iframe's click was their idea and they can see the in-flight indicator already.
- **Citation text isn't structured.** The KG renders citations like `vendor_master:V-1042 · Approved · DE · Cloud Services` — a single string blob. To build a useful click intent we need to either (a) parse the citation string back into structured fields client-side, or (b) plumb structured citations through the artefact's `ui/update-data` payload. (b) is cleaner; M3 includes a small payload-shape adjustment to ship structured citations alongside the rendered strings.

## Velocity Baseline

| Metric | Value |
|--------|-------|
| Recent velocity | ~600 LOC/day on this fork |
| Scope | ~80 LOC frontend wiring + ~150 LOC artefact JS + ~30 LOC deletions + ~50 LOC docs |
| Total estimated | ~1.5 days |
| Wall-clock target | M1–M3 single session, M4 follow-up |

## Out of Scope (deferred)

- Full spec path: `ui/update-model-context → ADK session state → next-turn agent prompt`. We short-circuit at the host instead. Documenting the "production version" path is in the design doc; implementing it is a separate sprint.
- User-confirmation / draft-send flow. Auto-send only.
- Per-message MCP App embeds in chat bubbles. Still workbench/audit-only.
- New MCP App artefacts. Two strong ones beats three weak ones.
