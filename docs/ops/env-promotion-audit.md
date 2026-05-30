# Env-promotion audit — dev → test → prod

> The promise of `dev → test → prod` is that **test catches drift so prod is
> boring**. Dev → test is emphatically not boring — this doc exists so the
> next cut (test → prod) is.

**Status**: prod is live (2026-04-22). API-SECURITY sprint (M6) applied all 5
security controls to `aitana-multivac-production` — build 52952275 SUCCESS.
`ai.aitana.chat` v5 traffic unaffected.

## Why this exists

The v6 dev → test promotion hit **four distinct drift classes** in one go.
Each was invisible until the terraform or smoke step failed; each would
have re-surfaced on the test → prod cut if we hadn't written it down.

The user's framing was explicit: *"It must be almost boring to promote
test to prod."* That's the bar. This doc is the audit procedure + the
lessons that got us there.

Running principle, also user-explicit: **no manual IAM grants.** Every
role terraform needs lives in HCL, committed, reviewed, cascaded.

## The IAM cascade pattern (load-bearing)

This is the single most important thing to internalise. Every
terraform-SA role that must exist on `aitana-multivac-{dev,test,prod}`
is managed in **one place**:

```
multivac-aitana/infrastructure/bootstrap/terraform.tfvars
  └─ var.tf_account_permissions (list of roles)
       │
       ▼
bootstrap/main.tf:81-90
  module "terraform_permissions_on_folder" {
    source = "../modules/service_accounts_folder"
    folder = var.folder                 # = "492200293118"
    roles  = var.tf_account_permissions
    member = "serviceAccount:${var.tf_service_account}"
  }
       │
       ▼
modules/service_accounts_folder/main.tf
  resource "google_folder_iam_member" "this" {
    for_each = toset(var.roles)
    folder   = var.folder
    role     = each.value
    member   = var.member
  }
       │
       ▼ (GCP auto-cascades folder IAM to child projects)
aitana-multivac-dev  ✔ role granted
aitana-multivac-test ✔ role granted
aitana-multivac-prod ✔ role granted
```

**Lesson:** if the terraform SA needs a new role on a target project,
it is **one edit in one file**: append to `tf_account_permissions`,
commit, push to `dev` — the bootstrap trigger
(`trigger-bootstrap-multivac-deploy-aitana`) applies and the folder
cascade propagates to every env within ~60s.

**Do NOT** add `google_project_iam_member` resources inside
`environments/{dev,test,prod}/`. That is exactly how dev → test drift
happens.

## Promotion flow in one picture

```
GitHub: Aitana-Labs/platform           GitHub: sunholo-data/multivac-aitana
  dev ── merge ──▶ test ── merge ──▶ prod    dev ── merge ──▶ test ── merge ──▶ prod
   │                                          │
   │ (push fires includedFiles=backend/**,    │ (push fires terraform trigger
   │  frontend/**, cloudbuild.yaml)           │  with dir=environments/${BRANCH_NAME})
   ▼                                          ▼
trigger-aitana-${env}-aitana-v6-{backend,     trigger-terraform-multivac-deploy-aitana
   frontend}                                     ├─ auto-applies env dir
   ├─ firebase deploy firestore:rules,indexes    └─ also auto-applies bootstrap on
   ├─ docker build + push to Artifact Registry      infra/bootstrap/** change
   ├─ terraform-free Cloud Run deploy
   └─ smoke-deployed.sh (fails build on non-200)
```

Key subtleties baked into this flow (they each bit us):

- **`trigger-aitana-${env}-aitana-v6-*` lives in `multivac-deploy-aitana`**,
  not `multivac-deploy`. The terraform SA + its triggers live in the
  latter; v6's branch-deploy triggers live in the former.
- **Bootstrap is a single shared workspace**, not per-env. It cascades
  to all three envs via folder IAM. There is no `bootstrap-test`.
- **v6 frontend trigger's `includedFiles` filter** only fires on
  `frontend/**`, `backend/**`, `cloudbuild.yaml`. Edits to
  `firestore.rules` / `firestore.indexes.json` do **not** auto-fire;
  they must be bundled with a frontend/backend change or the trigger
  manually fired. (Follow-up: add `firestore.*` to `includedFiles`.)
- **Firebase Identity Platform is a singleton** — each env's
  `auth_config.tf` uses a declarative `import {}` block. First-time
  bring-up of a new env is a no-op to terraform if the config already
  exists.

## The four drift classes we hit

