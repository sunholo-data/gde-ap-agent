"""Tests for the org-scoped GCS bucket binding (Scenario B of A2A-FILES).

Six tests covering the v1 per-deploy binding contract:
  - `get_bound_bucket` reads env var; returns None when unset; normalises trailing slash
  - `list_documents_in_bucket` returns [] when GCS errors (defence in depth)
  - `list_org_documents` tool returns [] when no binding
  - `read_org_document` tool returns ok=False when no binding
  - List limit honoured (A2A_ORG_BUCKET_LIST_LIMIT)
  - Bad bucket URI returns [] (logged warning, no exception)

The GCS-touching paths are exercised via monkeypatch on _gcs_client so
unit tests run without Cloud credentials. The end-to-end probe (real
GCS LIST against gs://gde-ap-agent-demo-invoices) is in M3's
simulate-a2a-peer.py Step 8.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from protocols import a2a_org_bucket


@pytest.fixture(autouse=True)
def reset_module_caches() -> None:
    """Ensure the lru_cache singletons don't leak across tests."""
    a2a_org_bucket._gcs_client.cache_clear()


def test_get_bound_bucket_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """`A2A_AGENT_DOCUMENTS_BUCKET` not set → None (graceful degradation)."""
    monkeypatch.delenv("A2A_AGENT_DOCUMENTS_BUCKET", raising=False)
    assert a2a_org_bucket.get_bound_bucket() is None


def test_get_bound_bucket_normalises_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow both `gs://bucket` and `gs://bucket/` configs to work; the
    returned URI always has exactly one trailing slash so downstream
    `f"{bucket}{name}"` concatenation produces clean object paths.
    """
    monkeypatch.setenv("A2A_AGENT_DOCUMENTS_BUCKET", "gs://my-bucket")
    assert a2a_org_bucket.get_bound_bucket() == "gs://my-bucket/"
    monkeypatch.setenv("A2A_AGENT_DOCUMENTS_BUCKET", "gs://my-bucket/")
    assert a2a_org_bucket.get_bound_bucket() == "gs://my-bucket/"
    monkeypatch.setenv("A2A_AGENT_DOCUMENTS_BUCKET", "gs://my-bucket/prefix")
    assert a2a_org_bucket.get_bound_bucket() == "gs://my-bucket/prefix/"


def test_get_bound_bucket_rejects_non_gs_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    """A misconfigured env (e.g. accidentally an https:// URL) must not
    propagate into the GCS client — that would surface as a confusing
    auth error far from the source. Return None instead.
    """
    monkeypatch.setenv("A2A_AGENT_DOCUMENTS_BUCKET", "https://example.com/bucket")
    assert a2a_org_bucket.get_bound_bucket() is None


def test_list_documents_in_bucket_returns_empty_when_gcs_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any exception from the GCS client during LIST is caught and
    returns []. The tool degrades to "no documents available" rather
    than 500-ing the agent turn — critical for tenant-level resilience
    (a misconfigured IAM grant shouldn't break the whole agent).
    """

    class _BadClient:
        def list_blobs(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("simulated GCS failure")

        def bucket(self, name: str) -> Any:
            return MagicMock()

    monkeypatch.setattr(a2a_org_bucket, "_gcs_client", lambda: _BadClient())

    result = asyncio.run(a2a_org_bucket.list_documents_in_bucket("gs://my-bucket/", prefix=""))
    assert result == []


def test_list_documents_in_bucket_respects_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """When A2A_ORG_BUCKET_LIST_LIMIT is set, list_blobs is called with
    matching max_results. The cap matters because peers asking for "all
    invoices" against a 10k-object bucket would otherwise blow up the
    model's context window.
    """
    monkeypatch.setenv("A2A_ORG_BUCKET_LIST_LIMIT", "5")

    captured_max: list[int | None] = []

    def _list_blobs(bucket: Any, prefix: str = "", max_results: int | None = None) -> list[Any]:
        captured_max.append(max_results)
        return []

    class _Client:
        def __init__(self) -> None:
            self.list_blobs = _list_blobs

        def bucket(self, name: str) -> Any:
            return MagicMock(name=name)

    monkeypatch.setattr(a2a_org_bucket, "_gcs_client", lambda: _Client())

    asyncio.run(a2a_org_bucket.list_documents_in_bucket("gs://my-bucket/", prefix=""))
    assert captured_max == [5]


def test_list_documents_in_bucket_returns_object_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy-path: LIST returns name, size, mimeType, timeCreated.
    Confirms the dict shape the orchestrator's instruction depends on.
    """

    blob1 = MagicMock()
    blob1.name = "vendor-master/acme.json"
    blob1.size = 1024
    blob1.content_type = "application/json"
    blob1.time_created = datetime.datetime(2026, 1, 15, 12, 0, 0)

    blob2 = MagicMock()
    blob2.name = "invoices/2026/INV-001.pdf"
    blob2.size = 4096
    blob2.content_type = "application/pdf"
    blob2.time_created = datetime.datetime(2026, 2, 1, 9, 30, 0)

    class _Client:
        def list_blobs(self, bucket: Any, prefix: str = "", max_results: int | None = None) -> list[Any]:
            return [blob1, blob2]

        def bucket(self, name: str) -> Any:
            return MagicMock(name=name)

    monkeypatch.setattr(a2a_org_bucket, "_gcs_client", lambda: _Client())

    result = asyncio.run(a2a_org_bucket.list_documents_in_bucket("gs://my-bucket/", prefix=""))
    assert len(result) == 2
    assert result[0] == {
        "name": "vendor-master/acme.json",
        "size": 1024,
        "mimeType": "application/json",
        "timeCreated": "2026-01-15T12:00:00",
    }
    assert result[1]["name"] == "invoices/2026/INV-001.pdf"
    assert result[1]["mimeType"] == "application/pdf"


# ---------------------------------------------------------------------------
# Tool-layer tests
# ---------------------------------------------------------------------------


def test_list_org_documents_returns_empty_when_unbound(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model-facing tool MUST return [] (not raise) when no bucket
    is bound. The orchestrator's instruction depends on this contract
    to know when to fall back to text-only answering.
    """
    monkeypatch.delenv("A2A_AGENT_DOCUMENTS_BUCKET", raising=False)

    from tools.org_documents import list_org_documents

    result = asyncio.run(list_org_documents(prefix=""))
    assert result == []


def test_read_org_document_returns_failure_when_unbound(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same contract for read: graceful, never raises, ok=False on no binding."""
    monkeypatch.delenv("A2A_AGENT_DOCUMENTS_BUCKET", raising=False)

    from tools.org_documents import read_org_document

    result = asyncio.run(read_org_document(name="something.pdf"))
    assert result["ok"] is False
    assert result["doc_id"] is None
    assert "bound" in result["message"].lower()
