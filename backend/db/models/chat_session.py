"""ChatSessionIndex — lightweight Firestore index row for chat sessions.

Events and state live in ADK VertexAiSessionService (Agent Engine).
This model is the queryable metadata mirror: list, filter, share, and
rename without touching Agent Engine's O(n) list_sessions scan.

Access enforcement reuses the shared `AccessControl` + `can_access()`
pipeline from resource-access-control (1A.1b). Default at session start:
inherit the parent document's accessControl (copy verbatim).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from db.models.access import AccessControl


class ChatSessionIndex(BaseModel):
    """Firestore document at `chat_sessions/{sessionId}`.

    `owner_id` property satisfies the `_HasAccess` protocol used by
    `auth.access_context.can_access()`.

    ``document_ids`` is the full list of documents that have ever been
    attached to this session — added by ``make_document_loader`` via
    ``ArrayUnion`` whenever the user opens a new tab. The
    ``list_sessions_for_document`` query uses ``array_contains`` so a
    session shows up under each of its docs' history panels.
    """

    session_id: str = Field(alias="sessionId")
    document_ids: list[str] = Field(default_factory=list, alias="documentIds")
    skill_id: str = Field(alias="skillId")
    owner_uid: str = Field(alias="ownerUid")
    access_control: AccessControl = Field(alias="accessControl")
    title: str | None = None
    turn_count: int = Field(default=0, alias="turnCount")
    first_message_at: datetime = Field(alias="firstMessageAt")
    last_message_at: datetime = Field(alias="lastMessageAt")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")

    model_config = ConfigDict(populate_by_name=True)

    @property
    def owner_id(self) -> str:
        """Satisfies the `_HasAccess` protocol (owner_id field)."""
        return self.owner_uid


__all__ = ["ChatSessionIndex"]
