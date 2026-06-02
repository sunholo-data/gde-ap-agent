# GCS Bucket Browser — Sprint Plan

**Sprint ID**: GCS-BROWSER
**Design Doc**: [gcs-bucket-browser.md](./gcs-bucket-browser.md)
**Status**: Ready to Execute
**Created**: 2026-06-02
**Deadline**: 2026-06-05 17:00 PT (competition submission)

## Sprint Summary

Add a GCS file browser to the AP Agent sidebar with two sections:
- **Example Invoices**: pre-populated demo bucket, one-click import → AILANG Parse → Firestore
- **Your GCS Bucket**: user-specified bucket (name in localStorage), app SA auth, friendly error on deny

Demo files already exist in `infrastructure/demo-invoices/` (9 files, 6 formats). Backend
reuses `upload.py` parse pipeline. Frontend follows `DocListView`/`useDocBrowser` patterns.

## Velocity Baseline

| Metric | Value |
|--------|-------|
| Recent velocity | ~665 LOC/day (29 commits, 4665 insertions over 7 days) |
| Backend tests | 1337 passing, 0 failing |
| Frontend quality | lint + typecheck clean |
| Reuse factor | High — `_upload_to_gcs`, `_run_parse`, `_store_document`, `ParsedDocumentResponse` all copied from `upload.py` |

## Milestones

### M1 — Backend: GCS List + Import API (~3 hours, ~280 LOC)

**Scope:** `backend`

**Tasks:**
- [ ] Create `backend/tools/gcs_browser/__init__.py` (~2 LOC)
- [ ] Create `backend/tools/gcs_browser/browser.py` (~150 LOC)
  - `validate_bucket_name(name)` — GCS naming regex guard
  - `list_gcs_objects(bucket_name, prefix, delimiter)` — returns `GCSListResponse`
  - `_resolve_demo_bucket()` — substitutes `AP_DEMO_BUCKET` for sentinel `"demo"`
  - `import_gcs_object(user, bucket_name, object_path, folder_id, skill_id)` — downloads from GCS, calls `_upload_to_gcs` + `_run_parse` + `_store_document` from `upload.py`
- [ ] Create `backend/tools/gcs_browser/routes.py` (~80 LOC)
  - `GET /api/gcs/list?bucket=demo|<name>&prefix=&delimiter=/`
  - `POST /api/gcs/import` body `{bucket, path, folder_id?, skill_id?}`
  - Pydantic models: `GCSObject`, `GCSListResponse`, `GCSImportRequest`
- [ ] Register router in `backend/fast_api_app.py` (~3 LOC)
- [ ] Add `AP_DEMO_BUCKET` + `AP_DEMO_PREFIX` to `cloudbuild.yaml` and `backend/.env.example` (~6 LOC)
- [ ] Tests: `backend/tests/tool_tests/test_gcs_browser.py` (~80 LOC)
  - mock GCS client for list: demo sentinel, user bucket, 403 path, invalid name
  - mock GCS client for import: success path, unsupported extension

**Acceptance Criteria:**
- [ ] `GET /api/gcs/list?bucket=demo` returns list of objects (mocked in tests)
- [ ] `GET /api/gcs/list?bucket=bad name!!` returns 400
- [ ] `GET /api/gcs/list` with SA 403 returns JSON with `sa_email` field
- [ ] `POST /api/gcs/import` returns `ParsedDocumentResponse` shape
- [ ] `cd backend && make lint && make test-fast` passes

**Risk:** Low — pure reuse of existing GCS + parse pipeline. Main unknown is SA credential path in local dev (may need `GOOGLE_APPLICATION_CREDENTIALS` set).

---

### M2 — Frontend: GCSFileBrowser sidebar component (~3 hours, ~320 LOC)

**Scope:** `frontend`

**Tasks:**
- [ ] `frontend/src/hooks/useGCSBucket.ts` (~60 LOC)
  - Calls `GET /api/proxy/api/gcs/list?bucket=...&prefix=...`
  - Returns `{ objects, prefixes, isLoading, error, saEmail }`
  - Debounced re-fetch on bucket/prefix change (300 ms)
- [ ] `frontend/src/components/doc-browser/GCSFileItem.tsx` (~70 LOC)
  - File row: type icon, display name, size badge, **Import** button
  - Local state: `idle | importing | done | error`
  - On Import: `POST /api/proxy/api/gcs/import`; on done → Firestore listener picks up new doc automatically
