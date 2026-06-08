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
    artifact is saved with the AG-UI-shape parsed blocks; state["document_ids"]
    is populated; the FilePart is removed from message.parts so ADK's
    native converter doesn't double-inject it into Gemini.

    Parse path is monkeypatched to return canned blocks — same fixture
    pattern as the AG-UI upload tests. Real ailang-parse is not called.
    """
    import json as _json

    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    # Monkeypatch ailang-parse to return canned blocks. The interceptor
    # detects this is a deterministic MIME (.docx → ailang-parse-supported)
    # and writes the structured blocks shape as the artifact body.
    canned_blocks = [
        {"type": "heading", "level": 1, "text": "Invoice INV-2026-042"},
        {"type": "paragraph", "text": "Vendor: Acme GmbH (Berlin)"},
    ]
    from tools.documents.ailang_parse import ParseOutcome

    def _fake_parse(tmp_path: str, output_format: str) -> ParseOutcome:
        assert output_format == "blocks"
        return ParseOutcome(content=canned_blocks, output_format=output_format)

    monkeypatch.setattr("tools.documents.ailang_parse._parse_file_sync", _fake_parse)

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [
            _text_part("Process this invoice"),
            _file_with_bytes_part(
                b"PK\x03\x04 fake docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                name="acme.docx",
            ),
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

    # Artifact was saved with the deterministic doc:{id}.json filename
    # AND the body is the AG-UI-shape parsed blocks (not the bytes envelope).
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
    body = _json.loads(artifact.inline_data.data.decode("utf-8"))
    assert body == canned_blocks, f"artifact body must be the parsed blocks shape (AG-UI parity), got {body!r}"


def test_a2a_file_parse_failure_falls_back_to_bytes_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ailang-parse returns an error for a deterministic MIME, the
    interceptor must fall back to the v1 bytes-envelope artifact so the
    pipeline keeps working (Gemini multimodal can still read the bytes)."""
    import json as _json

    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    from tools.documents.ailang_parse import ParseOutcome

    def _fake_parse_error(tmp_path: str, output_format: str) -> ParseOutcome:
        return ParseOutcome(error="corrupt docx structure", error_code="format", output_format=output_format)

    monkeypatch.setattr("tools.documents.ailang_parse._parse_file_sync", _fake_parse_error)

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    raw = b"PK\x03\x04 not really a docx"
    context = _build_context(
        [
            _file_with_bytes_part(
                raw,
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                name="broken.docx",
            ),
        ],
        context_id="test-session-fallback",
    )

    asyncio.run(interceptor.before_agent(context))

    expected_user = "A2A_USER_test-session-fallback"
    session = asyncio.run(
        runner.session_service.get_session(
            app_name="test_a2a_files", user_id=expected_user, session_id="test-session-fallback"
        )
    )
    doc_ids = session.state.get("document_ids", [])
    assert len(doc_ids) == 1

    doc_id = doc_ids[0]
    artifact = asyncio.run(
        runner.artifact_service.load_artifact(
            app_name="test_a2a_files",
            user_id=expected_user,
            session_id="test-session-fallback",
            filename=f"doc:{doc_id}.json",
        )
    )
    assert artifact is not None
    body = _json.loads(artifact.inline_data.data.decode("utf-8"))
    # bytes envelope: single dict with kind=a2a-inline-file
    assert isinstance(body, list) and len(body) == 1
    assert body[0].get("kind") == "a2a-inline-file", f"parse error must fall back to bytes envelope, got {body!r}"
    assert body[0].get("bytesBase64"), "bytes envelope must preserve raw bytes"


def test_a2a_file_unsupported_mime_skips_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """For MIMEs outside ailang-parse's deterministic set (e.g. text/plain,
    application/pdf), the parse step must NOT be attempted — fall straight
    through to the bytes envelope. Verifies via a sentinel-counting fake
    parser that's never invoked."""
    import json as _json

    monkeypatch.setenv("ENABLE_A2A_FILE_INPUT", "true")

    parse_call_count = {"n": 0}

    def _sentinel_parse(tmp_path: str, output_format: str) -> Any:
        parse_call_count["n"] += 1
        raise AssertionError("parse must not be called for unsupported MIME")

    monkeypatch.setattr("tools.documents.ailang_parse._parse_file_sync", _sentinel_parse)

    from protocols.a2a_file_extraction import make_file_extraction_interceptor

    runner = _build_runner()
    interceptor = make_file_extraction_interceptor(runner, app_name="test_a2a_files", user_id="a2a-public-peer")
    context = _build_context(
        [
            _file_with_bytes_part(b"hello world", mime_type="text/plain", name="note.txt"),
        ],
        context_id="test-session-skip",
    )

    asyncio.run(interceptor.before_agent(context))
    assert parse_call_count["n"] == 0, "parse must be skipped for non-deterministic MIME"

    expected_user = "A2A_USER_test-session-skip"
    session = asyncio.run(
        runner.session_service.get_session(
            app_name="test_a2a_files", user_id=expected_user, session_id="test-session-skip"
        )
    )
    doc_ids = session.state.get("document_ids", [])
    assert len(doc_ids) == 1
    doc_id = doc_ids[0]
    artifact = asyncio.run(
        runner.artifact_service.load_artifact(
            app_name="test_a2a_files",
            user_id=expected_user,
            session_id="test-session-skip",
            filename=f"doc:{doc_id}.json",
        )
    )
    assert artifact is not None
    body = _json.loads(artifact.inline_data.data.decode("utf-8"))
    assert isinstance(body, list) and body[0].get("kind") == "a2a-inline-file"


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
