# GDE AP Agent — Track 3 Submission Readiness (v0.1.0)

**Status**: Planned — pre-submission gap-close
**Priority**: P0 — Devpost deadline 2026-06-05 17:00 PT (~4 days from 2026-06-01)
**Scope**: Harden `sunholo-data/gde-ap-agent` for the Google for Startups AI Agents Challenge, Track 3 (Refactor for Google Cloud Marketplace & Gemini Enterprise)
**Dependencies**: `ai-protocol-platform` public template (already forked); `feat(ap)` commit `dca1323` (already landed)
**Created**: 2026-06-01

## Context

`sunholo-data/gde-ap-agent` is a fork of the public template `sunholo-data/ai-protocol-platform`. One substantive commit (`dca1323`) added the Accounts-Payable multi-agent skill bundle:

- `ap-orchestrator` (gemini-2.5-pro) — workflow + human handoff
- `docparse` (flash) — extraction
- `ap-validator` (flash) — grounded validation via Vertex AI Search
- `ap-poster` (flash) — post xor escalate with audit trail

Wiring fixes (`find_by_name` name-resolution, `datastore_id` toolConfig key, LOCAL_MODE seeding, Vertex-via-ADC project re-export in `dev-local.sh`) are in place and the orchestrator assembles correctly. **The bones are right.**

What is missing is the *evidence* a Track 3 judge looks for: a clear submission narrative, tests that demonstrate reliability, an evalset that exercises the AP workflow, a real (or clearly stubbed) enterprise grounding corpus, and a coherent deploy/demo posture.

This doc lists the six gaps identified in the 2026-06-01 audit and the work items to close each before the deadline.

## Non-Goals

- Wiring a real ERP MCP write-back. `ap-poster` emits a structured posting record; live ERP integration is explicitly Phase 2 and called out in the skill template.
- Migrating `docparse` to a polyglot A2A `RemoteA2aAgent`. The skill template flags this as future work; in-process is fine for the submission demo.
- Multi-region or multi-tenant Marketplace packaging. Track 3 asks for "prepped for listing" — a single-region dev deploy + a documented listing path is sufficient.

## Gap → Work Item Map

### Gap 1 — README/CLAUDE.md not rebranded

**Symptom**: A judge cloning the repo lands on docs that say "Aitana Platform v6" and link back to `Aitana-Labs/platform`. Nothing on the landing page explains this fork is the Track 3 submission or that the headline artifact is the AP multi-agent system.

**Work item 1.1 — `README.md` top section.**
Add a `## Track 3 Submission — Accounts-Payable Multi-Agent System` section directly under the title. Three short paragraphs:
1. What this fork is (a Track 3 submission built on the open-source `ai-protocol-platform`).
2. What the headline artifact is (the AP multi-agent system: orchestrator + docparse + validator + poster).
3. Where to look (link to `SUBMISSION.md`, the AP skill templates, and `dev-local.sh`).

Keep the existing "What's New in v6" / Quick Start sections below — they describe the platform the AP system runs on, which is part of the story.

**Work item 1.2 — `CLAUDE.md` fork note.**
Add a `## This Fork` section at the top noting the repo is `gde-ap-agent` (Track 3) and that the canonical platform docs upstream are unchanged. The rest of CLAUDE.md stays — it is correct guidance for working in the codebase.

**DoD**: A reader cloning the repo and reading `README.md` understands within 30 seconds (a) what this is, (b) what the deliverable is, and (c) how to run it.

---

### Gap 2 — No AP-specific evalset

**Symptom**: `backend/tests/eval/evalsets/basic.evalset.json` is the template's generic greeting/search eval. Track 3 is judged on "production-grade reliability" — the submission needs to *demonstrate* the AP workflow, not just claim it.

**Work item 2.1 — `accounts_payable.evalset.json`.**
Create `backend/tests/eval/evalsets/accounts_payable.evalset.json` with three eval cases covering the three workflow outcomes:

