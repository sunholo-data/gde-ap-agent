"""Seed the five default platform-owned skills into Firestore.

Called by POST /api/admin/seed-platform-skills, which is hit once per
deploy by the Cloud Build seed step. Idempotent: any template whose
`name` already exists as a platform-owned skill is skipped, so repeat
runs are safe (and the expected steady state).

Template layout (one directory per skill):
    backend/skills/templates/<name>/SKILL.md    # YAML frontmatter + markdown body

The frontmatter supplies name/description/metadata; the body is the
agent instruction. Platform-owned skills are always created with
owner_id=PLATFORM_OWNER_UID and accessControl={type: public}.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from config.local_mode import is_local_mode
from db import firestore as fs
from skills import skill_config
from skills.platform import PLATFORM_OWNER_UID
from skills.slugify import slugify, unique_slug

logger = logging.getLogger(__name__)

# Email recorded as the owner of platform-seeded skills.
# Resolved lazily by _resolve_owner_email() so module import never raises —
# the validation fires at seed() call time where the error message is actionable.
PLATFORM_OWNER_EMAIL = os.environ.get("PLATFORM_OWNER_EMAIL", "platform@aitanalabs.com")
DEFAULT_TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "skills" / "templates"


@dataclass
class SeedSummary:
    created: int = 0
    skipped: int = 0
    purged: int = 0
    failed: list[str] = field(default_factory=list)
    tool_permissions_wildcard_seeded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "purged": self.purged,
            "failed": self.failed,
            "tool_permissions_wildcard_seeded": self.tool_permissions_wildcard_seeded,
        }


def _parse_template(skill_md: Path) -> dict[str, Any]:
    """Parse a SKILL.md file into a dict with `name`, `description`, `instructions`, `metadata`.

    Raises ValueError on malformed frontmatter.
    """
    text = skill_md.read_text()
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter in {skill_md}")

    # Split on the closing --- of the frontmatter. [0] is "", [1] is the
    # frontmatter YAML, [2]+ is the body.
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"missing frontmatter close fence in {skill_md}")

    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML frontmatter in {skill_md}: {e}") from e

    if "name" not in front:
        raise ValueError(f"frontmatter missing 'name' in {skill_md}")

    return {
        "name": front["name"],
        "description": (front.get("description") or "").strip(),
        "instructions": parts[2].strip(),
        "metadata": front.get("metadata") or {},
    }


def _existing_platform_skill_names() -> set[str]:
    configs = skill_config.list_skills(owner_id=PLATFORM_OWNER_UID, limit=200)
    return {c.name for c in configs}


def _ensure_tool_permissions_wildcard() -> bool:
    """Idempotent: write a wildcard allow-all rule if none exists.

    Returns True if the doc was created, False if it already existed.
    Mirrors the wildcard that local_fixture.py seeds for LOCAL_MODE so dev
    and prod stay consistent (item #20 from the CPH Uni upstream feedback).
    """
    existing = fs.get_document("tool_permissions", "*")
    if existing is not None:
        return False
    fs.set_document(
        "tool_permissions",
        "*",
        {
            "type": "wildcard",
            "tools": ["*"],
            "denied": [],
            "created_by": "platform_seed",
        },
    )
    logger.info("platform_seed: seeded tool_permissions wildcard allow-all rule")
    return True


def _resolve_owner_email() -> str:
    """Return the platform owner email, with fail-loud validation.

    Forks MUST set PLATFORM_OWNER_EMAIL. The module-level default keeps
    the Aitana fallback so tests can import without env vars, but the
    first real seed() call in a non-LOCAL_MODE environment will surface a
    clear error instead of silently shipping skills owned by Aitana.
    """
    email = os.environ.get("PLATFORM_OWNER_EMAIL", "")
    if email:
        return email
    if is_local_mode():
        return "platform@localhost"
    raise RuntimeError(
        "PLATFORM_OWNER_EMAIL env var is required in non-LOCAL_MODE. "
        "Set it to the platform admin email for this deployment "
        "(e.g. platform@yourdomain.com). "
        "Forks: add it to your Cloud Build substitutions as _PLATFORM_OWNER_EMAIL."
    )


def seed(templates_root: Path | None = None) -> SeedSummary:
    """Seed platform skills from disk templates. Idempotent by `name`.

    Also purges any platform-owned skills in Firestore whose names are
    NOT present in the current template set — this keeps Firestore in
    sync when templates are deleted from the repo (e.g. when a fork
    removes non-AP defaults). The purge fires before upserts.

    Returns a SeedSummary counting created/skipped/purged/failed entries.
    """
    owner_email = _resolve_owner_email()
    root = templates_root or DEFAULT_TEMPLATES_ROOT
    summary = SeedSummary()
    summary.tool_permissions_wildcard_seeded = _ensure_tool_permissions_wildcard()
    existing = _existing_platform_skill_names()

    # Build the set of names that *should* exist after this seed.
    template_names: set[str] = set()
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            parsed = _parse_template(skill_md)
            template_names.add(parsed["name"])
        except Exception:  # noqa: BLE001 — parse errors handled below
            pass

    # Purge platform skills that are no longer in templates.
    stale = existing - template_names
    for name in stale:
        try:
            configs = skill_config.list_skills(owner_id=PLATFORM_OWNER_UID, limit=200)
            for cfg in configs:
                if cfg.name == name:
                    skill_config.delete_skill(cfg.skillId)
                    logger.info("platform_seed: purged stale platform skill %r (%s)", name, cfg.skillId)
                    summary.purged += 1
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning("platform_seed: failed to purge %s: %s", name, e)

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            parsed = _parse_template(skill_md)
        except Exception as e:
            logger.warning("platform_seed: failed to parse %s: %s", skill_md, e)
            summary.failed.append(child.name)
            continue

        if parsed["name"] in existing:
            summary.skipped += 1
            continue

        try:
            # Generate slug at creation time so the friendly URL
            # /chat/@gde-ap-agent/{slug} works without a follow-up
            # backfill. unique_slug guards against collisions if a
            # template name slugifies to the same value as another
            # platform skill (defensive — current templates don't).
            slug = unique_slug(PLATFORM_OWNER_UID, slugify(parsed["name"]))
            skill_config.create_skill(
                name=parsed["name"],
                description=parsed["description"],
                instructions=parsed["instructions"],
                owner_id=PLATFORM_OWNER_UID,
                owner_email=owner_email,
                accessControl={"type": "public"},
                skillMetadata=parsed["metadata"],
                slug=slug,
            )
            summary.created += 1
        except Exception as e:
            logger.warning("platform_seed: failed to create %s: %s", parsed["name"], e)
            summary.failed.append(parsed["name"])

    return summary
