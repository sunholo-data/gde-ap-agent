# Protocol-stack friction in the AP template — workshop learnings

> Captured 2026-06-03 after a debugging session that surfaced four
> intertwined bugs in the deployed demo. None of them were "protocol
> design" bugs — they were template-layer + integration-seam bugs
> that the workshop story should call out explicitly so attendees
> don't rediscover them.

## TL;DR

The protocol stack (AG-UI / A2UI / MCP / function-as-schema) was the
right choice and IS doing useful work. The friction comes from three
specific places where the **template defaults** push authors into
patterns that are subtly wrong for an AP-style pipeline:

1. **Two-pass `response_schema` callback** as the default for
   structured output — costs a Gemini round-trip per specialist.
2. **`updateDataModel` defaulting to root-REPLACE** in A2UI v0.9 —
   non-obvious to template authors writing multi-stage workflows.
3. **`after_agent_callback` return values silently dropped** by the
   template's composition wrapper — a 12-line bug that erased every
   schema callback's output before it reached the wire.

The workshop should teach the **better defaults** up front and use
the friction points as worked examples. Specifics below.

---

## Friction 1 — Structured output: prefer function-as-schema

### What the template ships

The template ships `backend/tools/structured_extraction.py` plus a
schema registry in `backend/tools/schemas/__init__.py`. A skill
declares `metadata.extractionSchema: <name>` and the
`after_agent_callback` fires a SECOND Gemini call with
`response_mime_type: application/json` + `response_schema: <schema>`
to produce schema-validated JSON. The validated JSON is appended to
the agent's response as an extra `Part`.

### Why it's the template's default

