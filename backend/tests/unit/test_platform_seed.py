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
        "description": "Pre-existing description.",
        "instructions": "Pre-existing instructions.",
        "skillId": f"platform-{name}",
        "ownerId": "gde-ap-agent",
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
        assert kwargs["owner_id"] == "gde-ap-agent"
        assert kwargs["owner_email"]  # non-empty — value comes from PLATFORM_OWNER_EMAIL env
        assert kwargs["accessControl"] == {"type": "public"}


def test_seed_refreshes_template_fields_on_existing(tmp_path):
    """Second run: templates already present → refresh template-sourced
    fields (description, instructions, skillMetadata) so SKILL.md edits
    (eg. new metadata.structuredInput) propagate to Firestore on deploy.
    Owner-customisable fields (slug, accessControl, displayName) are
    untouched. See multi-agent-inspector-ux sprint follow-up.
    """
    _fake_template_dir(tmp_path, "alpha", metadata={"model": "gemini-2.5-flash"})
    _fake_template_dir(tmp_path, "beta", metadata={"model": "gemini-2.5-flash"})

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.create_skill") as mock_create,
        patch("admin.platform_seed.skill_config.update_skill") as mock_update,
    ):
        mock_list.return_value = [_make_config("alpha"), _make_config("beta")]
        summary = seed(templates_root=tmp_path)

    assert summary.created == 0
    assert summary.updated == 2
    assert summary.failed == []
    mock_create.assert_not_called()
    # Each existing skill received the refresh call with template-sourced fields.
    assert mock_update.call_count == 2
    call_args = mock_update.call_args_list[0]
    updated_id, updated_payload = call_args.args
    assert updated_id == "platform-alpha"
    assert set(updated_payload.keys()) == {"description", "instructions", "skillMetadata"}
    assert updated_payload["skillMetadata"] == {"model": "gemini-2.5-flash"}


def test_seed_purges_stale_platform_skill_uses_snake_case_id(tmp_path):
    """Regression: SkillConfig exposes the id as `skill_id` (Pydantic
    field name), not `skillId` (camelCase alias). The original code
    accessed `cfg.skillId` which raised AttributeError, caught silently
    by the broad except, leaving every stale skill behind every seed
    run. Observed in dev as "docparse" surviving the rename to
    "invoice-extractor" until this fix.
    """
    # Single template "alpha"; Firestore has both "alpha" and stale "docparse"
    _fake_template_dir(tmp_path, "alpha")

    alpha_cfg = _make_config("alpha", skillId="platform-alpha")
    stale_cfg = _make_config("docparse", skillId="platform-docparse")

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.delete_skill") as mock_delete,
        patch("admin.platform_seed.skill_config.update_skill"),
        patch("admin.platform_seed.skill_config.create_skill"),
    ):
        mock_list.return_value = [alpha_cfg, stale_cfg]
        summary = seed(templates_root=tmp_path)

    assert summary.purged == 1
    assert summary.failed == [], f"expected no failures, got {summary.failed!r}"
    # The actual delete must be called with the snake_case id from the config
    mock_delete.assert_called_once_with("platform-docparse")


def test_seed_refresh_failure_does_not_abort(tmp_path):
    """If update_skill raises for one template, the run continues and
    the failure is recorded — never bring down a deploy on a refresh."""
    _fake_template_dir(tmp_path, "alpha")
    _fake_template_dir(tmp_path, "beta")

    with (
        patch("admin.platform_seed.skill_config.list_skills") as mock_list,
        patch("admin.platform_seed.skill_config.create_skill") as mock_create,
        patch("admin.platform_seed.skill_config.update_skill") as mock_update,
    ):
        mock_list.return_value = [_make_config("alpha"), _make_config("beta")]
        mock_update.side_effect = [RuntimeError("Firestore unavailable"), None]
        summary = seed(templates_root=tmp_path)

    assert summary.updated == 1
    assert summary.failed == ["alpha"]
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
    URL /chat/@gde-ap-agent/{slug} 404s and we have to backfill in every
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


# === WORKFLOW-PIPELINE M2: ap-pipeline template ===


def test_ap_pipeline_template_parses_with_sequential_agent_type():
    """The real ap-pipeline/SKILL.md must parse with agentType=sequential
    and list the three specialist sub-skills. If this breaks, the
    SequentialAgent build path in create_agent gets bypassed silently
    and the pipeline reverts to LlmAgent behaviour (the bug we're fixing).
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    template = repo_root / "backend" / "skills" / "templates" / "ap-pipeline" / "SKILL.md"
    assert template.exists(), f"missing template at {template}"

    parsed = _parse_template(template)
    assert parsed["name"] == "ap-pipeline"
    metadata = parsed["metadata"]
    assert metadata.get("agentType") == "sequential"
    sub_skills = metadata.get("subSkills") or []
    assert sub_skills == ["invoice-extractor", "ap-validator", "ap-poster"], (
        f"ap-pipeline must walk Extract → Validate → Post in order, got {sub_skills!r}"
    )


def test_ap_orchestrator_template_now_points_to_ap_pipeline():
    """ap-orchestrator must transfer to ap-pipeline (the SequentialAgent)
    rather than the three specialists directly — otherwise the model can
    stop after one transfer like it did before the WORKFLOW-PIPELINE
    refactor.
    """
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    template = repo_root / "backend" / "skills" / "templates" / "ap-orchestrator" / "SKILL.md"
    parsed = _parse_template(template)
    sub_skills = parsed["metadata"].get("subSkills") or []
    assert sub_skills == ["ap-pipeline"], f"orchestrator should delegate to ap-pipeline only, got {sub_skills!r}"


def test_ap_pipeline_metadata_round_trips_through_skill_metadata_model():
    """The metadata dict parsed from ap-pipeline/SKILL.md must validate
    cleanly through SkillMetadata (Pydantic with populate_by_name=True)
    so platform_seed's create_skill call doesn't reject the new
    agentType field.
    """
    from pathlib import Path

    from db.models import SkillMetadata

    repo_root = Path(__file__).resolve().parents[3]
    template = repo_root / "backend" / "skills" / "templates" / "ap-pipeline" / "SKILL.md"
    parsed = _parse_template(template)
    md = SkillMetadata.model_validate(parsed["metadata"])
    assert md.agent_type == "sequential"
    assert md.sub_skills == ["invoice-extractor", "ap-validator", "ap-poster"]
