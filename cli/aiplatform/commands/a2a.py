"""`aiplatform a2a` — interact with the deployed A2A surface.

Two subcommands today:

  `aiplatform a2a invoke <url> --text "..." [--file <path>]`
      POST a `message/send` JSON-RPC payload to the agent's `card.url`.
      File argument is base64-encoded locally and sent as a `FilePart`
      (so peer agents and humans share the same wire shape). Useful for
      reproducing peer-agent invocations from a laptop without curling
      JSON by hand.

  `aiplatform a2a card <url>`
      Fetch and pretty-print the agent card. Highlights protocolVersion,
      defaultInputModes, capabilities.extensions, and the skill count.

These commands talk to the agent's PUBLIC URL (not the proxied
/api/proxy path) — A2A is meant to be reachable by external peers
through the well-known card, so the CLI mirrors that surface.

The bucket-binding subcommand was scoped in the A2A-FILES design doc
but landed as a per-deploy env var (A2A_AGENT_DOCUMENTS_BUCKET) once
Discovery Engine rejected custom metadata fields. Binding inspection
is therefore a deploy concern, not a CLI command. If multi-tenant
per-call binding ships in a follow-up sprint, the CLI surface returns
here as `aiplatform a2a bucket bind/show`.
"""

from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import click


def _http_post(url: str, body: dict, *, timeout: int = 60) -> tuple[int, str]:
    """POST JSON, return (status, body_text). Catches HTTPError so we can
    show the server's JSON-RPC error envelope rather than masking it."""
    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def _http_get(url: str, *, timeout: int = 15) -> tuple[int, str]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


@click.group()
def a2a() -> None:
    """Probe and invoke A2A-compliant agents (Gemini Enterprise peers, etc.)."""


@a2a.command()
@click.argument("agent_url")
def card(agent_url: str) -> None:
    """Fetch the agent card at AGENT_URL/.well-known/agent.json.

    AGENT_URL: the public base URL (no trailing slash), e.g.
    https://gde-ap-agent-blqtqfexwa-ew.a.run.app
    """
    url = agent_url.rstrip("/") + "/.well-known/agent.json"
    status, body = _http_get(url)
    if status != 200:
        click.secho(f"HTTP {status}", fg="red", err=True)
        click.echo(body, err=True)
        sys.exit(1)
    try:
        c = json.loads(body)
    except json.JSONDecodeError as exc:
        click.secho(f"non-JSON response: {exc}", fg="red", err=True)
        sys.exit(1)

    click.echo(f"{click.style('name', fg='cyan')}            {c.get('name', '?')}")
    click.echo(f"{click.style('protocolVersion', fg='cyan')} {c.get('protocolVersion', '?')}")
    click.echo(f"{click.style('url', fg='cyan')}             {c.get('url', '?')}")
    click.echo(f"{click.style('version', fg='cyan')}         {c.get('version', '?')}")

    modes = c.get("defaultInputModes") or []
    click.echo(f"{click.style('defaultInputModes', fg='cyan')} ({len(modes)}):")
    for m in modes:
        click.echo(f"  - {m}")

    caps = c.get("capabilities") or {}
    exts = caps.get("extensions") or []
    click.echo(f"{click.style('capabilities.extensions', fg='cyan')} ({len(exts)}):")
    for e in exts:
        uri = e.get("uri") if isinstance(e, dict) else str(e)
        click.echo(f"  - {uri}")

    skills = c.get("skills") or []
    click.echo(f"{click.style('skills', fg='cyan')} ({len(skills)}):")
    for s in skills:
        click.echo(f"  - {s.get('name', '?')}  ({s.get('id', '?')})")


@a2a.command()
@click.argument("agent_url")
@click.option("--text", default=None, help="Text part of the message.")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Local file to attach as a FilePart (base64-encoded inline).",
)
@click.option("--mime", default=None, help="Override MIME type (auto-detected from suffix when omitted).")
@click.option("--json-output", is_flag=True, help="Print raw JSON-RPC response only.")
def invoke(
    agent_url: str,
    text: str | None,
    file_path: Path | None,
    mime: str | None,
    json_output: bool,
) -> None:
    """Send a `message/send` JSON-RPC to AGENT_URL with optional text/file parts.

    AGENT_URL: the public A2A invocation endpoint. Usually the agent
    card's `url` field (e.g. https://gde-ap-agent-.../a2a).

    Examples:

        aiplatform a2a invoke https://example.run.app/a2a --text "hi"

        aiplatform a2a invoke https://example.run.app/a2a \\
            --text "Process this invoice" \\
            --file infrastructure/demo-invoices/acme-gmbh-invoice-2026-042.docx

        aiplatform a2a invoke https://example.run.app/a2a --file invoice.pdf --json-output
    """
    if text is None and file_path is None:
        click.secho("Provide --text and/or --file.", fg="red", err=True)
        sys.exit(1)

    parts: list[dict] = []
    if text is not None:
        parts.append({"kind": "text", "text": text})

    if file_path is not None:
        data = file_path.read_bytes()
        resolved_mime = mime or _guess_mime_from_suffix(file_path.suffix.lower())
        parts.append(
            {
                "kind": "file",
                "file": {
                    "bytes": base64.b64encode(data).decode("ascii"),
                    "mimeType": resolved_mime,
                    "name": file_path.name,
                },
            }
        )

    msg_id = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": parts,
                "messageId": msg_id,
            },
            "configuration": {"acceptedOutputModes": ["text"]},
        },
    }

    status, body = _http_post(agent_url, payload)

    if json_output:
        click.echo(body)
        if status != 200:
            sys.exit(1)
        return

    if status != 200:
        click.secho(f"HTTP {status}", fg="red", err=True)
        click.echo(body, err=True)
        sys.exit(1)

    # Pretty-print the agent's text artifacts.
    try:
        resp = json.loads(body)
    except json.JSONDecodeError:
        click.echo(body)
        return

    result = resp.get("result") or {}
    task_id = result.get("id") or result.get("taskId") or "?"
    click.secho(f"task id: {task_id}", fg="green")
    artifacts = result.get("artifacts") or []
    if not artifacts:
        click.echo("(no artifacts in response)")
        click.echo(json.dumps(result, indent=2))
        return
    for art in artifacts:
        for part in art.get("parts") or []:
            txt = part.get("text")
            if txt:
                click.echo(txt)


_MIME_BY_SUFFIX: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".eml": "message/rfc822",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def _guess_mime_from_suffix(suffix: str) -> str:
    """Map a file suffix to a MIME type the agent's defaultInputModes accepts."""
    return _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
