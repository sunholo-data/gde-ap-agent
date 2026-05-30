# Template Improvements — Upstream Feedback Tracker

**Source:** CPH Uni AIPLA fork (`cphu/aipla-app`) v0.1 sprint, May 2026  
**Target:** `sunholo-data/ai-protocol-platform` public template  
**Owner:** Mark / Aitana Labs  
**Last Updated:** 2026-05-21

This directory tracks design docs for improvements to the **public template** surfaced by
downstream forks. Each item maps to one or more numbered feedback entries from the AIPLA
sprint's upstream-feedback log. Items resolved in the Aitana platform but not yet pushed to
the template are marked **Sync needed**.

---

## Design Docs

| Doc | Items | Status | Est | Notes |
|-----|-------|--------|-----|-------|
| [template-fork-ergonomics.md](template-fork-ergonomics.md) | #1 #2 #3 #4 #11 #12 | Planned | 2d | Config/brand hardcoding — biggest fork-friction cluster |
| [template-cloudbuild-hardening.md](template-cloudbuild-hardening.md) | #5 #6 #7 #8 #13 #14 | Planned | 1d | Cloud Build setup pain; mostly docs + small YAML changes |
| [template-auth-hardening.md](template-auth-hardening.md) | #9 #19 #20 #21 | Planned | 1d | Auth/permissions for non-Aitana identity modes |
| [template-tool-opt-out.md](template-tool-opt-out.md) | #22 #25 | **Sync needed** | 0.5d | Resolved in AIPLA fork; ready to upstream as PR |
| [template-session-management.md](template-session-management.md) | #26 #27 | Planned | 1d | Session state correctness; #27 requires new endpoint |
| [template-mcp-apps-artefacts.md](template-mcp-apps-artefacts.md) | #28 #29 #30 | Planned | 2d | iframe/MCP Apps architecture; largest scope item |
| [template-dx-hardening.md](template-dx-hardening.md) | #10 #15 #17 #18 #24 | Planned | 1d | DX, docs, discoverability, Dockerfile ARG |

**Total estimated effort:** ~8.5 days across seven PRs.

---

## Item Index

| # | Short title | Doc | Status |
|---|------------|-----|--------|
| 1 | `seed_skills.py` closed-set DISPLAY_NAMES dict | fork-ergonomics | Planned |
| 2 | `seed_skills.py` pins GCP project to aitana-multivac-dev | fork-ergonomics | Planned |
| 3 | `PLATFORM_OWNER_EMAIL` defaults to platform@aitanalabs.com | fork-ergonomics | Planned |
| 4 | CLI hardcoded as `aiplatform` / Aitana URLs | fork-ergonomics | Planned |
| 5 | `cloudbuild.yaml` non-optional channel secrets | cloudbuild-hardening | Planned |
| 6 | `cloudbuild.yaml` hardcodes Aitana logs bucket | cloudbuild-hardening | Planned |
| 7 | New GCP projects lack legacy Cloud Build SA | cloudbuild-hardening | Planned |
| 8 | Cloud Build v2 repo registration needs GitHub admin | cloudbuild-hardening | Planned |
| 9 | Firebase Resource Location ID set by first Firestore create | auth-hardening | Planned |
| 10 | Anchored `/^join$/i` regex breaks on any rebrand | dx-hardening | Planned |
| 11 | "Aitana" strings embedded in code / protocol URIs | fork-ergonomics | Planned |
| 12 | `_MCP_SANDBOX_URL` points at Aitana's Cloud Run URL | fork-ergonomics | Planned |
| 13 | `gcloud auth print-identity-token` fails under user-managed SA | cloudbuild-hardening | Planned |
| 14 | Minted ID token missing `email` claim — backend silently 403 | cloudbuild-hardening | Planned |
| 15 | Skill-invoke endpoint path not discoverable without reading source | dx-hardening | Planned |
| 16 | Anonymous-group state lives in process memory | — | ✅ Shipped in v6.2.0 (2.11) — **sync template** |
| 17 | `/gcs_config` volume mount wired but nothing reads it | dx-hardening | Planned |
| 18 | `frontend/Dockerfile` silently drops undeclared `NEXT_PUBLIC_*` ARGs | dx-hardening | Planned |
| 19 | `auth/permissions.py` crashes on empty `user_email` | auth-hardening | Planned |
| 20 | `tool_permissions/*` wildcard seeded in LOCAL_MODE but not in prod | auth-hardening | Planned |
| 21 | Frontend `onSnapshot` listeners → `permission-denied` for anonymous users | auth-hardening | Planned |
| 22 | A2UI toolset appended to every skill regardless of `tools: []` | tool-opt-out | **Sync needed** |
| 23 | Chat-page flex column missing `min-h-0` | — | ✅ Fixed in platform (commit `36ee3cd`) — **sync template** |
| 24 | Template should ship vendored protocol specs as a project-local skill | dx-hardening | Planned |
| 25 | Four default tools (artifacts + memory) wired unconditionally | tool-opt-out | **Sync needed** |
| 26 | `GET /api/sessions/{id}/state` uses `skill_id` not `APP_NAME` | session-management | Planned |
| 27 | `ChatSessionIndex` created lazily — iframe pushes pre-first-turn 404 | session-management | Planned |
| 28 | Sandboxed iframe opaque origin — bypass of sandbox-proxy documented | mcp-apps-artefacts | Planned |
| 29 | `wrap_with_iframe_context` defensive framing → model ignores state | mcp-apps-artefacts | Planned |
| 30 | No paved path for static (non-agent-summoned) iframe artefacts | mcp-apps-artefacts | Planned |

---

## Template Sync Items (already shipped in Aitana, need to reach the public template)

These are resolved in the Aitana platform but not yet in `sunholo-data/ai-protocol-platform`.
Run the `aitana-template-publish` skill to sync after each PR merges.

| Item | Platform commit / design doc | What to sync |
|------|------------------------------|--------------|
| #16 anonymous-group persistence | v6.2.0 doc `anonymous-group-id-auth.md` | `backend/auth/group_id_auth.py` Firestore persistence |
| #22 A2UI opt-out | AIPLA commit (pending push) | `A2uiToolConfig.enabled` field + agent factory gate |
| #23 flex min-h-0 | platform commit `36ee3cd` + layout.tsx fix | `chat/[...path]/page.tsx` + `app/layout.tsx` |
| #25 defaults tool opt-out | AIPLA commit (pending push) | `toolConfigs.defaults` flags + agent factory gates |

---

## Priority Order

Recommended ship order (each is an independent PR against the template):

1. **tool-opt-out** — already coded, just needs a PR opened (0.5d)
2. **auth-hardening** — prevents silent 403/400 in fresh forks (1d)
3. **cloudbuild-hardening** — unblocks new GCP project setup (1d)
4. **fork-ergonomics** — largest quality-of-life win for downstream forks (2d)
5. **session-management** — correctness; `#26` is a one-liner (1d)
6. **dx-hardening** — discoverability + dead code cleanup (1d)
7. **mcp-apps-artefacts** — largest scope; unblocks static-artefact use cases (2d)
