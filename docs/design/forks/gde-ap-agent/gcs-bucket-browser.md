# GCS Bucket Browser — Demo Invoice Library + User Bucket Integration

**Status**: Planned
**Priority**: P0 (competition demo blocker)
**Estimated**: 2 days (backend ~1 day, frontend ~1 day)
**Scope**: Fullstack
**Dependencies**: Existing document upload pipeline (`upload.py`), AILANG Parse, `useDocBrowser` hook
**Created**: 2026-06-02
**Last Updated**: 2026-06-02

## Problem Statement

The GDE AP Agent is a competition demo for the Google AI Agents Challenge (Track 3, deadline 2026-06-05 17:00 PT). Judges and reviewers need a zero-friction way to feed invoices into the AP pipeline without having their own files to hand.

**Current State:**
- Users must upload files via drag-drop or the upload zone — friction for a first-time evaluator
- No shared demo corpus; every reviewer starts from an empty workspace
- Users who have existing AP invoices in their own GCS bucket cannot browse or import them
- The sidebar shows only previously-uploaded user documents; there is no concept of a "source bucket"

**Impact:**
- Judges who open the demo and see an empty sidebar have nowhere to start
- Competitive demos with pre-loaded example data score higher on "ease of use"
- AP practitioners who want to test with real production invoices (not uploads) cannot do so

## Goals

**Primary Goal:** Display a curated set of demo AP invoices in the sidebar that any user can import with one click, and allow power users to browse files from their own GCS bucket.

**Success Metrics:**
- Time-to-first-invoice-processed for a new user: < 30 seconds (click demo file → import → agent processes it)
- Zero additional friction: import requires only one click, no credential setup for the demo bucket
- User bucket: shows files within 3 seconds of bucket name entry; friendly error if SA lacks access

**Non-Goals:**
- Full GCS file manager (create/delete/rename objects, manage ACLs)
- Multi-level deep folder navigation (one prefix level is enough for the demo)
- Real-time GCS bucket sync / file-watching
- Support for non-GCS cloud storage (S3, Azure Blob)
- Replacing the existing upload zone (the two paths are complementary)

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +1 | Skeleton loaders during GCS list; optimistic "Importing…" state while parse runs |
| 2 | EARNED TRUST | 0 | File browser returns metadata only; no factual claims |
| 3 | SKILLS, NOT FEATURES | 0 | Infrastructure feature; invisible to skill definitions |
| 4 | RIGHT MODEL, RIGHT MOMENT | +1 | Import runs AILANG Parse (deterministic, no LLM tokens); model only invoked when user starts a chat |
| 5 | GRACEFUL DEGRADATION | +1 | SA permission denied → friendly error with IAM instructions; bucket empty → empty state; parse failure → `preview_only` (existing fallback) |
| 6 | PROTOCOL OVER CUSTOM | 0 | Uses standard GCS client library APIs; no custom protocol boundaries |
| 7 | API FIRST | +1 | `/api/gcs/list` and `/api/gcs/import` are backend endpoints; channel-agnostic |
| 8 | OBSERVABLE BY DEFAULT | 0 | Covered by existing FastAPI + Cloud Trace instrumentation |
| 9 | SECURE BY CONSTRUCTION | -1 | New data access: user-controlled bucket name reaches GCS API (see justification) |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | All GCS listing + import logic in backend; frontend renders metadata only |
| | **Net Score** | **+4** | Threshold: >= +4 ✅ |

**Conflict Justifications:**
- **#9 SECURE BY CONSTRUCTION**: The user supplies a GCS bucket name for the "Your GCS Bucket" feature. Mitigations: (a) bucket names are validated against GCS naming rules server-side before any API call, (b) the backend uses only the app SA's credentials — no user credentials are ever forwarded to GCS, (c) the SA can only `storage.objects.list` on buckets where it has been explicitly granted access, so a user cannot probe arbitrary GCS infrastructure, (d) listing returns object metadata only (names, sizes, types) — no content is read until the user explicitly clicks Import, (e) the demo bucket path is fully server-controlled via `AP_DEMO_BUCKET` env var and is never user-modifiable.

