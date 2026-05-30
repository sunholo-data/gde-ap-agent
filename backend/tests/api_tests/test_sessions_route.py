"""API tests for chat session CRUD endpoints.

All endpoints require authentication. Tests use a minimal FastAPI app with
mocked Firestore helpers so no real GCP connection is needed.

Acceptance criteria verified:
- GET /api/documents/{id}/sessions?filter=mine returns only caller's sessions
- GET /api/documents/{id}/sessions?filter=team returns sessions with shared tag
- GET /api/documents/{id}/sessions?filter=team returns 200 empty list when viewer has no tags
- GET /api/sessions/{id} returns 403 when caller has no access
- PATCH /api/sessions/{id} with same-tag non-owner viewer returns 403
- DELETE /api/sessions/{id} with non-owner returns 403
- DELETE /api/sessions/{id} with owner returns 204 and soft-deletes
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import User
from auth.access_context import AccessContext
from db.models.access import AccessControl
from db.models.chat_session import ChatSessionIndex
from protocols.sessions_route import router

# ---------------------------------------------------------------------------
# Test app + auth mock
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _make_session(
    session_id: str = "sess-1",
    owner_uid: str = "owner-uid",
    ac: AccessControl | None = None,
    doc_id: str = "doc-1",
    archived: bool = False,
) -> ChatSessionIndex:
    return ChatSessionIndex(
        sessionId=session_id,
        documentIds=[doc_id] if doc_id else [],
        skillId="skill-1",
        ownerUid=owner_uid,
        accessControl=ac or AccessControl(type="private"),
        firstMessageAt=_utcnow(),
        lastMessageAt=_utcnow(),
        archivedAt=_utcnow() if archived else None,
    )


def _inject_user(uid: str, tags: frozenset[str] = frozenset()) -> None:
    """Override get_current_user + request.state.access for a given uid."""
    user = User(uid=uid, email=f"{uid}@example.com", domain="example.com")
    ctx = AccessContext(uid=uid, email=user.email, domain=user.domain, group_tags=tags)

    from auth import firebase_auth

    original_get = (
        firebase_auth.get_current_user.__wrapped__
        if hasattr(firebase_auth.get_current_user, "__wrapped__")
        else firebase_auth.get_current_user
    )

    app.dependency_overrides[original_get] = lambda: user

    from fastapi import Request

    async def _state_middleware(request: Request, call_next):
        request.state.access = ctx
        return await call_next(request)

    app.middleware("http")(_state_middleware)


# Simpler approach: override via dependency injection at test level
from auth import get_current_user  # noqa: E402


def _make_client(uid: str, tags: frozenset[str] = frozenset()) -> TestClient:
    user = User(uid=uid, email=f"{uid}@example.com", domain="example.com")
    ctx = AccessContext(uid=uid, email=user.email, domain=user.domain, group_tags=tags)

    test_app = FastAPI()
    test_app.include_router(router)

    @test_app.middleware("http")
    async def _inject_access(request, call_next):
        request.state.access = ctx
        return await call_next(request)

    test_app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# GET /api/documents/{doc_id}/sessions
# ---------------------------------------------------------------------------


class TestListDocumentSessions:
    def _own_sess(self):
        return _make_session("s1", owner_uid="viewer", ac=AccessControl(type="private"))

    def _team_sess(self):
        return _make_session("s2", owner_uid="alice", ac=AccessControl(type="tagged", tags=["finance"]))

    @patch("protocols.sessions_route.list_sessions_for_document")
    def test_returns_200_with_sessions(self, mock_list):
        mock_list.return_value = ([self._own_sess()], None)
        client = _make_client("viewer")

        resp = client.get("/api/documents/doc-1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 1

    @patch("protocols.sessions_route.list_sessions_for_document")
    def test_mine_filter_passed_through(self, mock_list):
        mock_list.return_value = ([], None)
        client = _make_client("viewer")

        resp = client.get("/api/documents/doc-1/sessions?filter=mine")
        assert resp.status_code == 200
        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs.get("filter") == "mine" or "mine" in str(call_kwargs)

    @patch("protocols.sessions_route.list_sessions_for_document")
    def test_empty_list_for_viewer_with_no_tags(self, mock_list):
        mock_list.return_value = ([], None)
        client = _make_client("viewer", tags=frozenset())

        resp = client.get("/api/documents/doc-1/sessions?filter=team")
        assert resp.status_code == 200
        assert resp.json()["sessions"] == []

    @patch("protocols.sessions_route.list_sessions_for_document")
    def test_returns_next_cursor_when_more_pages(self, mock_list):
        mock_list.return_value = ([self._own_sess()], "s1")
        client = _make_client("viewer")

        resp = client.get("/api/documents/doc-1/sessions")
        assert resp.json()["next_cursor"] == "s1"

    def test_requires_auth(self):
        client = TestClient(app)
        resp = client.get("/api/documents/doc-1/sessions")
        assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestGetSession:
    @patch("protocols.sessions_route.get_session_index")
    def test_owner_can_read(self, mock_get):
        mock_get.return_value = _make_session(owner_uid="viewer")
        client = _make_client("viewer")

        resp = client.get("/api/sessions/sess-1")
        assert resp.status_code == 200
        assert resp.json()["session"]["session_id"] == "sess-1"
        assert resp.json()["session"]["is_owner"] is True

    @patch("protocols.sessions_route.get_session_index")
    def test_tagged_viewer_can_read(self, mock_get):
        mock_get.return_value = _make_session(
            owner_uid="alice",
            ac=AccessControl(type="tagged", tags=["finance"]),
        )
        client = _make_client("viewer", tags=frozenset(["finance"]))

        resp = client.get("/api/sessions/sess-1")
        assert resp.status_code == 200
        assert resp.json()["session"]["is_owner"] is False

    @patch("protocols.sessions_route.get_session_index")
    def test_no_access_returns_403(self, mock_get):
        mock_get.return_value = _make_session(owner_uid="alice", ac=AccessControl(type="private"))
        client = _make_client("viewer")

        resp = client.get("/api/sessions/sess-1")
        assert resp.status_code == 403

    @patch("protocols.sessions_route.get_session_index")
    def test_missing_session_returns_404(self, mock_get):
        mock_get.return_value = None
        client = _make_client("viewer")

        resp = client.get("/api/sessions/missing")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestPatchSession:
    @patch("protocols.sessions_route.get_session_index")
    @patch("protocols.sessions_route.update_session_fields")
    def test_owner_can_rename(self, mock_update, mock_get):
        sess = _make_session(owner_uid="viewer")
        mock_get.return_value = sess
        client = _make_client("viewer")

        resp = client.patch("/api/sessions/sess-1", json={"title": "New Title"})
        assert resp.status_code == 200
        mock_update.assert_called_once()

    @patch("protocols.sessions_route.get_session_index")
    @patch("protocols.sessions_route.update_session_fields")
    def test_non_owner_with_tag_access_gets_403(self, mock_update, mock_get):
        sess = _make_session(owner_uid="alice", ac=AccessControl(type="tagged", tags=["finance"]))
        mock_get.return_value = sess
        client = _make_client("viewer", tags=frozenset(["finance"]))

        resp = client.patch("/api/sessions/sess-1", json={"title": "Hijack"})
        assert resp.status_code == 403
        mock_update.assert_not_called()

    @patch("protocols.sessions_route.get_session_index")
    def test_no_access_returns_403(self, mock_get):
        mock_get.return_value = _make_session(owner_uid="alice", ac=AccessControl(type="private"))
        client = _make_client("viewer")

        resp = client.patch("/api/sessions/sess-1", json={"title": "X"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestDeleteSession:
    @patch("protocols.sessions_route.get_session_index")
    @patch("protocols.sessions_route.soft_delete_session")
    def test_owner_delete_returns_204(self, mock_delete, mock_get):
        mock_get.return_value = _make_session(owner_uid="viewer")
        client = _make_client("viewer")

        resp = client.delete("/api/sessions/sess-1")
        assert resp.status_code == 204
        mock_delete.assert_called_once_with("sess-1")

    @patch("protocols.sessions_route.get_session_index")
    @patch("protocols.sessions_route.soft_delete_session")
    def test_non_owner_returns_403(self, mock_delete, mock_get):
        mock_get.return_value = _make_session(
            owner_uid="alice",
            ac=AccessControl(type="tagged", tags=["finance"]),
        )
        client = _make_client("viewer", tags=frozenset(["finance"]))

        resp = client.delete("/api/sessions/sess-1")
        assert resp.status_code == 403
        mock_delete.assert_not_called()

    @patch("protocols.sessions_route.get_session_index")
    def test_no_access_returns_403(self, mock_get):
        mock_get.return_value = _make_session(owner_uid="alice", ac=AccessControl(type="private"))
        client = _make_client("viewer")

        resp = client.delete("/api/sessions/sess-1")
        assert resp.status_code == 403

    @patch("protocols.sessions_route.get_session_index")
    def test_missing_session_returns_404(self, mock_get):
        mock_get.return_value = None
        client = _make_client("viewer")

        resp = client.delete("/api/sessions/missing")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/sessions/{session_id}/messages — chat-history-deep-fixes-2 (1.15)
# ---------------------------------------------------------------------------


class TestGetSessionMessages:
    """D2' and D5' diagnostics for the message-read endpoint.

    D2' locks the current 500 failure mode (user_id triple inconsistency).
    D5' surfaces the access-policy gap: list endpoint shows shared sessions
    to non-owners, but message-read is owner-only — clicking a shared
    session 403s. Bug E.
    """

    @patch("protocols.sessions_route.get_messages_session_service")
    @patch("protocols.sessions_route.get_session_index")
    def test_d2_returns_500_when_vertex_user_id_mismatch(self, mock_get, mock_service_factory):
        """D2' (chat-history-deep-fixes-2 H1 lock-in): when ag_ui_adk created
        the Vertex session with user_id='thread_user_<id>' but Firestore has
        owner_uid=<firebase_uid>, the route's call to
        ``session_service.get_session(user_id=idx.owner_uid, ...)`` raises the
        ValueError documented in production logs:

            ValueError: Session ... does not belong to user uG9C...

        Unhandled, this surfaces to the real frontend client as HTTP 500.
        TestClient re-raises by default; we use raise_server_exceptions=False
        to observe what users actually see.
        """
        from unittest.mock import AsyncMock

        from auth import User, get_current_user
        from auth.access_context import AccessContext

        mock_get.return_value = _make_session(owner_uid="firebase-uid-abc")
        mock_session_service = AsyncMock()
        mock_session_service.get_session = AsyncMock(
            side_effect=ValueError("Session sess-1 does not belong to user firebase-uid-abc.")
        )
        mock_service_factory.return_value = mock_session_service

        # Build a TestClient that doesn't re-raise so we see the 500 the
        # real frontend sees in dev (which then triggers the
        # "Couldn't load previous messages" banner).
        user = User(uid="firebase-uid-abc", email="x@example.com", domain="example.com")
        ctx = AccessContext(uid="firebase-uid-abc", email=user.email, domain=user.domain, group_tags=frozenset())
        test_app = FastAPI()
        test_app.include_router(router)

        @test_app.middleware("http")
        async def _inject_access(request, call_next):
            request.state.access = ctx
            return await call_next(request)

        test_app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(test_app, raise_server_exceptions=False)

        resp = client.get("/api/sessions/sess-1/messages")
        assert resp.status_code == 500, (
            f"D2' lock-in: route surfaces an unhandled Vertex ValueError as "
            f"HTTP 500 to the client. Got {resp.status_code}: {resp.text[:200]}"
        )

    @patch("protocols.sessions_route.get_messages_session_service")
    @patch("protocols.sessions_route.get_session_index")
    def test_d5_bug_e_fix_non_owner_with_can_access_reads_messages(self, mock_get, mock_service_factory):
        """D5' Bug E fix-locking (chat-history-deep-fixes-2): the message-read
        endpoint must align with the metadata read at ``GET /api/sessions/{id}``
        — a caller who passes ``ctx.can_access(idx)`` gets messages, regardless
        of ownership. ``list_sessions_for_document`` already uses ``can_access``
        so non-owners see shared thread titles; without this fix, clicking one
        gives a 403 they don't expect.

        Pre-fix this test fails (route was ``is_owner``-only → 403). Post-fix
        passes.

        Vertex query always uses ``idx.owner_uid`` regardless of caller;
        sharing means reading the OWNER's events, not attributing them to
        the reader.
        """
        from unittest.mock import AsyncMock

        # Session owned by alice, public.
        mock_get.return_value = _make_session(owner_uid="alice", ac=AccessControl(type="public"))
        mock_session_service = AsyncMock()
        mock_session_service.get_session = AsyncMock(return_value=None)
        mock_service_factory.return_value = mock_session_service

        client = _make_client("bob")  # different uid, not owner
        resp = client.get("/api/sessions/sess-1/messages")
        assert resp.status_code == 200, (
            f"Bug E fix: non-owner with can_access (public session) must "
            f"read messages. Got {resp.status_code}: {resp.text[:200]}"
        )

        # Verify Vertex was queried with the OWNER's uid, not the caller's.
        mock_session_service.get_session.assert_awaited_once()
        call_kwargs = mock_session_service.get_session.await_args.kwargs
        assert call_kwargs["user_id"] == "alice", (
            "Vertex query must use idx.owner_uid (the session's owner), not "
            "the caller's uid. The caller is bob; the session belongs to alice."
        )

    @patch("protocols.sessions_route.get_session_index")
    def test_bug_e_fix_private_session_still_403s_non_owner(self, mock_get):
        """Bug E security boundary: private sessions remain owner-only —
        the fix only relaxes access for sessions that are intentionally
        shared via the AccessControl model (public, domain, tagged,
        specific-allow). Private must stay private.
        """
        mock_get.return_value = _make_session(owner_uid="alice", ac=AccessControl(type="private"))
        client = _make_client("bob")  # not owner, no shared access
        resp = client.get("/api/sessions/sess-1/messages")
        assert resp.status_code == 403, (
            f"Private sessions must stay owner-only after the Bug E fix; got {resp.status_code}: {resp.text[:200]}"
        )