Gemini's API forbids combining `tools` with `response_schema` strict
mode in a single `generate_content` call ([Gemini structured-output
docs](https://ai.google.dev/gemini-api/docs/structured-output)). For
agents that need BOTH tools AND validated JSON output, the two-pass
pattern is the most direct workaround — you run the agent normally
to get tool calls + narration, then re-extract via a constrained
call. The design doc that introduced this pattern ([forks/gde-ap-agent/schema-enforced-extraction.md](../design/forks/gde-ap-agent/schema-enforced-extraction.md))
explicitly rejected function-as-schema for **determinism**: "the
callback fires unconditionally when a schema is declared, not on the
LLM's prompt-following discretion."

### What the better default is

**Function-as-schema.** Declare each specialist's structured output as
a `FunctionTool` whose typed parameters mirror the JSON Schema.
Gemini's function-calling enforces the types as schema — the model
literally cannot emit a call with the wrong arg types.

For the AP pipeline this looks like:

```python
# backend/tools/ap_pipeline_emit.py
async def emit_invoice_extraction(
    vendor_name: str,
    invoice_number: str,
    currency: str,
    total: float,
    # … optional typed fields …
    tool_context: ToolContext = None,
) -> str:
    """Emit the extracted invoice in the canonical ap_invoice schema.

    Call exactly once at end of turn. The typed parameters ARE the
    schema; Gemini's function-calling enforces them.
    """
    payload = {"vendor_name": vendor_name, ...}
    tool_context.state["app:emitted:invoice"] = payload
    return f"Emitted ap_invoice for {vendor_name} / {invoice_number}"
```

In the SKILL.md frontmatter, add the tool name to `tools:`. In the
prompt body, instruct: "Call `emit_invoice_extraction` exactly once at
the end of your turn."

### Trade-offs to teach explicitly

| Aspect | response_schema callback | function-as-schema |
| --- | --- | --- |
| LLM calls per specialist | **2** | **1** |
| Latency overhead | +3-5s per specialist | none |
| Schema enforcement | strict (constrained decoding) | strict (function-calling) |
| Failure mode | callback always runs | LLM might forget to call tool |
| Frontend integration | text Part needs JSON-sniffing | tool-call event is canonical |
| Determinism story | strong | needs strong prompting |

### The right answer is both

Function-as-schema as the **primary path**, response_schema as a
**fallback** when the emit tool wasn't called this turn. In
`backend/tools/structured_extraction.py` short-circuit the callback
when `app:emitted:<skill>` is set:

```python
for key in ("app:emitted:invoice", "app:emitted:verdict", "app:emitted:posting"):
    if callback_context.state.get(key):
        return None  # function-as-schema win
```

The fallback only fires on the LLM-forgot-to-call-the-tool case,
preserving determinism while keeping the success-path fast.

### Template improvement

Ship `tools/<skill>_emit.py` as the canonical pattern, with
`structured_extraction_callback` documented as the fallback. The
current template inverts that emphasis.

---

## Friction 2 — A2UI `updateDataModel` defaults to root-REPLACE

### Symptom

Multi-stage pipeline where each specialist patches its slice of a
shared workspace surface. The extractor emits the full layout +
`updateDataModel` with `{vendor, invoiceNumber, total, ...}`.
Validator emits `updateDataModel` with `{status, verdict}`. Poster
emits `updateDataModel` with `{status, glCode, action}`. By the time
the user sees the final card, every field except the poster's is
**blank**.

### Root cause

A2UI v0.9 `updateDataModel.value` with no `path` field defaults to
`path: "/"`, and the SDK calls `surface.dataModel.set("/", value)`
which **replaces the entire data model** (see
`@a2ui/web_core/v0_9/processing/message-processor.js`
`processUpdateDataModelMessage`).

So when the validator's update lands with `{status, verdict}`, the
SDK overwrites root and the extractor's `vendor`, `invoiceNumber`,
etc. are gone.

### The fix

Send **per-path** patches:

```json
[
  { "version": "v0.9", "updateDataModel": { "surfaceId": "workspace", "path": "/status", "value": "..." } },
  { "version": "v0.9", "updateDataModel": { "surfaceId": "workspace", "path": "/verdict", "value": "..." } }
]
```

Each `set("/status", "...")` patches a single leaf, leaving prior
fields intact.

### Template improvement

The starter SKILL.md template for multi-stage skills should ship the
per-path form, not the root-level form. And the template's docs
section on A2UI should call out this gotcha — it's the kind of thing
that bites every author once.

---

## Friction 3 — `after_agent_callback` return values silently dropped

### Symptom

The schema-validated JSON Part appended by
`structured_extraction_callback` (`Content(role="model",
parts=[Part.from_text(json)])`) never appeared in the AG-UI stream
the frontend received. So the frontend's `JsonCardBuilder` (which
detects pure-JSON text and converts it to an A2UI Card) had nothing
to chew on. Net effect: even when the agent obeyed "don't emit JSON
inline," the chat had no Card to show.

### Root cause

In `backend/adk/agent.py`:

```python
async def _composed_after_agent(callback_context: object) -> None:
    _after_agent_response(callback_context)
    await structured_extraction_callback(callback_context)  # ← return value dropped
```

The composition wrapper was annotated `-> None` and **silently
discarded** the callback's return value. ADK only emits an extra
response event when the callback returns `Content`; with `None`
returned, nothing appears.

Twelve-line bug, hours to find from the symptom because every
component looked right in isolation.

### Template improvement

The composition pattern is template-shipped. The fix is one line
(`return await structured_extraction_callback(callback_context)`)
plus a typed return annotation, but it would be better to ship a
helper:

```python
def compose_after_agent_callbacks(*callbacks):
    """Compose after-agent callbacks; the first non-None return wins."""
    async def composed(ctx):
        for cb in callbacks:
            result = await cb(ctx) if asyncio.iscoroutinefunction(cb) else cb(ctx)
            if result is not None:
                return result
        return None
    return composed
```

…by analogy with `compose_before_tool_callbacks` already in the
template. Returning the first non-None Content matches ADK's
expectation that an after-agent callback either modifies state OR
returns a follow-up Content event.

---

## Friction 4 (small) — A2UI `Button` shape changed across v0.8 → v0.9

### Symptom

The first `send_a2ui_json_to_client` call in every pipeline run
returned a validation error:

```
'show_vendor_globe' is not valid under any of the given schemas
'child' is a required property
'action', 'component', 'context', 'label' were unexpected
```

The LLM retried with the correct shape on attempt 2. Every run paid
one wasted Gemini turn.

### Root cause

The SKILL.md template's workspace-card JSON used the v0.8 Button shape:

```json
{"id": "btn", "component": "Button", "label": "...", "action": "stringName", "context": {}}
```

A2UI v0.9's BasicCatalog Button requires:

```json
{"id": "btn", "component": "Button", "child": "btn_text", "action": {"event": {"name": "...", "context": {}}}}
{"id": "btn_text", "component": "Text", "text": "..."}
```

### Template improvement

Ship the v0.9 examples in the template (the SKILL.md JSON snippets
explicitly), and add a backend validation step that runs the
template's surface examples through the SDK schema validator at
seed time, so a regression is caught at deploy rather than at
runtime.

---

## What WORKED well in the protocol stack

To balance — the protocols ARE doing useful work in this demo:

- **A2UI workspace surface** is the centrepiece of the user-facing
  story. The "Acme GmbH invoice review card on the left, chat on the
  right, both driven by structured agent output" demo lands cleanly
  once the per-path issue above is fixed. The declarative-UI angle is
  genuinely valuable.

- **AG-UI streaming** never failed once during the debug session.
  Text deltas, tool calls, custom STAGE_PROGRESS events all flowed
  reliably. The `firedStages` improvement we added (accumulating
  stage names so progress rails advance through SequentialAgent
  sub-stages) was a pure feature add, not a fix.

- **ADK SequentialAgent** is the right abstraction for a deterministic
  pipeline like this. The orchestrator transfers once; the pipeline
  walks specialists in order; no LLM at the workflow layer means no
  prompt-injection risk for the pipeline ordering.

- **MCP for vendor-master + erp-posting** is a clean separation —
  agents call typed tools, the implementations live in a separate
  process the platform team can swap. (Live-deployed wiring of this
  remains buggy — `vendor-master` server not registered in dev
  Firestore — but the architecture is sound.)

The summary: protocols good, defaults in the template need work.

---

## Workshop talking points

1. **Show function-as-schema as the default, not response_schema
   callback.** Save the callback pattern for the case where the
   specialist genuinely has no tools at all.

2. **Demo the `updateDataModel` per-path vs root-replace difference**
   explicitly. Show the data-clobber bug in a 30-second worked
   example. Attendees will hit this once and never forget.

3. **`after_agent_callback` return values are the canonical way to
   emit follow-up events.** Show the composed-callbacks pattern that
   forwards Content rather than dropping it.

4. **The template should ship verifying smoke scripts.** Our
   `whoami_smoke.py` + `verify-judge-path.sh` pair lets an agent
   self-verify a deploy end-to-end. Workshop should hand attendees
   the same pair pre-wired.

5. **Don't conflate "protocol limitation" with "template default
   limitation".** The protocol stack here is solid; the template's
   ergonomics around it are what needs improvement. That distinction
   matters for the workshop's pitch — we're teaching protocols, not
   apologising for ADK.

---

# Update 2026-06-05 — chat-surface frictions

A second round of friction surfaced while polishing the chat surface
for the AP demo (workbench layout, audit panes, embedded MCP App
iframes, avatars). None of these are protocol bugs either — they're
template-component defaults that don't survive a real-world skill with
many sessions, many docs, and three MCP App embeds active at once.
Captured here so the next workshop / template-cut absorbs them.

## Friction 5 — `DocumentHistoryPanel` grows unbounded

### Symptom

Open a frequently-used document in the workbench Document tab.
`DocumentHistoryPanel` lists every chat session that touched that doc.
For a doc with 50+ sessions, the list pushes the actual
`DocumentPanel` off-screen — the user can't see the document they
opened.

### Root cause

[frontend/src/components/chat/DocumentHistoryPanel.tsx](../../frontend/src/components/chat/DocumentHistoryPanel.tsx)
defaults `isOpen={true}` and renders its open body with no `max-h` or
internal scroll. The parent Document pane is a flex column with
`flex-1` on `DocumentPanel` and the history panel as a sibling — when
the history's intrinsic height exceeds available space, it wins
because the row body is `space-y-3` with intrinsic content height.

### Fix

```tsx
const [isOpen, setIsOpen] = useState(false); // collapsed by default

// body wrapper
<div className="max-h-[25vh] space-y-3 overflow-y-auto …">
```

Default-collapsed makes the document the primary thing on screen; the
25vh cap means even an expanded list scrolls within its own container
instead of pushing siblings out of the viewport. A count badge next to
the header (`Conversations [50]`) tells the user the history exists
without needing to expand.

### Template improvement

Ship the cap + collapsed default. Optionally take a `maxHeight` prop
for forks that want a taller list. The current default ("always
visible, unbounded") is wrong for any doc used more than a handful of
times.

---

## Friction 6 — A2UI `Row` has no fixed-label-column convention

### Symptom

Every JSON-shaped Card the template renders — audit pane input/output,
inline emit_* in the chat bubble, workspace surface card — shows
cramped, two-line labels: "Po Reference", "Invoice Number", "Currency"
wrap onto two lines as the container narrows. Numeric values land on
the next line below the label, breaking the "ledger" reading that
financial data needs.

### Root cause

`buildA2UICardFromJson` in
[frontend/src/components/chat/JsonCardBuilder.ts](../../frontend/src/components/chat/JsonCardBuilder.ts)
renders scalar key/value pairs as
`Row([labelText, valueText])` — both children are A2UI `Text`
components, neither has a width constraint. A2UI v0.9's BasicCatalog
`Row` is a `flex` container with no convention for "label column +
value column"; the SDK gives both children whatever width their
content wants and wraps in flow order.

### Fix

Bypass A2UI for scalar-heavy JSON. We added
[JsonAsStructuredCard.tsx](../../frontend/src/components/chat/JsonAsStructuredCard.tsx)
+ a [DefinitionList](../../frontend/src/components/shared/DefinitionList.tsx)
primitive that owns the layout: labels in a fixed `minmax(120px, 160px)`
column, values flex-grow with monospace tabular-nums on numeric fields.
The workspace path (`A2UISurfaceMount` consuming backend-emitted A2UI
messages) is untouched — that's still "real A2UI on the wire" for
the protocol-purity story; the change is only at the JSON→inline-card
render layer.

### Template improvement

Ship a `<DefinitionList>` primitive in the template and switch
`JsonAsA2UICard`'s inline render path to use it. Or — better — extend
the A2UI BasicCatalog with a `DefinitionList` component whose semantics
explicitly include a label-column convention. The current cramped feel
is felt by **every** fork that renders structured tool payloads
inline, not just the AP one.

---

## Friction 7 — `InputOutputCard` is empty on every `emit_*` audit row

### Symptom

Open the Audit View on any specialist that uses function-as-schema
(invoice-extractor, ap-validator, ap-poster). The INPUT side renders
the structured payload nicely. The OUTPUT side shows:

> *Your structured output has been recorded. STOP. Do NOT call this
> tool again. End your turn now — the SequentialAgent pipeline will
> advance to the next specialist.*

…which is the orchestrator-facing STOP message, not the emitted data.
Judges open the audit view to see the agent's structured output and
find a blank panel with a guard rail string.

### Root cause

[backend/tools/ap_pipeline_emit.py](../../backend/tools/ap_pipeline_emit.py)
returns the STOP_AFTER_EMIT_MESSAGE string — that **is** the tool
result. The actual emitted payload is the tool *args* (the
function-as-schema pattern). The frontend's
`useSpecialistInvocations` records `argsJson` (input) and the tool's
result text (output) but never substitutes args for output on
function-as-schema tools.

### Fix

In [InspectorPanel.tsx](../../frontend/src/components/audit/InspectorPanel.tsx)
gate on the tool name:

```tsx
<InputOutputCard
  title={record.name}
  input={record.argsJson}
  output={
    record.name.startsWith("emit_") && record.argsJson
      ? record.argsJson  // for emit_* the args ARE the payload
      : record.resultContent
  }
  outputLabel={
    record.name.startsWith("emit_")
      ? "Emitted payload (function-as-schema)"
      : "Output (specialist → orchestrator)"
  }
/>
```

The audit view now shows the same structured Card on both sides — INPUT
labelled as "orchestrator → specialist", OUTPUT labelled as "emitted
payload" — making the function-as-schema mental model explicit.

### Template improvement

Bake the `emit_*` substitution into the template's audit view, or
generalise it: any tool whose result equals a "stop" sentinel should
show its args as the output. Better still — surface a typed flag on
the FunctionTool itself (e.g., `result_is_sentinel=True`) so the
audit view doesn't have to string-match tool names.

---

## Friction 8 — Workspace pane is a single-slot conditional ladder

### Symptom

When the user opens the Vendor Globe MCP App, the invoice card
disappears. When the AP Dashboard opens, the globe disappears.
When a doc is expanded from the sidebar, both vanish. The user
loses context every time the agent emits a `surface_action`.

### Root cause

The template's chat page renders the right-hand pane with
mutually-exclusive conditionals:

```tsx
{expandedTab && <DocumentPanel … />}
{!expandedTab && !globeContext && <WorkspaceSurfaceRegion … />}
{!expandedTab && globeContext && !dashboardOpen && <VendorGlobePanel … />}
{!expandedTab && dashboardOpen && <APDashboardPanel … />}
```

Only one slot can render at a time. The `surface_action` handler swaps
the slot wholesale, which means:
- MCP App iframes remount on every switch (postMessage handshake fires
  again — observable as a ~200ms flash + re-init)
- The user's mental model breaks ("where did my invoice go?")
- Inline emit_* Cards in the chat bubble and the workspace
  surface card render the same data in two different styles

### Fix

Replace the conditional ladder with a persistent tabbed
[`Workbench`](../../frontend/src/components/chat/Workbench.tsx). All
tabs (Invoice · Document · Vendor · Analytics) stay mounted; switching
just toggles a `hidden` class so iframes don't remount. The
`surface_action` handler badges the relevant tab instead of swapping
panes; the user keeps control of what's visible.

### Template improvement

Ship the tabbed-pane primitive as the default workspace pattern. The
current "swap the whole right pane" pattern works for skills with one
output type, but every interesting skill has multiple (chat output,
document view, embedded artifacts). Make the multi-surface case the
default; the single-surface case is just a one-tab Workbench.

---

## Friction 9 — MCP App artefacts ignore `hostContext.theme`

### Symptom

The host shell flipped to light mode (parse-blue on white). The
embedded MCP App iframes (Vendor Globe, AP Analytics, Vendor KG) still
render in dark navy + gold — visually clashing with the host page,
looking pasted-on.

### Root cause

`StaticArtefactFrame` correctly sends `hostContext.theme` in the
`ui/initialize` handshake (per [MCP Apps spec §Host Context](https://modelcontextprotocol.io)).
The template's artefact HTMLs in
[infrastructure/mcp-sandbox/artefacts/](../../infrastructure/mcp-sandbox/artefacts/)
hardcode their colours (`#0a0f1e`, `#e8a800`) and never read the
hostContext field — so the host's theme intent is lost.

### Fix

Replace hardcoded colours with CSS custom properties on
`:root[data-theme="light"|"dark"]`. After the artefact's
`ui/initialize` response comes back, set
`document.documentElement.dataset.theme = initResult.hostContext.theme`.
Also add a runtime `ui/update-theme` notification so the host can flip
themes mid-session.

### Template improvement

Ship a shared `infrastructure/mcp-sandbox/artefacts/shared/theme.css`
with the canonical CSS-var palette + theme handler boilerplate, and
have every starter artefact `@import` it. Workshop should teach
"never hardcode colours in an MCP App — always consume hostContext"
as a first-class principle, not a "nice to have."

---

## Friction 10 — MCP App artefacts ship with empty/skeletal default state

### Symptom

The Vendor Knowledge Graph MCP App opens to a single placeholder node
with text "Run the validator to populate the graph." Judges open it
once, see nothing interesting, never come back. The MCP App protocol's
whole pitch is "rich interactive artifact running in a sandboxed
iframe" — that pitch lands only if there's something rich on screen
the moment they look.

### Root cause

The template's
[ap-vendor-kg/index.html](../../infrastructure/mcp-sandbox/artefacts/ap-vendor-kg/index.html)
treats the empty state as the literal default — no seed data, just a
"waiting" message.

### Fix

Pre-seed the artefact with a realistic snapshot lifted from the same
vendor master fixture the backend reads (Acme GmbH + V-1042 +
PO-2026-0189 + 2 prior invoices + canonical citations). Validator's
runtime push overlays the current invoice on top of the seeded graph.

### Template improvement

The template's starter artefacts should ship with **demonstrable
content** by default — even if it's marked "DEMO + LIVE" or watermarked.
"Empty state" is a UX failure mode for a showcase template; users need
to see what good looks like before they touch the data flow.

---

## Friction 11 — `DocTab` viewMode buttons assume a non-tabbed layout

### Symptom

Each doc tab in the navbar has three little icons (side / focus /
minimize). After the Workbench landed, clicking these does nothing
visible — the Workbench Document tab owns layout, the viewMode
property is now decorative. The user reports "the navbar buttons no
longer work."

Related: the Workbench Document tab also gated on
`tab.viewMode !== "minimized"` because that's the old "expanded" flag,
which meant a freshly-clicked tab (default `viewMode="minimized"`)
never appeared in the Document tab. Two coupled bugs from the same
assumption.

### Root cause

The template's `DocTab` and `DocTabsBar` were designed for the
single-slot conditional ladder where the right pane could be in one of
three states (no doc, side panel, fullscreen). The Workbench changes
the layout contract; the buttons + flag are still wired but operate on
state nothing observes.

### Fix

Add `hideViewModeButtons?: boolean` to DocTab and DocTabsBar, default
false (preserves template behaviour for other skills). In the AP chat
page, pass `hideViewModeButtons={isApOrchestrator}`. And the Workbench
Document tab keys off `activeDocTab` (whichever tab is focused) rather
than `expandedTab` (the viewMode-gated one), so a click in the navbar
actually opens the doc.

### Template improvement

When the template ships the tabbed Workbench (per Friction 8), the
viewMode toggle buttons should be optional / off by default. The
mental model "I open a doc by clicking on it; the workbench tab
opens" is simpler than the viewMode dance. Keep the viewMode property
for forks that genuinely need a side panel; don't make it the entry
path.

---

## Friction 12 — Inline `emit_*` Card duplicates the workspace surface Card

### Symptom

Two visually different renderings of the same payload appear after
each pipeline step: one inline in the chat bubble (MessageBubble) and
one in the workspace surface pane. Different border styles, different
spacing, different label-wrap behaviour. Reads as a styling bug; user
asks "why is this rendered twice?"

### Root cause

`emit_invoice_extraction` produces both a text Part AND an A2UI tool
call. The frontend's MessageBubble renders the text Part inline as a
JsonAsA2UICard; the SurfaceRegistry routes the tool call to the
workspace surface mount, which renders the same payload again via
A2UISurfaceMount.

### Fix

Two-pronged: (a) keep both views (user prefers "two views of one
thing, mirrored"), and (b) **harmonise their styles** so the
duplication reads as intentional. Inline gets a compact summary
variant of JsonAsStructuredCard with the same border + typography as
the workspace card; the workspace card stays as the canonical full
view.

### Template improvement

Either suppress the inline render when a workspace mount is also
populated (cleanest), or — if the duplication is intentional — make
the inline variant explicitly a "summary card" with a `View full →`
link to the workbench. Pick one model and ship it consistently; the
current "two slightly-different cards" feels like a bug even when
working as designed.

---

## Friction 13 — Chat avatars hardcoded gradients, `user.photoURL` not threaded

### Symptom

User avatar in the chat bubble is a teal-green initial chip
(`from-teal-400 to-teal-600`). Bot avatar is an amber gradient
(`from-amber-400 to-yellow-600`). Both clash with the new
parse-blue/white shell. Also: when the user signs in with Google,
their profile photo is available in `user.photoURL` but the template
doesn't thread it through to `MessageBubble`, so they see an "M"
initial chip instead of their own face.

### Root cause

Two separate template gaps:
- `BrandAvatar.tsx` and `MessageBubble.tsx` use Tailwind color literals
  rather than theme tokens.
- The prop chain `useAuth → chat page → ChatMessageList → MessageBubble`
  carries `userInitial` but not `userPhotoURL`.

### Fix

`BrandAvatar` → soft `bg-primary/5` + `border-primary/20` ring with the
app mark. User bubble: `user.photoURL` threaded through; when present,
render the photo as an `<img>` with `border-border` and
`object-cover`; fallback to a parse-blue initial chip when null.

### Template improvement

Ship the user-photo path as the default. Forks that don't use Firebase
Auth's Google provider get the initial-chip fallback automatically.
Use theme tokens for both avatars so a rebrand doesn't require
touching avatar code.

---

## Friction 14 — MCP sandbox auto-deploy gap

### Symptom

Frontend / backend changes deploy automatically on push to `dev` via
Cloud Build. Changes to `infrastructure/mcp-sandbox/artefacts/**` —
the HTML/JS that runs **inside** the MCP App iframes — do not. The
fork user pushes a retheme, sees the new app shell, opens the iframe,
sees the OLD artefact, and assumes the deploy didn't happen.

### Root cause

The `mcp-sandbox` service is a separate Cloud Run service with its own
`cloudbuild.yaml` but no automated trigger watching the artefact path.
Only the [scripts/deploy-mcp-sandbox.sh](../../scripts/deploy-mcp-sandbox.sh)
helper exists, run manually.

### Fix (template)

Add a Cloud Build trigger that watches `infrastructure/mcp-sandbox/**`
paths on the dev branch and deploys the sandbox service. Or — simpler
— have the main backend cloudbuild.yaml detect `git diff` against
that path and chain the sandbox deploy as a step.

### Template improvement

Either path makes the "push a retheme, see it land" loop work like
every other change. The current "you also need to remember `make
deploy-mcp-sandbox`" is exactly the kind of foot-gun the template
should eliminate.

---

## What still works well, after round two

- **The protocol stack itself** — AG-UI streaming, A2UI surface
  routing, MCP App handshake — never failed during any of the polish
  work. The frictions above are all template/component defaults, not
  protocol bugs.
- **ADK SequentialAgent + function-as-schema** held up under the
  bigger demo (sample picker → auto-process → emit_* cards → tabbed
  workbench → audit chips → MCP App embeds). The original Friction 1
  fix (function-as-schema) compounds: every other improvement is
  cleaner because the schema enforcement is already deterministic.
- **The `light theme` default** (`globals.css :root` palette) was
  always there in the template — the host just needed to drop the
  hardcoded `dark` class on `<html>`. The template ships both palettes
  ready; the choice of default is a one-line fork decision.

## Workshop talking points — round two additions

6. **Layout primitives matter as much as protocol primitives.** A
   `DefinitionList` component owned by the template would have
   prevented Friction 6 from biting every fork. Workshop should call
   this out: "the protocol gives you a typed payload; you still need a
   layout primitive to render it well."

7. **Tabbed workbench, not slot-swapping.** Show the conditional
   ladder pattern AND the tabbed Workbench replacement side-by-side.
   Make the case that multi-surface skills are the norm, not the
   exception.

8. **MCP App artefacts are templates too.** They have their own
   default-state problem (Friction 10) AND their own theme problem
   (Friction 9). Workshop should hand attendees a starter artefact
   that already consumes `hostContext.theme` and ships with realistic
   demo data.

9. **Auto-deploy every code surface.** The mcp-sandbox-not-auto-deploy
   gap is the kind of infrastructure foot-gun that wastes an hour the
   first time someone hits it. Workshop's deploy story should include
   "what surfaces auto-deploy and what surfaces don't" up front.

---

## Index of recent commits (forks that want to absorb these)

The fixes for Frictions 5–14 ship across these commits on
`Aitana-Labs/gde-ap-agent@dev`. A fork that wants to absorb them can
cherry-pick:

| Friction | Commit(s) |
| --- | --- |
| 5 — DocumentHistoryPanel unbounded | `ce70a82` |
| 6 — A2UI Row label wrap → DefinitionList | `2965c87` (DefinitionList, JsonAsStructuredCard) |
| 7 — emit_* audit pane shows args as output | `2965c87` (InspectorPanel + sharedView) |
| 8 — Tabbed Workbench replaces conditional ladder | `2965c87` (Workbench + APWorkbench wiring) |
| 9 — MCP App artefacts consume hostContext.theme | `2965c87` (3 artefact HTMLs + StaticArtefactFrame caller) |
| 10 — Vendor KG pre-seeded with vendor master | `2965c87` (ap-vendor-kg seed) |
| 11 — DocTab viewMode buttons hidden in AP mode | `123928f` |
| 12 — Inline emit_* card harmonised | `2965c87` (MessageBubble) |
| 13 — Avatar restyling + user.photoURL threaded | `ca9053f` |
| 14 — MCP sandbox auto-deploy gap | (template-only — not fixed here) |
