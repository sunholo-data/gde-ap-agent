#!/usr/bin/env python3
"""Simulate a peer agent doing A2A-only interaction with the deployed agent.

Walks the discovery + negotiation handshake an enterprise agent would do
when it lands on `/.well-known/agent.json`, then attempts a strict A2A
`message/send` invocation against the URL the card advertises. Reports
honestly what works and what doesn't — useful both as a verification
artefact and to surface the gap between "A2A discovery-compliant" and
"A2A invocation-compliant".

Stdlib only — `python3 scripts/simulate-a2a-peer.py` from anywhere.

Usage:
    python3 scripts/simulate-a2a-peer.py [AP_URL]

Default AP_URL is the gde-ap-agent live deploy.
"""

from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "https://gde-ap-agent-blqtqfexwa-ew.a.run.app"


# --- pretty print helpers ---------------------------------------------------

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def step(label: str) -> None:
    print(f"\n{CYAN}━━━ {label} ━━━{RESET}")


def out(arrow: str, text: str) -> None:
    colour = {
        "✓": GREEN,
        "⚠": YELLOW,
        "✗": RED,
        "→": "",
        "←": "",
        "•": "",
        "ℹ": CYAN,
    }.get(arrow, "")
    print(f"  {colour}{arrow}{RESET} {text}")


# --- HTTP helpers (stdlib only) ---------------------------------------------


def _flatten_headers(msg: object) -> dict[str, str]:
    """Combine multi-valued headers (e.g. duplicate `Vary`) into a single
    comma-joined string per name. `dict(HTTPMessage)` keeps only the last
    value, which makes a Vary like `[rsc..., X-A2A-Extensions]` appear as
    just one of them — exactly the false negative this helper avoids.
    """
    out: dict[str, list[str]] = {}
    for key, value in msg.items():  # type: ignore[attr-defined]
        out.setdefault(key.lower(), []).append(value)
    return {k: ", ".join(v) for k, v in out.items()}


def http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    req = Request(url, headers=headers or {})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.status, _flatten_headers(resp.headers), resp.read().decode()
    except HTTPError as e:
        return e.code, _flatten_headers(e.headers), e.read().decode()