| eval_id | Input | Expected verdict | Why this case |
|---|---|---|---|
| `ap_clean_invoice` | "Process the invoice in `demo-invoice-clean.pdf`" | `pass` → posting record emitted | Happy path: vendor approved, PO matches, no duplicate, tax correct. |
| `ap_needs_review_po_mismatch` | "Process the invoice in `demo-invoice-po-mismatch.pdf`" | `needs_review` → escalation with PO-mismatch citation | Exception path: validator must catch and cite the mismatch. |
| `ap_needs_review_duplicate` | "Process the invoice in `demo-invoice-duplicate.pdf`" | `needs_review` → escalation with duplicate-citation | Exception path: duplicate-detection grounding. |

Use ADK's `tool_trajectory` scoring to assert the orchestrator delegates to `docparse` → `ap-validator` → `ap-poster` in that order. LLM-as-judge scoring on the final response checks the verdict + presence of citations.

**Work item 2.2 — Fixture invoices.**
Add three PDF fixtures under `backend/tests/eval/fixtures/ap/`:
- `demo-invoice-clean.pdf`
- `demo-invoice-po-mismatch.pdf`
- `demo-invoice-duplicate.pdf`

Generated via a small `scripts/gen-ap-fixtures.py` (ReportLab) so they are reproducible and the PRs stay small.

**Work item 2.3 — `eval_config.json` update.**
Add the new evalset to the eval config so `make eval` picks it up.

**DoD**: `cd backend && make eval` runs the new evalset locally and at least the clean-invoice case scores `pass` end-to-end against Vertex (or a captured fixture, see Gap 4).

---

### Gap 3 — No AP-specific unit/integration test

**Symptom**: The orchestrator's sub-agent wiring is "verified" only in the commit message ("orchestrator assembles via create_agent() with all 3 sub_agents wired"). A regression that breaks the `subSkills` name→id resolution would silently ship.

**Work item 3.1 — `tests/unit/test_ap_orchestrator_wiring.py`.**

Three assertions:
1. Loading the `ap-orchestrator` template via `_parse_template` yields `sub_skills == ["docparse", "ap-validator", "ap-poster"]`.
2. After `_seed_ap_skills`, calling `create_agent("ap-orchestrator")` returns an `LlmAgent` whose `sub_agents` are named `docparse`, `ap-validator`, `ap-poster` (in that order).
3. Calling `create_agent("ap-validator")` returns an `LlmAgent` whose `tools` includes an `AgentTool` wrapping an agent named `enterprise_search_agent` (proves `datastore_id` is read, not the old buggy `datastore` key).

This test runs in LOCAL_MODE (no GCP). It would have caught the original `datastore`-vs-`datastore_id` bug.

**DoD**: `cd backend && pytest tests/unit/test_ap_orchestrator_wiring.py` passes; the test file ships with the submission.

---

### Gap 4 — Vertex AI Search datastore `ds-ap-vendors` doesn't exist

**Symptom**: `ap-validator/SKILL.md` references `datastore_id: ds-ap-vendors`. In LOCAL_MODE `vertex_search` is stubbed, so grounding only lights up in cloud mode — and the cloud-mode datastore has not been created. A judge running `make eval` against Vertex hits the stub or a 404.

**Work item 4.1 — Decide the demo posture.** Two viable options, pick one:

- **Option A — Create a real datastore.** Add a `scripts/setup-ap-datastore.sh` that creates `ds-ap-vendors` in the demo GCP project, indexes ~10 seed vendor docs, ~5 open POs, and a 1-page approval policy. Update `ap-validator/SKILL.md` to use the full resource path `projects/<proj>/locations/<loc>/collections/default_collection/dataStores/ds-ap-vendors` and pin it via env var. Higher effort, more impressive.
- **Option B — Stub deterministically + document.** Replace the `vertex_search` LOCAL_MODE stub with a fixture that returns canned grounded responses for the three eval invoices, and document in `SUBMISSION.md` that "the live datastore is configured at deploy time via `AP_DATASTORE_ID`; the LOCAL_MODE fixture demonstrates the grounding flow." Lower effort, clear story.

**Recommendation: Option B for the submission, Option A for the post-submission Marketplace listing.** Reason: the deadline is 4 days out; creating + indexing a real Vertex AI Search datastore is a 4-6 hour exercise with non-trivial IAM and quota work. A deterministic stub keeps the eval reproducible and gives the judge a clean local run.

