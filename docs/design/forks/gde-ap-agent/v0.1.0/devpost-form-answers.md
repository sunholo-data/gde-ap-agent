# Devpost submission form — field-by-field draft

> Working doc for the Google for Startups AI Agents Challenge — Track 3
> submission form (deadline 2026-06-05 17:00 PT). Each section maps a
> field on the Devpost form to a draft answer, with sources from
> existing repo assets so we can iterate without re-writing.
>
> Source of truth for the long-form pitch is [`SUBMISSION.md`](../../../../../SUBMISSION.md);
> this doc adapts that material to Devpost's field shapes + word limits.

---

## Project header

| Field | Draft |
| --- | --- |
| Project name | **ailang-parse · AP Showcase — multi-agent AP pipeline on Google ADK** *(decided)* |
| Theme | Refactor for Google Cloud Marketplace & Gemini Enterprise *(prefilled)* |
| Region | EMEA *(prefilled)* |
| Status | Submission-ready — bump from "Idea" once form is final |

---

## Project assets

| Asset | Status | Link / source |
| --- | --- | --- |
| **Video*** | **TODO — needs recording** | Suggest 90s screencast of the SUBMISSION.md demo flow steps 1–9. Host on YouTube unlisted. |
| **Code*** | Ready | `https://github.com/sunholo-data/gde-ap-agent` *(decided)* |
| **Testing access*** | Ready | Live deploy: `https://gde-ap-agent-blqtqfexwa-ew.a.run.app` — accepts guests, no sign-in friction for judges *(decided)* |
| **Architecture diagram*** | Ready *(decided)* | Link the live `/tech` page: `https://gde-ap-agent-blqtqfexwa-ew.a.run.app/tech` — renders [`ArchitectureDiagram.tsx`](../../../../../frontend/src/components/tech/ArchitectureDiagram.tsx) (purpose-built AP-pipeline + protocol-stack SVG) inline with explanatory copy. Fallback: screenshot to PNG, commit to `docs/talks/assets/ap-architecture-diagram.png`, link the raw GitHub URL — only if Devpost rejects a page URL. |
| Hero image | **TODO** | Suggest a screenshot of the AP workbench mid-run: Invoice Hero Card on the Invoice tab (vendor name + total + NEEDS_REVIEW status), Vendor Knowledge Graph on the MCP App Vendor tab with `LIVE` citation badges (vendor_master / open_pos / prior_invoices clickable to query the agent), and the AP Validator chip lit up in the top nav. Captures all three protocols visibly — AG-UI streaming the pipeline, A2UI rendering the hero card, MCP Apps with the bidirectional click-to-chat the Vendor KG enables. |

**Asks for Mark:**
1. Record the 90s screencast — flow in SUBMISSION.md "Demo flow" §
   already reads as a shot list.
2. Decide: judge sign-in via Firebase Auth Google, or stand up a
   judge-only `LOCAL_MODE` URL with a known stub identity?
3. Architecture diagram — happy to generate an AP-pipeline-specific
   one from a description; otherwise reuse the chat-rendering SVG and
   annotate.

---

## Description block

### Problem to solve

> Accounts-Payable teams still process invoices manually because the
> available tools force a trade-off: rule engines are deterministic
> but brittle; LLM extractors are flexible but hallucinate vendor
> data and skip audit trails. Finance can't accept either failure
> mode. The result is a £50k–£500k/yr cost in any mid-market AP
> function — a handful of FTEs typing data into an ERP and
> reconciling exceptions.

### Our solution

> A multi-agent AP pipeline on Google ADK that turns an incoming
> invoice into a trustworthy posting decision with a complete audit
> trail. **No Pro tokens, no LLM at the workflow layer.** An entry
> agent (`ap-orchestrator`, Gemini 3.5 Flash) owns the human handoff
> and delegates to `ap-pipeline` — an ADK `SequentialAgent` that
> walks Extract → Validate → Post in code, not prose, removing
> prompt-injection risk from the routing path. The three
> specialists are: **invoice-extractor** (Gemini 2.5 Flash) using
> ailang-parse for deterministic field extraction (no LLM tokens on
> structured formats); **ap-validator** (Gemini 3.1 Flash-Lite)
> grounding every claim against the vendor master via Vertex AI
> Search; **ap-poster** (Gemini 3.1 Flash-Lite) writing the journal
> entry or escalating with citations. Each step is observable live:
> users see an AG-UI pipeline visualiser, an A2UI invoice review
> card in the workspace pane, and an embedded MCP App vendor
> knowledge graph showing exactly which records were cited. The
> whole system is five declarative `SKILL.md` files plus ~80 lines
> of wiring — no orchestration loop, no prompt-chaining glue.

### Technologies used