| # | Class | Surface | What broke | How it was fixed | How to catch next time |
|---|---|---|---|---|---|
| 1 | **File drift** | `environments/test/main.tf` | Missing `module "aitana_v6_telemetry"` + `github_connection` coalesce added in dev-only commit | PR copying dev/main.tf | `diff environments/dev/main.tf environments/test/main.tf` before promotion PR |
| 2 | **Schema drift** | `environments/{test,prod}/variables.tf` | `cloud_run_client` / `cloud_run_multiple` object types missing `github_connection = optional(string)` (dev-only commit 317fa27) | Copy dev/variables.tf verbatim | `diff environments/dev/variables.tf environments/test/variables.tf` before promotion PR |
| 3 | **IAM drift** (root cause of the longest outage) | `terraform@multivac-deploy` perms on aitana-multivac-test | Missing `roles/identityplatform.admin` + `roles/firebase.admin`; test's `google_identity_platform_config.auth` apply 403'd | Append two roles to `tf_account_permissions` in `bootstrap/terraform.tfvars`; folder cascade propagated | `gcloud projects get-iam-policy <target>` diff against dev, filtered to the terraform SA — any delta is drift |
| 4 | **Firestore index drift** | `firestore.indexes.json` (this repo) | Missing composite `accessControl.type (ASC) + usageCount (DESC)` required by `skill_config.list_marketplace`; dev had it manually created in the console | Added to `firestore.indexes.json`; deployed via cloudbuild firebase step | `diff` the file against what `gcloud firestore indexes composite list --project=<dev>` produces |

### Why IAM drift was the sneaky one

Dev was working because, during the auth sprint, somebody granted
`identityplatform.admin` on `aitana-multivac-dev` via console/gcloud.
That manual grant was invisible to terraform and silently carried
dev for weeks. Test was a fresh project with no such manual crutch, so
it was the first time the missing role surfaced.

The user's diagnosis was dead-on: *"we have extensive permissions
already granted at the other terraform project multivac — I suspect
that has not been accounted for"*. Exactly that. The bootstrap folder
cascade already handled every other terraform SA role; two were
simply missing from the list.

**Fix diff** (`multivac-aitana/infrastructure/bootstrap/terraform.tfvars`):

```diff
   "roles/cloudbuild.builds.editor",
+  "roles/firebase.admin",
+  "roles/identityplatform.admin",
   "roles/iam.securityAdmin",
```

That was it. No new module, no per-env IAM, no manual gcloud.

### Why Firestore-index drift was the second sneaky one

Same shape as IAM drift: dev had the index from early local console
tinkering; `firestore.indexes.json` in the repo had never captured it.
The v6 frontend trigger's `includedFiles` doesn't include `firestore.*`,
so even after we added the missing index to the file, the change
didn't auto-fire a deploy — we had to manually run the trigger.

## Pre-promotion audit procedure

Run these mechanical diffs **before opening the promotion PR**. Any
non-empty diff that isn't on the allow-list below is a blocker.

```bash
SRC=dev; TGT=test   # or TGT=prod
AITANA_INFRA=/Users/mark/dev/sunholo/multivac-aitana/infrastructure

# 1. Terraform file drift
diff "$AITANA_INFRA/environments/$SRC/main.tf" \
     "$AITANA_INFRA/environments/$TGT/main.tf"
diff "$AITANA_INFRA/environments/$SRC/variables.tf" \
     "$AITANA_INFRA/environments/$TGT/variables.tf"

# 2. Per-env tfvars drift (in GCS, not git)
gcloud storage cat gs://multivac-deploy-aitana-terraform-state/deploy/$TGT/run_client.tfvars \
  > /tmp/tgt.tfvars
gcloud storage cat gs://multivac-deploy-aitana-terraform-state/deploy/$SRC/run_client.tfvars \
  > /tmp/src.tfvars
diff /tmp/src.tfvars /tmp/tgt.tfvars   # only URL + project_id deltas should remain

# 3. Enabled services drift
gcloud services list --enabled --project=aitana-multivac-$SRC  --format='value(config.name)' | sort > /tmp/src.svc
gcloud services list --enabled --project=aitana-multivac-$TGT  --format='value(config.name)' | sort > /tmp/tgt.svc
diff /tmp/src.svc /tmp/tgt.svc

# 4. Terraform SA IAM drift (folder cascade must match)
for P in $SRC $TGT; do
  gcloud projects get-iam-policy aitana-multivac-$P \
    --flatten='bindings[].members' \
    --filter='bindings.members:terraform@multivac-deploy.iam.gserviceaccount.com' \
    --format='value(bindings.role)' | sort > /tmp/$P.tf-roles
done
diff /tmp/$SRC.tf-roles /tmp/$TGT.tf-roles   # MUST be empty

# 5. Firestore composite index drift
gcloud firestore indexes composite list --project=aitana-multivac-$SRC \
  --format=json | jq -S '.' > /tmp/$SRC.idx
gcloud firestore indexes composite list --project=aitana-multivac-$TGT \
  --format=json | jq -S '.' > /tmp/$TGT.idx
diff /tmp/$SRC.idx /tmp/$TGT.idx   # deltas → add to firestore.indexes.json

# 6. Allow-listed environment deltas (these are expected to differ)
#    - project_id
#    - Cloud Run service URLs (they contain the generated project hash)
#    - Firebase Web API key
#    - any explicit env-specific overrides
```

