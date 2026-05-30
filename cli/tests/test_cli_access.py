"""Tests for `aitana access` subcommands.

Note: the backend /api/access/check endpoint is not yet implemented. These
tests pin the PLANNED request shape so the CLI lines up with the backend
follow-up.
"""

from __future__ import annotations

import json

import httpx
import respx
from click.testing import CliRunner

from aiplatform.cli import main

BASE = "http://localhost:1956"


@respx.mock
def test_access_check_bucket_only() -> None:
    route = respx.post(f"{BASE}/api/access/check").mock(
        return_value=httpx.Response(200, json={"allowed": True, "reason": "owner"})
    )
    runner = CliRunner()
    result = runner.invoke(main, ["--env", "local", "access", "check", "--bucket", "bkt-1"])
    assert result.exit_code == 0, result.output
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"bucketId": "bkt-1"}
    assert "allowed" in result.output


@respx.mock
def test_access_check_with_as_email() -> None:
    route = respx.post(f"{BASE}/api/access/check").mock(
        return_value=httpx.Response(200, json={"allowed": False, "reason": "not-in-acl"})
    )
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--env",
            "local",
            "access",
            "check",
            "--bucket",
            "bkt-1",
            "--folder",
            "f-1",
            "--as-email",
            "alice@example.com",
        ],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "bucketId": "bkt-1",
        "folderId": "f-1",
        "asEmail": "alice@example.com",
    }


def test_access_check_requires_bucket_or_folder() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--env", "local", "access", "check"])
    assert result.exit_code != 0
    assert "--bucket" in result.output or "--folder" in result.output
