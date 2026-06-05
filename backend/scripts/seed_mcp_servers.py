"""Seed Firestore mcp_servers/ collection with MCP server configs.

Idempotent: re-running with the same args is safe (uses set with merge=False so
the document is replaced, not appended). Reads optional URL overrides from
flags so the same script seeds local-dev (localhost:3001) and deployed
(Cloud Run sidecar URL) without code changes.

Usage:
    # Local dev (default — points at localhost:3001/mcp)
    uv run python scripts/seed_mcp_servers.py

    # Deployed dev (override URL)
    uv run python scripts/seed_mcp_servers.py \\
        --url https://mcp-ext-apps-map-dev-<hash>.run.app/mcp

    # Dry run
    uv run python scripts/seed_mcp_servers.py --dry-run

The seeded server is then activated per-skill by adding its id to the
SkillConfig's tool_configs.mcp.servers list (handled by seed_skills.py
or the skill admin UI; not this script's concern).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Pin to aitana-multivac-dev before db.firestore reads GCP_PROJECT.
# See gotcha_gcp_project_env_shadow / scripts/_env.pin_project_for_env.
from scripts._env import pin_project_for_env

pin_project_for_env("dev")

from db import firestore as fs  # noqa: E402

COLLECTION = "mcp_servers"
DEFAULT_LOCAL_URL = "http://localhost:3001/mcp"
# WORKFLOW-PIPELINE M3: the simulated vendor-master + erp-posting MCP servers
# run in-process inside the gde-ap-agent backend, mounted at /mcp/<name>. The
# agent's McpToolset talks to them via loopback — on Cloud Run multi-container
# the public URL routes to the frontend (404 on /mcp/*), so the public
# hostname is the *wrong* default. Use --backend-base-url to override (e.g.
# a sibling deploy or a remote MCP host).
DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:1956"

EXT_APPS_MAP_CONFIG = {
    "name": "Geo / 3D Globe (ext-apps map-server)",
    "transport": "http",
    "headers": {},
    "source_repo": "https://github.com/modelcontextprotocol/ext-apps",
    "source_path": "examples/map-server",
    "source_commit": "0008d3b7",  # ext-apps 1.7.1; pinned in M1 fixture capture
    "operated_by": "aitana",
    "tags": ["geo", "visualization", "mcp-app"],
}

# WORKFLOW-PIPELINE M3 configs. The validator and poster reference these
# by id (vendor-master, erp-posting) in their SKILL.md tool_configs.mcp.
VENDOR_MASTER_CONFIG = {
    "name": "Vendor Master (simulated)",
    "transport": "http",
    "headers": {},
    "operated_by": "aitana",
    "tags": ["ap", "grounding", "simulated"],
}

ERP_POSTING_CONFIG = {
    "name": "ERP Posting (simulated)",
    "transport": "http",
    "headers": {},
    "operated_by": "aitana",
    "tags": ["ap", "action", "simulated"],
}


def seed_ext_apps_map(url: str, *, dry_run: bool = False) -> None:
    config = {**EXT_APPS_MAP_CONFIG, "url": url}
    if dry_run:
        print(f"[dry-run] would write mcp_servers/ext-apps-map: url={url}")
        return
    fs.set_document(COLLECTION, "ext-apps-map", config)
    print(f"Seeded mcp_servers/ext-apps-map: url={url}")


def seed_workflow_pipeline_servers(backend_base_url: str, *, dry_run: bool = False) -> None:
    """Seed vendor-master + erp-posting (WORKFLOW-PIPELINE M3) Firestore docs.

    Both URLs follow the same shape: <backend_base_url>/mcp/<server_name>.
    Trailing slash matters — FastMCP mounts the streamable-HTTP root at "/",
    so the McpToolset's POST lands at /mcp/<server_name>/.
    """
    base = backend_base_url.rstrip("/")
    targets = [
        ("vendor-master", VENDOR_MASTER_CONFIG, f"{base}/mcp/vendor-master/"),
        ("erp-posting", ERP_POSTING_CONFIG, f"{base}/mcp/erp-posting/"),
    ]
    for doc_id, config, url in targets:
        full = {**config, "url": url}
        if dry_run:
            print(f"[dry-run] would write mcp_servers/{doc_id}: url={url}")
            continue
        fs.set_document(COLLECTION, doc_id, full)
        print(f"Seeded mcp_servers/{doc_id}: url={url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=DEFAULT_LOCAL_URL,
        help=f"ext-apps-map MCP server URL (default: {DEFAULT_LOCAL_URL})",
    )
    parser.add_argument(
        "--backend-base-url",
        default=DEFAULT_BACKEND_BASE_URL,
        help=(
            "Base URL for the gde-ap-agent backend (hosts the in-process "
            "vendor-master + erp-posting MCP servers at /mcp/<name>/). "
            f"Default: {DEFAULT_BACKEND_BASE_URL}"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written, don't touch Firestore",
    )
    args = parser.parse_args()
    seed_ext_apps_map(args.url, dry_run=args.dry_run)
    seed_workflow_pipeline_servers(args.backend_base_url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