> - **Google ADK** — agent orchestration, `SequentialAgent` pipeline, sub-agent delegation, sessions
> - **Gemini 3.5 Flash / 3.1 Flash-Lite / 2.5 Flash** via Vertex AI — entry agent + specialist models (no Pro tokens; workflow layer has no LLM)
> - **Vertex AI Agent Engine** (Reasoning Engine) — managed ADK session service + Memory Bank for cross-session recall (`load_memory` tool); chat history and user memory persist across deploys
> - **Vertex AI Search** — grounded validation against vendor master, open POs, approval policy
> - **Google Cloud Run** — backend, frontend, and MCP Apps sandbox services (`europe-west1`)
> - **Firebase Auth + Firestore** — auth, skill registry, session mirror
> - **Cloud Build** — branch-based CI/CD (dev → test → prod promotion)
> - **AG-UI / A2UI / MCP / MCP Apps / A2A** — the protocol stack (`@ag-ui/client` `HttpAgent` SSE stream, A2UI v0.9 surfaces, MCP tool registry, MCP Apps sandboxed iframes, A2A discovery card)
> - **ailang-parse** — deterministic Office/PDF extraction (<1s, no LLM cost)
> - **Open-source template:** `sunholo-data/ai-protocol-platform` (we built and maintain it)

### Data sources

> - **Vendor master** (sample dataset of 50 vendors with addresses, payment terms, GL accounts) — served to `ap-validator` via a Vertex AI Search datastore
> - **Open purchase orders** + **approval policy** — same datastore, separate document collection
> - **Demo invoices** (`frontend/public/demo-invoices/`) — PDFs and structured fixtures for the sample picker
> - **MCP server registry** — `vendor-master` and `erp-posting` MCP servers (vendor lookup + posting write-back); ERP MCP wired but scoped behind a feature flag for the live demo
> - **No PII / no customer data** — all fixtures are synthetic

### Findings and learnings

> Three findings worth sharing. **(1) Function-as-schema beats
> two-pass response_schema for structured output** — declaring each
> specialist's emit step as a `FunctionTool` with typed args lets
> Gemini's function-calling enforce the schema in one call instead
> of two, saving ~3–5s per specialist and removing a fragile JSON
> sniffing path on the frontend. **(2) Protocol primitives need
> layout primitives** — A2UI gives you typed payloads but no
> "label column + value column" convention; we added a
> `DefinitionList` primitive and a tabbed `Workbench` because the
> default slot-swap pattern destroyed user context every time an
> agent emitted a new surface. **(3) ADK's `SequentialAgent` is the
> right abstraction for a deterministic AP pipeline** — no LLM at
> the workflow layer means no prompt-injection risk for the
> pipeline ordering, and the audit story is dramatically simpler.
> The full friction log (14 findings, with template-PR-ready
> fixes) is in `docs/learnings/template-protocols-friction.md`.

### Third-party integrations *(if applicable)*

> - **ailang-parse** (sunholo) — Apache-2.0; deterministic doc parsing. We own this — no third-party authorisation required.
> - **ai-protocol-platform** template (sunholo) — Apache-2.0; we own + maintain.
> - **`@ag-ui/client`** (`HttpAgent`) — MIT; SSE streaming client for the AG-UI protocol.
> - **A2UI SDK** (`@a2ui/web_core`) — open spec, MIT reference implementation.
> - All Google Cloud services accessed under the submitter's GCP account; no third-party data redistributed.

---

## Submission questions

### Q1. Google Cloud familiarity (1–5)

> **5.** Sunholo runs a multi-project GCP estate (`aitana-multivac-{dev,test,production}`), authored 60+ design docs against Google Cloud services, and ships the `agents-cli` deployment toolchain that wraps Cloud Build + Cloud Run + Artifact Registry.

### Q2. Google AI Studio familiarity (1–5)

> **4.** Used AI Studio for Gemini 2.5 Pro/Flash prompt iteration and for `GEMINI_API_KEY` issuance during LOCAL_MODE bring-up. Most production prompting is via Vertex AI, not Studio directly.

### Q3. Describe the readiness of your project for launch

> Production-ready on Google Cloud. The system is deployed to Cloud
> Run in `europe-west1` (`gde-ap-agent` backend + frontend +
> `mcp-sandbox`), wired to Vertex AI for both models and grounding
> search, fronted by Firebase Auth, and gated by a Cloud Build CI
> pipeline (lint + test-fast on every PR; smoke checks every
> deploy). A fork-and-deploy path is documented end-to-end in
> `SUBMISSION.md` — `scripts/bootstrap-gcp-project.sh <project>
> <sa-email>` provisions the infra, a Cloud Build trigger handles
> deploys, and `scripts/smoke-deployed.sh` validates the live
> endpoints. The open-source template (`ai-protocol-platform`) is
> the same code path we use internally; a buyer forks it and
> redeploys without touching agent code. Gaps before commercial
> launch are documented honestly in
> `docs/design/forks/gde-ap-agent/v0.1.0/submission-readiness.md`
> — primarily ERP MCP write-back (scoped, not wired live) and the
> vendor-master Firestore registration.

