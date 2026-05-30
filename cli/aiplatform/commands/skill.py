"""`aiplatform skill` — skill-side dev affordances.

Today: a single `probe` command that fires one streaming chat turn at the
backend with `?probe=1` so the LATENCY_REPORT AG-UI Custom event rides at
the end of the stream. Prints the per-stage breakdown (request_received,
session_index_done, before_agent_done, before_model_done, first_model_token,
first_agui_event, first_sse_byte) plus model + routing + tools count.

Used to:
  * Sanity-check chat latency from a terminal without opening a browser.
  * Run the M5 A/B baseline (AITANA_TTFT_MODE=full vs off).
  * Diagnose where time is being spent in production traffic without
    scraping logs.

See docs/design/v6.1.0/ttft-instrumentation.md.
"""

from __future__ import annotations

import json as _json
import uuid

import click
import httpx

from aiplatform.http import AIPlatformClient, APIError, resolve_base_url

# Stage names emitted by backend/observability/timing.py — keep in sync.
_STAGES_IN_ORDER = (
    "request_received",
    "session_index_done",
    "before_agent_done",
    "before_model_done",
    "first_model_token",
    "first_agui_event",
    "first_sse_byte",
)


@click.group()
def skill() -> None:
    """Skill-side dev affordances (probe, etc.)."""


@skill.command("probe")
@click.argument("skill_id")
@click.option(
    "--message",
    "-m",
    default="Hello",
    show_default=True,
    help="Test message to send to the skill.",
)
@click.option(
    "--session",
    default=None,
    help="Existing session/thread id to resume. Default: a fresh thread.",
)
@click.option(
    "--timeout",
    default=60.0,
    show_default=True,
    type=float,
    help="HTTP timeout for the streaming request, in seconds.",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    default=False,
    help="Print the raw LATENCY_REPORT payload as JSON instead of the table.",
)
@click.pass_context
def probe(
    ctx: click.Context,
    skill_id: str,
    message: str,
    session: str | None,
    timeout: float,
    json_output: bool,
) -> None:
    """Fire one chat turn at SKILL_ID and print the TTFT breakdown.

    Sends POST /api/skill/{SKILL_ID}/stream?probe=1 with a minimal
    AG-UI HttpAgent body, reads the SSE stream, finds the LATENCY_REPORT
    Custom event at end-of-stream, and pretty-prints it.

    Requires AITANA_TTFT_MODE != "off" on the backend; off mode is a
    true no-op and emits no LATENCY_REPORT.
    """
    env = ctx.obj["env"]
    base_url = resolve_base_url(env)
    client = AIPlatformClient(env=env, base_url=base_url)
    headers = client._auth_headers()  # noqa: SLF001  internal helper, intentional
    headers["Accept"] = "text/event-stream"

    thread_id = session or f"probe-{uuid.uuid4().hex[:12]}"
    body = {
        "threadId": thread_id,
        "runId": f"run-probe-{uuid.uuid4().hex[:8]}",
        "messages": [
            {"id": f"msg-{uuid.uuid4().hex[:8]}", "role": "user", "content": message},
        ],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }

    url = f"{base_url}/api/skill/{skill_id}/stream"
    report: dict | None = None
    error_event: dict | None = None
    event_count = 0

    try:
        with httpx.stream(
            "POST",
            url,
            headers=headers,
            params={"probe": "1"},
            json=body,
            timeout=timeout,
        ) as resp:
            if resp.status_code >= 400:
                # Drain the response so the error message reaches the user.
                detail = resp.read().decode("utf-8", errors="replace")
                raise APIError(f"POST /api/skill/{skill_id}/stream returned {resp.status_code}: {detail}")
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                try:
                    event = _json.loads(payload)
                except ValueError:
                    continue
                event_count += 1
                name = event.get("name")
                if name == "LATENCY_REPORT":
                    value = event.get("value")
                    if isinstance(value, dict):
                        report = value
                elif event.get("type") == "RUN_ERROR":
                    error_event = event
    except httpx.HTTPError as exc:
        raise APIError(f"HTTP transport error during probe: {exc}") from exc

    if error_event is not None:
        click.secho(f"RUN_ERROR: {error_event.get('message', '(no message)')}", fg="red", err=True)
        ctx.exit(1)

    if report is None:
        click.secho(
            "No LATENCY_REPORT in stream. "
            "Backend may have AITANA_TTFT_MODE=off, or the stream ended before "
            f"the report event was emitted ({event_count} non-data events seen).",
            fg="yellow",
            err=True,
        )
        ctx.exit(2)

    if json_output:
        click.echo(_json.dumps(report, indent=2, sort_keys=True))
        return

    _print_table(report)


def _print_table(report: dict) -> None:
    """Pretty-print the LATENCY_REPORT payload as a 2-col table."""
    click.echo()
    click.secho("TTFT breakdown", bold=True)
    click.echo("─" * 40)
    for stage in _STAGES_IN_ORDER:
        key = f"{stage}_ms"
        value = report.get(key)
        formatted = f"{value:>8.2f}ms" if isinstance(value, (int, float)) else "       —"
        marker = "  ← TTFT" if stage == "first_model_token" else ""
        click.echo(f"  {stage:<22}{formatted}{marker}")

    click.echo("─" * 40)
    total = report.get("total_response_ms")
    if isinstance(total, (int, float)):
        click.echo(f"  {'total':<22}{total:>8.2f}ms")
    click.echo()
    click.echo(
        f"  model:   {report.get('model_used') or '—'}    "
        f"routing: {report.get('routing_choice') or '—'}    "
        f"tools:   {report.get('tools_invoked_count', 0)}"
    )
    click.echo(f"  mode:    {report.get('ttft_mode') or '—'}")
    click.echo()
