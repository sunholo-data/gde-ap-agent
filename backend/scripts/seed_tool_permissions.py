"""Seed Firestore with tool-permission documents for dev/test.

Creates three documents in the ``tool_permissions`` collection:

1. A **domain** doc for --domain (e.g. ``aitanalabs.com``) granting all tools
   (or a specified list) with an optional deny list.
2. A **wildcard** doc (``*``) granting a baseline set of tools if --wildcard
   is passed.
3. An optional **user** doc for --email granting tools with user-wins priority.

Usage:
    uv run python scripts/seed_tool_permissions.py \\
        --domain aitanalabs.com --wildcard

    # Or grant everything to a specific user:
    uv run python scripts/seed_tool_permissions.py \\
        --email mark@aitanalabs.com --tools '*'

    # Dry-run:
    uv run python scripts/seed_tool_permissions.py \\
        --domain aitanalabs.com --wildcard --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add backend root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pin to aitana-multivac-dev before db.firestore reads GCP_PROJECT.
# See gotcha_gcp_project_env_shadow / scripts/_env.pin_project_for_env.
from scripts._env import pin_project_for_env

pin_project_for_env("dev")

from db import firestore as fs  # noqa: E402

COLLECTION = "tool_permissions"

# Baseline tools granted by the wildcard doc.
DEFAULT_TOOLS = [
    "google_search",
    "code_execution",
]


def seed(
    domain: str | None,
    email: str | None,
    tools: list[str] | None,
    wildcard: bool,
    dry_run: bool,
) -> None:
    if not domain and not email and not wildcard:
        print("ERROR: at least one of --domain, --email, or --wildcard is required.")
        sys.exit(2)

    docs: list[tuple[str, dict]] = []

    if domain:
        docs.append(
            (
                domain,
                {
                    "type": "domain",
                    "tools": tools or ["*"],
                    "denied": [],
                },
            )
        )

    if wildcard:
        docs.append(
            (
                "*",
                {
                    "type": "wildcard",
                    "tools": tools or DEFAULT_TOOLS,
                    "denied": [],
                },
            )
        )

    if email:
        docs.append(
            (
                email,
                {
                    "type": "user",
                    "tools": tools or ["*"],
                    "denied": [],
                },
            )
        )

    for doc_id, data in docs:
        if dry_run:
            print(f"  DRY   {COLLECTION}/{doc_id} → {data}")
        else:
            fs.set_document(COLLECTION, doc_id, data, merge=False)
            print(f"  SEED  {COLLECTION}/{doc_id} → {data}")

    print("Done.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed tool_permissions in Firestore.")
    p.add_argument("--domain", default=None, help="Domain to grant tools to (e.g. aitanalabs.com)")
    p.add_argument("--email", default=None, help="Specific user email to grant tools to")
    p.add_argument(
        "--tools",
        nargs="*",
        default=None,
        help="Tool names to grant (default: all '*' for user/domain, baseline set for wildcard)",
    )
    p.add_argument("--wildcard", action="store_true", help="Also seed a wildcard (*) doc")
    p.add_argument("--dry-run", action="store_true", help="Print what would be seeded, write nothing")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.dry_run:
        print("DRY RUN — no Firestore writes")
    seed(
        domain=args.domain,
        email=args.email,
        tools=args.tools,
        wildcard=args.wildcard,
        dry_run=args.dry_run,
    )