**Work item 4.2 — Deterministic LOCAL_MODE grounding fixture.**
Extend the existing `vertex_search` stub so that for the three eval invoices it returns plausible grounded responses (e.g. "Vendor 'Acme Co' active in vendor master; PO-1234 lists 10 widgets @ €10 each, total €110; no prior invoice with number INV-2031"). Cite a fictional but consistent corpus.

**Work item 4.3 — `SUBMISSION.md` datastore section.**
Document the contract: `AP_DATASTORE_ID` env var → full Vertex AI Search resource path. Include the `gcloud discoveryengine` commands a deployer would run to provision it, even if we are not running them for the submission.

**DoD**: `make eval` runs end-to-end in LOCAL_MODE with grounded `needs_review` reasons. `SUBMISSION.md` documents the prod datastore setup.

---

### Gap 5 — No deploy-readiness story

**Symptom**: `cloudbuild.yaml` references `_SERVICE_NAME: aitana-v6-frontend` and `terraform_managed` substitutions inherited from the original Aitana infra. There is no terraform in this fork that provisions a `gde-ap-agent` project, so a `git push` to this repo deploys nothing meaningful.

**Work item 5.1 — Pick a deploy posture.** Three options:

- **A — LOCAL_MODE only (recommended for submission).** Document in `SUBMISSION.md` that the demo runs via `./scripts/dev-local.sh`; remove or comment out `cloudbuild.yaml` so it doesn't mislead. The judge can clone, set `GEMINI_API_KEY`, and run.
- **B — Single Cloud Run deploy on a fresh GCP project.** Provision a minimal terraform stack (one project, one Cloud Run service, no terraform-managed substitutions). 1-2 days of work, risk of last-minute GCP/quota surprises.
- **C — Reuse an existing GCP project (e.g. an Aitana dev project)** with renamed services. Fastest cloud deploy, but muddies the "this is a clean Track 3 fork" story.

**Recommendation: A.** A polished local demo + a documented "to deploy to Cloud Run, point terraform at your project and run `terraform apply`" is a stronger submission than a half-finished cloud deploy. Track 3 is about *refactor for Marketplace*, not *be live on Marketplace by June 5*.

**Work item 5.2 — Update or stub `cloudbuild.yaml`.**
If picking A: rename the file `cloudbuild.yaml.template` and add a header comment "Provided as a deploy template; copy and set substitutions for your env." If picking B or C: do the full retarget. Either way, the file must not look like it deploys to the original Aitana infra.

**Work item 5.3 — Cloud Build trigger hygiene.**
Verify no Cloud Build triggers from the original template are inadvertently firing on pushes to this repo. (`gh api repos/sunholo-data/gde-ap-agent/hooks` to list webhooks.)

**DoD**: `SUBMISSION.md` "How to run this" section is honest about what works out of the box (LOCAL_MODE) and what a deployer would do for Cloud Run/Marketplace.

---

### Gap 6 — Devpost submission write-up missing

**Symptom**: There is no top-level doc that connects the technical work to the Track 3 judging criteria. A judge has to reverse-engineer the story from the commit message and the skill templates.

**Work item 6.1 — `SUBMISSION.md` at repo root.**
Single-page submission narrative, structured around the three Track 3 framings:

