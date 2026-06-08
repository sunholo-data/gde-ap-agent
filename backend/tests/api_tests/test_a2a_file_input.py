"""Tests for A2A FilePart extraction via ExecuteInterceptor.

Six tests covering the contract M1 of the A2A-FILES sprint establishes:
  - FileWithBytes is extracted, a document_id is minted, the artifact
    bucket receives `doc:{id}.json`
  - FileWithUri is registered (pointer artifact) and document_id minted
  - Oversized FileWithBytes is rejected with a comprehensible note in
    the response message (turn doesn't fail, peer is told why)
  - Unknown MIME type is rejected
  - File scheme on FileWithUri is rejected (file:///etc/passwd)
  - Text-only messages are an exact pass-through (regression guard)

The interceptor needs a real Runner + session_service to inject state.
Tests use the same minimal-LlmAgent + InMemorySessionService pattern
already established in test_a2a_invocation.py.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

import pytest


def _build_runner() -> Any:
    """Minimal Runner backed by InMemorySessionService + InMemoryArtifactService.

    Same pattern as `test_a2a_invocation.test_build_a2a_app_returns_mountable_starlette_app`
    — never actually invokes Gemini; we only exercise the interceptor's
    state + artifact effects.
    """
    from google.adk.agents import LlmAgent
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    agent = LlmAgent(
        name="probe_agent",
        model="gemini-2.5-flash",
        description="probe",
        instruction="probe",
    )
    return Runner(
        app_name="test_a2a_files",
        agent=agent,
        session_service=InMemorySessionService(),
        artifact_service=InMemoryArtifactService(),
    )


def _build_context(parts: list[Any], context_id: str = "test-session-1") -> Any:
    """Construct a minimal RequestContext with the given parts.

    a2a-sdk's RequestContext takes a MessageSendParams; we build a
    Message and wrap it. Real A2A peers send through the same path.
    """
    import uuid

    from a2a.server.agent_execution.context import RequestContext
    from a2a.types import Message, MessageSendParams

    msg = Message(
        message_id=str(uuid.uuid4()),
        role="user",
        parts=parts,
        context_id=context_id,
    )
    params = MessageSendParams(message=msg)
    return RequestContext(request=params, context_id=context_id)


def _text_part(text: str) -> Any:
    from a2a.types import Part, TextPart

    return Part(root=TextPart(text=text))


def _file_with_bytes_part(decoded: bytes, *, mime_type: str, name: str = "test.bin") -> Any:
    from a2a.types import FilePart, FileWithBytes, Part

    return Part(
        root=FilePart(
            file=FileWithBytes(
                bytes=base64.b64encode(decoded).decode("ascii"),
                mime_type=mime_type,
                name=name,
            )
        )
    )


def _file_with_uri_part(uri: str, *, mime_type: str | None = None, name: str = "test.pdf") -> Any:
    from a2a.types import FilePart, FileWithUri, Part

    return Part(root=FilePart(file=FileWithUri(uri=uri, mime_type=mime_type, name=name)))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_a2a_file_with_bytes_extracted_to_document_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A FileWithBytes part is extracted; a document_id is minted; an
    artifact is saved; state["document_ids"] is populated; the FilePart
    is removed from message.parts so ADK's native converter doesn't
    double-inject it into Gemini.
    """
    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [
            _text_part("Process this invoice"),
            _file_with_bytes_part(b"%PDF-1.4 fake invoice", mime_type="application/pdf", name="acme.pdf"),
        ]
    )

    new_context = asyncio.run(interceptor.before_agent(context))

    # FilePart was stripped; only the text part remains.
    parts = new_context.message.parts
    assert len(parts) == 1, f"expected 1 part after strip, got {len(parts)}: {parts!r}"

    # Session created with document_ids — interceptor derives user_id
    # from the context_id (matches ADK's request_converter convention).
    expected_user = "A2A_USER_test-session-1"
    session = asyncio.run(
        runner.session_service.get_session(
            app_name="test_a2a_files", user_id=expected_user, session_id="test-session-1"
        )
    )
    assert session is not None, "interceptor must create the session if missing"
    doc_ids = session.state.get("document_ids", [])
    assert len(doc_ids) == 1, f"expected 1 document_id, got {doc_ids!r}"

    # Artifact was saved with the deterministic doc:{id}.json filename.
    doc_id = doc_ids[0]
    artifact = asyncio.run(
        runner.artifact_service.load_artifact(
            app_name="test_a2a_files",
            user_id=expected_user,
            session_id="test-session-1",
            filename=f"doc:{doc_id}.json",
        )
    )
    assert artifact is not None, "artifact_service must have the doc:{id}.json blob"


