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
