"""Unit tests for backend/admin/platform_seed.py.

The seeder reads backend/skills/templates/*/SKILL.md, parses YAML
frontmatter + markdown body, and creates each as a platform-owned
public skill. Idempotent: skips any template whose `name` already exists
in Firestore.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from admin.platform_seed import (
    SeedSummary,
    _ensure_tool_permissions_wildcard,
    _parse_template,
    seed,
)
from db.models import SkillConfig


@pytest.fixture(autouse=True)
def _platform_owner_email(monkeypatch):
    """Provide PLATFORM_OWNER_EMAIL so seed() doesn't raise in non-LOCAL_MODE."""
    monkeypatch.setenv("PLATFORM_OWNER_EMAIL", "platform@test.com")


def _fake_template_dir(tmp_path, name: str, body: str = "Be helpful.", metadata: dict | None = None):
    md = metadata or {"model": "gemini-2.5-flash"}
    content = "---\n"
    content += f"name: {name}\n"
    content += "description: >\n  Do things.\n"
    content += "metadata:\n"
    for k, v in md.items():
        content += f"  {k}: {v}\n"
    content += "---\n\n"
    content += body + "\n"
    skill_dir = tmp_path / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(content)
    return tmp_path


def _make_config(name: str, **overrides) -> SkillConfig:
    defaults = {
        "name": name,
        "skillId": f"platform-{name}",
        "ownerId": "aitana-platform",
        "ownerEmail": "platform@aitanalabs.com",
        "accessControl": {"type": "public"},
    }
    defaults.update(overrides)
    return SkillConfig(**defaults)


# === _parse_template ===


def test_parse_template_extracts_frontmatter_and_body(tmp_path):
    _fake_template_dir(tmp_path, "alpha", body="Help the user.")
    parsed = _parse_template(tmp_path / "alpha" / "SKILL.md")
    assert parsed["name"] == "alpha"
    assert "Help the user" in parsed["instructions"]
    assert parsed["metadata"]["model"] == "gemini-2.5-flash"


def test_parse_template_missing_frontmatter_raises(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("Just body, no frontmatter\n")
    with pytest.raises(ValueError, match="frontmatter"):
        _parse_template(bad / "SKILL.md")


# === seed() ===


def test_seed_empty_firestore_creates_all(tmp_path):
    """First run: no existing platform skills → create one for each template."""
    _fake_template_dir(tmp_path, "alpha")
    _fake_template_dir(tmp_path, "beta")

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.create_skill") as mock_create,
    ):
        mock_list.return_value = []  # no existing platform skills
        mock_create.side_effect = lambda **kw: _make_config(name=kw["name"])

        summary = seed(templates_root=tmp_path)

    assert summary.created == 2
    assert summary.skipped == 0
    assert summary.failed == []
    # Verify each create call sets the right owner + access
    for call in mock_create.call_args_list:
        kwargs = call.kwargs
        assert kwargs["owner_id"] == "aitana-platform"
        assert kwargs["owner_email"]  # non-empty — value comes from PLATFORM_OWNER_EMAIL env
        assert kwargs["accessControl"] == {"type": "public"}


def test_seed_idempotent_skips_existing(tmp_path):
    """Second run: templates already present → skip, don't recreate."""
    _fake_template_dir(tmp_path, "alpha")
    _fake_template_dir(tmp_path, "beta")

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.create_skill") as mock_create,
    ):
        mock_list.return_value = [_make_config("alpha"), _make_config("beta")]
        summary = seed(templates_root=tmp_path)

    assert summary.created == 0
    assert summary.skipped == 2
    assert summary.failed == []
    mock_create.assert_not_called()


def test_seed_malformed_template_is_failed_not_raise(tmp_path):
    """One bad template should not abort the whole run."""
    _fake_template_dir(tmp_path, "alpha")  # valid
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "SKILL.md").write_text("no frontmatter here\n")

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.create_skill") as mock_create,
    ):
        mock_list.return_value = []
        mock_create.side_effect = lambda **kw: _make_config(name=kw["name"])

        summary = seed(templates_root=tmp_path)

    assert summary.created == 1
    assert summary.skipped == 0
    assert "broken" in summary.failed


