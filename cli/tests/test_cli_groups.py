"""Tests for `aitana groups` subcommands.

Note: the backend endpoints are not implemented yet (TODO in the command
module). These tests assert the CLI hits the PLANNED URL + method + payload
shape so the CLI is ready the moment the backend lands.
"""

from __future__ import annotations

import json

import httpx
import respx
from click.testing import CliRunner

from aiplatform.cli import main

BASE = "http://localhost:1956"


@respx.mock
def test_groups_add_user_posts_uid() -> None:
    route = respx.post(f"{BASE}/api/groups/ops/members").mock(return_value=httpx.Response(200, json={"ok": True}))
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--env", "local", "groups", "add-user", "--group", "ops", "--uid", "u-1"],
    )
    assert result.exit_code == 0, result.output
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"uid": "u-1"}


@respx.mock
def test_groups_remove_user_deletes() -> None:
    route = respx.delete(f"{BASE}/api/groups/ops/members/u-1").mock(return_value=httpx.Response(204))
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["--env", "local", "groups", "remove-user", "--group", "ops", "--uid", "u-1"],
    )
    assert result.exit_code == 0, result.output
    assert route.called
    assert route.calls.last.request.method == "DELETE"


@respx.mock
def test_groups_list_user_gets_user_groups() -> None:
    route = respx.get(f"{BASE}/api/users/u-1/groups").mock(return_value=httpx.Response(200, json=["ops", "admins"]))
    runner = CliRunner()
    result = runner.invoke(main, ["--env", "local", "groups", "list-user", "--uid", "u-1"])
    assert result.exit_code == 0, result.output
    assert route.called
    assert route.calls.last.request.method == "GET"
    assert "ops" in result.output
