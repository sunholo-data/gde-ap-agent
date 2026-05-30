"""`aitana access check` — dry-run access checks against a bucket or folder.

TODO(RESOURCE-ACCESS follow-up): backend /api/access/check endpoint is NOT yet
implemented. This command targets the planned shape so tests + wiring can land
now; backend wiring is a follow-on milestone.

Planned endpoint:
    POST /api/access/check
    body: {"bucketId": "...", "folderId": "...", "asEmail": "..."}
    resp: {"allowed": bool, "reason": "..."}
"""

from __future__ import annotations

import json as _json

import click

from aiplatform.http import AIPlatformClient


def _client(ctx: click.Context) -> AIPlatformClient:
    return AIPlatformClient(env=ctx.obj["env"])


@click.group()
def access() -> None:
    """Access-control dry-run helpers."""


@access.command("check")
@click.option("--bucket", "bucket_id", default=None, help="Bucket ID to test.")
@click.option("--folder", "folder_id", default=None, help="Folder ID to test.")
@click.option(
    "--as-email",
    "as_email",
    default=None,
    help="Check as another user (admin-only server-side). Omit to check as self.",
)
@click.pass_context
def check(ctx: click.Context, bucket_id: str | None, folder_id: str | None, as_email: str | None) -> None:
    """Dry-run: would the current user (or --as-email) have access to this resource?"""
    if not bucket_id and not folder_id:
        raise click.UsageError("Provide --bucket and/or --folder")
    payload: dict = {}
    if bucket_id:
        payload["bucketId"] = bucket_id
    if folder_id:
        payload["folderId"] = folder_id
    if as_email:
        payload["asEmail"] = as_email
    # TODO: backend wiring pending — see module docstring.
    result = _client(ctx).post("/api/access/check", json=payload)
    click.echo(_json.dumps(result, indent=2))