## Design

### Overview

Two new backend endpoints (`GET /api/gcs/list`, `POST /api/gcs/import`) expose GCS bucket browsing and one-click import. The frontend sidebar gains a `GCSFileBrowser` component with two collapsible sections: **Example Invoices** (always available, backed by a curated demo bucket) and **Your GCS Bucket** (user-configurable, bucket name stored in localStorage). Importing a file runs it through the existing AILANG Parse → Firestore pipeline, so it appears in the user's document library exactly like a manually-uploaded file.

### Architecture

```
Sidebar
├── [Skill Info Card]            (existing)
├── [Sessions Panel]             (existing)
├── [GCSFileBrowser]             ← NEW
│   ├── Example Invoices         ← GET /api/gcs/list?bucket=demo
│   │   ├── acme-gmbh-inv-042.txt   → POST /api/gcs/import → parse pipeline
│   │   └── ...
│   └── Your GCS Bucket
│       ├── [bucket input]       ← GET /api/gcs/list?bucket=user-bucket
│       └── [file list]
├── [DocListView]                (existing — user's uploaded/imported docs)
└── [UploadDropZone]             (existing)
```

```
POST /api/gcs/import
        │
        ▼
  download_gcs_object()          (google.cloud.storage)
        │
        ▼
  _upload_to_gcs()               (reuse from upload.py)
        │
        ▼
  _run_parse() / AILANG Parse    (reuse from upload.py)
        │
        ▼
  _store_document()              (reuse from upload.py)
        │
        ▼
  ParsedDocumentResponse → Firestore real-time listener → DocListView updates
```

### Backend Changes

**New module: `backend/tools/gcs_browser/`**

```
backend/tools/gcs_browser/
├── __init__.py
├── browser.py        # list_gcs_objects(), import_gcs_object()
└── routes.py         # FastAPI router: /api/gcs/*
```

**`browser.py` — Core functions:**

```python
GCS_BUCKET_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$')

def validate_bucket_name(bucket_name: str) -> str:
    """Raise ValueError if not a valid GCS bucket name."""
    if not GCS_BUCKET_NAME_RE.match(bucket_name):
        raise ValueError(f"Invalid GCS bucket name: {bucket_name!r}")
    return bucket_name

async def list_gcs_objects(
    bucket_name: str,
    prefix: str = "",
    delimiter: str = "/",
) -> GCSListResponse:
    """List objects in a GCS bucket using the app SA. Returns metadata only."""
    ...

async def import_gcs_object(
    user: User,
    bucket_name: str,
    object_path: str,
    folder_id: str = "",
    skill_id: str = "",
) -> ParsedDocumentResponse:
    """Download object from GCS, run through parse pipeline, store in user's library."""
    # 1. Download to tempfile using google.cloud.storage
    # 2. Reuse upload.py: _upload_to_gcs, _run_parse, _store_document
    ...
```

**`routes.py` — Endpoints:**

```
GET  /api/gcs/list
     ?bucket=demo|<bucket-name>
     &prefix=<prefix>      (default "")
     &delimiter=<delim>    (default "/")

     → { bucket, prefix, objects: [{ name, size, contentType, updated }], prefixes: [str] }
     → 403 if SA lacks access (includes sa_email in response for IAM instructions)
     → 400 if bucket name invalid

POST /api/gcs/import
     { bucket: str, path: str, folder_id?: str, skill_id?: str }

     → ParsedDocumentResponse (same shape as /api/documents/upload)
     → 403 if SA lacks access to source bucket
     → 400 if file extension not in _ALLOWED_EXTENSIONS
```

`bucket=demo` is a special sentinel: the backend substitutes `os.getenv("AP_DEMO_BUCKET")`. Users cannot discover or override the demo bucket name.

**Response models:**

```python
class GCSObject(BaseModel):
    name: str           # full object path within bucket
    display_name: str   # basename for UI display
    size: int           # bytes
    content_type: str
    updated: str        # ISO 8601

class GCSListResponse(BaseModel):
    bucket: str
    prefix: str
    objects: list[GCSObject]
    prefixes: list[str]   # "subdirectory" prefixes if delimiter is "/"
    sa_email: str | None  # populated only on permission error, for IAM instructions
```

