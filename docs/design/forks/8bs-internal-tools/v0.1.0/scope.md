# 8-bit Sheep Internal AI Tools — Fork Scope (v0.1.0 PoC)

**Status**: Pitch — pre-collective-review
**Priority**: P2 — internal productivity + second commercial fork validating the template multi-use-case shape
**Scope**: Internal AI assistant platform for 8-bit Sheep collective, forked from `sunholo-data/ai-protocol-platform`
**Dependencies**:
- `sunholo-data/ai-protocol-platform` (public template, shipped)
- 8bs GCP project access
- Collective sign-off on initial 40hr scope + use-case prioritisation
**Created**: 2026-05-16
**Working name**: "Shepherd" (TBC — taken from the `#shepherds-and-sheep` Discord channel)

## Problem Statement

8-bit Sheep (8bs) operates a collective where shared operational work — finance routines (Severa / Netvisor / Säästöpankki), contract management (Google Drive), and other recurring tasks — is handled by rotating Sheep on roles like "Finance Sheep" and "Shepherd." Two compounding failure modes:

1. **Manual work that adds up but never disappears.** Monthly invoicing touches three SaaS platforms (Severa → Netvisor → bank), weekly unpaid-invoice chasing requires correlating Netvisor + Säästöpankki, contract renewal tracking depends on someone remembering. The collective spends 12-24h/year per role on routines that are mostly look-up + ping work. Institutional knowledge of "what to do, when, and where" lives in individual heads.
2. **Reactive, not proactive.** Contract renewals get noticed *after* they auto-renew or lapse. Unpaid invoices get found weeks late. The system has no daemon eyes on it.

8bs already runs on GCP. The protocol-first platform template (`sunholo-data/ai-protocol-platform`, the public fork of Aitana v6) is the right shape for the problem: **many small skills, many channels, scale-to-zero, easy to add the next thing.** A 40hr proof-of-concept is plausible because most of the platform is inherited free.

