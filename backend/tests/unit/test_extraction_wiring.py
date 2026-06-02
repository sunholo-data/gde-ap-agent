"""Tests for SCHEMA-ENFORCE M2 — Gemini 2.x/3.x config branching + before-agent wiring.

The Gemini 3.x structured-output API ships with a different config
payload shape vs 2.x. This test module locks the branching behaviour
of `_extraction_config_for_model` and the before-agent state setter
that wires `metadata.extraction_schema` into session state.
"""

from __future__ import annotations

from db.models import SkillConfig, SkillMetadata
from tools.structured_extraction import _extraction_config_for_model


class TestExtractionConfigForModel:
    """Verified empirically — both 2.x and 3.x families accept the
    legacy 2.x config shape via google-genai 1.73.1. The new
    response_format shape from the API docs isn't yet exposed by the
    SDK's GenerateContentConfig Pydantic model. See the docstring on
    `_extraction_config_for_model` for the probe trail.
    """

    SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}}

    def test_gemini_25_flash_uses_legacy_keys(self):
        cfg = _extraction_config_for_model("gemini-2.5-flash", self.SCHEMA)
        assert cfg == {
            "response_mime_type": "application/json",
            "response_schema": self.SCHEMA,
        }

    def test_gemini_25_flash_no_schema_drops_schema_key(self):
        cfg = _extraction_config_for_model("gemini-2.5-flash", None)
        assert cfg == {"response_mime_type": "application/json"}
        assert "response_schema" not in cfg

    def test_gemini_3_flash_also_uses_legacy_keys(self):
        cfg = _extraction_config_for_model("gemini-3-flash", self.SCHEMA)
        assert cfg == {
            "response_mime_type": "application/json",
            "response_schema": self.SCHEMA,
        }

    def test_gemini_35_flash_uses_legacy_keys(self):
        cfg = _extraction_config_for_model("gemini-3.5-flash", self.SCHEMA)
        assert "response_schema" in cfg

    def test_gemini_31_flash_lite_uses_legacy_keys(self):
        cfg = _extraction_config_for_model("gemini-3.1-flash-lite", self.SCHEMA)
        assert "response_schema" in cfg

    def test_unknown_model_does_not_crash(self):
        cfg = _extraction_config_for_model("some-future-model", self.SCHEMA)
        assert "response_mime_type" in cfg

    def test_empty_model_string_does_not_crash(self):
        cfg = _extraction_config_for_model("", self.SCHEMA)
        assert "response_mime_type" in cfg


class TestResolveExtractionSchemaForSkill:
    """Resolution at agent build time — name, inline, unknown, None."""

    def _config(self, extraction_schema):
        return SkillConfig(
            skillId="test-skill",
            name="test-skill",
            description="x",
            instructions="y",
            displayName="Test",
            ownerEmail="t@e.com",
            ownerId="u1",
            skillMetadata=SkillMetadata(extraction_schema=extraction_schema),
        )

    def test_named_reference_resolves(self):
        from adk.agent import _resolve_extraction_schema_for_skill

        schema = _resolve_extraction_schema_for_skill(self._config("ap_invoice"))
        assert schema is not None
        assert schema["type"] == "object"
        assert "vendor_name" in schema["properties"]

    def test_inline_dict_passes_through(self):
        from adk.agent import _resolve_extraction_schema_for_skill

        inline = {"type": "object", "properties": {"x": {"type": "string"}}}
        schema = _resolve_extraction_schema_for_skill(self._config(inline))
        assert schema == inline

    def test_none_returns_none(self):
        from adk.agent import _resolve_extraction_schema_for_skill

        assert _resolve_extraction_schema_for_skill(self._config(None)) is None

    def test_unknown_name_logs_warning_returns_none(self, caplog):
        """SKILL.md typos shouldn't take down the agent — log + no-op."""
        import logging

        from adk.agent import _resolve_extraction_schema_for_skill

        with caplog.at_level(logging.WARNING):
            schema = _resolve_extraction_schema_for_skill(self._config("not_a_real_schema"))
        assert schema is None
        assert any("not_a_real_schema" in r.message for r in caplog.records)


class TestSetExtractionSchemaInState:
    """Before-agent setter writes app:extraction_schema."""

    def _fake_context(self):
        class FakeCtx:
            def __init__(self):
                self.state = {}

        return FakeCtx()

    def test_sets_schema_when_present(self):
        from adk.agent import _set_extraction_schema_in_state

        ctx = self._fake_context()
        schema = {"type": "object"}
        _set_extraction_schema_in_state(ctx, schema)
        assert ctx.state["app:extraction_schema"] is schema

    def test_none_overrides_prior_value(self):
        """Defensive: clearing prevents schema leakage between skills."""
        from adk.agent import _set_extraction_schema_in_state

        ctx = self._fake_context()
        ctx.state["app:extraction_schema"] = {"leftover": True}
        _set_extraction_schema_in_state(ctx, None)
        assert ctx.state["app:extraction_schema"] is None

    def test_no_state_no_op(self):
        from adk.agent import _set_extraction_schema_in_state

        class CtxNoState:
            pass

        # Must not raise even though there's no .state attribute
        _set_extraction_schema_in_state(CtxNoState(), {"type": "object"})