**`fast_api_app.py` registration:**
```python
from tools.gcs_browser.routes import router as gcs_browser_router
app.include_router(gcs_browser_router)  # /api/gcs
```

**New environment variables:**

| Variable | Purpose | Required |
|----------|---------|----------|
| `AP_DEMO_BUCKET` | GCS bucket name holding demo invoice files | Yes (demo) |
| `AP_DEMO_PREFIX` | Prefix within demo bucket (default: `""`) | No |

Add to `cloudbuild.yaml` substitutions:
```yaml
_AP_DEMO_BUCKET: 'gde-ap-agent-demo-invoices'
```
And to the `--set-env-vars` block in the backend deploy step.

### Frontend Changes

**New hook: `frontend/src/hooks/useGCSBucket.ts`**
```typescript
interface GCSObject { name: string; displayName: string; size: number; contentType: string; updated: string; }
interface UseGCSBucketResult { objects: GCSObject[]; prefixes: string[]; isLoading: boolean; error: string | null; saEmail?: string; }

function useGCSBucket(bucket: string, prefix?: string): UseGCSBucketResult
// Calls GET /api/proxy/api/gcs/list?bucket=...&prefix=...
// Returns empty array + error when bucket is empty or SA denied
```

**New components: `frontend/src/components/doc-browser/`**

- `GCSFileBrowser.tsx` — accordion container with two sections; manages bucket input state (localStorage key: `ap-gcs-user-bucket`)
- `GCSFileItem.tsx` — individual file row: file-type icon, name, size badge, "Import" button; shows "Importing…" spinner during POST; on success appends to DocListView via the Firestore real-time listener (no additional state needed)
- `GCSBucketInput.tsx` — single text input accepting `gs://bucket-name` or bare `bucket-name`; strips `gs://` prefix before passing to hook

**Integration in `page.tsx`:**
```tsx
<aside ...>
  {activeSkillMeta && <SkillInfoCard meta={activeSkillMeta} />}  {/* existing */}
  <GCSFileBrowser skillId={skillId} />                           {/* NEW — above sessions */}
  <div className="border-b border-border px-3 py-2.5">          {/* existing sessions */}
    ...
  </div>
  <DocListView uid={user.uid} onDocClick={handleDocClick} />     {/* existing */}
  <UploadDropZone skillId={skillId} />                           {/* existing */}
</aside>
```

**UI layout — GCSFileBrowser:**
```
┌─ Example Invoices ────────────────────── ▾ ─┐
│  📄 acme-gmbh-inv-042.txt          1.2 KB [Import] │
│  📄 techcorp-uk-inv-018.txt        0.9 KB [Import] │
│  📊 nordic-parts-batch.csv         2.1 KB [Import] │
│  📄 apex-consulting-inv-103.txt    0.8 KB [Import] │
│  📄 global-supplies-inv-q2.txt     1.1 KB [Import] │
└─────────────────────────────────────────────┘
┌─ Your GCS Bucket ─────────────────────── ▾ ─┐
│  [gs://your-bucket/invoices/     ] [Browse] │
│  (empty state or file list)                 │
└─────────────────────────────────────────────┘
```

### Demo Invoice Files

Five synthetic but realistic AP invoices created as plain text files, stored in `infrastructure/demo-invoices/`. A setup script uploads them to the demo GCS bucket.

| Filename | Vendor | Currency | Scenario |
|----------|--------|----------|----------|
| `acme-gmbh-inv-2026-042.txt` | Acme GmbH (Germany) | EUR 8,500 | Standard NET 30, GL 5200-OPEX |
| `techcorp-uk-inv-2026-018.txt` | TechCorp Ltd (UK) | GBP 12,750 | Software licenses, GL 5400-SOFT |
| `nordic-parts-inv-2026-889.txt` | Nordic Parts AB (Sweden) | EUR 3,200 | Spare parts, GL 5100-COGS |
| `apex-consulting-inv-2026-103.txt` | Apex Consulting (USA) | USD 22,000 | Professional services, GL 5300-CONSULT |
| `global-supplies-batch-q2-2026.csv` | Global Supplies Inc (USA) | USD multi-line | 3-line CSV batch invoice |