Any diff outside the allow-list is drift. Fix it in the **source**
(bootstrap tfvars, environments/${SRC}, or the file in this repo) and
re-run the diff until clean.

## One-time per-env bring-up

These are the steps that **only happen once when cutting a new env**
(i.e. the first time test existed, and will happen again once when
prod is cut). Zero manual gcloud in the happy path.

- `git checkout -b <env> origin/dev && git push -u origin <env>` on
  both `Aitana-Labs/platform` and `sunholo-data/multivac-aitana`.
- `infrastructure/environments/<env>/` created by copying from
  `infrastructure/environments/dev/`, with project_id + URLs swapped.
- `backend/scripts/_env.py` — append `<env>` entry with project_id,
  Firebase Web API key, deployed frontend URL.
- `docs/ops/deployed-urls.md` — append env section.
- Firebase Identity Platform: first terraform apply imports the
  singleton via the declarative `import {}` block in
  `auth_config.tf`. No manual `terraform import` needed anymore.

## Post-apply verification

```bash
cd backend
# Rules + smoke, one env:
GCP_PROJECT=aitana-multivac-<env> GOOGLE_CLOUD_PROJECT=aitana-multivac-<env> \
  uv run python scripts/verify_rules.py --env <env>   # → 11/11 PASS
GCP_PROJECT=aitana-multivac-<env> GOOGLE_CLOUD_PROJECT=aitana-multivac-<env> \
  uv run python scripts/whoami_smoke.py --env <env>   # → 200 + groupTags

cd ..
./scripts/smoke-deployed.sh <env> all   # all probes 200
curl -s -o /dev/null -w "%{http_code}\n" \
  https://<frontend-url>/api/proxy/api/skills/marketplace   # → 200
```

## The "one edit in bootstrap" rule

For any future *"terraform needs role X on a target project"*:

1. `bootstrap/terraform.tfvars` — append `"roles/<role>"` to
   `tf_account_permissions`.
2. Commit + push to `dev` on `sunholo-data/multivac-aitana`.
3. `trigger-bootstrap-multivac-deploy-aitana` auto-applies.
4. Folder cascade propagates to dev/test/prod within ~60s.

Do NOT:
- Add `google_project_iam_member` in per-env dirs.
- Grant manually via gcloud/console "just to unblock".
- Add a new `terraform_sa_iam` module (that mechanism already exists
  — see the cascade diagram above).

## Prod-readiness checklist

Before merging `test → prod` on either repo, **every box below must
be ticked**.

- [ ] All audit-procedure diffs (§ Pre-promotion audit procedure) empty
      or allow-listed only.
- [ ] `terraform plan` against test workspace is a no-op.
- [ ] Test smokes (`verify_rules`, `whoami_smoke`, `smoke-deployed.sh`)
      have been green for at least 24h.
- [ ] Firestore rules **and** composite indexes live on test
      (check via `firestore indexes composite list`).
- [ ] Prod branches cut on both repos (`Aitana-Labs/platform` and
      `sunholo-data/multivac-aitana`).
- [ ] Prod `run_client.tfvars` uploaded to GCS, diffed against test
      (URL + project_id deltas only).
- [ ] Prod entry appended to `backend/scripts/_env.py`.
- [ ] Prod entry appended to `docs/ops/deployed-urls.md`.
- [ ] Firebase Identity Platform singleton imported in
      `environments/prod/auth_config.tf`.
- [ ] Terraform SA IAM on prod matches dev/test (folder cascade — the
      `gcloud projects get-iam-policy` diff above must be empty).
- [ ] Prod Firestore composite indexes match dev/test (the
      `firestore indexes composite list` diff must be empty).

