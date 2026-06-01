# GDE AP Agent — Competition Polish Sprint

**Sprint ID:** GDE-POLISH  
**Duration:** June 1–4, 2026  
**Deadline:** June 5, 2026 17:00 PT (Track 3, Google AI Agents Challenge)  
**Goal:** Transform a working AP pipeline into a competition-worthy showcase with professional AP/finance UI, agent chain visualization, and live MCP Apps (vendor globe + analytics dashboard).

---

## Baseline

- 4-skill AP pipeline deployed and passing smoke (`ap-orchestrator → docparse → ap-validator → ap-poster`)
- 1337 backend tests passing, frontend quality:check:fast clean
- MCP Apps infrastructure **fully built** (StaticArtefactFrame, AppRenderer, sandbox proxy, MCPAppToolCallRouter) but disabled (`_MCP_SANDBOX_URL` is blank)
- `mcp-sandbox` service has its own `infrastructure/mcp-sandbox/` with Dockerfile + Cloud Build — just needs deploying
- A2UI pipeline wired; ap-orchestrator targets `default_surface: workspace`
- Theme: CSS vars, Tailwind, shadcn/Radix. Current primary is orange (`24 95% 53%`). Branding file says "Sunholo".
- Velocity: 16 commits / 14 days, 1084 insertions. Conservative estimate: 150–250 LOC/day on new features.

---

## Milestones

### M1 — Branding + AP Finance Theme (`frontend`, Day 1)
**Goal:** Every user-visible string says "GDE AP Agent". Primary colour shifts from orange to gold. The app looks like a professional AP/finance SaaS at first glance.

**Tasks:**
1. `frontend/src/lib/branding.ts` — update `appName`, `tagline`, `description`, `contact` (≈20 LOC)
2. `frontend/src/app/globals.css` — shift `--primary`/`--ring` from orange `24 95% 53%` to gold `45 90% 50%`; tweak light/dark muted tones for finance palette (≈15 LOC)
3. `frontend/src/components/chat/BrandAvatar.tsx` — gradient `from-orange → from-amber/gold` (≈5 LOC)
4. `frontend/src/components/chat/ToolCallChip.tsx` — spinner `text-orange-500 → text-amber-500` (≈3 LOC)
5. `infrastructure/mcp-sandbox/sandbox.html` title — `"Aitana MCP Sandbox" → "GDE AP Agent Sandbox"` (≈1 LOC)
6. Logo swap: create SVG wordmark or simple "AP" monogram for `/public/images/logo/` (≈30 LOC SVG)
7. `frontend/src/app/layout.tsx` — page title / meta description from BRANDING (confirm wired)

**Acceptance:**
- `npm run quality:check:fast` green
- Browser tab says "GDE AP Agent"
- Chat avatar is gold, not orange
- No "Sunholo" or "Aitana" visible in normal UI flows

**Estimated LOC:** ~80  
**Risk:** Low — CSS var + string changes.

---

### M2 — AP Pipeline Step Visualizer (`frontend`, Day 1–2)
**Goal:** As the orchestrator delegates to each sub-agent, a 4-step progress rail appears in the chat showing which step is active (pulsing dot), complete (gold checkmark), or pending (grey). Makes the multi-agent architecture immediately legible to judges.

**Tasks:**
1. New component `frontend/src/components/chat/APPipelineSteps.tsx` — 4-step horizontal rail: Intake → Extract → Validate → Post (≈120 LOC)
2. Map tool call events to steps:
   - `docparse` tool running/done → step 2
   - `ap_validator` tool running/done → step 3
   - `ap_poster` / `route_to_human` tool running/done → step 4
   - Orchestrator `running` → step 1 active
3. Mount in `MessageBubble.tsx` for bot messages from the `ap-orchestrator` skill (check `skillId` prop)
4. Vitest snapshot test for each step state (≈40 LOC test)

**Acceptance:**
- Processing an AP invoice shows all 4 steps lighting up in sequence
- Component passes typecheck + snapshot test
- No layout shift on existing non-AP skills

**Estimated LOC:** ~160  
**Risk:** Medium — need to reliably detect sub-agent tool calls from streaming events. AG-UI `TOOL_CALL_START` name should match sub-agent delegation tool name.