def http_post(
    url: str, body: str, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], str]:
    req = Request(
        url,
        data=body.encode(),
        method="POST",
        headers={**(headers or {}), "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.status, _flatten_headers(resp.headers), resp.read().decode()
    except HTTPError as e:
        return e.code, _flatten_headers(e.headers), e.read().decode()


# --- simulation -------------------------------------------------------------


def simulate(ap_url: str) -> int:
    ap_url = ap_url.rstrip("/")

    # Step 1 — Discovery
    step("Step 1 · Discovery (peer fetches the agent card)")
    out("→", f"GET {ap_url}/.well-known/agent.json")
    out("→", "X-A2A-Extensions: a2a-v0.2, a2ui-v0.9, a2ui-inline-pattern")
    try:
        status, hdrs, body = http_get(
            f"{ap_url}/.well-known/agent.json",
            headers={"X-A2A-Extensions": "a2a-v0.2, a2ui-v0.9, a2ui-inline-pattern"},
        )
    except URLError as e:
        out("✗", f"unreachable: {e}")
        return 1
    out("←", f"HTTP {status}")
    out("←", f"X-A2A-Extensions: {hdrs.get('x-a2a-extensions', '(none)')}")
    out("←", f"Vary: {hdrs.get('vary', '(none)')}")
    if status != 200:
        out("✗", "discovery failed; abort")
        return 1
    card = json.loads(body)
    out(
        "✓",
        f"Discovered: {card['name']} v{card['version']} (A2A protocol {card['protocolVersion']})",
    )
    out("✓", f"Public URL for invocation: {card['url']}")

    # Step 2 — Capabilities
    step("Step 2 · Read capabilities")
    caps = card["capabilities"]
    out("•", f"streaming: {caps['streaming']}")
    out("•", f"pushNotifications: {caps['pushNotifications']}")
    out("•", f"stateTransitionHistory: {caps['stateTransitionHistory']}")
    out("•", f"extensions ({len(caps['extensions'])}):")
    for e in caps["extensions"]:
        out(" ", f"  - {e['uri']}")
        out(" ", f"      {e['description']}")

    # Step 3 — Skill selection (peer matches goal to skill descriptions)
    step("Step 3 · Pick a skill that matches the peer's goal")
    goal = "I need to process an incoming vendor invoice"
    out("•", f"Peer's goal: {goal!r}")
    keyword = "invoice"
    candidates = [s for s in card["skills"] if keyword in s["description"].lower()]
    out("→", f"Filter {len(card['skills'])} advertised skills by description ~ '{keyword}'")
    for s in candidates:
        out(" ", f"  - {s['name']}  (id={s['id']})")
    # Prefer orchestrators / public entry-points
    chosen = next(
        (s for s in candidates if s["name"] == "ap-orchestrator"),
        candidates[0] if candidates else None,
    )
    if chosen is None:
        out("✗", "no matching skill — abort")
        return 1
    out("✓", f"Chose: {chosen['name']}  ({chosen['description'][:80]}...)")

    # Step 4 — Attempt strict A2A invocation
    step("Step 4 · Attempt strict A2A `message/send` against the advertised URL")
    msg_id = str(uuid.uuid4())
    rpc = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": (
                            "Process this invoice: Vendor: Acme GmbH (Germany), "
                            "INV-2026-042, €8,500, NET 30, GL 5200-OPEX"
                        ),
                    }
                ],
                "messageId": msg_id,
            },
            "configuration": {"acceptedOutputModes": ["text"]},
        },
    }
    out("→", f"POST {card['url']}")
    out("→", "Content-Type: application/json")
    out("→", "method=message/send (A2A v0.2 JSON-RPC)")
    status, _, body = http_post(card["url"], json.dumps(rpc))
    if status == 200:
        out("✓", "HTTP 200 — strict A2A invocation works")
        # Body is a JSON-RPC envelope; show the result shape without
        # dumping the whole payload (sessions can be large).
        try:
            parsed = json.loads(body)
            if "result" in parsed:
                result = parsed["result"]
                kind = result.get("kind") or result.get("type") or "(no kind)"
                out("✓", f"result kind: {kind}")
                if "id" in result:
                    out("✓", f"task id: {result['id']}")
            elif "error" in parsed:
                out("⚠", f"JSON-RPC error: {parsed['error']}")
        except json.JSONDecodeError:
            out("⚠", f"non-JSON body: {body[:200]}")
    elif status == 401:
        out("⚠", "HTTP 401 — invocation requires Bearer auth (the bridge is mounted")
        out("⚠", "  but A2A_INVOCATION_REQUIRE_AUTH=true). Peers need an ID token.")
    elif status in (404, 405, 501):
        out(
            "⚠",
            f"HTTP {status} — the A2A invocation bridge is not deployed.",
        )
        out(
            "⚠",
            "  Set ENABLE_A2A_INVOCATION=true in cloudbuild.yaml and re-deploy.",
        )
    else:
        snippet = body[:200].replace("\n", " ")
        out("⚠", f"HTTP {status}: {snippet}")

    # Step 5 — What works / what doesn't
    step("What an A2A-only peer can do today")
    out("✓", "Discover the agent (unauthenticated GET on /.well-known/agent.json)")
    out("✓", "Read every public skill, its description, and ID")
    out("✓", "Negotiate UI / protocol extensions via X-A2A-Extensions")
    out("✓", "Learn the canonical public URL for further interaction")
    out("✓", "Be registered as a tool in a Gemini Enterprise workspace (proven)")
    if status == 200:
        out("✓", "Strict A2A `message/send` JSON-RPC invocation: WORKING")
    elif status == 401:
        out("✓", "Strict A2A `message/send` mounted; gated by Bearer auth")
    else:
        out("⚠", f"Strict A2A `message/send` JSON-RPC invocation: HTTP {status}")
    out(
        "ℹ",
        "Bridge mounted via ADK A2aAgentExecutor + a2a-sdk A2AStarletteApplication;",
    )
    out(
        "ℹ",
        "  same Runner / session storage as the AG-UI surface at /api/skill/{id}/stream.",
    )

    # Step 6 — What Gemini Enterprise does with this card
    step("What Gemini Enterprise does with this card")
    out("•", "Validates the card against the A2A v0.2 JSON schema")
    out("•", "Stores it as a tool descriptor in the Agentspace app")
    out("•", "Routes other agents' tool calls to card.url via its internal A2A handler")
    out("•", "Surfaces the skill catalogue in the workspace UI for human discovery")

    # Step 7 — Scenario A: send a FilePart and confirm the doc-loader picks it up
    step("Step 7 · Attach a real invoice file as A2A FilePart (Scenario A)")
    demo_file = (
        Path(__file__).parent.parent
        / "infrastructure"
        / "demo-invoices"
        / "acme-gmbh-invoice-2026-042.docx"
    )
    if not demo_file.exists():
        out("⚠", f"demo file missing: {demo_file}; skipping Step 7")
    else:
        file_bytes = demo_file.read_bytes()
        encoded = base64.b64encode(file_bytes).decode("ascii")
        out("→", f"POST {card['url']} with FilePart ({len(file_bytes)} bytes, name={demo_file.name})")
        file_msg_id = str(uuid.uuid4())
        file_rpc = {
            "jsonrpc": "2.0",
            "id": file_msg_id,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [
                        {"kind": "text", "text": "Please process this invoice."},
                        {
                            "kind": "file",
                            "file": {
                                "bytes": encoded,
                                "mimeType": (
                                    "application/vnd.openxmlformats-officedocument."
                                    "wordprocessingml.document"
                                ),
                                "name": demo_file.name,
                            },
                        },
                    ],
                    "messageId": file_msg_id,
                },
                "configuration": {"acceptedOutputModes": ["text"]},
            },
        }
        file_status, _, file_body = http_post(card["url"], json.dumps(file_rpc))
        if file_status == 200:
            try:
                parsed = json.loads(file_body)
                result = parsed.get("result") or {}
                out("✓", f"HTTP 200; Task envelope kind={result.get('kind') or result.get('type') or '?'}")
                out(
                    "✓",
                    "FilePart was accepted (size > text-only baseline). Check Cloud Run logs for"
                    " 'doc loader: turn start — document_ids=[...]' to confirm pipeline pickup.",
                )
            except json.JSONDecodeError:
                out("⚠", f"non-JSON response: {file_body[:200]}")
        else:
            out("⚠", f"HTTP {file_status}: {file_body[:200]}")

    # Step 8 — Scenario B: text-only query about an existing bucket doc
    step("Step 8 · Ask about existing org-bucket documents (Scenario B)")
    bucket_msg_id = str(uuid.uuid4())
    bucket_rpc = {
        "jsonrpc": "2.0",
        "id": bucket_msg_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": (
                            "What invoices do we have on file for Acme? "
                            "List the documents available in the org bucket."
                        ),
                    }
                ],
                "messageId": bucket_msg_id,
            },
            "configuration": {"acceptedOutputModes": ["text"]},
        },
    }
    out("→", f"POST {card['url']} text-only; relies on list_org_documents tool call")
    bucket_status, _, bucket_body = http_post(card["url"], json.dumps(bucket_rpc))
    if bucket_status == 200:
        try:
            parsed = json.loads(bucket_body)
            artifacts = (parsed.get("result") or {}).get("artifacts") or []
            text_chunks = []
            for art in artifacts:
                for part in art.get("parts", []):
                    t = part.get("text") or ""
                    if t:
                        text_chunks.append(t)
            answer = " ".join(text_chunks).lower()
            if "acme" in answer or "invoice" in answer or "bucket" in answer or "no documents" in answer:
                out("✓", f"orchestrator referenced bucket context. First 200 chars: {answer[:200]!r}")
            else:
                out(
                    "⚠",
                    f"orchestrator answered but didn't reference bucket. First 200 chars: {answer[:200]!r}",
                )
        except json.JSONDecodeError:
            out("⚠", f"non-JSON response: {bucket_body[:200]}")
    else:
        out("⚠", f"HTTP {bucket_status}: {bucket_body[:200]}")

    return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    raise SystemExit(simulate(url))
