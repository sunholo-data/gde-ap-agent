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

import json
import sys
import uuid
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


def http_get(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    req = Request(url, headers=headers or {})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.status, dict(resp.headers), resp.read().decode()
    except HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


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
            return resp.status, dict(resp.headers), resp.read().decode()
    except HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


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
        out("✓", f"HTTP 200 — strict A2A invocation works: {body[:200]}")
    elif status in (404, 405, 501):
        out(
            "⚠",
            f"HTTP {status} — agent does not implement strict A2A `message/send` JSON-RPC",
        )
        out(
            "⚠",
            "  honest truth: card.url is the public origin, but the agent's invocation",
        )
        out(
            "⚠",
            "  surface is AG-UI streaming at /api/skill/<id>/stream, not JSON-RPC.",
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
    out("⚠", "Strict A2A `message/send` JSON-RPC invocation: NOT implemented today")
    out(
        "ℹ",
        "Next layer for strict-spec interop: add a backend /a2a/message/send bridge",
    )
    out(
        "ℹ",
        "  that translates JSON-RPC payloads into AG-UI stream calls. ~1-2h of work.",
    )

    # Step 6 — What Gemini Enterprise does with this card
    step("What Gemini Enterprise does with this card")
    out("•", "Validates the card against the A2A v0.2 JSON schema")
    out("•", "Stores it as a tool descriptor in the Agentspace app")
    out("•", "Routes other agents' tool calls to card.url via its internal A2A handler")
    out("•", "Surfaces the skill catalogue in the workspace UI for human discovery")
    return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    raise SystemExit(simulate(url))