The business case (from Erik's analysis): 12-24h/year saved = 1200-2400 EUR/yr direct, or 2160-4320 EUR/yr if reallocated to billable client work = **3360-6720 EUR/yr total**. A 40hr build at internal rates pays back well inside year 1, and the platform compounds — each new skill is hours, not weeks.

This fork also serves two strategic purposes:
- **July Croatia workshop story.** Two concrete forks of the same template — Playground Tutor (single-skill, customer-facing, anonymous users) and Shepherd (multi-skill, internal, multi-channel) — demonstrate the template's range.
- **Gemini Enterprise Marketplace dry-run.** ADK ships with A2A. The same agents that run internally can be exposed via the Marketplace for future external offerings without re-architecting.

## Goals

**Primary:** Ship a 40hr PoC on 8bs GCP that handles one production use case (Contract Q&A or Renewal Alert), one connected channel (Discord), and proves any Sheep can add a new skill in an afternoon.

**Secondary:**
- Validate the multi-channel pattern (MCP + Discord + email + CLI + Web) on real internal users
- De-risk the Gemini Enterprise Marketplace path via A2A
- Workshop demo material — show forking + customising the template live

**Success Metrics:**
- All Sheep can reach the assistant via Discord within 1 week of MVP
- A new skill (function + prompt) goes from idea to deployed in ≤2 hours
- One contract-renewal alert and/or one invoice-reminder fires in production within month 1
- Zero manual deployment steps after initial Terraform apply
- Sheep can connect from their own AI harness (Claude Code, Cursor, etc.) via MCP without onboarding friction

**Non-Goals (v0.1.0):**
- Write actions against Severa/Netvisor — read-only v1, no posting invoices
- Banking integration (Säästöpankki) — different beast, defer
- Multi-tenancy — one collective, one deployment
- Public-facing distribution — A2A discoverability is architectural, not v1
- Full automation of finance routines — start with reminders and Q&A, not actuation

**Stretch (if 40hr runs hot):**
- Gemini Enterprise RAG backend (alternative to inherited AILANG Parse + pgvector)
- A2A registration toward Gemini Enterprise Marketplace
- A second connector (Severa-read OR Netvisor-read)

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | Discord-native = "feels like another Sheep on the team," not a tool you visit |
| 2 | EARNED TRUST | +2 | Internal, audit log visible, no scraping or auth-bypass shortcuts |
| 3 | SKILLS, NOT FEATURES | +2 | DX for adding skills *is* the headline; success metric is "afternoon to ship a new one" |
| 4 | RIGHT MODEL, RIGHT MOMENT | +1 | Finance accuracy needs Haiku/Sonnet+thinking; chit-chat Q&A can be Flash |
| 5 | GRACEFUL DEGRADATION | 0 | Internal users, less degradation pressure than playground |
| 6 | PROTOCOL OVER CUSTOM | +2 | MCP for connectors, AG-UI for web, A2A for marketplace path |
| 7 | API FIRST | +1 | Sheep connect from their own AI harnesses via MCP — proves the API boundary |
| 8 | OBSERVABLE BY DEFAULT | +2 | Analytics + debugging UI is an explicit MVP feature, not an afterthought |
| 9 | SECURE BY CONSTRUCTION | +1 | Read-only connectors v1; Firebase auth on web; Discord OAuth; per-Sheep audit |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | Channels are thin adapters; all logic lives in skills + MCP servers |
| | **Net Score** | **+13** | Threshold: >= +4 |

## Design

### Architecture sketch

Event-driven, serverless, scale-to-zero on 8bs GCP:

```
┌──────────────────────────────────────────────────────────────────────┐
│ Channels (clients)                                                   │
│  Discord ⟷  Email ⟷  CLI ⟷  MCP (Claude Code, Cursor)  ⟷  Web UI    │
└────────┬─────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Cloud Run: shepherd-backend  (template-inherited FastAPI + ADK)      │
│  Skills: contract-qa, contract-watch, finance-reminder, ...          │
│  before_model_callback = guardrails + audit log → Firestore          │
└────────┬─────────────────────────────────────────────────────────────┘
         │
   ┌─────┼────────────────┬───────────────────┬──────────────────────┐
   ▼     ▼                ▼                   ▼                      ▼
Pub/Sub  Firestore     Cloud Storage      Vertex AI             MCP servers
(events: (skills,      (parsed docs,      Sessions              (drive-read,
 scans,   audit log,   artifacts)         (+optional             severa-read*,
 alerts)  state)                          Gemini Enterprise      netvisor-read*,
                                          RAG backend)           discord-bot,
                                                                 email-sink)
         ▲
         │  cron + event triggers
         │
┌────────┴─────────────────────────────────────────────────────────────┐
│ Cloud Scheduler ──► Pub/Sub topics ──► Cloud Run worker jobs         │
│  Periodic: Drive scan, contract review, unpaid-invoice check         │
└──────────────────────────────────────────────────────────────────────┘

* stretch
```

### Use cases prioritised

| # | Use case | Skill | New MCP server | Trigger | Estimated value |
|---|----------|-------|----------------|---------|-----------------|
| 1 | Contract Q&A ("what's our scope with X?") | `contract-qa` | `drive-contracts` (read) | Discord / Web on-demand | Highest — multi-user, daily-ish |
| 2 | Contract renewal alert | `contract-watch` | `drive-contracts` (scan) | Scheduled (daily) | High — currently zero coverage |
| 3 | Unpaid invoice reminder | `unpaid-invoice-check` | `netvisor-read` | Scheduled (weekly) | High but heavier connector lift |
| 4 | Severa→Netvisor transfer reminder | `severa-transfer-reminder` | (none — cron + prompt) | Scheduled (monthly) | Medium — just a ping, no read needed |
| 5 | Freelamber invoice reminder | `freelamber-invoice-reminder` | (none initially) | Inbound Discord/email | Medium |
| 6 | Looker dashboard reminder | `looker-finance-reminder` | (none) | Scheduled (monthly) | Low — pure ping |
| 7 | AI assistant planning (Erik's first) | `assistant-planner` | (none) | On-demand | Meta — useful for team conversations |

**v0.1.0 (40hr) commitment:** #1 + #2 + the platform shell to make #4-7 trivial follow-ups. #3 stretches the connector budget — defer to v0.2.0 unless Netvisor API onboarding is unexpectedly clean.

### Channels

| Channel | Inherited shape | Net-new work |
|---------|-----------------|--------------|
| **MCP** | Template ships an MCP server | Mostly free — Sheep point Claude Code / Cursor at the deployed URL |
| **CLI** | `aiplatform` CLI exists in template (renamed locally) | Branding rename + auth wiring; ~1h |
| **Discord** | Telegram channel pattern exists in v6.1.0 (`backend/channels/telegram.py`) | Adapt to Discord slash commands + thread context; ~8h |
| **Email** | v6.1.0 design + v5 port available | Inbound parsing + outbound digest; ~4h |
| **Web** | Template ships chat UI; need analytics route | Audit-log view, skill firing log, cost tracker; ~6h |

### Net-new MCP servers (and their auth pain)

| Server | API auth | Risk | Estimated build |
|--------|----------|------|-----------------|
| `drive-contracts` | Google service account + domain-wide delegation | Low — standard pattern, 8bs already on Google Workspace | 4h |
| `discord-bot` | Bot token + slash command registration | Low — well-documented | (channel work, counted there) |
| `email-sink` | Gmail API or simple SMTP/IMAP via service account | Medium — Gmail API delegation can be fiddly | (channel work) |
| `severa-read` (stretch) | Severa API key + per-project access | Medium — Finnish SaaS, less obvious docs | 4h |
| `netvisor-read` (stretch) | Netvisor API auth (partner + customer key) | High — historically painful API per Erik's R-script workaround | 4-6h |

## Coverage Matrix — What's Inherited vs Net-New

**This is the "where are we for support" answer.** Three inheritance sources, not one.

### Inherited from `sunholo-data/ai-protocol-platform` (the template)

- ADK + FastAPI agent runtime
- Skills abstraction + Firestore persistence + skill CRUD
- MCP server pattern (FastMCP mount + McpToolset)
- AG-UI streaming for web UI
- Firebase auth + role-based permissions
- Cloud Run deployment + Cloud Build CI/CD
- Bootstrap folder cascade + dev/test/prod promotion pattern
- OTEL → Cloud Trace + Cloud Logging observability
- Code execution via ADK FunctionTool (v5-ported)
- AILANG Parse for document ingestion (alternative to Gemini Enterprise RAG)
- Three-provider model routing (Gemini / Claude / OpenAI) with cost-aware selection
- ADK sessions + memory (Vertex AI)
- Smoke probes + post-deploy auth round-trip
- `aiplatform` local CLI for ops + debugging
- Web chat UI shell

### Inherited from `sunholo/ailang-multivac/terraform/` (Pub/Sub + event topology)

The 8bs Terraform is an **adapt** of `ailang-multivac` patterns, not a fresh design. Concrete files we lift and rename:

| File | What it gives 8bs |
|------|-------------------|
| [`pubsub.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/pubsub.tf) + [`pubsub_cascade.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/pubsub_cascade.tf) | Pub/Sub topics + DLQ + fan-out pattern |
| [`eventarc.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/eventarc.tf) | Cloud Scheduler → Pub/Sub → Cloud Run trigger pattern |
| [`cloud_run.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/cloud_run.tf) + [`cloud_run_mcp.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/cloud_run_mcp.tf) | Backend + MCP server service definitions |
| [`cloud_run_jobs.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/cloud_run_jobs.tf) | Scheduled worker job pattern (the "daemon eyes" for contract-watch) |
| [`artifact_storage.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/artifact_storage.tf) + [`config_storage.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/config_storage.tf) | GCS buckets with TTL lifecycle rules |
| [`iam.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/iam.tf) + [`security.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/security.tf) | SA + role cascade (per [no-manual-iam-grants](../../../../../../.claude/projects/-Users-mark-dev-aitana-labs-platform/memory/feedback_no_manual_iam_grants.md) rule) |
| [`docparse.tf`](/Users/mark/dev/sunholo/ailang-multivac/terraform/docparse.tf) | Document-processing wiring (relevant if we self-host parsing instead of Gemini Enterprise) |

### Inherited from `aitana-labs/frontend/backend/` (v5)

| File | What it gives 8bs |
|------|-------------------|
| [`email_integration.py`](/Users/mark/dev/aitana-labs/frontend/backend/email_integration.py) | Working email channel — Sheep can talk to the bot via email |
| [`email_subscription.py`](/Users/mark/dev/aitana-labs/frontend/backend/email_subscription.py) | Subscription pattern for periodic email digests |
| [`channel_mappings.py`](/Users/mark/dev/aitana-labs/frontend/backend/channel_mappings.py) | Channel-to-skill routing pattern |

Port = strip Sunholo imports, wire to the template's channel adapter pattern, drop into `backend/channels/email.py`. Same pattern v6 used for Telegram.

### MCP servers — use Google-hosted, do not build

Google released a catalogue of hosted Workspace MCP servers (Drive, Gmail, Calendar, etc.) in early May 2026. **Plan:** wire the Drive + Gmail servers via `McpToolset` (which the template already supports). No bespoke `drive-contracts` server. The skill's prompt asks "use the Drive search tool, scope to folder X" — the model calls Google's server, gets results, grounds the answer.

Implications:
- Auth is OAuth-via-Google rather than service-account-with-DWD (different security model, more user-tied)
- Drive folder scoping happens in the skill's tool-permission config, not in a server we control
- Future commercial Google MCP servers (Calendar reminders, Sheets reads) are free additions, not new code

This needs verification before commitment — see §Open Questions. If the released servers don't cover read-by-folder-path or have rate limits unsuitable for periodic scanning, fall back to a 4h `drive-contracts` server build.

### Net-new for this fork

**Update 2026-05-16:** Channels framework + 4 adapters (Discord, Email, Telegram, WhatsApp) + the CLI demo + the Cloud Run TF module all shipped in v6.1.0 sprint 1.6. The Discord and Email line items below collapse from "build" to "configure + brand" — they're inherited from the template, gated on env vars (`DISCORD_PUBLIC_KEY`, `MAILGUN_SIGNING_KEY`). Net effect: the 40h scope is now MORE comfortable, with ~14-15h of buffer or stretch instead of ~9h.

| Component | Est (was) | Est (now) | Notes |
|-----------|-----------|-----------|-------|
| ~~Discord channel adapter~~ | 8h | **0h** | Inherited from template (v6.1.0 1.6a ✅) — set `DISCORD_PUBLIC_KEY` + `DISCORD_TOKEN`; ship a fork-specific guild allowlist in Firestore `channel_routes/discord/{guild_id}` |
| ~~Email channel port (v5 → v6 stripped)~~ | 2h | **0h** | Inherited from template (v6.1.0 1.6 ✅) — set `MAILGUN_SIGNING_KEY` + domain |
| Wire commercial Google MCP servers (Drive + Gmail) | 1h | 1h | Config + OAuth flow, not server build |
| Skill: `contract-qa` | 2h | 2h | Glue + prompt |
| Skill: `contract-watch` (scheduled) | 4h | 4h | Glue + prompt + Pub/Sub trigger wiring (now built on shipped event-driven-skills design — see v6.2.0/event-driven-skills.md) |
| Web UI for analytics/audit log | 6h | 6h | New route; see v6.2.0/audit-log-and-analytics.md design |
| Terraform adapt from `ailang-multivac` to 8bs | 3h | 3h | Rename + reconfigure, not redesign |
| 8bs branding pass (logo, copy, manifest) | 1h | 1h | `branding.ts` |
| GCP project bootstrap on 8bs org/folder | 2h | 2h | Run the adapted Terraform |
| Discord + Mailgun creds + per-guild Firestore allowlist | — | 2h | New: provisioning since adapters are already built |
| Wiring, testing, deployment, smoke + dry-run | 2h | 2h | Includes fresh-laptop verification |
| **Subtotal — core scope** | ~31h | **~23h** | -8h thanks to channels framework |
| **Buffer for stretch** | ~9h | **~17h** | Now fits TWO stretch items (e.g., Severa-read + AI-Assistant-planning) |
| **Total committed** | ~40h | **~40h** | Same total, more delivered |
| **Total committed** | **~40h** | |

### Stretch options (pick one to fit the 9h buffer)

| Stretch | Est | Pick when... |
|---------|-----|--------------|
| `severa-read` MCP server + Severa-transfer reminder skill | 6-8h | Severa API onboarding is clean (cleanest write-up; lowest risk) |
| `netvisor-read` MCP server + unpaid-invoice skill | 8-10h | Only attempt if Severa came in <6h or is descoped; Erik's R-script workaround is signal that Netvisor's API is painful |
| Erik's "AI Assistant planning" skill (meta) | 4-6h | Lowest-risk fit for the buffer; high collective value, low integration cost |
| Inbound Gmail parsing for invoice notifications | 4h | If the bot needs to react to Freelamber invoice emails as events, not just respond on-demand |
| Gemini Enterprise RAG backend swap | 8-16h | Don't pick — too big for buffer; v0.2.0 conversation |
| A2A registration toward Gemini Enterprise Marketplace | 4h | Pick if collective wants the marketplace story for July workshop |

## Implementation Plan

40hr PoC in 4 chunks of ~10hr. Pause points at end of chunks 1 and 3 for collective review. Stretch item picked at end of Chunk 3 based on real chunk-by-chunk burn rate.

### Chunk 1 — Fork + Terraform adapt + bootstrap (~10h)
- Fork `sunholo-data/ai-protocol-platform` (0h — admin)
- 8bs branding pass (1h)
- Lift `ailang-multivac/terraform/*.tf` into `infrastructure/`, rename to 8bs (3h)
- Apply Terraform on 8bs GCP project: Pub/Sub topics, Cloud Run service skeleton, GCS buckets, IAM (2h)
- Email channel port: v5 `email_integration.py` → `backend/channels/email.py`, strip Sunholo (2h)
- Smoke deploy: chat round-trip via web UI works on the new project (2h)
- **Gate:** any Sheep can chat with a stock agent on 8bs deployment; email channel reachable

### Chunk 2 — Google Workspace MCP + Contract Q&A (~10h)
- Verify and pick the Google-hosted MCP server(s) for Drive read (see §Open Questions; budget 2h for the decision + OAuth wiring) (2h)
- `contract-qa` skill (prompt + tool wiring + folder scope) (2h)
- Optional: AILANG Parse ingestion of selected Drive folders → pgvector for RAG-grounded answers (3h)
  - Skip this if the Google MCP server's native search is sufficient for the use case
- Integration test: "what's our scope with X?" returns grounded answer with source Drive link (2h)
- Audit log wiring (every skill firing → Firestore) (1h)
- **Gate:** use case #1 works end-to-end via web UI; audit log populated

### Chunk 3 — Discord + Renewal Watch + collective review (~10h)
- Discord bot adapter — slash commands + thread context + role mapping (8h)
- `contract-watch` scheduled skill — Cloud Scheduler → Pub/Sub → worker job → Discord ping (2h)
- **Gate (collective review):** Sheep get a renewal alert on Discord; on-demand Q&A works in Discord too. **Decide here:** which stretch item from §Stretch options gets the buffer

### Chunk 4 — Web analytics + chosen stretch + polish (~10h)
- Web UI audit log + skill-firing view + cost tracker (6h)
- Chosen stretch item (3-4h of the 9h buffer; first 5-6h was reserved for any chunk overrun)
- "How to add a new skill in an afternoon" runbook — written by *actually adding a new skill while following the runbook* (1h, mostly capture-as-you-go)
- **Gate (launch):** any Sheep can follow the runbook and ship a trivial new skill

### Risk register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Google-hosted MCP server doesn't cover Drive-read-by-folder cleanly | Medium | Fall back to a 4h `drive-contracts` server build using `email_integration.py`-style direct API code; cuts into Chunk 4 buffer but core scope is preserved |
| Google MCP OAuth flow is per-user not service-account, breaking the "scheduled scan" pattern | Medium | Run `contract-watch` under a designated bot Sheep's account, or fall back to service-account direct-API for the scheduled scanner only |
| Discord adapter takes >8h | Medium | Email is already working from Chunk 1 — Discord can ship in v0.2.0 without blocking value delivery |
| 40h is still too tight | Medium | Two firewalls: drop AILANG Parse RAG in Chunk 2 if Google MCP search is sufficient (-3h); skip the stretch entirely (-4h). Worst-case ship 31h scope. |
| 8bs GCP project bootstrap is greenfield (no org/folder cascade) | Medium | First 2h of Chunk 1 will reveal this; add 4h buffer if bootstrap is from scratch — the [no-manual-iam-grants](../../../../../../.claude/projects/-Users-mark-dev-aitana-labs-platform/memory/feedback_no_manual_iam_grants.md) rule means TF-via-bootstrap pattern, not console clicks |
| Audit log + analytics UI sprawls | Medium | MVP = list view + filter by skill + simple count-by-day. No charts, no time series, no exports |
| Stretch attempted before Chunk 3 gate | High | Hard rule: stretch picked at end of Chunk 3, written in Chunk 4. No exceptions, even if a chunk finishes early |

## Migration & Rollout

No migration — greenfield internal deployment. Rollout:

1. **Internal alpha:** Mark + one other Sheep, on dev environment, friendly bugs
2. **Soft launch:** All Sheep can connect via Discord; renewal alerts go to `#shepherds-and-sheep`
3. **Iteration:** Two-week feedback loop; add one new skill per fortnight based on Sheep requests
4. **v0.2.0 trigger:** When Sheep are requesting features faster than they can be built, add the next connector (Severa or Netvisor)

Rollback: standard Cloud Run revision rollback per environment.

## Testing Strategy

- **Unit:** Skill validation, audit log schema, Pub/Sub message contracts
- **Integration:** Drive MCP round-trip (mock + live), Discord slash command flow, scheduled trigger fires
- **Eval:** ADK evalset with contract-Q&A sample transcripts + grounding rubric
- **Adversarial:** Confirm read-only connectors cannot escalate to write
- **DX self-test:** During Chunk 4, write the new-skill runbook by adding a real skill while following the runbook — if friction, fix the platform not the doc

## Security Considerations

- **Service-account scoping:** Drive read-only, domain-wide delegation limited to specified folder paths
- **Audit log:** Every skill firing → Firestore audit log (who, when, what skill, what tools called, what was answered). Retained 90 days minimum.
- **Discord auth:** Bot token in Secret Manager; users authenticated by Discord OAuth → mapped to Sheep identity via allowlist
- **Web UI:** Firebase auth + domain allowlist (8bs email domain)
- **MCP exposure:** Authenticated; bearer-token or OAuth-flow before agents can call
- **No write actions in v1:** Severa, Netvisor, banking — read-only or notification-only. Write actions require a separate scoping pass with explicit consent of the role-owner.
- **Data residency:** All processing in EU regions (8bs is Finland/Denmark — Looker/Severa/Netvisor data is EU-origin)

## Open Questions

### For 8bs (collective decisions)

1. **Channel priority.** Email is free (from v5 port in Chunk 1). Is Discord the right second channel, or would CLI / MCP via Claude Code be higher-value for the developer Sheep?
2. **Notification cadence.** Contract renewal — daily digest or real-time per-document? Renewal-soon threshold (30 days? 60?)
3. **Contract scope.** Which Drive folders to index? Are there confidential contracts that should be excluded?
4. **Ownership routing.** When the bot pings about a renewal, who does it ping? Round-robin Shepherd? Original contract signer? Channel default?
5. **Finance read access.** Severa + Netvisor read tokens — who provisions them, and which Sheep accounts have permission?
6. **Cost ceiling.** What's the monthly cloud + LLM budget Sheep will tolerate? (PoC should be <50 EUR/month at expected volume)
7. **Stretch pick.** Which 9h stretch item — Severa-read, Erik's AI Assistant planning skill, inbound Gmail parsing, or A2A registration? The doc recommends picking at end of Chunk 3 based on real burn rate.

### For Mark — and for "what to add to the template" upstream

1. **Google-hosted MCP server selection.** Google released a batch of Workspace MCP servers early May 2026. Need to pick the one that covers:
   - Drive read by folder path (or shared-drive scoping)
   - Service-account auth or domain-wide delegation (so scheduled scans don't depend on a single Sheep's OAuth token)
   - Search/query capability sufficient for "what's our scope with X?" (not just file metadata)
   - **TBD: Mark will survey the Google catalogue first day of Chunk 2.** Fallback is a 4h `drive-contracts` server build, but commercial-MCP-first is the bet.
2. **Repo location.** Under `Aitana-Labs/`, `sunholo-data/`, or a new `eightbit-sheep/` org? Decision parked alongside Playground Tutor's location decision (next Monday).
3. **Workshop alignment.** Croatia is July. If Shepherd ships clean in June, it's a real workshop demo alongside Playground Tutor — two forks of the same template, one customer-facing and one internal. Strong story.
4. **Template upstream contributions.** This fork will expose template gaps. Strong candidates to flow back to `ai-protocol-platform`:
   - **Discord channel adapter** — generic enough to be a template channel, like Telegram is
   - **Pub/Sub-triggered skill pattern** — `eventarc.tf` adaptation + worker-job pattern; template currently is request/response only
   - **Audit log + analytics view** — every fork wants this; should not be reinvented per fork
   - **Google Workspace MCP wiring docs** — once we pick a server and figure out the OAuth/service-account story, the template should document the pattern
   - These should be tagged as "template-eligible" PRs against the private repo, then merged upstream after the 8bs PoC ships
5. **40hr vs reality.** Revised math says 31h committed + 9h stretch = 40h plausible. Pitch can stay at 40h. Severa/Netvisor write actions and v2 polish remain explicitly v0.2.0.

## Related Documents

- [Template split strategy](../../../v6.0.0/template-split-strategy.md) — the public-fork mechanics
- [Playground Tutor scope](../../playground-tutor/v0.1.0/scope.md) — sibling fork, different shape (single-skill customer-facing vs multi-skill internal)
- [v6.1.0 channels design](../../../v6.1.0/channels.md) — Telegram pattern to adapt for Discord; email design to port
- [Auth and permissions](../../../v6.0.0/implemented/auth-and-permissions.md) — Firebase + role tags pattern
- [Skills data model](../../../v6.0.0/implemented/skills-data-model.md) — skill abstraction the use cases extend
- [Workshop tracker](../../../talks/ai-ui-protocol-stack.md) — July 2026 Croatia demo target
- [Public template](https://github.com/sunholo-data/ai-protocol-platform) — fork source
- `sunholo/ailang-multivac/terraform/` — Pub/Sub + Cloud Run + eventarc patterns being lifted
- `aitana-labs/frontend/backend/email_integration.py` — v5 email channel being ported
