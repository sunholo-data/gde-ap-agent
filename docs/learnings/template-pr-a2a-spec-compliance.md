# Template PR brief — A2A spec compliance for Gemini Enterprise

> **For the template-repo agent on `sunholo-data/ai-protocol-platform`.**
> Three coupled bugs found while doing a real `agents-cli
> register-gemini-enterprise` registration against a Discovery Engine app on
> 2026-06-07. All three are pure A2A spec / proxy-topology bugs with zero
> AP-specific logic — every fork deploying the template behind a Next.js →
> FastAPI sidecar topology will hit them when they try to register with
> Gemini Enterprise. Each was caught only because we did a REAL registration
> against a live Discovery Engine app, not because static schema tests caught
> them — the template's existing tests passed all the way through.
>
> Source: `sunholo-data/gde-ap-agent` commits `236fdcb` (URL rewrite),
> `dbc5856` (protocolVersion + tests + probe), and (this round)
> `<next-sha>` (extensions[] descriptor shape).
>
> Companion friction-log entries: TODO — add Friction 22, 23, 24 below the
> existing entries in `docs/learnings/template-protocols-friction.md`.
> Content for those entries is at the bottom of this brief.

## TL;DR

Three changes + one new script + strengthened tests:

1. **Backend, card body** ([§1](#1-backend-protocolsa2apy)) — TWO related fixes:
   - Add `protocolVersion: "0.2.0"` to the card root.
   - Emit `capabilities.extensions` as A2A `AgentExtension` objects
     (`{uri, description, required}`), NOT bare strings. Header still
     carries bare IDs.
2. **Frontend proxy** ([§2](#2-frontend-well-known-agent-card-route)) —
   rewrite the card's `url` field to the public origin before returning it.
   The backend cannot know its public URL when it's a sidecar behind the
   Next.js ingress; this is the only layer that does.
3. **New script** ([§3](#3-new-scripts-verify-a2a-sh)) — 12-check spec
   compliance probe that catches all of the above + asserts capability
   negotiation works end-to-end.
4. **Strengthened tests** ([§4](#4-backend-test-strengthening)) — require
   `protocolVersion`, require `AgentExtension` shape, helper for extracting
   bare IDs out of descriptors so the rest of the suite stays readable.

**Critical insight for the template's test strategy:** Discovery Engine's
JSON-schema validator is the practical compliance backstop, NOT our own
test suite. All three bugs sailed past 13 passing pytest cases. The verify
script in §3 is a "would Discovery Engine accept this" probe and should be
the gate, not just `pytest` green.

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

### 1a. Add `protocolVersion` to the card root

**Where:** inside `_build_card()`, top of the returned dict (immediately
before `name`).

**Failure observed:**

```
INVALID_ARGUMENT: required property 'protocolVersion' not found in object
```

**Fix:**

```diff
 return {
+    # A2A wire-protocol version this card complies with. Required by
+    # the Discovery Engine / Gemini Enterprise card validator — a
+    # missing protocolVersion makes `agents-cli register-gemini-enterprise
+    # --registration-type a2a` fail with INVALID_ARGUMENT. Matches the
+    # `a2a-v0.2` value we advertise in `capabilities.extensions`.
+    "protocolVersion": "0.2.0",
     "name": os.getenv("A2A_AGENT_NAME", "..."),
     ...
 }
```

The value `"0.2.0"` is the A2A wire protocol version this card complies with.
It matches the `a2a-v0.2` URI we advertise in `capabilities.extensions`. Keep
them in sync — if the template ever moves to A2A 0.3+, both need to move
together. This is a top-level field on the card root, NOT inside
`capabilities`.

### 1b. Emit `capabilities.extensions` as `AgentExtension` objects, not strings

**Failure observed (after fixing 1a):**

```
INVALID_ARGUMENT: At /capabilities/extensions/0 of "a2ui-v0.9" -
unexpected instance type
```

The A2A v0.2 schema defines `capabilities.extensions[]` as an array of
`AgentExtension` objects, each with at least a `uri` field. The template
today emits bare strings — discovery clients reading the body get an ID
list, but Discovery Engine's strict validator rejects the card.

**Fix — collapse the parallel SUPPORTED_EXTENSIONS list into a single
info table, derive both the bare ID tuple AND a descriptor builder:**

```diff
-SUPPORTED_EXTENSIONS: tuple[str, ...] = (
-    "a2ui-v0.9",
-    "a2ui-basic-catalog-v0.9",
-    "a2ui-inline-pattern",
-    "a2ui-decoupled-pattern",
-    "a2a-v0.2",
-    "mcp-apps-v1",
-    "adk-workflow-v1",
-)
+# A2A extensions this agent supports. Single source of truth keyed by the
+# extension ID — the header uses just the IDs (per the integration guide),
+# the card body needs full AgentExtension descriptors (per A2A v0.2 schema,
+# enforced by Discovery Engine / Gemini Enterprise — emitting bare strings
+# fails registration with "unexpected instance type" at
+# /capabilities/extensions/N. Real failure 2026-06-07.)
+SUPPORTED_EXTENSION_INFO: dict[str, tuple[str, str]] = {
+    "a2ui-v0.9": (
+        "https://github.com/agentic-protocols/a2ui/blob/main/spec/v0.9.md",
+        "A2UI v0.9 declarative UI surfaces",
+    ),
+    "a2ui-basic-catalog-v0.9": (
+        "https://github.com/agentic-protocols/a2ui/blob/main/spec/basic-catalog-v0.9.md",
+        "A2UI BasicCatalog component set",
+    ),
+    "a2ui-inline-pattern": (
+        "https://github.com/agentic-protocols/a2ui/blob/main/spec/inline-pattern.md",
+        "A2UI inline-rendered surfaces (in-chat)",
+    ),
+    "a2ui-decoupled-pattern": (
+        "https://github.com/agentic-protocols/a2ui/blob/main/spec/decoupled-pattern.md",
+        "A2UI decoupled surfaces (separate pane)",
+    ),
+    "a2a-v0.2": (
+        "https://a2aproject.github.io/A2A/v0.2",
+        "A2A protocol v0.2 (this card complies with this version)",
+    ),
+    "mcp-apps-v1": (
+        "https://modelcontextprotocol.io/specification/draft/server/apps",
+        "MCP Apps v1 sandboxed iframe artefacts",
+    ),
+    "adk-workflow-v1": (
+        "https://google.github.io/adk-docs/agents/workflow-agents/",
+        "ADK workflow agents (SequentialAgent / ParallelAgent / LoopAgent)",
+    ),
+}
+
+# Canonical ID list — derived so any new extension only needs adding to
+# the info dict above (single source of truth, no parallel arrays to drift).
+# Public callers (negotiation, header echo) still use this as iteration order.
+SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(SUPPORTED_EXTENSION_INFO.keys())
+
+
+def _extension_descriptor(ext_id: str) -> dict[str, Any]:
+    """Wrap a supported extension ID as an A2A AgentExtension object.
+
+    Falls back to a synthetic urn:-style URI if the ID is missing from the
+    info table — defence in depth so a fork adding a new extension without
+    updating SUPPORTED_EXTENSION_INFO still produces a card that passes
+    schema validation rather than crashing the endpoint.
+    """
+    uri, description = SUPPORTED_EXTENSION_INFO.get(
+        ext_id, (f"urn:sunholo:a2a-extension:{ext_id}", ext_id),
+    )
+    return {"uri": uri, "description": description, "required": False}
```

**Then in `_build_card`'s capabilities block, swap the list comprehension:**

```diff
 "capabilities": {
     "streaming": True,
     "pushNotifications": False,
     "stateTransitionHistory": False,
-    "extensions": list(SUPPORTED_EXTENSIONS),
+    "extensions": [_extension_descriptor(ext) for ext in SUPPORTED_EXTENSIONS],
 },
```

**Forks that already extended `SUPPORTED_EXTENSIONS` need to migrate that
list into the new info dict.** The `_extension_descriptor` fallback (urn:-)
keeps them compliant if they forget the URI/description pair, but the
descriptor will be the bare ID under a urn: scheme — works for Discovery
Engine but not friendly to a human reading the card. Forks should pick
canonical URIs for their custom extensions.

**Important: the `X-A2A-Extensions` negotiation header still carries bare
IDs** (per the integration guide). Only the card body needs descriptors.
The existing `_parse_client_extensions` / `_negotiate_extensions` functions
don't change.

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
  # A2A v0.2 schema: capabilities.extensions[] must be AgentExtension objects
  # with a `uri` field — Discovery Engine / Gemini Enterprise rejects bare
  # strings with "unexpected instance type" (caught 2026-06-07).
  ALL_OBJECTS=$(jq -r '.capabilities.extensions | map(type == "object" and has("uri")) | all' "$BODY_FILE")
  if [[ "$ALL_OBJECTS" == "true" ]]; then
    URIS=$(jq -r '.capabilities.extensions | map(.uri) | join(", ")' "$BODY_FILE")
    ok "capabilities.extensions advertises ${EXT_COUNT} AgentExtension descriptor(s)"
    info "uris: ${URIS}"
  else
    fail "capabilities.extensions[] entries are not AgentExtension objects with .uri"
    fail "  → Gemini Enterprise registration will reject with 'unexpected instance type'"
  fi
  if jq -e '.capabilities.extensions | map(.uri // "") | any(. | endswith("a2a/v0.2") or contains("a2a-v0.2"))' "$BODY_FILE" >/dev/null; then
    ok "advertises an A2A v0.2 extension descriptor"
  else
    fail "capabilities.extensions does not include an A2A v0.2 entry"
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

### 4a. Add a `_extension_ids` helper (top of file, after imports)

The old assertions assumed extensions were bare strings. After §1b they're
`AgentExtension` objects. Add a helper that recovers the bare IDs via
reverse-lookup in `SUPPORTED_EXTENSION_INFO`, then convert every old
`assert "ext-id" in caps["extensions"]` to use it. Centralising means
the helper is the only thing that touches the schema directly — a v0.3
shape change edits one place.

```python
def _extension_ids(card: dict[str, Any]) -> list[str]:
    """Extract bare extension IDs from a card's capabilities.extensions.

    A2A v0.2 schema makes these AgentExtension objects ({uri, description,
    required}); we reverse-lookup each URI in SUPPORTED_EXTENSION_INFO to
    recover the canonical IDs the rest of the codebase uses. Centralised so
    a schema bump (v0.3 etc.) only edits this helper.
    """
    from protocols.a2a import SUPPORTED_EXTENSION_INFO

    uri_to_id = {uri: ext_id for ext_id, (uri, _) in SUPPORTED_EXTENSION_INFO.items()}
    return [uri_to_id.get(ext["uri"], ext["uri"]) for ext in card["capabilities"]["extensions"]]
```

### 4b. Strengthen `test_agent_card_returns_minimum_a2a_fields`

```diff
-    for field in ("name", "description", "url", "version", "capabilities", "skills"):
+    # protocolVersion required by Discovery Engine — missing one makes
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
+    assert card["protocolVersion"] == "0.2.0"
```

### 4c. Reshape `test_agent_card_advertises_extensions_on_body`

Assert each entry is an `AgentExtension` object (`{uri, ...}`), then use the
helper for the membership checks:

```diff
     assert "extensions" in caps, "capabilities.extensions missing from card"
     assert isinstance(caps["extensions"], list)
-    # The four canonical A2UI extensions from the integration guide.
-    for required in (
-        "a2ui-v0.9",
-        ...
-    ):
-        assert required in caps["extensions"], f"extension missing: {required}"
+    # Each entry must be a full AgentExtension descriptor (A2A v0.2 schema —
+    # Discovery Engine rejects bare strings).
+    for ext in caps["extensions"]:
+        assert isinstance(ext, dict), f"extension entry must be an object, got {type(ext).__name__}"
+        assert "uri" in ext, f"AgentExtension missing required `uri`: {ext!r}"
+    ids = _extension_ids(resp.json())
+    for required in (
+        "a2ui-v0.9",
+        "a2ui-basic-catalog-v0.9",
+        "a2ui-inline-pattern",
+        "a2ui-decoupled-pattern",
+    ):
+        assert required in ids, f"extension missing: {required}"
```

### 4d. Update header/body parity, adk-workflow, intersection tests

All three tests assumed `caps["extensions"]` was a list of strings. Swap to
the helper:

```diff
-    body = resp.json()["capabilities"]["extensions"]
-    assert echoed == body, "header set must match body set when no negotiation occurred"
+    body_ids = _extension_ids(resp.json())
+    assert echoed == body_ids, "header IDs must match body IDs when no negotiation occurred"

-    extensions = resp.json()["capabilities"]["extensions"]
-    assert "adk-workflow-v1" in extensions, ...
+    ids = _extension_ids(resp.json())
+    assert "adk-workflow-v1" in ids, ...

-    body = resp.json()["capabilities"]["extensions"]
-    assert "a2ui-decoupled-pattern" in body, ...
+    body_ids = _extension_ids(resp.json())
+    assert "a2ui-decoupled-pattern" in body_ids, ...
```

### 4e. Reshape the schema validator (in `_assert_card_matches_a2a_schema`)

The validator's `extensions` block treats entries as strings. Update to
require object-with-`uri`:

```diff
-    # Optional but spec-recognised: capabilities.extensions (list of strings).
+    # Optional but spec-recognised: capabilities.extensions — A2A v0.2 schema
+    # requires a list of AgentExtension objects each with a `uri` field
+    # (Discovery Engine enforces this — bare strings get
+    # "unexpected instance type" rejections).
     if "extensions" in caps:
         if not isinstance(caps["extensions"], list):
             errors.append("capabilities.extensions: expected list")
         else:
             for i, ext in enumerate(caps["extensions"]):
-                if not isinstance(ext, str):
-                    errors.append(f"capabilities.extensions[{i}]: expected str, got {type(ext).__name__}")
+                if not isinstance(ext, dict):
+                    errors.append(f"capabilities.extensions[{i}]: expected AgentExtension object, got {type(ext).__name__}")
+                elif "uri" not in ext:
+                    errors.append(f"capabilities.extensions[{i}]: AgentExtension missing required `uri`")
+                elif not isinstance(ext["uri"], str):
+                    errors.append(f"capabilities.extensions[{i}].uri: expected str, got {type(ext['uri']).__name__}")
```

Run: `cd backend && uv run pytest tests/api_tests/test_a2a.py -x -q` — 13
tests must still pass.

---

## Friction-log entries (paste into `docs/learnings/template-protocols-friction.md`)

Append these as Friction 22, 23, and 24 (or whatever number is next in the
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

### Friction 24 — A2A card `capabilities.extensions` must be `AgentExtension` objects, not strings

**Symptom**

`agents-cli register-gemini-enterprise --registration-type a2a` rejects the
card (after fixing Friction 23) with:

```
INVALID_ARGUMENT: At /capabilities/extensions/0 of "a2ui-v0.9" -
unexpected instance type
```

**Root cause**

A2A spec v0.2 defines `capabilities.extensions[]` as an array of
`AgentExtension` objects, each with `uri` (required), `description`
(optional), `required` (optional). The template emits bare string IDs —
permissive A2A clients tolerate it, but Discovery Engine's strict schema
validator rejects the card before any agent ever runs.

The `X-A2A-Extensions` negotiation header still uses bare IDs (the
integration guide is explicit about this); only the card body needs
descriptors.

**Fix**

Replace the single `SUPPORTED_EXTENSIONS` tuple with a `SUPPORTED_EXTENSION_INFO`
dict keyed by ID, valued as `(uri, description)` tuples. Derive
`SUPPORTED_EXTENSIONS = tuple(SUPPORTED_EXTENSION_INFO.keys())` so the
single source of truth fans out to both the header (bare IDs) and the
body (descriptors via `_extension_descriptor`). See §1b above.

**Template improvement**

Ship the info-dict pattern with canonical URIs for every extension the
template advertises. Add a backend test asserting `AgentExtension` shape
plus the new `verify-a2a.sh` check that fails fast on bare-string emission.
Critical: do this BEFORE the next fork's first Gemini Enterprise
registration attempt — the failure mode is silent (discovery looks fine,
local tests pass) until the registration HTTP 400 returns.

---

## §5 (added 2026-06-07) — Strict A2A `message/send` invocation bridge

> Brings the template from "A2A-discovery-compliant" to "A2A-invocation-compliant".
> Closes the gap that the simulate-a2a-peer.py probe surfaces at Step 4 (HTTP 405).
> Implementation in `Aitana-Labs/gde-ap-agent` commits abe9bc9 (M1 bridge),
> 0b2d59e (M2 auth + tests), 9cdc629 (M3 cloudbuild + probes).
>
> **Design rationale + tradeoffs**: see
> `docs/design/forks/gde-ap-agent/v0.1.0/a2a-message-send-bridge.md` — captures
> all six surface decisions (URL mount, card authoring, skill selection,
> streaming overlap, sessions, auth) with explicit alternatives. Forks should
> read that doc before touching this code.

### 5a. The wrinkle that took ~90 min to debug

`google.adk.a2a.utils.agent_to_a2a.to_a2a()` returns a Starlette app whose
A2A routes are registered via a **lifespan event** — not at construction
time. When that app is mounted as a sub-app on FastAPI
(`fastapi_app.mount("/a2a", to_a2a(...))`), **Starlette does not propagate
lifespan to mounted sub-apps**. The lifespan never fires, the routes never
register, and every request to `/a2a/*` returns 404. ADK's `to_a2a` works
as the root app (uvicorn enters its lifespan); it does NOT work as a sub-app
on FastAPI.

**Fix**: don't use `to_a2a()` directly. Replicate its body synchronously
using the `a2a-sdk` building blocks ADK itself uses (`A2AStarletteApplication`,
`DefaultRequestHandler`, `InMemoryTaskStore`, `InMemoryPushNotificationConfigStore`,
ADK's `A2aAgentExecutor`). All routes register at construction time, mounting
works as expected.

### 5b. Backend — `backend/protocols/a2a_invocation.py` (new ~200 LOC)

Three responsibilities:
1. `build_a2a_app(agent, base_url) -> Starlette` — constructs the A2A
   sub-app synchronously, hands ADK's `A2aAgentExecutor` our pre-built
   `Runner` (so sessions and observability share the AG-UI surface's
   storage), passes our hand-built `AgentCard` from `_build_card_model`
   (so the mounted card and the root discovery card stay byte-identical).
2. `A2AAuthMiddleware` — Starlette `BaseHTTPMiddleware` that runs
   `get_current_user` on invocation paths and returns a JSON-RPC 2.0
   error envelope on auth failure (not an HTML 401, which a strict A2A
   client cannot parse). Discovery paths under the mount
   (`/.well-known/agent.json`, `/.well-known/agent-card.json`) skip auth
   per A2A spec.
3. Gated by env `A2A_INVOCATION_REQUIRE_AUTH` (default `true`). Forks
   that integrate with peer-agent routing flows that don't carry Bearer
   tokens (some Gemini Enterprise modes inject service identity differently)
   can set `false` and rely on network-level isolation.

Key function signatures (copy verbatim into the template):

```python
# Synchronous A2A surface construction — the lifespan workaround.
def build_a2a_app(agent: BaseAgent, base_url: str) -> Starlette:
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import (
        InMemoryPushNotificationConfigStore,
        InMemoryTaskStore,
    )
    from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
    from starlette.applications import Starlette

    from protocols.a2a import _build_card_model

    agent_card = _build_card_model(base_url)
    runner = _build_runner(agent)  # uses get_session_service / memory / artifact singletons

    executor = A2aAgentExecutor(runner=runner)
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        push_config_store=InMemoryPushNotificationConfigStore(),
    )
    a2a_starlette = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    a2a_app = Starlette()
    a2a_starlette.add_routes_to_app(a2a_app)  # synchronous, NOT via lifespan
    a2a_app.add_middleware(A2AAuthMiddleware)
    return a2a_app
```

The auth middleware returns proper JSON-RPC envelopes:

```python
class A2AAuthMiddleware(BaseHTTPMiddleware):
    _UNAUTH_PATHS = ("/.well-known/agent.json", "/.well-known/agent-card.json")

    async def dispatch(self, request, call_next):
        if not _auth_required():
            return await call_next(request)
        if request.url.path in self._UNAUTH_PATHS:
            return await call_next(request)

        from auth import get_current_user
        try:
            request.state.user = await get_current_user(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32000, "message": str(exc.detail)},
                },
            )
        return await call_next(request)
```

### 5c. Backend — `backend/protocols/a2a.py` card-builder split

Discovery card and ADK-mounted card must agree, so split the existing
`_build_card` into two variants sharing the same data:

```python
A2A_INVOCATION_PATH = "/a2a"

def _build_card_dict(base_url: str) -> dict[str, Any]:
    # ... existing body ...
    return {
        # ...
        "url": f"{base_url.rstrip('/')}{A2A_INVOCATION_PATH}",  # not bare base_url
        # ...
    }

def _build_card_model(base_url: str) -> "AgentCard":
    """ADK AgentCard pydantic model — for to_a2a(agent_card=)."""
    from a2a.types import AgentCard
    return AgentCard.model_validate(_build_card_dict(base_url))

# Back-compat alias for callers that still import _build_card
_build_card = _build_card_dict
```

The dict variant is what the well-known FastAPI route returns on the
wire; the model variant is what gets passed to `A2AStarletteApplication`.

### 5d. FastAPI mount (in `backend/fast_api_app.py`)

```python
if os.environ.get("ENABLE_A2A_INVOCATION", "false").lower() in ("true", "1", "yes"):
    try:
        from auth.firebase_auth import User
        from auth.access_context import AccessContext
        from adk.agent import create_agent
        from skills.skill_config import find_by_name
        from protocols.a2a import A2A_INVOCATION_PATH
        from protocols.a2a_invocation import build_a2a_app

        _skill = find_by_name("ap-orchestrator")  # or your fork's entry skill
        if _skill is not None:
            _system_user = User(uid="a2a-public-peer", email="", domain="")
            _agent = create_agent(_skill, _system_user, access_context=AccessContext(uid=_system_user.uid))
            _base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:1956")
            app.mount(A2A_INVOCATION_PATH, build_a2a_app(_agent, _base_url))
    except Exception:
        logger.exception("Failed to mount A2A invocation surface — continuing without it")
```

### 5e. Tests — `backend/tests/api_tests/test_a2a_invocation.py` (new)

Six tests, mix of pure card-shape + middleware-isolation + FastAPI-mount
integration. The integration test is the one that catches the
lifespan-on-mount bug:

```python
def test_build_a2a_app_returns_mountable_starlette_app(monkeypatch):
    monkeypatch.setenv("A2A_INVOCATION_REQUIRE_AUTH", "false")
    from google.adk.agents import LlmAgent
    from protocols.a2a_invocation import build_a2a_app

    agent = LlmAgent(name="probe", model="gemini-2.5-flash", description="...", instruction="...")
    a2a_app = build_a2a_app(agent, "https://example.com")

    fastapi_app = FastAPI()
    fastapi_app.mount("/a2a", a2a_app)
    client = TestClient(fastapi_app)

    resp = client.get("/a2a/.well-known/agent.json")
    assert resp.status_code == 200  # ← this is the bug check
    assert resp.json()["url"] == "https://example.com/a2a"
```

Without the synchronous `add_routes_to_app` call in `build_a2a_app`, this
returns 404 instead of 200. The other 5 tests cover the card-URL regression
guard, dict/model byte-equality, JSON-RPC-error-envelope on missing Bearer,
discovery-paths-skip-auth, and auth-disabled pass-through.

### 5f. Cloud Build deploy (in `backend/cloudbuild.yaml`)

Three env vars to add:

```yaml
- '--set-env-vars=ENABLE_A2A_INVOCATION=true'
- '--set-env-vars=PUBLIC_BASE_URL=https://<your-cloud-run-host>'
- '--set-env-vars=A2A_INVOCATION_REQUIRE_AUTH=true'  # or false depending on peer auth
```

`PUBLIC_BASE_URL` is what the ADK-mounted card at
`/a2a/.well-known/agent-card.json` advertises as the `url` field. The
root `/.well-known/agent.json` is still URL-rewritten by the Next.js
proxy from the incoming request's origin (per §2 above), so the
discovery card stays correct regardless. Setting `PUBLIC_BASE_URL`
keeps the two cards consistent.

---

### Friction 25 — `to_a2a` Starlette app loses lifespan when mounted on FastAPI

**Symptom**

`fastapi_app.mount("/a2a", to_a2a(agent))` doesn't error at boot but
every request to `/a2a/*` (including `/a2a/.well-known/agent.json`)
returns 404. ADK's docstring suggests the mount should work.

**Root cause**

`to_a2a` uses a Starlette lifespan event to call `setup_a2a()` which
creates the `A2AStarletteApplication` and calls `add_routes_to_app(app)`.
Starlette does NOT propagate lifespan to mounted sub-apps, so the
lifespan never fires when the app is a sub-mount on FastAPI. The routes
never register.

**Fix**

Don't use `to_a2a()` directly when mounting. Replicate its setup
synchronously using the same `a2a-sdk` building blocks
(`A2AStarletteApplication`, `DefaultRequestHandler`,
`A2aAgentExecutor`). See §5b above for the code.

**Template improvement**

Either (a) file an ADK issue requesting a synchronous variant of
`to_a2a`, or (b) ship the synchronous helper as a template-level utility
that every fork can call. We chose (b) because the synchronous pattern
is small (~20 lines), composable, and doesn't depend on ADK accepting
upstream changes.

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
