"""Bridge from channel webhook to `process_skill_request`.

Channels arrive at this layer with a Firebase UID (from
`IdentityResolver`) and a normalised `InboundMessage`. This module:

  1. Synthesises a minimal `User` + `AccessContext` (no JWT involved —
     identity already verified by the channel's webhook signature)
  2. Calls `skills.skill_processor.process_skill_request`
  3. Consumes the AG-UI event stream and concatenates `TEXT_MESSAGE_CONTENT`
     deltas
  4. Returns the assistant reply as one string

Channels are non-streaming by default (collect-then-send). Discord
overrides `send` to live-edit messages by consuming the same stream
through a different entry point (`_skill_invoke_streaming`, M2).
"""

from __future__ import annotations

import logging
from typing import Any

from auth.access_context import build_access_context
from auth.firebase_auth import User

logger = logging.getLogger(__name__)


async def invoke_skill_collected(
    *,
    skill_id: str,
    firebase_uid: str,
    message: str,
    attachment_ids: list[str] | None = None,
    channel_name: str,
    channel_metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> str:
    """Run the skill end-to-end and return the assembled assistant text.

    `channel_name` and `channel_metadata` are logged on every invocation
    so trace context links a channel's webhook to the skill it triggered.
    Once the audit-log extension (v6.2.0 audit-log-and-analytics.md)
    lands, both fields flow into the per-firing audit record without
    further signature changes on this function.

    `attachment_ids` are the doc IDs created by `AttachmentPipeline`;
    `process_skill_request` accepts them as `document_ids` so the agent
    can read the parsed content.
    """
    # Late import to avoid circular load (skill_processor imports adk
    # which initialises Vertex AI session services on import).
    from skills.skill_processor import SkillNotFoundError, process_skill_request

    user = _build_channel_user(firebase_uid)
    access = build_access_context(user)
    logger.info(
        "channel_invoke channel=%s skill=%s uid=%s metadata_keys=%s",
        channel_name,
        skill_id,
        firebase_uid,
        sorted((channel_metadata or {}).keys()),
    )

    pieces: list[str] = []
    try:
        async for event in process_skill_request(
            skill_id=skill_id,
            user=user,
            access=access,
            session_id=session_id,
            message=message,
            document_ids=attachment_ids or None,
        ):
            if event.get("type") == "TEXT_MESSAGE_CONTENT":
                delta = event.get("delta")
                if isinstance(delta, str):
                    pieces.append(delta)
    except SkillNotFoundError:
        logger.warning(
            "channel=%s skill_not_found skill_id=%s uid=%s metadata=%s",
            channel_name,
            skill_id,
            firebase_uid,
            channel_metadata,
        )
        return f"Skill {skill_id!r} is not available. Use /skills to list available skills."

    if not pieces:
        return "(no response)"
    return "".join(pieces)


def _build_channel_user(firebase_uid: str) -> User:
    """Construct a `User` for skill processing from a channel UID.

    Channels resolve their wire-format user ID to a Firebase UID via
    `IdentityResolver`. The skill processor needs a richer `User`
    (email, domain, group_tags) for access checks and per-domain
    bucket resolution.

    TODO(channels M2/M3): read `channel_identities/{channel}_{user_id}`
    advisory fields (email, domain, group_tags) and populate User
    accordingly. Until then, channel-authed users hitting
    domain-restricted or tagged skills will be denied — they only
    match public, owner, or specific-email-list skills, and the
    last only if the email field is set on the channel_identity
    record. Acceptable for M1 framework where no real channel is
    wired; Discord adapter (M2) is the first place this gap surfaces.
    """
    return User(uid=firebase_uid, email="", domain="", group_tags=frozenset())


__all__ = ["invoke_skill_collected"]