### Q4. Which specific feature of Agent Platform was most critical to your project's impact, and what is one thing it's currently missing?

> **Most critical:** ADK's `SequentialAgent` + sub-agent delegation
> via declarative `subSkills`. We define the entire AP pipeline in
> five `SKILL.md` files (~80 lines of wiring) and ADK handles
> sessions, artifacts, sub-agent routing, and event streaming end
> to end. The workflow layer has **no LLM at all** — `ap-pipeline`
> is a `SequentialAgent` that walks Extract → Validate → Post in
> Python, not by asking a model what to do next. That single
> design choice removes prompt-injection risk from the routing
> path AND keeps unit cost dominated by Flash-Lite specialists
> rather than a Pro orchestrator (we don't use Pro anywhere). This
> is the decision that let us ship a real multi-agent product
> instead of a prompt-chaining prototype.
>
> **Missing:** a first-class **function-as-schema** pattern for
> structured output. Today, combining `tools` with strict
> `response_schema` requires a two-pass workaround (run the agent,
> then re-extract via a constrained call) that costs a Gemini
> round-trip per specialist. We worked around it by declaring each
> specialist's emit step as a typed `FunctionTool` — but the
> Agent Platform docs should call out this pattern (and the cost
> trade-off) explicitly, and the ADK should ship a helper that
> wires it into `after_agent_callback` as a fallback when the LLM
> forgets to call the emit tool. Full write-up:
> `docs/learnings/template-protocols-friction.md` — Friction 1.

### Q5. If you could add one specific API capability or integration that would have saved 2+ hours of work, what would it be?

**255-char limit — paste exactly:**

> An A2UI surface validator (gcloud agent-platform validate --extension a2ui-v0.9 surface.json). Catches Button/updateDataModel/Row schema drift at author time, not via wasted Gemini retries. We lost >2h per author to runtime-only A2UI validation.

*(245 chars. Honourable mention — a Cloud Build trigger preset for `infrastructure/mcp-sandbox/**` paths, which every MCP-Apps-shipping fork would benefit from — has to live in Q6 instead; no room here.)*

### Q6. Additional information

> - **Built on an open-source platform we maintain** —
>   `github.com/sunholo-data/ai-protocol-platform`. The AP system
>   in this submission is a fork; the platform underneath is
>   already in production use beyond AP.
> - **Full template-friction log** — 14 friction points found while
>   building this, with template-PR-ready fixes, in
>   `docs/learnings/template-protocols-friction.md`. Submitted as
>   field notes for future Agent Platform / A2UI iteration.
> - **Gemini Enterprise + A2UI alignment** — theme-by-theme map
>   against Google's practitioner's guide is in
>   `docs/design/forks/gde-ap-agent/v0.1.0/gemini-enterprise-a2ui-alignment.md`.
>   The platform exposes `/.well-known/agent.json` with
>   `X-A2A-Extensions` capability negotiation; ready to register
>   with Gemini Enterprise via `agents-cli register-gemini-enterprise`.
> - **Workshop track** — this codebase doubles as the working
>   example for an open AI agent protocols workshop
>   (`WORKSHOP.md` + `docs/talks/ai-ui-protocol-stack.md`); a
>   judge could run the demo locally in <30 minutes with
>   `LOCAL_MODE=1 make dev` and no GCP credentials.
> - **Honourable mention from Q5** — a Cloud Build trigger preset
>   that watches `infrastructure/mcp-sandbox/**` paths would close
>   an auto-deploy gap every MCP-Apps-shipping fork hits (Friction
>   14 in the friction doc). Couldn't fit in Q5's 255-char limit.

---

## Video script (2 minutes, ~270 spoken words)

> Format: `[mm:ss–mm:ss]` BEAT — **ACTION** on screen / **VO** spoken.
> Target ~135 wpm with light pauses on the wow moment. Record screen
> at 1920×1080. Cold open — no title card, just the deployed app.
> Captions on (judges may watch muted).

### [0:00–0:10] Hook — the trade-off frame

**ACTION:** Cold open on the deployed app, `ap-orchestrator` selected,
chat empty.
**VO:** "Most AP automation forces a choice — deterministic rule
engines that break, or LLMs that hallucinate vendor data. This is
what an audit-grade alternative looks like, built on Google ADK."

### [0:10–0:20] What it is — the cost angle

**ACTION:** Cursor sweeps the four Audit chips in the top nav
(`Orchestrator · Extractor · Validator · Poster`).
**VO:** "A multi-agent pipeline. No Gemini Pro tokens. No LLM at the
workflow layer — the routing is code, not prose, so prompt-injection
can't steer the pipeline."

### [0:20–0:35] Demo start — AG-UI streaming

**ACTION:** Type and send: `"Process this invoice: Vendor: Acme GmbH
(Germany), INV-2026-042, €8,500, NET 30, GL 5200-OPEX"`. The 4-step
pipeline visualiser animates Intake → Extract → Validate → Post.
**VO:** "Drop an invoice in. The pipeline visualiser streams over
AG-UI as each specialist runs — Flash-class models all the way down."

### [0:35–0:55] Audit panel — A2UI + MCP App inside the audit view

**ACTION:** Audit chips light up live with latency badges. Click the
**Validator** chip → side panel slides in. Scroll to the embedded
`ap-vendor-kg` MCP App.
**VO:** "Each specialist is observable live — input, tool calls,
structured output. The validator's audit view embeds an MCP App that
visualises exactly what it grounded against: vendor master record,
matching PO, prior invoices. AG-UI, A2UI, and MCP Apps in one frame."

### [0:55–1:25] Wow moment — bidirectional MCP Apps loop

**ACTION:** Close audit panel. Click the Workbench **Vendor** tab.
Hover a citation row with a `LIVE` badge. Click
`vendor_master:V-1042`. Chat scrolls up — the orchestrator answers
"V-1042 is Acme GmbH, NET 30 terms, GL 5200…" with citations.
**VO:** "Now the bidirectional loop. Click any citation inside the
sandboxed MCP App. The iframe posts `ui/update-model-context`. The
host turns that into a chat query. The orchestrator answers — without
ever leaving the visualisation. That's the full MCP Apps protocol,
not just an embedded widget."

### [1:25–1:45] Analytics + the stack under the hood

**ACTION:** Switch to the **Analytics** tab — aging bar, top-vendors
bar, GL-code donut, attribution chip pulsing "Updated by Orchestrator
· just now". Cut to the `/tech` page architecture diagram.
**VO:** "Same protocol on the analytics dashboard. Under the
surfaces: ADK `SequentialAgent` for routing, Vertex AI Agent Engine
for managed sessions and Memory Bank, Vertex AI Search for grounding,
Cloud Run for compute. Built on our open-source `ai-protocol-platform`
template."

### [1:45–2:00] Close — the Marketplace path

**ACTION:** Editor with the five SKILL.md files visible side by side
(`ap-orchestrator`, `ap-pipeline`, `invoice-extractor`,
`ap-validator`, `ap-poster`).
**VO:** "The entire system is five declarative `SKILL.md` files —
around eighty lines of wiring. Fork the template, register with
Gemini Enterprise via `agents-cli`, deploy on Cloud Run. That's the
Marketplace path for any vertical agent."

### Production checklist

- [ ] Screen recording at 1920×1080, 30fps. Use the live deploy, not localhost.
- [ ] Light theme on (parse-blue palette reads better in compressed YouTube than dark navy).
- [ ] Pre-warm the agent with one practice run so first-token latency doesn't eat the 0:20 beat.
- [ ] Mouse cursor visible + smoothed (Cleanshot / Loom).
- [ ] Voice-over recorded separately, normalised to −16 LUFS.
- [ ] Burn-in captions (judges may watch muted).
- [ ] Upload to YouTube **Unlisted**, paste link into the Devpost Video asset field.

---

## Open items before submit

1. **Video** — record + upload using the 2-minute script above. Host on YouTube Unlisted.
2. **Hero image** — screenshot of workbench mid-run:
   - Invoice Hero Card on the Invoice tab (vendor + total + status chip)
   - Vendor Knowledge Graph on the Vendor tab with `LIVE` citation badges
   - AP Validator chip lit in the top nav (or all three chips with timings)
   Shows AG-UI + A2UI + MCP Apps in a single frame. The Vendor Globe
   was dropped in the [MCP Apps Interaction Pass](../mcp-apps-interaction-pass.md);
   the KG with clickable citations replaces it and tells the
   bidirectional-protocol story the globe couldn't.

## Decided

- Project name: *ailang-parse · AP Showcase — multi-agent AP pipeline on Google ADK*
- Code URL: `https://github.com/sunholo-data/gde-ap-agent`
- Testing access: existing live demo URL accepts guests
- Q1/Q2 self-rating: 5 / 4
- Architecture diagram: live `/tech` page on the deployed app (component: `ArchitectureDiagram.tsx`)
