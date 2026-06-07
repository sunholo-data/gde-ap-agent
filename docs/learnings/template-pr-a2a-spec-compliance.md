# Template PR brief — A2A spec compliance for Gemini Enterprise

> **For the template-repo agent on `sunholo-data/ai-protocol-platform`.**
> Two coupled bugs found while doing a real `agents-cli register-gemini-enterprise`
> registration against a Discovery Engine app on 2026-06-07. Both are pure
> A2A spec / proxy-topology bugs with zero AP-specific logic — every fork
> deploying the template behind a Next.js → FastAPI sidecar topology will hit
> them when they try to register with Gemini Enterprise.
>
> Source: `Aitana-Labs/gde-ap-agent` commits `236fdcb` (URL rewrite) and
> `dbc5856` (protocolVersion + tests + probe).
>
> Companion friction-log entries: TODO — add Friction 15 + 16 below the
> existing 14 in `docs/learnings/template-protocols-friction.md`. Content
> for those entries is at the bottom of this brief.

## TL;DR

Two changes + one new script + one strengthened test:

1. **Backend** ([`backend/protocols/a2a.py`](#1-backend-protocolsa2apy)) — add
   `protocolVersion: "0.2.0"` to the agent card body. Discovery Engine
   rejects the card without it.
2. **Frontend** ([`frontend/src/app/.well-known/agent.json/route.ts`](#2-frontend-well-known-agent-card-route)) —
   rewrite the card's `url` field to the public origin before returning it.
   The backend can't know its public URL when it's a sidecar behind the
   Next.js ingress; this is the only layer that does.
3. **New** ([`scripts/verify-a2a.sh`](#3-new-scripts-verify-a2a-sh)) — 11-check
   spec compliance probe that catches both bugs above + asserts capability
   negotiation works end-to-end.
4. **Test** ([`backend/tests/api_tests/test_a2a.py`](#4-backend-test-strengthening)) —
   require `protocolVersion` in `test_agent_card_returns_minimum_a2a_fields`
   so the regression can't slip back.

## Why this matters — the failure mode in production

The whole point of the template's A2A surface is "another agent can discover
and coordinate with you." Today the template **passes discovery** (the
`/.well-known/agent.json` route returns 200 with the right shape) but **fails
Gemini Enterprise registration** in two ways the spec-compliance tests don't
catch:

```bash
# 1. URL leak — card advertises localhost
$ curl -s https://<fork-host>/.well-known/agent.json | jq -r .url
http://localhost:1956   ← Gemini Enterprise would store this and try to invoke it

# 2. Spec violation — card missing protocolVersion
$ agents-cli register-gemini-enterprise --registration-type a2a \
    --agent-card-url https://<fork-host>/.well-known/agent.json \
    --gemini-enterprise-app-id <...>
Error: 400 INVALID_ARGUMENT: required property 'protocolVersion' not found in object
```

Both are real failures observed on the gde-ap-agent fork's Discovery Engine
registration on 2026-06-07.

---

## 1. Backend — `backend/protocols/a2a.py`

**Where:** inside `_build_card()`, top of the returned dict (immediately
before `name`).

**Diff:**

```diff
 def _build_card(base_url: str) -> dict[str, Any]:
     try:
         skills = list_marketplace(limit=100)
     except Exception:
         logger.exception("a2a._build_card: list_marketplace failed; serving empty skills")
         skills = []
     return {
+        # A2A wire-protocol version this card complies with. Required by
+        # the Discovery Engine / Gemini Enterprise card validator — a
+        # missing protocolVersion makes `agents-cli register-gemini-enterprise
+        # --registration-type a2a` fail with INVALID_ARGUMENT. Matches the
+        # `a2a-v0.2` value we advertise in `capabilities.extensions`.
+        "protocolVersion": "0.2.0",
         "name": os.getenv("A2A_AGENT_NAME", "..."),
         "description": os.getenv("A2A_AGENT_DESCRIPTION", "..."),
         "url": base_url,
         "version": "6.0.0",
         "capabilities": {
             "streaming": True,
             ...
             "extensions": list(SUPPORTED_EXTENSIONS),
         },
         "defaultInputModes": ["text"],
         "defaultOutputModes": ["text"],
         "skills": [_skill_to_a2a(s) for s in skills],
     }
```

**Notes for template fork:**
- The value `"0.2.0"` is the A2A wire protocol version this card complies
  with. It matches the `a2a-v0.2` token already in
  `SUPPORTED_EXTENSIONS`. Keep them in sync — if the template ever upgrades
  to A2A 0.3 or later, both need to move together.
- This is a top-level field on the card root, NOT inside `capabilities`.

---

## 2. Frontend — well-known agent-card route

**File:** `frontend/src/app/.well-known/agent.json/route.ts`

**Problem:** the FastAPI backend has no way to know its public URL — it sits
as a sidecar behind the Next.js ingress. Left alone the card advertises
`http://localhost:1956` (the backend's `PUBLIC_BASE_URL` fallback), which
means a peer A2A client or Gemini Enterprise can DISCOVER the card but
cannot actually invoke any skill on it. The Next route is the only layer
that knows the real public URL.

**Replacement `GET` handler + helper:**

```ts
/**
 * Public-host the agent card claims it lives at.
 *
 * The FastAPI backend has no idea what URL the outside world reaches it by — it
 * sits as a sidecar behind this Next.js ingress. Left untouched, the card
 * advertises `http://localhost:1956` (the backend's PUBLIC_BASE_URL fallback),
 * which means a peer A2A agent or Gemini Enterprise can discover the card but
 * cannot actually invoke any skill on it. This route is the one layer that
 * knows the real public URL, so it rewrites the `url` field to match the
 * incoming request's origin.
 *
 * Cloud Run terminates TLS at the GFE and forwards via `X-Forwarded-Proto`;
 * NextRequest.nextUrl already accounts for that, so `req.nextUrl.origin` is
 * the right authority to advertise.
 */
function publicOrigin(req: NextRequest): string {
  // Prefer forwarded headers (Cloud Run GFE always sets these) over
  // req.nextUrl.origin so we never accidentally advertise an internal host.
  const proto =
    req.headers.get("x-forwarded-proto") ?? req.nextUrl.protocol.replace(":", "");
  const host =
    req.headers.get("x-forwarded-host") ??
    req.headers.get("host") ??
    req.nextUrl.host;
  return `${proto}://${host}`;
}

export async function GET(req: NextRequest): Promise<NextResponse> {
  const url = `${BACKEND_URL}/.well-known/agent.json`;
  try {
    const upstream = await fetch(url, {
      method: "GET",
      headers: filterRequestHeaders(req.headers),
      cache: "no-store",
    });
    const headers = filterResponseHeaders(upstream.headers);
    const contentType = upstream.headers.get("content-type") ?? "";

    // Pass non-JSON or non-2xx responses through untouched so error bodies
    // are not silently rewritten into something they aren't.
    if (!contentType.includes("application/json") || !upstream.ok) {
      const passthrough = await upstream.arrayBuffer();
      return new NextResponse(passthrough, {
        status: upstream.status,
        headers,
      });
    }

    const card = (await upstream.json()) as Record<string, unknown>;
    card.url = publicOrigin(req);
    const rewritten = JSON.stringify(card);
    headers.set("content-type", "application/json");
    return new NextResponse(rewritten, { status: upstream.status, headers });
  } catch (err) {
    return NextResponse.json(
      { error: "backend_unreachable", message: String(err) },
      { status: 502 },
    );
  }
}
```

**Imports / constants** (already in the existing file, listed for completeness):

```ts
import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:1956";

// Existing helpers — keep as-is:
//   - BLOCKED_REQUEST_HEADERS
//   - BLOCKED_RESPONSE_HEADERS
//   - filterRequestHeaders()
//   - filterResponseHeaders()
```

---

## 3. New — `scripts/verify-a2a.sh`

Drop-in script. 11 assertions cover discovery 200, capability negotiation,
all required spec fields (including the new `protocolVersion`), the
non-localhost URL, the `a2a-v0.2` extension, and a non-empty skills array.
Skip-don't-fail on missing `curl` / `jq`. Exit code 1 on any assertion
failure → suitable for CI.

```bash
#!/usr/bin/env bash
# scripts/verify-a2a.sh — assert the deployed agent card is A2A-spec-compliant
# and ready for Gemini Enterprise / peer-agent discovery.
set -euo pipefail

AP_URL="${AP_URL:-https://<your-fork-host>.run.app}"   # forks override
CARD_URL="${AP_URL%/}/.well-known/agent.json"

skip() { echo "skipping verify-a2a — $1" >&2; exit 0; }
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
fail() { printf "  \033[31mFAIL\033[0m %s\n" "$1"; FAILED=1; }
info() { printf "  \033[36m...\033[0m  %s\n" "$1"; }

command -v curl >/dev/null 2>&1 || skip "curl not on PATH"
command -v jq   >/dev/null 2>&1 || skip "jq not on PATH"

FAILED=0
echo "verify-a2a: probing ${CARD_URL}"
echo

info "fetching card with X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern"
HEADERS_FILE="$(mktemp)"
BODY_FILE="$(mktemp)"
trap 'rm -f "$HEADERS_FILE" "$BODY_FILE"' EXIT

STATUS=$(curl -s -o "$BODY_FILE" -D "$HEADERS_FILE" -w "%{http_code}" \
  -H 'X-A2A-Extensions: a2ui-v0.9, a2ui-decoupled-pattern' \
  "$CARD_URL")

if [[ "$STATUS" == "200" ]]; then
  ok "HTTP 200 (unauthenticated discovery)"
else
  fail "expected HTTP 200, got $STATUS"
fi

NEGOTIATED=$(grep -i '^x-a2a-extensions:' "$HEADERS_FILE" | head -1 | sed 's/^[^:]*: *//' | tr -d '\r')
VARY=$(grep -i '^vary:' "$HEADERS_FILE" | sed 's/^[^:]*: *//' | tr -d '\r')

if [[ -n "$NEGOTIATED" ]]; then
  ok "X-A2A-Extensions echoed on response: ${NEGOTIATED}"
else
  fail "X-A2A-Extensions header missing on response"
fi
if echo "$VARY" | grep -qi "X-A2A-Extensions"; then
  ok "Vary advertises X-A2A-Extensions (cache-correctness)"
else
  fail "Vary does NOT include X-A2A-Extensions"
fi

# protocolVersion is required by Discovery Engine / Gemini Enterprise — a
# missing one makes `agents-cli register-gemini-enterprise --registration-type
# a2a` fail with INVALID_ARGUMENT.
for field in protocolVersion name description url version capabilities skills; do
  if jq -e ".${field}" "$BODY_FILE" >/dev/null 2>&1; then
    ok "card has required field: ${field}"
  else
    fail "card MISSING required field: ${field}"
  fi
done

ADVERTISED_URL=$(jq -r '.url' "$BODY_FILE")
if [[ "$ADVERTISED_URL" == http*localhost* ]] || [[ "$ADVERTISED_URL" == http*127.0.0.1* ]]; then
  fail "card advertises a non-routable URL: ${ADVERTISED_URL}"
else
  ok "card advertises a public URL: ${ADVERTISED_URL}"
fi

EXT_COUNT=$(jq -r '.capabilities.extensions | length' "$BODY_FILE" 2>/dev/null || echo 0)
if [[ "$EXT_COUNT" -gt 0 ]]; then
  EXTS=$(jq -r '.capabilities.extensions | join(", ")' "$BODY_FILE")
  ok "capabilities.extensions advertises ${EXT_COUNT} extension(s): ${EXTS}"
  if jq -e '.capabilities.extensions | index("a2a-v0.2")' "$BODY_FILE" >/dev/null; then
    ok "advertises a2a-v0.2 (canonical A2A extension)"
  else
    fail "capabilities.extensions does not include a2a-v0.2"
  fi
else
  fail "capabilities.extensions is empty or missing"
fi

SKILL_COUNT=$(jq -r '.skills | length' "$BODY_FILE")
if [[ "$SKILL_COUNT" -gt 0 ]]; then
  ok "card advertises ${SKILL_COUNT} skill(s)"
  jq -r '.skills[].name' "$BODY_FILE" | sed 's/^/         - /'
else
  fail "card advertises zero skills"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
  printf "\033[32mverify-a2a: all checks passed\033[0m\n"
  exit 0
else
  printf "\033[31mverify-a2a: one or more checks failed\033[0m\n"
  exit 1
fi
```

Make it executable: `chmod +x scripts/verify-a2a.sh`.

Optionally add to the root `Makefile`:

```makefile
verify-a2a:
	./scripts/verify-a2a.sh
```

---

## 4. Backend test strengthening

**File:** `backend/tests/api_tests/test_a2a.py`

**Update `test_agent_card_returns_minimum_a2a_fields`:**

```diff
 def test_agent_card_returns_minimum_a2a_fields(client: TestClient) -> None:
     with patch("protocols.a2a.list_marketplace", return_value=[]):
         resp = client.get("/.well-known/agent.json")
     assert resp.status_code == 200
     card = resp.json()
-    # A2A minimum fields.
-    for field in ("name", "description", "url", "version", "capabilities", "skills"):
+    # A2A minimum fields. protocolVersion is required by Discovery Engine /
+    # Gemini Enterprise validation — a missing one makes
+    # `agents-cli register-gemini-enterprise --registration-type a2a` fail
+    # with INVALID_ARGUMENT (real failure 2026-06-07).
+    for field in (
+        "protocolVersion",
+        "name",
+        "description",
+        "url",
+        "version",
+        "capabilities",
+        "skills",
+    ):
         assert field in card, f"card missing field: {field}"
     assert isinstance(card["skills"], list)
     assert isinstance(card["capabilities"], dict)
     assert card["capabilities"]["streaming"] is True
+    # Match the value we advertise in capabilities.extensions (a2a-v0.2).
+    assert card["protocolVersion"] == "0.2.0"
```

Run: `cd backend && uv run pytest tests/api_tests/test_a2a.py -x -q` — 13
tests must still pass.

---

## Friction-log entries (paste into `docs/learnings/template-protocols-friction.md`)

Append these as Friction 22 and 23 (or whatever number is next in the
template's friction log).

### Friction 22 — A2A card `url` leaks localhost behind a Next.js proxy

**Symptom**

Card discovery on the deployed app returns 200 with the right body, but the
`url` field reads `http://localhost:1956`. Result: A2A peers can discover the
agent but cannot invoke any skill, and Gemini Enterprise registration stores
an unreachable URL.

**Root cause**

The FastAPI backend has no way to know its public URL — it's a sidecar behind
the Next.js ingress. `backend/protocols/a2a.py` falls back to
`os.getenv("PUBLIC_BASE_URL", "http://localhost:1956")`; Cloud Run deploys
don't set the env var.

**Fix**

Rewrite the `url` field at the Next.js well-known route — the only layer
that knows the public origin. See section 2 above.

**Template improvement**

Ship the rewrite as the default well-known handler. Document the topology
constraint ("backend cannot know its own public URL through a proxy") in the
deployment guide.

---

### Friction 23 — A2A card missing `protocolVersion` fails Gemini Enterprise registration

**Symptom**

`agents-cli register-gemini-enterprise --registration-type a2a` rejects the
card with:

```
INVALID_ARGUMENT: required property 'protocolVersion' not found in object
```

**Root cause**

A2A spec v0.2+ requires a top-level `protocolVersion` field on the card.
Discovery Engine's validator enforces it. The template's `_build_card`
advertises `a2a-v0.2` in `capabilities.extensions` but does not emit the
top-level field.

**Fix**

Add `"protocolVersion": "0.2.0"` to the card root in
`backend/protocols/a2a.py:_build_card`. See section 1 above.

**Template improvement**

Bake this into the template. Add a backend test asserting it, and add a
`verify-a2a.sh` script (section 3) that catches this class of regression at
the integration level so the template doesn't have to wait for a Gemini
Enterprise round-trip to discover it next time.

---

## Verification

After applying all four changes and deploying:

```bash
# 1. Spec compliance — all green
./scripts/verify-a2a.sh

# 2. Regression coverage — green
cd backend && uv run pytest tests/api_tests/test_a2a.py -x -q

# 3. The real interop test (requires gcloud auth + a Discovery Engine app)
agents-cli register-gemini-enterprise \
  --registration-type a2a \
  --agent-card-url https://<your-fork-host>/.well-known/agent.json \
  --gemini-enterprise-app-id projects/<num>/locations/global/collections/default_collection/engines/<engine-id> \
  --display-name "<your agent>" \
  --deployment-target cloud_run
# → expect: HTTP 200 + registration confirmation. The agent now appears in
#   the Gemini Enterprise console as a registered tool.
```