**Setup script: `infrastructure/demo-invoices/setup-demo-bucket.sh`**
```bash
#!/usr/bin/env bash
# Creates AP_DEMO_BUCKET and uploads demo invoice files
# Usage: ./setup-demo-bucket.sh [project-id]
PROJECT=${1:-multivac-internal-dev}
BUCKET=gde-ap-agent-demo-invoices
gsutil mb -p $PROJECT -l europe-west1 gs://$BUCKET 2>/dev/null || true
gsutil -m cp *.txt *.csv gs://$BUCKET/
# Grant app SA read access
SA=aitana-v6@$PROJECT.iam.gserviceaccount.com
gsutil iam ch serviceAccount:$SA:objectViewer gs://$BUCKET
echo "Demo bucket ready: gs://$BUCKET"
```

### API Changes

| Method | Endpoint | Description | Breaking? |
|--------|----------|-------------|-----------|
| GET | `/api/gcs/list` | List objects in a GCS bucket (demo or user-specified) | No — new |
| POST | `/api/gcs/import` | Import a GCS object into the user's document library | No — new |

### Security Considerations

1. **Bucket name validation**: regex check `^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$` before any GCS call
2. **Demo bucket isolation**: `bucket=demo` substitutes server-side env var; user cannot enumerate which bucket it maps to
3. **SA-only credentials**: no user credentials forwarded; backend uses app SA exclusively
4. **Path traversal**: `object_path` is validated to not contain `..` and is treated as an opaque GCS key (GCS has no filesystem path traversal risk, but we normalize anyway)
5. **Extension allowlist**: import reuses `_ALLOWED_EXTENSIONS` from `upload.py`; unsupported extensions return 400
6. **Content never read on list**: `GET /api/gcs/list` returns metadata only; content only flows on explicit `POST /api/gcs/import`

## Implementation Plan

### Phase 1: Demo Bucket + Backend (~1 day)

- [ ] Create `infrastructure/demo-invoices/` with 5 synthetic invoice files (~50 LOC text)
- [ ] Write `setup-demo-bucket.sh` script (~30 LOC)
- [ ] Create `backend/tools/gcs_browser/browser.py`:
  - `validate_bucket_name()` + `list_gcs_objects()` + `import_gcs_object()` (~120 LOC)
  - Reuse `_upload_to_gcs`, `_run_parse`, `_store_document` from `upload.py`
- [ ] Create `backend/tools/gcs_browser/routes.py`: two endpoints + Pydantic models (~80 LOC)
- [ ] Register router in `fast_api_app.py` (~3 LOC)
- [ ] Add `AP_DEMO_BUCKET` to `cloudbuild.yaml` and `.env.example` (~5 LOC)
- [ ] Write backend tests: `tests/tool_tests/test_gcs_browser.py` (~80 LOC)

### Phase 2: Frontend Browser (~1 day)

- [ ] `frontend/src/hooks/useGCSBucket.ts` (~60 LOC)
- [ ] `frontend/src/components/doc-browser/GCSFileItem.tsx` (~60 LOC)
- [ ] `frontend/src/components/doc-browser/GCSBucketInput.tsx` (~40 LOC)
- [ ] `frontend/src/components/doc-browser/GCSFileBrowser.tsx` (~120 LOC)
- [ ] Wire into sidebar in `page.tsx` (~10 LOC)
- [ ] Write frontend tests: `GCSFileBrowser.test.tsx` + `useGCSBucket.test.ts` (~80 LOC)

### Phase 3: Infrastructure + Polish (~0.5 day)

- [ ] Run `setup-demo-bucket.sh` against `multivac-internal-dev`
- [ ] Verify demo files appear and can be imported end-to-end
- [ ] Add skeleton loading states to `GCSFileBrowser`
- [ ] Add "Grant access" instructional copy when SA is denied user bucket access
- [ ] Quality gate: `npm run quality:check:fast` + `cd backend && make lint && make test-fast`
- [ ] Commit + push to trigger Cloud Build

