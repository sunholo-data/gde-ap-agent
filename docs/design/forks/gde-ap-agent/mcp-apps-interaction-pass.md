# MCP Apps Interaction Pass — From Decorative Iframes to Interactive Primitives

**Status**: Proposed
**Priority**: P1 (post-submission polish; the protocol value-story differentiator)
**Estimated**: 1.5 days (frontend ~0.5d, sandbox artefact JS ~0.5d, backend/SKILL.md tidy ~0.5d)
**Scope**: Fullstack — sandbox artefact HTML/JS, frontend host wiring, SKILL.md copy
**Dependencies**: Existing MCP Apps sandbox plumbing ([StaticArtefactFrame.tsx](../../../frontend/src/components/workspace/StaticArtefactFrame.tsx)), tabbed Workbench (Friction 8 fix), AP pipeline emit_* state keys
**Created**: 2026-06-05
**Last Updated**: 2026-06-05

## Context

The AP orchestrator ships **three MCP App artefacts** today — Vendor Knowledge Graph, Vendor Globe, and AP Analytics Dashboard. They all render through the same spec-compliant handshake (`StaticArtefactFrame` → proxy iframe → `ui/initialize` → `ui/update-data`), they all consume `hostContext.theme` correctly (Friction 9), and they all ship with realistic seed data (Friction 10). The protocol surface is technically sound.

