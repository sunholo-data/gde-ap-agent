"""`aitana groups` — add-user / remove-user / list-user subcommands.

TODO(RESOURCE-ACCESS follow-up): backend /api/groups endpoints are NOT yet
implemented. These commands target the planned shape so tests + wiring can
land now; backend wiring is a follow-on milestone.

Planned endpoints:
    POST   /api/groups/{group}/members   body: {"uid": "..."}     -> add
    DELETE /api/groups/{group}/members/{uid}                      -> remove
    GET    /api/users/{uid}/groups                                -> list-user
"""

from __future__ import annotations

import json as _json

import click

from aiplatform.http import AIPlatformClient


def _client(ctx: click.Context) -> AIPlatformClient:
    return AIPlatformClient(env=ctx.obj["env"])


@click.group()
def groups() -> None:
    """Manage group membership (add-user / remove-user / list-user)."""


@groups.command("add-user")
@click.option("--group", required=True, help="Group name.")
@click.option("--uid", required=True, help="User UID to add.")
@click.pass_context
def add_user(ctx: click.Context, group: str, uid: str) -> None:
    """Add a user to a group."""
    # TODO: backend wiring pending — see module docstring.
    result = _client(ctx).post(f"/api/groups/{group}/members", json={"uid": uid})
    click.echo(_json.dumps(result, indent=2))


@groups.command("remove-user")
@click.option("--group", required=True, help="Group name.")
@click.option("--uid", required=True, help="User UID to remove.")
@click.pass_context
def remove_user(ctx: click.Context, group: str, uid: str) -> None:
    """Remove a user from a group."""
    # TODO: backend wiring pending — see module docstring.
    _client(ctx).delete(f"/api/groups/{group}/members/{uid}")
    click.echo(f"Removed uid={uid} from group={group}")


@groups.command("list-user")
@click.option("--uid", required=True, help="User UID to look up.")
@click.pass_context
def list_user(ctx: click.Context, uid: str) -> None:
    """List all groups a user belongs to."""
    # TODO: backend wiring pending — see module docstring.
    result = _client(ctx).get(f"/api/users/{uid}/groups")
    click.echo(_json.dumps(result, indent=2))
