"""The ADK 2 admin surfaces use this fork's existing service-account gate."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from fast_api_app import _is_adk_native_path, app

PATHS = ["/list-apps", "/agent-identity/finalize", "/config/telemetry", "/apps/gde_ap_agent/users/u/sessions"]


@pytest.mark.parametrize("path", PATHS)
def test_native_routes_are_guarded(path):
    assert _is_adk_native_path(path)
    client = TestClient(app, raise_server_exceptions=False)
    with patch("admin.auth._assert_caller_is_service_account", side_effect=HTTPException(401, "Unauthorized")):
        assert client.get(path).status_code == 401


def test_product_routes_keep_their_existing_authorization():
    assert not _is_adk_native_path("/api/skills")
    assert not _is_adk_native_path("/health")