---

### M3 — Invoice Review Card (A2UI, `fullstack`, Day 2)
**Goal:** After processing, the orchestrator renders a structured invoice card in the workspace pane — not a wall of text. Card shows: vendor, invoice number, amount+currency, due date, line items table, GL code, approval status chip (Approved / Exception / Needs Review).

**Tasks:**
1. Update `backend/skills/templates/ap-orchestrator/SKILL.md` instruction: after ap-poster responds, call `send_a2ui_json_to_client` with a `createSurface` message containing the invoice summary card schema (≈30 LOC instruction text)
2. A2UI card schema: `InvoiceCard` component — header row (vendor + status chip), metadata grid (invoice #, date, due date, PO ref), line items table, total row, GL code, audit trail section (≈60 LOC JSON schema in instruction)
3. Verify A2UIRenderer handles the card layout correctly — add a fixture to `/dev/rich-media` if needed (≈40 LOC)
4. Backend: `uv run pytest tests/ -m "not slow and not integration" -q` still green after instruction change

**Acceptance:**
- Processing a real invoice shows the card in the workspace pane
- Card renders: vendor name, total amount, approval status chip coloured correctly (green/amber/red)
- No regression in existing A2UI tests

**Estimated LOC:** ~130  
**Risk:** Low-medium — A2UI toolset already wired. Risk is the instruction reliably triggering the tool; may need 1–2 prompt iterations.

---

### M4 — MCP Sandbox Deploy + Vendor Globe (`fullstack`, Day 2–3)
**Goal:** Stand up the `mcp-sandbox` Cloud Run service for the GDE AP Agent project. Build a `vendor-globe` artefact using `globe.gl` that renders a rotating Earth with pulsing arcs from supplier locations to the user's company. The orchestrator emits a `load_mcp_app` tool call with extracted vendor country/city after docparse runs.

**Tasks:**
1. **Sandbox deploy:**
   - Create Cloud Build trigger for `infrastructure/mcp-sandbox/` targeting `multivac-internal-dev`
   - Update `infrastructure/mcp-sandbox/cloudbuild.yaml` — change `_ALLOWED_HOST_ORIGINS` to GDE AP Agent frontend URL
   - Set `_MCP_SANDBOX_URL` in main `cloudbuild.yaml` once sandbox URL is known

2. **Vendor globe artefact** (`infrastructure/mcp-sandbox/artefacts/vendor-globe/index.html`, ≈200 LOC):
   ```html
   <!-- globe.gl CDN, receives vendor {lat, lng, label, amount} via postMessage -->
   <!-- Shows rotating Earth, arcs from vendor location to origin (London default) -->
   <!-- Updates dynamically as more vendors are extracted -->
   ```
   - Uses `globe.gl` (Three.js-based, CDN import, no build step)
   - MCP Apps postMessage: `ui/initialize` → show empty globe; `ui/tool-result` → plot vendor arc
   - Country → lat/lng: static lookup table for top 50 countries (avoids geocoding API dependency)

3. **Backend:** add `load_vendor_globe` FunctionTool to ap-orchestrator (≈80 LOC):
   - Called after docparse, takes `vendor_name`, `vendor_country`, `invoice_amount`, `currency`
   - Returns `ui://vendor-globe` resource URI (MCP Apps spec)
   - Register tool in skill template SKILL.md

4. Smoke: `curl https://<sandbox-url>/healthz` returns 200; artefact loads in browser iframe

**Acceptance:**
- `_MCP_SANDBOX_URL` is non-blank in deployed Cloud Run env
- Processing an invoice with a vendor country in the extracted fields causes a globe to appear in chat
- Globe shows rotating Earth with a pulsing arc from vendor location

**Estimated LOC:** ~350  
**Risk:** High — two new deployments (sandbox + globe), CSP headers must allow `globe.gl` CDN, MCP Apps `ui://` tool call wiring is new for this skill. Descope globe to a static fixture if time runs out; the sandbox deploy is the critical path dependency for M5.

---

### M5 — AP Analytics Dashboard (`fullstack`, Day 3–4)
**Goal:** After processing a batch of invoices (or even one), the ap-validator triggers a Chart.js MCP App dashboard showing: invoice amount by vendor (bar), AP aging buckets (stacked bar), GL distribution (donut). Clicking a bar drills into that vendor's invoices.

**Tasks:**
1. **Analytics artefact** (`infrastructure/mcp-sandbox/artefacts/ap-dashboard/index.html`, ≈300 LOC):
   - Chart.js CDN, no build step
   - 3-tab layout: Overview (bar), Aging (stacked bar), GL (donut)
   - Receives `{vendors: [...], agingBuckets: [...], glDistribution: [...]}` via `ui/tool-result`
   - Dark/light theme via `ui/initialize` `hostContext.theme`

2. **Backend:** `load_ap_dashboard` FunctionTool on ap-validator (≈60 LOC):
   - Aggregates validation results into the dashboard data shape
   - Returns `ui://ap-dashboard` resource URI

3. Update ap-validator SKILL.md instruction to call `load_ap_dashboard` after validation summary

**Acceptance:**
- Dashboard renders in workspace pane after validation step
- At least 2 chart types visible
- Theme matches chat (dark/light)

**Estimated LOC:** ~380  
**Risk:** Medium — Chart.js CDN is standard, CSP for CDN scripts needs to be added to sandbox `?csp=` param.

---

### M6 — SUBMISSION.md + README Rebrand (`docs`, Day 4)
**Goal:** Complete the submission artefact and ensure no Aitana/Sunholo strings appear in the public-facing README.

**Tasks:**
1. `SUBMISSION.md` — fill in: live URL, demo video URL, architecture diagram (ASCII or mermaid), judges notes on multi-agent design, protocol stack callout (AG-UI + A2UI + MCP Apps)
2. `README.md` — find/replace Aitana/Sunholo references with GDE AP Agent. Add screenshot.
3. Final smoke: `./scripts/smoke-deployed.sh dev all` passes

**Estimated LOC:** ~100  
**Risk:** Low.

---

## Day-by-Day Schedule

| Day | Date | Milestones | Exit criteria |
|-----|------|-----------|---------------|
| 1 | Jun 1 | M1 (branding) + M2 start (pipeline steps component) | Brand clean, gold theme deployed, APPipelineSteps component built |
| 2 | Jun 2 | M2 finish + M3 (invoice card) + M4 start (sandbox deploy) | Pipeline viz in prod, invoice card renders, sandbox Cloud Run deployed |
| 3 | Jun 3 | M4 finish (globe artefact + wiring) + M5 start (analytics) | Globe visible in chat, analytics artefact renders with fixture data |
| 4 | Jun 4 | M5 finish + M6 (SUBMISSION + README) + buffer | All smoke checks pass, SUBMISSION.md complete |
| 5 | Jun 5 | Submit by 17:00 PT | — |

---

## Quality Gates (after every milestone)

```bash
# Frontend
cd frontend && npm run quality:check:fast

# Backend
cd backend && make lint && uv run pytest tests/ -m "not slow and not integration" -q

# Post-deploy
./scripts/smoke-deployed.sh dev all
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Globe CSP blocks globe.gl CDN | Medium | M4 blocked | Add `globe.gl` CDN origin to sandbox `resourceDomains` CSP param |
| Sandbox Cloud Build trigger setup blocked | Medium | M4/M5 blocked | Manual `gcloud run deploy` from laptop as fallback |
| ap-orchestrator prompt doesn't reliably call `load_vendor_globe` | Medium | M4 degraded | Add explicit "ALWAYS call load_vendor_globe after docparse" to instruction |
| A2UI invoice card JSON too complex for ADK tool | Low | M3 blocked | Simplify card to 5-field summary; full table is nice-to-have |
| Deadline crunch | High | M5 cut | M1+M2+M3 is the minimum viable competition entry; M4/M5 are stretch |

---

## Minimum Viable Competition Entry (if time runs out)

M1 (branding) + M2 (pipeline viz) + M3 (invoice card) = a polished, clearly branded multi-agent AP demo with professional UI. M4/M5 (globe + analytics) are the wow factor but not blockers for submission.