**But none of them are interactive.** Every artefact is a one-way visualisation: the host pushes data in via `ui/update-data` and the iframe paints pixels. Nothing flows back. The MCP Apps spec explicitly supports the return path — iframes can push structured payloads back via `ui/update-model-context` — and our `StaticArtefactFrame` already wires the receiver side ([StaticArtefactFrame.tsx:258-269](../../../frontend/src/components/workspace/StaticArtefactFrame.tsx#L258-L269)). The capability is plumbed; we just never exercise it.

The result is that the workshop's MCP Apps pitch — *"sandboxed UI primitives the agent can drive **and react to**"* — currently lands as half a story. Visitors see iframes. They don't see the iframe→agent loop, which is the part that makes MCP Apps interesting versus "yet another iframe embed."

Layered on top of that, the **placement** is wrong:
- The most interesting artefact (**Vendor KG**) is buried in the validator's audit-view inspector — clickable only by users who think to open a specialist chip.
- The **Vendor Globe** sits in the prime workbench Vendor tab but is decorative dead weight — a London-to-vendor arc with no information density and no interaction surface.
- The **AP Dashboard** is in the workbench Analytics tab but never moves unless the agent emits `show_ap_dashboard`, and its 640px-ish layout clips at typical 520–600px workbench widths.

## Goals

**Primary goal:** Make the MCP Apps story land by (a) cutting the artefact that adds no value, (b) promoting the interesting artefact into a visible workbench tab, and (c) wiring genuine click→agent interactivity through both remaining artefacts so the workshop can demo the bidirectional protocol loop.

**Success criteria:**
- Net artefact count drops from 3 → 2 (drop Vendor Globe).
- The Vendor KG renders in the workbench Vendor tab as well as in the validator audit view (single artefact, two mount sites).
- Clicking specific surfaces inside the KG and the Dashboard sends a structured user-intent message to the chat, which the orchestrator answers in the next turn — visible end-to-end in under 5 seconds.
- The workshop demo script can show "click vendor node → chat asks about that vendor → agent responds with grounded answer" without typing.
- No regression in the existing handshake, theme handoff, or Friction-10 seed data.

**Non-goals:**
- Adding new MCP App artefacts. Two with strong stories beats three with weak ones.
- Inline chat-bubble MCP App embeds (still workbench/audit-only — out of scope).
- A user-confirmation / draft-send flow (auto-send for demo; flag for future work).
- Implementing the full `ui/update-model-context` → ADK session state → next-turn agent prompt loop documented in [vendored MCP Apps spec](../../../.claude/skills/agent-protocols/references/mcp-apps-spec-2026-01-26.md). For this pass, the host intercepts the iframe payload locally and turns it into a chat send — the agent reacts via its normal chat path, not via session-state injection. Simpler, more demoable, less moving parts. Full session-state path is a future sprint.

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | Click → chat send → agent response in <5s; no new round-trip on the hot path |
| 2 | EARNED TRUST | 0 | Auto-send is a small trust surface (iframe initiates a chat message); mitigated by the message being visible in the chat log and the user free to stop/edit. Future user-confirmation flow noted in Non-Goals |
| 3 | SKILLS, NOT FEATURES | +1 | The interactive artefacts surface a skill's grounding data (vendor master, prior invoices, GL distribution) — they extend skill observability rather than adding novel feature affordances |
| 4 | RIGHT MODEL, RIGHT MOMENT | 0 | No model changes |
| 5 | GRACEFUL DEGRADATION | +1 | If the iframe handshake fails, the artefact still shows seed data (Friction 10 baseline); the click-to-chat is an additive layer that no-ops on handshake failure |
| 6 | PROTOCOL OVER CUSTOM | +1 | Uses the vendored spec's `ui/update-model-context` message type verbatim. The "user_intent" key is a fork-side convention layered on top of the spec, not a new wire format |
| 7 | API FIRST | 0 | No new backend endpoints; routing is frontend-local |
| 8 | OBSERVABLE BY DEFAULT | +1 | The auto-sent chat message is visible in the chat log; every interaction is traceable through the normal AG-UI event stream |
| 9 | SECURE BY CONSTRUCTION | 0 | The iframe runs in the existing sandbox (`allow-scripts allow-same-origin` inside the double-iframe proxy); no new origin, no new postMessage handler. The user_intent payload is treated as untrusted user input and goes through the same `sendMessage` path as a typed message |
| 10 | THIN CLIENT, FAT PROTOCOL | 0 | Marginal — the routing layer (intent → sendMessage) is client-side, but the click semantics are owned by the artefact (which is also client code shipped from the sandbox) |
| | **Net Score** | **+5** | Threshold: >= +4 ✅ |

**Conflict justifications:** None — no axiom scores -1.

## Design

### What to drop

**Vendor Globe** — delete entirely.

- File deletions: [infrastructure/mcp-sandbox/artefacts/vendor-globe/](../../../infrastructure/mcp-sandbox/artefacts/vendor-globe/), [frontend/src/components/workspace/VendorGlobePanel.tsx](../../../frontend/src/components/workspace/VendorGlobePanel.tsx)
- Frontend wiring removed: `show_vendor_globe` action handler in `handleAction` at [page.tsx](../../../frontend/src/app/chat/[...path]/page.tsx) + the legacy non-AP globe slot below it + `globeContext` state and the Vendor tab's globe-empty-state copy.
- Backend SKILL.md tidy: remove "show vendor on map" / `show_vendor_globe` references in [ap-orchestrator/SKILL.md](../../../backend/skills/templates/ap-orchestrator/SKILL.md), [ap-validator/SKILL.md](../../../backend/skills/templates/ap-validator/SKILL.md), and the workspace surface card layout in [invoice-extractor/SKILL.md](../../../backend/skills/templates/invoice-extractor/SKILL.md).

Justification: the globe is a London-to-vendor-country arc with no information density and no interaction surface. It demonstrates nothing about MCP Apps that the KG and Dashboard don't demonstrate better. Killing it shrinks the demo surface and removes the "tab badged, click, see an underwhelming globe" path that judges currently hit.

### What to promote

**Vendor Knowledge Graph** moves into the workbench Vendor tab — same artefact, two mount sites:

- Existing mount: validator audit view via [InspectorPanel.tsx](../../../frontend/src/components/audit/InspectorPanel.tsx) (unchanged).
- New mount: [APWorkbench](../../../frontend/src/app/chat/[...path]/page.tsx) Vendor tab — replaces the deleted `VendorGlobePanel`. Tab renamed from "Vendor" eyebrow to keep "MCP App · Vendor KG" eyebrow style.
- Both mounts feed the same artefact ([infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html](../../../infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html)) with the same `ui/update-data` payload shape, so the workbench mount and the audit-view mount stay in sync visually.
- Data source for the workbench mount: the merged emit_* payload already computed for [InvoiceHeroCard](../../../frontend/src/components/chat/InvoiceHeroCard.tsx) (vendor_name, audit_citations_csv, etc.). No new fetch.

### What to add — bidirectional click→chat loop

**Wire format (uses the vendored spec, no extension):**

The iframe pushes a structured user-intent payload via the spec's standard `ui/update-model-context` notification ([mcp-apps-spec-2026-01-26.md L34-L39](../../../.claude/skills/agent-protocols/references/mcp-apps-spec-2026-01-26.md#L34-L39)). The `structuredContent` field uses a fork-side convention:

```ts
// iframe → host (via JSON-RPC notification with method "ui/update-model-context")
{
  user_intent: {
    intent: "Tell me more about vendor V-1042's history",
    source: "vendor_kg" | "ap_dashboard",
    context?: { vendor_id?: string; invoice_id?: string; ... }  // best-effort, audit-only
  }
}
```

`StaticArtefactFrame` already receives `ui/update-model-context` and forwards `structuredContent` via its `onUpdate` callback ([StaticArtefactFrame.tsx:258-269](../../../frontend/src/components/workspace/StaticArtefactFrame.tsx#L258-L269)). The convention is therefore additive — no protocol change, no new message type, no new postMessage handler.

**Host-side routing:**

- `VendorKgPanel` and `APDashboardPanel` (the two callers of `StaticArtefactFrame`) gain a new prop `onUserIntent: (intent: string, context?: Record<string, unknown>) => void`.
- Inside the `onUpdate` callback they pattern-match on the `user_intent` key and call `onUserIntent(structuredContent.user_intent.intent, ...)`. Any other `structuredContent` shape continues to flow through unchanged (forward-compat with future iframe→host signals).
- `APWorkbench` accepts a new prop `onMcpUserIntent` and threads it down to both panels.
- The page's `APWorkbench` mount in [page.tsx](../../../frontend/src/app/chat/[...path]/page.tsx) supplies `onMcpUserIntent={(text) => void sendMessage(text, { documentIds: includedDocIds, resumedSession: enteredViaResume })}` — same `sendMessage` path a typed chat message uses, so the intent shows in the chat log and the agent responds via the normal AG-UI stream.

**Interactive surfaces — Vendor KG:**

| Click target | Intent string sent to chat |
|---|---|
| Citation row `vendor_master:V-1042` | "Tell me more about vendor V-1042's approval status and spend limit" |
| Citation row `open_pos:PO-2026-0189` | "Show me the open PO PO-2026-0189 — amount, approver, status" |
| Citation row `prior_invoices` | "Summarise the prior invoices from this vendor in the last 12 months" |
| Prior-invoice graph node | "Show me prior invoice {invoice_id} details" |
| Central vendor node | "What's the full vendor master record for {vendor_id}?" |

**Interactive surfaces — AP Dashboard:**

| Click target | Intent string sent to chat |
|---|---|
| "Exceptions" stat tile | "List the invoices currently flagged for review" |
| "Top Vendors by Value" row | "List all open invoices from {vendor}" |
| Aging-band bar (e.g. "31–60 days") | "Which invoices are in the 31–60 day aging band?" |
| GL code donut slice | "Show invoices coded to {gl_code}" |

Each clickable element gets an explicit hover state (`cursor: pointer`, subtle highlight) so the affordance is visible. Non-clickable elements (axes, legends) stay non-interactive — the interactivity is a focused affordance, not a "everything is clickable" surface.

### Trust & UX

Auto-sending a chat message from an iframe postMessage is a real trust surface. For this fork we accept it because:

1. The iframe origin is our own `mcp-sandbox` Cloud Run service (not third-party).
2. The user can see the auto-sent message in the chat log and the in-flight indicator immediately — nothing is hidden.
3. The user can hit Stop or send a follow-up to correct course.
4. The `intent` payload is treated as untrusted user input (same `sendMessage` path as typed text), so it can't bypass any prompt-injection mitigations the agent already has.

For a production version (out of scope here, noted for the workshop's "what would change for prod?" talking point):
- Render the intent as a **draft** in the chat input rather than auto-send; user confirms by hitting Send.
- Show an `[MCP App · Vendor KG]` provenance chip on the message bubble so the audit log distinguishes typed messages from iframe-initiated ones.
- Rate-limit click → intent flows to one per ~2s to prevent runaway loops if an artefact misbehaves.

### Implementation Plan

#### Phase 1 — Drop the globe (~2h)

- [ ] Delete `infrastructure/mcp-sandbox/artefacts/vendor-globe/` (directory)
- [ ] Delete `frontend/src/components/workspace/VendorGlobePanel.tsx`
- [ ] In `page.tsx`: remove `globeContext` state, remove `show_vendor_globe` branch from `handleAction`, remove the legacy non-AP globe slot and its `md:max-w-xl` wrapper
- [ ] In `APWorkbench`: remove the Vendor tab's empty-state copy referencing the globe; tab eyebrow stays "MCP App"
- [ ] In `ap-orchestrator/SKILL.md`, `ap-validator/SKILL.md`, `invoice-extractor/SKILL.md`: grep + remove `show_vendor_globe` / "show vendor on map" mentions
- [ ] Update [docs/learnings/template-protocols-friction.md](../../../docs/learnings/template-protocols-friction.md) — note in the existing "what worked well" section that we dropped the globe
- [ ] Verify `make verify-mcp-artefacts` still passes (will fail on the deleted globe URL; update the script's URL list)

#### Phase 2 — Vendor KG in workbench (~2h)

- [ ] Move `VendorKgPanel` import path if needed; mount inside `APWorkbench` Vendor tab content
- [ ] Wire the workbench mount to the merged emit_* payload (already computed via `emittedInvoicePayload` page state) — extract vendor + citations into the artefact's `ui/update-data` payload shape
- [ ] Keep the audit-view mount unchanged; both share the same payload shape so the artefact code stays single-source
- [ ] Empty-state copy when no invoice has been processed yet: "Process an invoice — the vendor knowledge graph will populate with the validator's grounded references."

#### Phase 3 — Bidirectional click→chat (~4h)

- [ ] In `ap-vendor-kg/index.html`: add click handlers on citation rows and graph nodes; on click, send `ui/update-model-context` notification with `structuredContent: { user_intent: { intent, source: "vendor_kg", context } }`
- [ ] In `ap-dashboard/index.html`: same for the four interactive surfaces listed above
- [ ] In `StaticArtefactFrame.tsx`: no change needed (already forwards `structuredContent`)
- [ ] Add `onUserIntent?: (intent: string, context?: Record<string, unknown>) => void` prop to `VendorKgPanel` and `APDashboardPanel`; pattern-match on the `user_intent` shape inside their `onUpdate` handlers
- [ ] Add `onMcpUserIntent?: (intent: string, context?: Record<string, unknown>) => void` prop to `APWorkbench`; thread it to both panels
- [ ] In `page.tsx`: pass `onMcpUserIntent={(text) => void sendMessage(text, { documentIds: includedDocIds, resumedSession: enteredViaResume })}` to `APWorkbench`
- [ ] Add cursor + hover states on each interactive surface in both artefacts
- [ ] Manual smoke test (see Testing)

#### Phase 4 — Layout + workshop polish (~2h)

- [ ] Tighten `ap-dashboard/index.html` layout to fit 480px workbench width (smaller donut, narrower legend, single-column responsive collapse below 520px)
- [ ] Update [SUBMISSION.md](../../../SUBMISSION.md) demo flow: add a "click in the MCP App" step
- [ ] Update workshop talking-points doc (or [docs/learnings/template-protocols-friction.md](../../../docs/learnings/template-protocols-friction.md)) with a Friction 19 entry: *"MCP Apps without an interactive return path read as 'just an iframe'. The 5-line addition of a click→`ui/update-model-context` handler turns the protocol into a story."*

### Files Changed Summary

| File | Change |
|---|---|
| `infrastructure/mcp-sandbox/artefacts/vendor-globe/**` | **DELETE** |
| `infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html` | Add click handlers + `ui/update-model-context` calls |
| `infrastructure/mcp-sandbox/artefacts/ap-dashboard/index.html` | Same + responsive layout tweaks for 480–600px |
| `frontend/src/components/workspace/VendorGlobePanel.tsx` | **DELETE** |
| `frontend/src/components/workspace/VendorKgPanel.tsx` | Add `onUserIntent` prop; pattern-match in `onUpdate` |
| `frontend/src/components/workspace/APDashboardPanel.tsx` | Same |
| `frontend/src/app/chat/[...path]/page.tsx` | `APWorkbench` gets `onMcpUserIntent` prop; remove `globeContext`; mount `VendorKgPanel` in Vendor tab |
| `backend/skills/templates/{ap-orchestrator,ap-validator,invoice-extractor}/SKILL.md` | Remove `show_vendor_globe` references |
| `docs/learnings/template-protocols-friction.md` | Add Friction 19 note |
| `SUBMISSION.md` | Demo-script update |
| `scripts/verify-mcp-artefacts.sh` (or `Makefile` target) | Drop globe URL from probe list |

## Migration & Rollout

**Database / Firestore migrations:** None.

**Feature flags:** None — this is a demo polish, ship behind the standard `dev → test → prod` promotion. The interactive layer degrades gracefully (no click → no intent → no message), so there's no "kill switch" needed.

**Rollback plan:** Revert the commit. The dropped globe artefact is recoverable via git; the artefact dir is small. No data implications.

**Sandbox deploy:** Both artefacts ship through `make deploy-mcp-sandbox` (per [Friction 14](../../../docs/learnings/template-protocols-friction.md)). The sandbox redeploy is a manual step today — out of scope to fix in this doc.

## Testing Strategy

**Manual (primary):**
- [ ] Run an invoice end-to-end on AP. Switch to the workbench Vendor tab — KG should render with vendor + citations from the validator's run.
- [ ] Click each interactive surface in the KG; confirm the chat receives the corresponding auto-sent message and the orchestrator answers.
- [ ] Switch to the Analytics tab. Click each interactive surface; same end-to-end check.
- [ ] Open the validator audit view; KG mount still works there (regression check).
- [ ] On a narrow viewport (~480px workbench), confirm the dashboard no longer clips.
- [ ] Resume an older session; KG and Dashboard populate from `emittedInvoicePayload`; click interactions still work.

**Automated:**
- [ ] `make verify-mcp-artefacts` passes after the globe URL is dropped from the probe list.
- [ ] Frontend `npm run quality:check:fast` — typecheck + lint pass with the new props.
- [ ] Add a Vitest unit test for the new `onUserIntent` handler in `VendorKgPanel` that feeds a synthetic `ui/update-model-context` structuredContent and asserts the callback fires with the expected intent string.

**Out-of-scope testing (worth noting for future work):**
- Backend integration test exercising the full `ui/update-model-context` → ADK session state → next-turn agent prompt path (spec's intended flow). Not in scope because we short-circuit at the host.

## Workshop Talking Points

The slide-friendly version of why this matters:

1. **MCP Apps are bidirectional by design.** The spec defines `ui/update-model-context` exactly for the iframe → agent return path. Most demos skip it; ours uses it.
2. **Sandboxed but not isolated.** The iframe runs in a strict sandbox (no host DOM access, no host storage), but it can still *talk* to the agent through a typed protocol channel. Sandboxing and integration aren't a dichotomy.
3. **Trust is a host policy decision.** Our demo auto-sends iframe-initiated intents; a production app could route them to a draft input for user confirmation. The protocol gives you the data flow; the trust posture is yours to set.
4. **Less is more.** Dropping the globe demonstrates that a polished two-artefact demo lands harder than a busy three-artefact demo. Tell judges *"we cut features to make the remaining ones shine."*

## Next Steps

This is the design doc only. Implementation should follow as a separate sprint doc — `mcp-apps-interaction-pass-sprint.md` — following the fork's existing pattern ([schema-enforced-extraction.md](./schema-enforced-extraction.md) → [schema-enforced-extraction-sprint.md](./schema-enforced-extraction-sprint.md)). The sprint doc should:

- Break the four phases above into day-1 / day-2 commits with rollback points
- Identify the canned demo invoice that exercises the most interactive surfaces
- Schedule a 15-minute live-demo dry run with the sandbox deployed, to catch any artefact loading / theme / postMessage regressions before workshop day

## Related Documents

- [Multi-Agent Inspector UX](./multi-agent-inspector-ux.md) — the sprint that introduced the validator audit view + the original `ap-vendor-kg` mount
- [Competition Polish Sprint](./competition-polish-sprint.md) — M1–M6 sprint that shipped the current MCP Apps wiring
- [Template Protocols Friction](../../../docs/learnings/template-protocols-friction.md) — Frictions 8 (Workbench), 9 (theme), 10 (seed data), 14 (sandbox auto-deploy gap) are the prior MCP App work this doc builds on
- [Vendored MCP Apps Spec](../../../.claude/skills/agent-protocols/references/mcp-apps-spec-2026-01-26.md) — the protocol reference; `ui/update-model-context` semantics
- [StaticArtefactFrame.tsx](../../../frontend/src/components/workspace/StaticArtefactFrame.tsx) — the host-side handshake; already wired for the receive side
- [VendorKgPanel.tsx](../../../frontend/src/components/workspace/VendorKgPanel.tsx), [APDashboardPanel.tsx](../../../frontend/src/components/workspace/APDashboardPanel.tsx) — the two panels that mount the artefacts
- [Product Axioms](../../../docs/product-axioms.md) — scoring rubric used above
