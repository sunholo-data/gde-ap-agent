# Platform Gotchas

Operational surprises that have burned us or the AIPLA fork. Each entry explains the symptom, root cause, and fix.

---

## Firebase resource-location must be set before first Firestore write

**Symptom:** `FirebaseError: Installations: Create Installation request failed with error "400 INVALID_ARGUMENT: Firebase resource location is not set."` — seen only in a fresh GCP project, usually in CI or when the fork bootstraps a new environment.

**Root cause:** Firebase requires `google_app.options.databaseURL` or an explicit resource-location to be set before the Firestore SDK can initialise. In the Aitana v6 / AIPLA template the Firebase Admin SDK picks up the app's resource location from the service account, but a brand-new project has no location until the first call to `firebase init` or until a resource (Firestore database) is created via the console / Terraform.

**Fix (template forks):**
1. Create the Firestore database in the correct region **before** the backend service starts. In Terraform: `google_firestore_database` with `location_id = "eur3"` (or your region).
2. If using the bootstrap script (`scripts/bootstrap-gcp-project.sh`), ensure the Firestore step runs before any Cloud Run deploy.
3. Set `FIRESTORE_EMULATOR_HOST=localhost:8080` in local dev so the SDK never hits production before the database exists.

**See also:** [template-cloudbuild-hardening.md](../design/template/template-cloudbuild-hardening.md) — item #9 in the upstream feedback.

---

## Empty user_email causes Firestore 400 on tool_permissions lookup

**Symptom:** `400 InvalidArgument: Document name must not be empty` when the permission enforcer looks up an anonymous user's tool access.

**Root cause:** `auth.permissions.can_use_tool()` previously passed `user_email=""` directly to `fs.get_document("tool_permissions", "")`, producing a Firestore path with a trailing slash (`tool_permissions/`).

**Fix:** Guard on empty email before the user-level lookup — see `backend/auth/permissions.py`:
```python
user_doc = fs.get_document(COLLECTION, user_email) if user_email else None
```
The lookup falls through to domain → wildcard as expected.

---

## Anonymous-group users trigger Firestore permission-denied console errors

**Symptom:** Dozens of `FirebaseError: Missing or insufficient permissions` in the browser console when running in `NEXT_PUBLIC_AUTH_MODE=anonymous_group_id` mode.

**Root cause:** `useDocBrowser`, `useDocument`, and related hooks called `onSnapshot()` unconditionally. Anonymous-group sessions have no Firebase Auth user, so Firestore rules deny the snapshot immediately — and the SDK retries forever, flooding the console.

**Fix:** Import `isAnonymousGroupAuthMode` and return early before calling `onSnapshot`:
```typescript
import { isAnonymousGroupAuthMode } from "@/lib/anonymousGroupAuth";
if (!db || !uid || isAnonymousGroupAuthMode()) return;
```
Applied to `useDocBrowser.ts` (both folder and document listeners) and `useDocument.ts`.

---

## Cloud Build secrets fail the deploy when a channel is disabled (#5)

**Symptom:** `gcloud run deploy` exits with `Secret Manager secret ... does not exist` even though the channel (Telegram, WhatsApp, email) is not being used.

**Root cause:** The original `cloudbuild.yaml` passed `--set-secrets=TELEGRAM_BOT_TOKEN=...` unconditionally. If the secret doesn't exist in Secret Manager the deploy step fails before the service starts.

**Fix:** The deploy step now uses channel feature flags (`_ENABLE_TELEGRAM`, `_ENABLE_WHATSAPP`, `_ENABLE_EMAIL`, `_ENABLE_ANTHROPIC`). Set any flag to `'false'` (default) and the corresponding `--set-secrets` flag is omitted entirely. To activate a channel, create the secret in Secret Manager and set the flag to `'true'` in the Terraform Cloud Build trigger substitutions.

---

## Cloud Build log bucket must exist before first deploy (#6)

**Symptom:** Cloud Build fails at the start with `bucket does not exist` or access-denied writing logs.

