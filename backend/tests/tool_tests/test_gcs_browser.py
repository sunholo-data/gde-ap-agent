"""Tests for tools/gcs_browser — GCS list + import API.

All GCS calls are mocked; no real network or bucket needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from auth import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(uid: str = "test-uid", email: str = "test@example.com") -> User:
    u = MagicMock(spec=User)
    u.uid = uid
    u.email = email
    return u


def _make_blob(name: str, size: int = 1024, content_type: str = "text/plain") -> MagicMock:
    blob = MagicMock()
    blob.name = name
    blob.size = size
    blob.content_type = content_type
    blob.updated = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    return blob


# ---------------------------------------------------------------------------
# validate_bucket_name
# ---------------------------------------------------------------------------


class TestValidateBucketName:
    def test_valid_simple(self):
        from tools.gcs_browser.browser import validate_bucket_name

        assert validate_bucket_name("my-bucket") == "my-bucket"

    def test_valid_with_dots(self):
        from tools.gcs_browser.browser import validate_bucket_name

        assert validate_bucket_name("gde-ap-agent-demo-invoices") == "gde-ap-agent-demo-invoices"

    def test_invalid_spaces(self):
        from tools.gcs_browser.browser import validate_bucket_name

        with pytest.raises(ValueError, match="Invalid GCS bucket name"):
            validate_bucket_name("bad name!!")

    def test_invalid_uppercase(self):
        from tools.gcs_browser.browser import validate_bucket_name

        with pytest.raises(ValueError, match="Invalid GCS bucket name"):
            validate_bucket_name("MyBucket")

    def test_invalid_too_short(self):
        from tools.gcs_browser.browser import validate_bucket_name

        with pytest.raises(ValueError, match="Invalid GCS bucket name"):
            validate_bucket_name("a")

    def test_demo_sentinel_not_validated(self):
        from tools.gcs_browser.browser import validate_bucket_name

        # "demo" passes — it's a valid bucket name pattern
        assert validate_bucket_name("demo") == "demo"


# ---------------------------------------------------------------------------
# list_gcs_objects
# ---------------------------------------------------------------------------


class TestListGCSObjects:
    @patch("tools.gcs_browser.browser.os.getenv", return_value="gde-ap-agent-demo-invoices")
    @patch("tools.gcs_browser.browser.storage")
    def test_demo_sentinel_substitutes_env_var(self, mock_storage, mock_getenv):
        from tools.gcs_browser.browser import list_gcs_objects

        blob = _make_blob(
            "acme-gmbh-invoice.docx",
            size=37000,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = iter([blob])

        result = list_gcs_objects("demo", prefix="", delimiter="/")

        mock_client.bucket.assert_called_once_with("gde-ap-agent-demo-invoices")
        assert len(result.objects) == 1
        assert result.objects[0].display_name == "acme-gmbh-invoice.docx"
        assert result.objects[0].size == 37000

    @patch("tools.gcs_browser.browser.storage")
    def test_user_bucket_listed_directly(self, mock_storage):
        from tools.gcs_browser.browser import list_gcs_objects

        blob = _make_blob("invoices/vendor-inv-001.xlsx")
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = iter([blob])

        result = list_gcs_objects("my-real-bucket", prefix="invoices/", delimiter="/")

        mock_client.bucket.assert_called_once_with("my-real-bucket")
        assert result.bucket == "my-real-bucket"
        assert result.prefix == "invoices/"

    @patch("tools.gcs_browser.browser.storage")
    def test_permission_denied_returns_sa_email(self, mock_storage):
        from google.api_core.exceptions import Forbidden

        from tools.gcs_browser.browser import list_gcs_objects

        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.side_effect = Forbidden("403 Forbidden")

        result = list_gcs_objects("restricted-bucket", prefix="", delimiter="/")

        assert result.objects == []
        assert result.error is not None
        assert "403" in result.error or "Forbidden" in result.error.lower() or result.sa_email is not None

    @patch("tools.gcs_browser.browser.storage")
    def test_prefixes_returned_for_delimiter(self, mock_storage):
        from tools.gcs_browser.browser import list_gcs_objects

        # GCS returns prefixes as separate iterator items when delimiter is set
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        blob = _make_blob("invoices/q1/inv.csv")
        mock_bucket.list_blobs.return_value = iter([blob])

        result = list_gcs_objects("my-bucket", prefix="", delimiter="/")
        assert isinstance(result.prefixes, list)

    def test_invalid_bucket_name_raises_value_error(self):
        from tools.gcs_browser.browser import list_gcs_objects

        with pytest.raises(ValueError, match="Invalid GCS bucket name"):
            list_gcs_objects("INVALID BUCKET NAME", prefix="", delimiter="/")


# ---------------------------------------------------------------------------
# import_gcs_object
# ---------------------------------------------------------------------------


class TestImportGCSObject:
    @patch("tools.gcs_browser.browser._store_document")
    @patch("tools.gcs_browser.browser._run_parse", new_callable=AsyncMock)
    @patch("tools.gcs_browser.browser._upload_to_gcs")
    @patch("tools.gcs_browser.browser.folders_db")
    @patch("tools.gcs_browser.browser.resolve_documents_bucket", return_value="user-docs-bucket")
    @patch("tools.gcs_browser.browser.storage")
    @pytest.mark.asyncio
    async def test_import_success(self, mock_storage, mock_resolve, mock_folders, mock_upload, mock_parse, mock_store):
        from tools.gcs_browser.browser import import_gcs_object

        mock_parse.return_value = ("parsed", [{"type": "text", "text": "Invoice content"}], 120, None)
        mock_folders.ensure_default_folder.return_value = "folder-001"

        # Mock GCS download
        mock_client = MagicMock()
        mock_storage.Client.return_value = mock_client
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_blob.download_as_bytes.return_value = b"fake docx content"
        mock_blob.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        user = _make_user()
        result = await import_gcs_object(
            user=user,
            bucket_name="source-bucket",
            object_path="invoices/acme-gmbh.docx",
            folder_id="",
            skill_id="ap-orchestrator",
        )

        assert result.status == "parsed"
        assert result.original_filename == "acme-gmbh.docx"
        assert result.folder_id == "folder-001"
        mock_upload.assert_called_once()
        mock_parse.assert_awaited_once()
        mock_store.assert_called()

    @pytest.mark.asyncio
    async def test_unsupported_extension_raises_400(self):
        from tools.gcs_browser.browser import import_gcs_object

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await import_gcs_object(
                user=user,
                bucket_name="source-bucket",
                object_path="malware.exe",
                folder_id="",
                skill_id="",
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_bucket_raises_400(self):
        from tools.gcs_browser.browser import import_gcs_object

        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await import_gcs_object(
                user=user,
                bucket_name="INVALID BUCKET!!",
                object_path="invoice.docx",
                folder_id="",
                skill_id="",
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# API routes (FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Isolated FastAPI test app with only the gcs_browser router."""
    from fastapi import FastAPI

    from tools.gcs_browser.routes import router

    app = FastAPI()

    # Override auth dependency
    from auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