def test_seed_summary_is_a_dataclass():
    s = SeedSummary(created=3, skipped=2, failed=["x"])
    assert s.created == 3
    assert s.skipped == 2
    assert s.failed == ["x"]


# === _ensure_tool_permissions_wildcard ===


def test_wildcard_seed_creates_doc_when_absent():
    """First run: no wildcard doc exists → create it, return True."""
    with (
        patch("admin.platform_seed.fs.get_document", return_value=None) as mock_get,
        patch("admin.platform_seed.fs.set_document") as mock_set,
    ):
        result = _ensure_tool_permissions_wildcard()

    assert result is True
    mock_get.assert_called_once_with("tool_permissions", "*")
    mock_set.assert_called_once()
    _, args_doc_id, payload = mock_set.call_args.args
    assert args_doc_id == "*"
    assert payload["tools"] == ["*"]
    assert payload["denied"] == []
    assert payload["type"] == "wildcard"


def test_wildcard_seed_idempotent_skips_when_present():
    """Second run: wildcard doc already exists → skip, return False."""
    existing = {"type": "wildcard", "tools": ["*"], "denied": [], "created_by": "platform_seed"}
    with (
        patch("admin.platform_seed.fs.get_document", return_value=existing),
        patch("admin.platform_seed.fs.set_document") as mock_set,
    ):
        result = _ensure_tool_permissions_wildcard()

    assert result is False
    mock_set.assert_not_called()


def test_seed_summary_includes_wildcard_flag(tmp_path):
    """seed() surfaces the wildcard-seeded flag in its summary."""
    _fake_template_dir(tmp_path, "alpha")

    with (
        patch("admin.platform_seed.skill_config.list_skills", return_value=[]),
        patch("admin.platform_seed.skill_config.create_skill", side_effect=lambda **kw: _make_config(name=kw["name"])),
        patch("admin.platform_seed.fs.get_document", return_value=None),
        patch("admin.platform_seed.fs.set_document"),
    ):
        summary = seed(templates_root=tmp_path)

    assert summary.tool_permissions_wildcard_seeded is True
    d = summary.as_dict()
    assert "tool_permissions_wildcard_seeded" in d


def test_seed_raises_when_platform_owner_email_unset(tmp_path, monkeypatch):
    """seed() must raise RuntimeError (not silently use Aitana email) when
    PLATFORM_OWNER_EMAIL is unset in non-LOCAL_MODE — item #3 of the template
    fork-ergonomics upstream feedback."""
    monkeypatch.delenv("PLATFORM_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("LOCAL_MODE", raising=False)

    with (
        patch("admin.platform_seed.skill_config.list_skills", return_value=[]),
        patch("admin.platform_seed.fs.get_document", return_value={"type": "wildcard"}),
    ):
        with pytest.raises(RuntimeError, match="PLATFORM_OWNER_EMAIL"):
            seed(templates_root=tmp_path)


def test_seed_sets_slug_at_creation(tmp_path):
    """Each newly seeded skill must have a slug — otherwise the friendly
    URL /chat/@aitana-platform/{slug} 404s and we have to backfill in every
    fresh environment. Regression for the bug where test/prod were cut
    without slugs and the marketplace links broke."""
    _fake_template_dir(tmp_path, "general-assistant")
    _fake_template_dir(tmp_path, "code-assistant")

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.create_skill") as mock_create,
        patch("admin.platform_seed.unique_slug", side_effect=lambda _o, base, **_: base),
    ):
        mock_list.return_value = []
        mock_create.side_effect = lambda **kw: _make_config(name=kw["name"])

        summary = seed(templates_root=tmp_path)

    assert summary.created == 2
    slugs = {call.kwargs["slug"] for call in mock_create.call_args_list}
    assert slugs == {"general-assistant", "code-assistant"}
