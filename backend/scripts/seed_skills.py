"""Seed Firestore with skill templates from backend/skills/templates/.

Idempotent: skips skills that already exist (matched by name).

Usage:
    uv run python scripts/seed_skills.py --owner-uid <firebase-uid> [--dry-run]

    # Or via env:
    SEED_OWNER_UID=<uid> uv run python scripts/seed_skills.py

The `--owner-uid` value must be a real Firebase uid in the target project.
The current dev uid is recorded in `docs/ops/dev-accounts.md`. Running without
a uid is refused — seeded skills would otherwise be orphaned under v6's
ownership model (AUTH-PERMISSIONS M2) and unreachable to their intended owner.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

# Add backend root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set the GCP project BEFORE importing db.firestore — the Firestore client
# reads GOOGLE_CLOUD_PROJECT at construction time.
#
# Resolution order (item #2 from template-fork-ergonomics):
#   1. PLATFORM_SEED_PROJECT env var (fork override)
#   2. GOOGLE_CLOUD_PROJECT env var (ADC / Cloud Run default)
#   3. pin_project_for_env("dev") for Aitana devs on a local shell where
#      GCP_PROJECT may be shadowed (gotcha_gcp_project_env_shadow)
_seed_project = os.environ.get("PLATFORM_SEED_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
if _seed_project:
    os.environ["GOOGLE_CLOUD_PROJECT"] = _seed_project
else:
    # Fall back to Aitana dev project — avoids the shadow-project gotcha
    # for Aitana developers. Forks should set PLATFORM_SEED_PROJECT instead.
    from scripts._env import pin_project_for_env

    pin_project_for_env("dev")

from db import firestore as fs  # noqa: E402
from skills.skill_config import COLLECTION, create_skill  # noqa: E402

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "skills" / "templates"


def parse_skill_md(skill_dir: Path) -> dict:
    """Parse a SKILL.md file into frontmatter + instructions."""
    skill_md = (skill_dir / "SKILL.md").read_text()
    parts = skill_md.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid SKILL.md format in {skill_dir}")

    frontmatter = yaml.safe_load(parts[1])
    instructions = parts[2].strip()

    # Load references/ if present
    references = {}
    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        for f in refs_dir.iterdir():
            if f.is_file():
                references[f.name] = f.read_text()

    name = frontmatter["name"]
    return {
        "name": name,
        "description": frontmatter["description"].strip(),
        "instructions": instructions,
        "metadata": frontmatter.get("metadata", {}),
        "references": references,
        # Human-readable display fields — read from frontmatter (item #1).
        # Falls back to sensible defaults so old templates without these
        # keys still seed correctly.
        "display_name": frontmatter.get("display_name") or name,
        "tags": frontmatter.get("tags") or [],
        "initial_message": frontmatter.get("initial_message") or "",
    }


def existing_skills_by_name() -> dict[str, dict]:
    """Map skill name → Firestore doc dict for existing skills."""
    docs = fs.query_documents(COLLECTION, limit=200)
    return {doc["name"]: doc for doc in docs if doc.get("name")}


def seed(
    owner_uid: str,
    owner_email: str = "",
    dry_run: bool = False,
    update_existing: bool = False,
) -> None:
    if not owner_uid:
        print("ERROR: owner uid is required. Pass --owner-uid <firebase-uid> or set SEED_OWNER_UID.")
        print("       Dev uid is recorded in docs/ops/dev-accounts.md.")
        sys.exit(2)

    if not TEMPLATES_DIR.exists():
        print(f"Templates directory not found: {TEMPLATES_DIR}")
        sys.exit(1)

    existing = {} if dry_run else existing_skills_by_name()
    template_dirs = sorted(d for d in TEMPLATES_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists())

    # Imported lazily to keep --dry-run fast without booting Firestore.
    from skills.skill_config import update_skill

    for skill_dir in template_dirs:
        parsed = parse_skill_md(skill_dir)
        name = parsed["name"]

        if name in existing:
            if not update_existing:
                print(f"  SKIP  {name} (already exists; pass --update-existing to push template changes)")
                continue
            doc = existing[name]
            # firestore.query_documents stamps the doc id as `__id`.
            skill_id = doc.get("__id") or doc.get("skill_id") or doc.get("id")
            if not skill_id:
                print(f"  WARN  {name} exists but has no skill_id; skipping")
                continue
            updates = {
                "description": parsed["description"],
                "instructions": parsed["instructions"],
                "displayName": parsed["display_name"],
                "tags": parsed["tags"],
                "initialMessage": parsed["initial_message"],
                "skillMetadata": parsed["metadata"],
                "references": parsed["references"],
            }
            if dry_run:
                print(f"  DRY   {name} (would update {skill_id})")
            else:
                update_skill(skill_id, updates)
                print(f"  UPDATE {name} → {skill_id}")
            continue

        if dry_run:
            print(f"  DRY   {name} (owner_uid={owner_uid})")
            continue

        config = create_skill(
            name=name,
            description=parsed["description"],
            instructions=parsed["instructions"],
            owner_email=owner_email,
            owner_id=owner_uid,
            displayName=parsed["display_name"],
            tags=parsed["tags"],
            initialMessage=parsed["initial_message"],
            skillMetadata=parsed["metadata"],
            references=parsed["references"],
            accessControl={"type": "public"},
        )
        print(f"  SEED  {name} → {config.skill_id}")

    print("Done.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed Firestore with v6 skill templates.")
    p.add_argument(
        "--owner-uid",
        default=os.environ.get("SEED_OWNER_UID", ""),
        help="Firebase uid to set as ownerId on every seeded skill (or SEED_OWNER_UID env var).",
    )
    p.add_argument(
        "--owner-email",
        default=os.environ.get("SEED_OWNER_EMAIL", ""),
        help="Optional email for ownerEmail metadata (not used for auth; cosmetic only).",
    )
    p.add_argument("--dry-run", action="store_true", help="Print what would be seeded, write nothing.")
    p.add_argument(
        "--update-existing",
        action="store_true",
        help="For skills that already exist, push template changes (description, "
        "instructions, displayName, tags, initialMessage, skillMetadata, references) "
        "instead of skipping. Owner / accessControl are preserved.",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.dry_run:
        print("DRY RUN — no Firestore writes")
    seed(
        owner_uid=args.owner_uid,
        owner_email=args.owner_email,
        dry_run=args.dry_run,
        update_existing=args.update_existing,
    )