**Root cause:** The original `cloudbuild.yaml` hardcoded `gs://multivac-deploy-aitana-logging-bucket` — an Aitana-owned bucket that forks don't have access to.

**Fix:** `logsBucket` now uses the `_LOG_BUCKET` substitution which defaults to `gs://${_PROJECT_ID}-cloudbuild-logs`. Create this bucket by running:
```bash
./scripts/bootstrap-gcp-project.sh <project-id> <runtime-sa-email>
```
The bootstrap script creates the bucket and grants the Cloud Build SA write access.

---

## Cloud Build service agent not auto-provisioned in new GCP projects (#7)

**Symptom:** `gcloud builds triggers create` or `gcloud run deploy` via Cloud Build fails with `INVALID_ARGUMENT` on projects created after mid-2024.

**Root cause:** Google stopped auto-provisioning the `service-<project-number>@gcp-sa-cloudbuild.iam.gserviceaccount.com` service agent on new projects. Without it, Cloud Build cannot act as the runtime SA or create triggers.

**Fix:** Run once before the first trigger creation:
```bash
./scripts/bootstrap-gcp-project.sh <project-id> <runtime-sa-email>
```
This materializes the agent via `gcloud beta services identity create` and grants it `iam.serviceAccountUser` on the runtime SA.

---

## Cloud Build v2 repository registration requires GitHub `admin` permission (#8)

**Symptom:** `gcloud builds repositories create` fails with an error naming the GitHub user but giving no hint about the missing permission.

**Root cause:** Setting up server-side webhooks requires `admin` on the GitHub repository. `push` permission is not enough.

**Fix:** Promote the CI bot account (or the authorizing GitHub user) to `admin` on the repository before running `gcloud builds repositories create`. For a dedicated bot, use a GitHub App with `admin:repo_hook` scope rather than a personal access token.

---

## `gcloud auth print-identity-token` fails under user-managed SA (#13)

**Symptom:** The `seed-platform-skills` Cloud Build step silently succeeds (`exit 0`) but the marketplace is empty. The step log shows `TOKEN=` with an empty value or an error that was swallowed.

**Root cause:** `gcloud auth print-identity-token --audiences=...` only works when Cloud Build runs under the default Compute SA. Under a user-managed SA it returns an error; the original step had `set +e; exit 0` so the failure was invisible.

**Fix:** The seed step now uses the GCE metadata server endpoint:
```bash
TOKEN=$(curl -sf \
  "http://metadata.google.internal/.../identity?audience=<URL>&format=full&include_email=true" \
  -H "Metadata-Flavor: Google")
```
This works under any SA. The step also no longer has `set +e; exit 0` — a non-200 response now fails the build visibly.

---

## Identity token missing `email` claim causes silent 403 (#14)

**Symptom:** Even after fixing #13, the seed step returns 403 with no useful body. The backend logs show nothing diagnostic.

**Root cause:** The GCE metadata server omits the `email` claim by default unless `include_email=true` is in the request query string. The backend's admin allowlist check required the claim.

**Fix (two-part):**
1. Append `&include_email=true` to the metadata server URL (see #13 above — already in the fixed seed step).
2. The backend now logs a clear error when the claim is absent:
   ```
   admin_auth_denied: email claim absent from token — did you forget include_email=true?
   ```
   The 403 detail also says `"email claim missing from token"` instead of the generic `"Not authorized"`.

---

## tool_permissions wildcard doc must be seeded on first deploy

**Symptom:** All tool calls are silently denied for every user in a fresh environment because there is no `tool_permissions/*` document.

**Root cause:** The permission enforcer falls through to "deny" when no user/domain/wildcard doc exists. A fresh project has no seed data.

**Fix:** `platform_seed.py` (called once per deploy by Cloud Build) now calls `_ensure_tool_permissions_wildcard()` which idempotently writes a `{"type":"wildcard","tools":["*"],"denied":[]}` doc if none exists. See `backend/admin/platform_seed.py`.
