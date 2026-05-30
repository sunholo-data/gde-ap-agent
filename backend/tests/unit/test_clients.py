"""Tests for db/clients.py — domain→bucket resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from auth.firebase_auth import User


def _user(domain: str) -> User:
    return User(uid="uid1", email=f"alice@{domain}", domain=domain)


class TestResolveDocumentsBucket:
    def test_returns_mapped_bucket_for_known_domain(self):
        from db.clients import resolve_documents_bucket

        mock_client = MagicMock()
        mock_client.documents_bucket = "rockwool-documents"

        with patch("db.clients.get_client_sync", return_value=mock_client):
            result = resolve_documents_bucket(_user("rockwool.com"))

        assert result == "rockwool-documents"

    def test_falls_back_to_env_for_unknown_domain(self, monkeypatch):
        from db.clients import resolve_documents_bucket

        monkeypatch.setenv("DOCUMENTS_BUCKET", "aitana-documents-bucket")

        with patch("db.clients.get_client_sync", return_value=None):
            result = resolve_documents_bucket(_user("unknown.com"))

        assert result == "aitana-documents-bucket"

    def test_falls_back_to_env_when_client_has_no_bucket(self, monkeypatch):
        from db.clients import resolve_documents_bucket

        monkeypatch.setenv("DOCUMENTS_BUCKET", "aitana-documents-bucket")

        mock_client = MagicMock()
        mock_client.documents_bucket = None

        with patch("db.clients.get_client_sync", return_value=mock_client):
            result = resolve_documents_bucket(_user("partial.com"))

        assert result == "aitana-documents-bucket"

    def test_uses_domain_from_user(self):
        from db.clients import resolve_documents_bucket

        calls = []

        def capturing_get(domain: str):
            calls.append(domain)
            return None

        with patch("db.clients.get_client_sync", side_effect=capturing_get):
            resolve_documents_bucket(_user("acme.org"))

        assert calls == ["acme.org"]


class TestGetClientSync:
    def test_returns_none_for_missing_doc(self):
        from db.clients import get_client_sync

        with patch("db.clients.get_document", return_value=None):
            assert get_client_sync("nope.com") is None

    def test_returns_client_config_for_existing_doc(self):
        from db.clients import get_client_sync

        with patch(
            "db.clients.get_document",
            return_value={
                "documents_bucket": "acme-docs",
                "display_name": "Acme Corp",
            },
        ):
            client = get_client_sync("acme.com")

        assert client is not None
        assert client.documents_bucket == "acme-docs"
        assert client.display_name == "Acme Corp"
        assert client.domain == "acme.com"