class TestGCSRoutes:
    @patch("tools.gcs_browser.routes.list_gcs_objects")
    def test_list_returns_200(self, mock_list, client):
        from tools.gcs_browser.browser import GCSListResponse, GCSObject

        mock_list.return_value = GCSListResponse(
            bucket="demo",
            prefix="",
            objects=[
                GCSObject(
                    name="acme-invoice.docx",
                    display_name="acme-invoice.docx",
                    size=37000,
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    updated="2026-06-01T00:00:00Z",
                )
            ],
            prefixes=[],
            error=None,
            sa_email=None,
        )

        resp = client.get("/api/gcs/list?bucket=demo")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["objects"]) == 1
        assert data["objects"][0]["displayName"] == "acme-invoice.docx"

    def test_list_invalid_bucket_returns_400(self, client):
        resp = client.get("/api/gcs/list?bucket=INVALID+NAME!!")
        assert resp.status_code == 400

    @patch("tools.gcs_browser.routes.import_gcs_object", new_callable=AsyncMock)
    def test_import_returns_200(self, mock_import, client):
        from tools.documents.upload import ParsedDocumentResponse

        mock_import.return_value = ParsedDocumentResponse(
            docId="doc-123",
            status="parsed",
            originalFilename="acme-invoice.docx",
            blocksCount=12,
            storagePath="users/test-uid/docs/folder-001/acme-invoice.docx",
            folderId="folder-001",
        )

        resp = client.post(
            "/api/gcs/import",
            json={"bucket": "source-bucket", "path": "invoices/acme-invoice.docx"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["docId"] == "doc-123"
        assert data["status"] == "parsed"

    def test_import_invalid_bucket_returns_400(self, client):
        resp = client.post(
            "/api/gcs/import",
            json={"bucket": "INVALID!!", "path": "invoice.docx"},
        )
        assert resp.status_code == 400