**Total estimate:** ~2 days, ~740 LOC (implementation + tests)

## Migration & Rollout

**Database Migrations:** None — imports use the existing `parsed_documents` Firestore collection.

**Feature Flags:** None needed — the GCS browser is additive. If `AP_DEMO_BUCKET` is unset, the Example Invoices section shows an empty state (no error).

**Rollback Plan:** Remove the `GCSFileBrowser` component from the sidebar in `page.tsx` and delete the two `/api/gcs/*` routes. Zero data migration required — imported documents are treated identically to uploaded documents.

**Environment Variables:**
| Variable | Dev | Prod |
|----------|-----|------|
| `AP_DEMO_BUCKET` | `gde-ap-agent-demo-invoices` | same |
| `AP_DEMO_PREFIX` | `""` | `""` |

## Testing Strategy

### Backend Tests (pytest)
- [ ] `test_list_gcs_objects_demo` — mock GCS client, verify demo sentinel substitution
- [ ] `test_list_gcs_objects_user_bucket` — mock GCS client, verify metadata shape
- [ ] `test_list_gcs_objects_permission_denied` — mock 403, verify saEmail in response
- [ ] `test_list_gcs_objects_invalid_bucket_name` — verify 400 on bad bucket name
- [ ] `test_import_gcs_object` — mock GCS download + upload, verify Firestore record created
- [ ] `test_import_gcs_object_unsupported_extension` — verify 400 on `.exe`

### Frontend Tests (Vitest + RTL)
- [ ] `GCSFileBrowser` renders skeleton during load
- [ ] `GCSFileBrowser` renders file list with import buttons
- [ ] `GCSFileItem` shows "Importing…" during POST, success state after
- [ ] `GCSBucketInput` strips `gs://` prefix before querying
- [ ] `useGCSBucket` returns error string on 403 with SA email
- [ ] Empty demo bucket shows empty state (no crash)

### Manual Testing
- [ ] Open fresh session → Example Invoices section shows 5 files
- [ ] Click Import on `acme-gmbh-inv-2026-042.txt` → file appears in Doc library → agent can process it
- [ ] Enter own GCS bucket → files list (if SA has access) or friendly error appears
- [ ] Unsupported extension → import button disabled or returns 400

## Performance Considerations

- GCS `list_blobs()` for a small bucket (< 1000 objects, single prefix) completes in < 500ms; no pagination needed for the competition scope
- Import is synchronous (matches upload.py); large files may take 2–5s — show "Importing…" spinner
- Frontend: no bundle size impact — all GCS SDK calls are server-side only

## Success Criteria

- [ ] All backend tests passing (`cd backend && make test-fast`)
- [ ] All frontend tests passing (`npm run test:run`)
- [ ] Lint and typecheck clean (`npm run quality:check:fast`)
- [ ] Demo bucket contains 5 invoice files accessible without credentials
- [ ] A new user can import a demo invoice and start an AP chat within 30 seconds
- [ ] Invalid bucket name returns 400 with clear error message
- [ ] SA permission denied returns 403 with SA email for IAM instructions
- [ ] Imported files appear in existing DocListView (no duplicate UI)

## Open Questions

- None — design decisions made:
  - ✅ Import → parse pipeline (not direct GCS URL to agent)
  - ✅ Synthetic text/CSV demo files
  - ✅ App SA tries to list (user sees SA email if denied)
  - ✅ User bucket stored in localStorage (Firestore persistence is a post-competition improvement)

## Related Documents

- [`competition-polish-sprint.md`](./competition-polish-sprint.md) — parent sprint context
- [`docs/design/v6.1.0/implemented/file-browser.md`](../../v6.1.0/implemented/file-browser.md) — existing document browser design
- [`backend/tools/documents/upload.py`](../../../../backend/tools/documents/upload.py) — parse pipeline to reuse
- [`frontend/src/components/doc-browser/`](../../../../frontend/src/components/doc-browser/) — existing doc browser components
