"""API tests for /api/buckets — the 4 CRUD ops x 5 access types x caller-identity matrix.

Mirrors the skills auth matrix (tests/api_tests/test_skills_auth.py). Mocks
`bucket_config.*` so the tests exercise route/handler logic against the
five-type evaluator — not Firestore round-trips.

Invariants locked in:
    - anon → 401 on everything
    - non-owner + no-access → 404 (don't leak existence)
    - non-owner + has-access → 200 GET, 403 PUT/DELETE
    - owner / admin → 200 / 201 / 204
    - POST never honours a body-supplied ownerId
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from auth import User, build_access_context, get_current_user
from buckets.routes import router
from db.models import BucketConfig

OWNER_UID = "owner-uid"
OWNER_EMAIL = "owner@aitanalabs.com"


def _make_bucket(**overrides) -> BucketConfig:
    defaults: dict = {
        "bucketId": "bkt-1",
        "displayName": "Sample Bucket",
        "gcsBucket": "sample-bucket",
        "ownerEmail": OWNER_EMAIL,
        "ownerId": OWNER_UID,
        "accessControl": {"type": "private"},
    }
    defaults.update(overrides)
    return BucketConfig(**defaults)


def _make_user(
    uid: str = "caller-uid",
    email: str = "caller@aitanalabs.com",
    domain: str = "aitanalabs.com",
    group_tags: frozenset[str] = frozenset(),
) -> User:
    return User(uid=uid, email=email, domain=domain, group_tags=group_tags)


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _install_user(app: FastAPI, user: User) -> Callable[[], None]:
    async def _override(request: Request) -> User:
        request.state.access = build_access_context(user)
        return user

    app.dependency_overrides[get_current_user] = _override

    def _cleanup() -> None:
        app.dependency_overrides.pop(get_current_user, None)

    return _cleanup


# ---------------------------------------------------------------------------
# Anonymous callers
# ---------------------------------------------------------------------------


def test_anon_list_401(client: TestClient) -> None:
    assert client.get("/api/buckets").status_code == 401


def test_anon_get_401(client: TestClient) -> None:
    assert client.get("/api/buckets/bkt-1").status_code == 401


def test_anon_create_401(client: TestClient) -> None:
    body = {"displayName": "x", "gcsBucket": "sample-bucket"}
    assert client.post("/api/buckets", json=body).status_code == 401


def test_anon_update_401(client: TestClient) -> None:
    assert client.put("/api/buckets/bkt-1", json={"displayName": "y"}).status_code == 401


def test_anon_delete_401(client: TestClient) -> None:
    assert client.delete("/api/buckets/bkt-1").status_code == 401


# ---------------------------------------------------------------------------
# GET /api/buckets/{id} — read access matrix
# ---------------------------------------------------------------------------


def test_non_owner_private_is_404(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(accessControl={"type": "private"})
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 404
    finally:
        cleanup()


def test_owner_private_200(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid=OWNER_UID, email=OWNER_EMAIL))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket()
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 200
        assert resp.json()["bucketId"] == "bkt-1"
    finally:
        cleanup()


def test_public_bucket_any_user_200(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(accessControl={"type": "public"})
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 200
    finally:
        cleanup()


def test_domain_match_200(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger", domain="aitanalabs.com"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(
                accessControl={"type": "domain", "domain": "aitanalabs.com"},
            )
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 200
    finally:
        cleanup()


def test_domain_no_match_404(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger", domain="evil.com"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(
                accessControl={"type": "domain", "domain": "aitanalabs.com"},
            )
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 404
    finally:
        cleanup()


def test_specific_email_match_200(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger", email="invited@corp.com"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(
                accessControl={"type": "specific", "emails": ["invited@corp.com"]},
            )
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 200
    finally:
        cleanup()


def test_tagged_match_200(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(
        app,
        _make_user(uid="stranger", group_tags=frozenset({"finance-team"})),
    )
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(
                accessControl={"type": "tagged", "tags": ["finance-team"]},
            )
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 200
    finally:
        cleanup()


def test_tagged_no_match_404(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger", group_tags=frozenset()))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = _make_bucket(
                accessControl={"type": "tagged", "tags": ["finance-team"]},
            )
            resp = client.get("/api/buckets/bkt-1")
        assert resp.status_code == 404
    finally:
        cleanup()


def test_get_nonexistent_404(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid=OWNER_UID, email=OWNER_EMAIL))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock:
            mock.return_value = None
            resp = client.get("/api/buckets/missing")
        assert resp.status_code == 404
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# POST — ownerId must come from the JWT
# ---------------------------------------------------------------------------


def test_create_sets_owner_from_jwt(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="jwt-uid", email="jwt@x.com"))
    try:
        with patch("buckets.routes.bucket_config.create_bucket") as mock:
            mock.return_value = _make_bucket(ownerId="jwt-uid", ownerEmail="jwt@x.com")
            resp = client.post(
                "/api/buckets",
                json={
                    "displayName": "My Bucket",
                    "gcsBucket": "my-bucket-dev",
                    # Client attempts to set ownerId — must be ignored.
                    "ownerId": "attacker",
                },
            )
        assert resp.status_code == 201
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["owner_id"] == "jwt-uid"
        assert call_kwargs["owner_email"] == "jwt@x.com"
    finally:
        cleanup()


def test_create_rejects_bad_access_control(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="jwt-uid", email="jwt@x.com"))
    try:
        resp = client.post(
            "/api/buckets",
            json={
                "displayName": "x",
                "gcsBucket": "my-bucket-dev",
                "accessControl": {"type": "not-a-real-type"},
            },
        )
        assert resp.status_code == 400
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# PUT — owner-only
# ---------------------------------------------------------------------------


def test_update_owner_200(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid=OWNER_UID, email=OWNER_EMAIL))
    try:
        with (
            patch("buckets.routes.bucket_config.get_bucket") as mock_get,
            patch("buckets.routes.bucket_config.update_bucket") as mock_update,
        ):
            mock_get.return_value = _make_bucket()
            mock_update.return_value = _make_bucket(displayName="Renamed")
            resp = client.put("/api/buckets/bkt-1", json={"displayName": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["displayName"] == "Renamed"
    finally:
        cleanup()


def test_update_non_owner_with_access_403(app: FastAPI, client: TestClient) -> None:
    """Caller CAN see the bucket (public) but is not the owner → real 403."""
    cleanup = _install_user(app, _make_user(uid="stranger"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock_get:
            mock_get.return_value = _make_bucket(accessControl={"type": "public"})
            resp = client.put("/api/buckets/bkt-1", json={"displayName": "Pwned"})
        assert resp.status_code == 403
    finally:
        cleanup()


def test_update_invisible_404(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock_get:
            mock_get.return_value = _make_bucket()  # private
            resp = client.put("/api/buckets/bkt-1", json={"displayName": "x"})
        assert resp.status_code == 404
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# DELETE — owner-or-admin
# ---------------------------------------------------------------------------


def test_delete_owner_204(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid=OWNER_UID, email=OWNER_EMAIL))
    try:
        with (
            patch("buckets.routes.bucket_config.get_bucket") as mock_get,
            patch("buckets.routes.bucket_config.delete_bucket") as mock_del,
        ):
            mock_get.return_value = _make_bucket()
            mock_del.return_value = True
            resp = client.delete("/api/buckets/bkt-1")
        assert resp.status_code == 204
    finally:
        cleanup()


def test_delete_non_owner_with_access_403(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger"))
    try:
        with patch("buckets.routes.bucket_config.get_bucket") as mock_get:
            mock_get.return_value = _make_bucket(accessControl={"type": "public"})
            resp = client.delete("/api/buckets/bkt-1")
        assert resp.status_code == 403
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# LIST — filters to what the caller can see
# ---------------------------------------------------------------------------


def test_list_filters_to_visible(app: FastAPI, client: TestClient) -> None:
    cleanup = _install_user(app, _make_user(uid="stranger", domain="evil.com"))
    try:
        with patch("buckets.routes.bucket_config.list_buckets") as mock_list:
            mock_list.return_value = [
                _make_bucket(bucketId="b-pub", accessControl={"type": "public"}),
                _make_bucket(bucketId="b-priv", accessControl={"type": "private"}),
            ]
            resp = client.get("/api/buckets")
        assert resp.status_code == 200
        ids = [b["bucketId"] for b in resp.json()]
        assert ids == ["b-pub"]
    finally:
        cleanup()
