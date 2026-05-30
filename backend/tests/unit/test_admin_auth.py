"""Unit tests for admin.auth._assert_caller_is_service_account.

Covers the token-verification and allowlist logic. google.oauth2.id_token is
mocked so no network I/O or real GCP credentials are required.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from admin.auth import _assert_caller_is_service_account


def _make_request(token: str = "tok") -> object:
    """Minimal request stub with an Authorization header."""
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/admin/seed-platform-skills",
        "headers": Headers({"authorization": f"Bearer {token}"}).raw,
    }
    return Request(scope)


def _patch_token(claims: dict):
    return patch("admin.auth.id_token.verify_oauth2_token", return_value=claims)


def _patch_allowed(emails: set[str]):
    return patch("admin.auth._allowed_emails", return_value=emails)


# --- missing / empty auth header ---


def test_missing_auth_header_raises_403():
    from starlette.datastructures import Headers
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": Headers({}).raw,
    }
    req = Request(scope)
    with pytest.raises(HTTPException) as exc:
        _assert_caller_is_service_account(req)
    assert exc.value.status_code == 403


# --- email claim absent → diagnostic log + 403 ---


def test_missing_email_claim_logs_and_raises(caplog):
    """When the token has no 'email' claim, the function must emit a diagnostic
    error log and raise 403 with a description that mentions 'email claim'.
    This catches the gotcha where `include_email=true` is omitted from the
    metadata server URL (item #14 in the upstream feedback)."""
    claims = {"sub": "some-sa@iam.gserviceaccount.com", "iss": "accounts.google.com"}

    with (
        _patch_token(claims),
        _patch_allowed({"some-sa@iam.gserviceaccount.com"}),
        caplog.at_level(logging.ERROR, logger="admin.auth"),
    ):
        with pytest.raises(HTTPException) as exc:
            _assert_caller_is_service_account(_make_request())

    assert exc.value.status_code == 403
    assert "email claim" in exc.value.detail.lower()
    assert any("include_email" in rec.message for rec in caplog.records)


# --- email not verified ---


def test_unverified_email_raises_403():
    claims = {"email": "sa@example.com", "email_verified": False}
    with _patch_token(claims), _patch_allowed({"sa@example.com"}):
        with pytest.raises(HTTPException) as exc:
            _assert_caller_is_service_account(_make_request())
    assert exc.value.status_code == 403
    assert "verified" in exc.value.detail.lower()


# --- happy path ---


def test_verified_email_in_allowlist_returns_email():
    claims = {"email": "cb-sa@my-project.iam.gserviceaccount.com", "email_verified": True}
    with _patch_token(claims), _patch_allowed({"cb-sa@my-project.iam.gserviceaccount.com"}):
        result = _assert_caller_is_service_account(_make_request())
    assert result == "cb-sa@my-project.iam.gserviceaccount.com"


# --- email not in allowlist ---


def test_email_not_in_allowlist_raises_403():
    claims = {"email": "intruder@evil.com", "email_verified": True}
    with _patch_token(claims), _patch_allowed({"legit-sa@project.iam.gserviceaccount.com"}):
        with pytest.raises(HTTPException) as exc:
            _assert_caller_is_service_account(_make_request())
    assert exc.value.status_code == 403