## Incident log

### #1 — dev → test, 2026-04-20

**Symptoms** (in the order we hit them):

1. test terraform apply failed: `module
   "aitana_v6_telemetry"` undefined + `github_connection` coalesce
   missing. (File drift.)
2. After copying dev/main.tf → apply failed: schema mismatch on
   `cloud_run_client` object type. (Schema drift.)
3. After copying dev/variables.tf → apply failed:
   `google_identity_platform_config.auth` returned 403 "the caller
   does not have permission". (IAM drift.)
4. After fixing IAM + rest of apply → frontend smoke step failed on
   `/api/proxy/api/skills/marketplace` with 500;
   Cloud Logging showed `FailedPrecondition: The query requires an
   index`. (Firestore index drift.)

**Fix**:

- File + schema drift: PRs copying dev files verbatim, then audit diff.
- IAM drift: **two-line edit** to
  `multivac-aitana/infrastructure/bootstrap/terraform.tfvars`, adding
  `roles/firebase.admin` and `roles/identityplatform.admin` to
  `tf_account_permissions`. Bootstrap apply; folder cascade did the
  rest.
- Index drift: added composite
  `{accessControl.type ASC, usageCount DESC}` to
  `firestore.indexes.json`; manually fired the v6 frontend trigger
  because `firestore.*` isn't in `includedFiles`.

**Lessons** (each is a memory entry, each shapes this doc):

1. **Check existing terraform before inventing a module.** I drafted a
   new `terraform_sa_iam` module before noticing `bootstrap/main.tf:81-90`
   already cascades roles folder-wide. The user's one-line insight
   (*"we have extensive permissions already granted at the other
   terraform project multivac — I suspect that has not been accounted
   for"*) was exactly the pattern. Grep existing HCL first.
2. **No manual IAM grants.** Dev's invisible
   `identityplatform.admin` grant hid the real drift for weeks. Every
   role goes in `tf_account_permissions`, full stop.
3. **Firestore indexes are code.** If it's in dev but not in
   `firestore.indexes.json`, it'll break test the first time a query
   needs it. Diff the live indexes against the file before promotion.
4. **`includedFiles` filters are invisible tripwires.** v6 frontend
   trigger doesn't watch `firestore.*` — edits there need a
   frontend/backend change to ride along, or a manual trigger fire.
   Follow-up: add `firestore.*` to the filter.
5. **Which deploy project?** v6 branch-deploy triggers live in
   `multivac-deploy-aitana`; the terraform SA + its triggers live in
   `multivac-deploy`. Easy to lose ~10 minutes grepping the wrong one.

### #2 — API-SECURITY sprint: test → prod, 2026-04-22

**Scope:** Port 5 post-incident security controls (API key referrer restrictions,
Cloud Audit Logs, quota overrides, monitoring alerts) from `sunholo/multivac`
into `aitana-multivac-production` via a shared terraform module.

**No drift-class incidents** — the audit procedure did its job. Two
operational incidents captured in sprint JSON (`INC-1`, `INC-2`); both were
resolved before the prod push.

**INC-1 (dev):** `google_apikeys_key` destroyed on first apply because the import
stored project as a number while the module config passed a project ID string;
provider treats project as immutable and planned destroy+replace. Recovered via
`gcloud services api-keys undelete`. Permanent fix: `lifecycle.ignore_changes =
[project, restrictions[0].api_targets]` + `prevent_destroy = true` in module.

**INC-2 (test):** `apikeys.googleapis.com` was disabled on test + prod (only dev
was auto-enabled by Firebase). The `import` block reads the existing key at
plan-time, requiring the API. Fix: one-time `gcloud services enable
apikeys.googleapis.com --project=aitana-multivac-{test,production}`. Documented
as a bootstrap prerequisite in `multivac-aitana/docs/security/api-key-audit-port.md`.

**Build results:** dev `021bb81a` SUCCESS, test `17f19dce` SUCCESS,
prod `52952275` SUCCESS.

**Lessons added to `gotcha_apikeys_project_replace.md`** (memory) and
`gotcha_two_deploy_projects.md` (memory).

## Cross-references

- [auth-smoke-testing.md](auth-smoke-testing.md) — whoami probe details
  and the four auth traps.
- [deployed-urls.md](deployed-urls.md) — canonical per-env URLs.
- `multivac-aitana/infrastructure/bootstrap/` — the folder-cascade.
- `multivac-aitana/infrastructure/environments/{dev,test,prod}/` —
  per-env terraform (no IAM here).