def test_a2a_file_with_uri_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """A FileWithUri part is accepted: doc_id minted, URI-pointer artifact
    saved; the actual fetch happens later (the loader path)."""
    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [_file_with_uri_part("gs://demo-invoices/acme.pdf", mime_type="application/pdf", name="acme.pdf")],
        context_id="test-session-uri",
    )

    new_context = asyncio.run(interceptor.before_agent(context))

    # FilePart was stripped (no text part either; legitimately empty
    # parts list after extraction).
    assert len(new_context.message.parts) == 0

    expected_user = "A2A_USER_test-session-uri"
    session = asyncio.run(
        runner.session_service.get_session(
            app_name="test_a2a_files",
            user_id=expected_user,
            session_id="test-session-uri",
        )
    )
    assert session is not None
    doc_ids = session.state.get("document_ids", [])
    assert len(doc_ids) == 1

    artifact = asyncio.run(
        runner.artifact_service.load_artifact(
            app_name="test_a2a_files",
            user_id=expected_user,
            session_id="test-session-uri",
            filename=f"doc:{doc_ids[0]}.json",
        )
    )
    assert artifact is not None


def test_a2a_oversized_file_rejected_with_synthetic_note(monkeypatch: pytest.MonkeyPatch) -> None:
    """A FileWithBytes over the size cap is rejected; a synthetic TextPart
    explains why so the peer (and the orchestrator) see useful feedback."""
    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")
    monkeypatch.setenv("A2A_FILE_MAX_BYTES", "1024")  # 1 KB cap for the test

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    big_bytes = b"X" * 2048  # 2 KB > 1 KB cap
    context = _build_context(
        [_file_with_bytes_part(big_bytes, mime_type="application/pdf", name="big.pdf")],
        context_id="test-session-big",
    )

    new_context = asyncio.run(interceptor.before_agent(context))

    # No document_id minted, but a synthetic TextPart with the reason was appended.
    parts = new_context.message.parts
    assert len(parts) == 1, f"expected 1 (synthetic) part, got {len(parts)}"
    from a2a.types import TextPart

    root = getattr(parts[0], "root", parts[0])
    assert isinstance(root, TextPart)
    assert "big.pdf" in root.text
    assert "exceeds" in root.text.lower() or "size" in root.text.lower()


def test_a2a_unknown_mime_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown MIME on FileWithBytes is rejected; synthetic TextPart names it."""
    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [_file_with_bytes_part(b"PK\x03\x04evil", mime_type="application/x-evil", name="evil.bin")],
        context_id="test-session-mime",
    )

    new_context = asyncio.run(interceptor.before_agent(context))
    parts = new_context.message.parts
    assert len(parts) == 1  # synthetic note
    from a2a.types import TextPart

    root = getattr(parts[0], "root", parts[0])
    assert isinstance(root, TextPart)
    assert "evil.bin" in root.text
    assert "MIME" in root.text or "format" in root.text.lower()


def test_a2a_file_uri_with_disallowed_scheme_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`file://` URI rejected — no local-file-read attack surface."""
    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [_file_with_uri_part("file:///etc/passwd", mime_type="text/plain", name="passwd")],
        context_id="test-session-scheme",
    )

    new_context = asyncio.run(interceptor.before_agent(context))
    parts = new_context.message.parts
    assert len(parts) == 1  # synthetic note only
    from a2a.types import TextPart

    root = getattr(parts[0], "root", parts[0])
    assert isinstance(root, TextPart)
    assert "passwd" in root.text
    assert "scheme" in root.text.lower() or "https" in root.text.lower()


def test_a2a_text_only_still_passes_through_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """A message with only TextParts is byte-identical pre/post interceptor.
    This is the regression guard for all A2A-INVOKE tests we don't want
    to break.
    """
    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [_text_part("Process this invoice"), _text_part("urgent")],
        context_id="test-session-text",
    )
    original_parts = list(context.message.parts)

    new_context = asyncio.run(interceptor.before_agent(context))

    # No mutation, no session creation, no doc_ids.
    assert new_context.message.parts == original_parts
    # Session should NOT have been created (no FileParts means no work).
    session = asyncio.run(
        runner.session_service.get_session(
            app_name="test_a2a_files",
            user_id="a2a-public-peer",
            session_id="test-session-text",
        )
    )
    assert session is None, "interceptor must not create session when no FileParts present"


def test_a2a_interceptor_is_noop_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """ENABLE_A2A_FILE_INPUT=false → interceptor is a no-op even when
    FileParts are present. Clean-rollback contract.
    """
    monkeypatch.delenv("ENABLE_A2A_FILE_INPUT", raising=False)

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [
            _text_part("Process this invoice"),
            _file_with_bytes_part(b"data", mime_type="application/pdf", name="x.pdf"),
        ],
        context_id="test-session-off",
    )
    original_part_count = len(context.message.parts)

    new_context = asyncio.run(interceptor.before_agent(context))

    # Flag off → no mutation, no session.
    assert len(new_context.message.parts) == original_part_count
    session = asyncio.run(
        runner.session_service.get_session(
            app_name="test_a2a_files",
            user_id="a2a-public-peer",
            session_id="test-session-off",
        )
    )
    assert session is None