1. **ADK + declarative intent.** Show that the AP system is four `SKILL.md` files + ~80 lines of wiring, not a procedural Python pipeline. Pull-quote from `ap-orchestrator/SKILL.md`. Link to the skill templates.
2. **MCP usage.** Document the *current* MCP surface (the platform's MCP tool registry; `list_documents` / `get_document_content` / `structured_extraction` are MCP-style tool wrappers) and the *planned* MCP surface (commented-out `mcp_servers/ext-ap-erp` in `ap-poster/SKILL.md` for ERP write-back). Be honest that the ERP MCP connector is Phase 2.
3. **Marketplace + Gemini Enterprise readiness.** Cover three things: (a) A2A discovery — the platform already exposes `/.well-known/agent.json` so the AP orchestrator is discoverable; (b) Gemini Enterprise registration path — `agents-cli register-gemini-enterprise` (link to the `agents-cli-publish` skill); (c) Marketplace packaging — point to the terraform module(s) a deployer would publish.

End with the **"How to run this in 5 minutes"** block (LOCAL_MODE) and a **"How a buyer would deploy this"** block (high-level pointer to terraform + datastore + Gemini Enterprise registration).

**Work item 6.2 — Run `agents-cli register-gemini-enterprise` in dry-run mode.**
Capture the output and include it as an appendix in `SUBMISSION.md` ("Gemini Enterprise registration manifest — generated by `agents-cli`"). This shows the judging panel that the registration path is real and one command away.

**Work item 6.3 — Demo video / GIF (optional but high-leverage).**
A 60-90s screen recording: drop a clean invoice in LOCAL_MODE → see the workspace card render with vendor/PO/total/citations → drop a duplicate invoice → see the escalation card. Attach to the Devpost submission.

**DoD**: A judge reading `SUBMISSION.md` end-to-end (5 min) understands what was built, why it fits Track 3, and how to run it.

---

## Sprint Plan (2026-06-01 → 2026-06-05)

| Day | Work items | Owner | Estimate |
|---|---|---|---|
| Mon 06-01 | 3.1 (wiring test), 6.1 (SUBMISSION.md skeleton) | Mark | 2 hrs |
| Tue 06-02 | 2.1 + 2.2 + 2.3 (evalset + fixtures + config), 4.2 (LOCAL_MODE grounding fixture) | Mark | 4 hrs |
| Wed 06-03 | 1.1 + 1.2 (README/CLAUDE rebrand), 5.1 + 5.2 (deploy posture A) | Mark | 2 hrs |
| Thu 06-04 | 6.2 (Gemini Enterprise dry-run), 4.3 (datastore section), 6.3 (demo video) | Mark | 3 hrs |
| Fri 06-05 AM | Final pass, push to `main`, submit on Devpost (deadline 5pm PT = 1am UK Sat) | Mark | 2 hrs |

**Total**: ~13 hrs over 4 days. Conservative — most items are docs + one new test file + one new evalset + extending an existing stub.

## Risks

- **Vertex AI Search via ADC is flaky from a laptop.** If the eval cases run live against Vertex they may hit auth/quota issues mid-week. **Mitigation:** LOCAL_MODE deterministic stub (Work item 4.2) makes the evals reproducible without GCP.
- **`agents-cli register-gemini-enterprise` dry-run may need real credentials.** If it does, fall back to including the static registration manifest the skill would generate. **Mitigation:** the `agents-cli-publish` skill documents the manifest format directly.
- **PDF fixture generation eats more time than estimated.** **Mitigation:** if `gen-ap-fixtures.py` slips, use three plain-text fixtures with `.txt` and adjust `docparse` to read them. The point is workflow coverage, not photo-quality PDFs.

## Open Questions

1. **Demo video** — is a screen recording in scope, or are we relying on the judge running it themselves? Default: include one if time allows.
2. **Branding** — do we want a one-line tagline ("Accounts-Payable on autopilot, grounded.") or keep it understated? Default: understated.
3. **Public visibility of the repo** — is `sunholo-data/gde-ap-agent` already public? If not, flip it before the Devpost submission so judges can clone. **Action:** check `gh repo view sunholo-data/gde-ap-agent --json visibility`.

## Related

- Audit conversation: 2026-06-01 (in `aitana-labs/platform` session)
- Upstream template: [sunholo-data/ai-protocol-platform](https://github.com/sunholo-data/ai-protocol-platform)
- Track 3 brief: Google for Startups AI Agents Challenge — Refactor for Google Cloud Marketplace & Gemini Enterprise; Devpost deadline 2026-06-05 17:00 PT
- Skills: [`backend/skills/templates/ap-orchestrator/SKILL.md`](../../../../backend/skills/templates/ap-orchestrator/SKILL.md), [`ap-validator`](../../../../backend/skills/templates/ap-validator/SKILL.md), [`ap-poster`](../../../../backend/skills/templates/ap-poster/SKILL.md), [`docparse`](../../../../backend/skills/templates/docparse/SKILL.md)
- Wiring commit: `dca1323` — feat(ap): Accounts-Payable multi-agent skill bundle + sub-skill wiring