- [ ] `frontend/src/components/doc-browser/GCSBucketInput.tsx` (~40 LOC)
  - Controlled input: strips `gs://` prefix, stores in `localStorage['ap-gcs-user-bucket']`
  - **Browse** button triggers fetch; **Clear** button resets
- [ ] `frontend/src/components/doc-browser/GCSFileBrowser.tsx` (~130 LOC)
  - Two `<details>` accordion sections: **Example Invoices** + **Your GCS Bucket**
  - Skeleton loader (3 pulse bars) during fetch
  - Empty state: "No demo files — run setup-demo-bucket.sh"
  - Error state: shows SA email with "Grant access" copy
  - File type icon helper: `.docx`→📄, `.xlsx`→📊, `.csv`→📋, `.eml`→✉️, `.odt`→📃, `.mbox`→📬, `.pdf`→📑
- [ ] Wire into `frontend/src/app/chat/[...path]/page.tsx` sidebar (~12 LOC)
  - Add `<GCSFileBrowser skillId={skillId} />` between skill info card and sessions panel
- [ ] Tests: `frontend/src/components/doc-browser/__tests__/GCSFileBrowser.test.tsx` (~80 LOC)
  - renders skeleton during load
  - renders file list with import buttons
  - import button shows "Importing…" then "Done"
  - error state shows SA email
  - bucket input strips `gs://` prefix

**Acceptance Criteria:**
- [ ] Example Invoices section shows 9 demo files (or empty state if bucket unset)
- [ ] Clicking Import on any file shows loading state → triggers `POST /api/proxy/api/gcs/import`
- [ ] Imported file appears in DocListView after Firestore listener fires (no page refresh)
- [ ] Your GCS Bucket input persists across page reloads (localStorage)
- [ ] `npm run quality:check:fast` passes (lint + typecheck)

**Risk:** Medium — Firestore real-time listener for imported docs must fire without user interaction. DocListView already listens to `parsed_documents` collection, so imported docs appear automatically. Verify this works end-to-end.

---

### M3 — Infrastructure: Demo bucket deploy + cloudbuild wiring (~30 min, ~15 LOC)

**Scope:** `backend` / infra

**Tasks:**
- [ ] Run `infrastructure/demo-invoices/setup-demo-bucket.sh multivac-internal-dev`
- [ ] Verify all 9 files appear in `gs://gde-ap-agent-demo-invoices/`
- [ ] Add `_AP_DEMO_BUCKET: 'gde-ap-agent-demo-invoices'` to `cloudbuild.yaml` substitutions
- [ ] Add to backend deploy `--set-env-vars` block in `cloudbuild.yaml`
- [ ] Smoke test: `GET /api/gcs/list?bucket=demo` against deployed backend

**Acceptance Criteria:**
- [ ] `gsutil ls gs://gde-ap-agent-demo-invoices/` lists 9 files
- [ ] Backend env var `AP_DEMO_BUCKET` resolves correctly in Cloud Run
- [ ] `GET /api/proxy/api/gcs/list?bucket=demo` returns 9 objects from deployed frontend

**Risk:** Low — bucket creation is a single gsutil command. `cloudbuild.yaml` substitution follows existing pattern (`_MCP_SANDBOX_URL`).

---

## Execution Order

```
M1 (backend) → M2 (frontend) → M3 (infra)
     ↓               ↓              ↓
  ~3 hours        ~3 hours       ~30 min
```

M1 before M2 because M2's hook calls the backend endpoint. M3 can run in parallel with M2 (only `cloudbuild.yaml` edit overlaps, minimal conflict).

## Day Plan (2026-06-02)

| Time | Work |
|------|------|
| Session 1 (~3h) | M1: backend browser + routes + tests |
| Session 2 (~3h) | M2: frontend hook + components + sidebar wire |
| Session 3 (~30m) | M3: bucket setup + cloudbuild + smoke test + commit + push |

## Quality Gates

After M1:
```bash
cd backend && make lint && make test-fast
```

After M2:
```bash
cd frontend && npm run quality:check:fast
```

After M3 (full CI parity):
```bash
cd frontend && npm run quality:check:fast
cd backend && make lint && make test-fast
```

## LOC Summary

| Milestone | Impl LOC | Test LOC | Total |
|-----------|----------|----------|-------|
| M1 Backend | ~235 | ~80 | ~315 |
| M2 Frontend | ~312 | ~80 | ~392 |
| M3 Infra | ~15 | — | ~15 |
| **Total** | **~562** | **~160** | **~722** |

At 665 LOC/day velocity: **~1.1 days**. Fits comfortably in today's session.
