"""`aitana docs` — user document folder management and upload.

Targets:
  GET/POST /api/folders
  GET /api/folders/{folderId}/documents
  POST /api/documents/upload
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import click

from aiplatform.http import AIPlatformClient

_FOLDERS_PATH = "/api/folders"


def _client(ctx: click.Context) -> AIPlatformClient:
    return AIPlatformClient(env=ctx.obj["env"])


@click.group()
def docs() -> None:
    """Manage user document folders and uploads."""


# ---------------------------------------------------------------------------
# aitana docs folder <sub>
# ---------------------------------------------------------------------------

@docs.group("folder")
def docs_folder() -> None:
    """Manage document folders (list/new)."""


@docs_folder.command("list")
@click.pass_context
def folder_list(ctx: click.Context) -> None:
    """List all folders with document counts."""
    result = _client(ctx).get(_FOLDERS_PATH)
    click.echo(_json.dumps(result, indent=2))


@docs_folder.command("new")
@click.argument("name")
@click.pass_context
def folder_new(ctx: click.Context, name: str) -> None:
    """Create a new folder and print its folderId."""
    result = _client(ctx).post(_FOLDERS_PATH, json={"name": name})
    click.echo(_json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# aitana docs upload
# ---------------------------------------------------------------------------

@docs.command("upload")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--folder", "folder_id", default="", show_default=False, help="Target folderId (auto-created when absent).")
@click.option("--skill", "skill_id", default="", help="Skill ID to associate the upload with.")
@click.pass_context
def upload(ctx: click.Context, files: tuple[Path, ...], folder_id: str, skill_id: str) -> None:
    """Upload one or more files to a folder.

    FILES may be individual paths. Shell globbing works:
      aitana docs upload reports/*.docx --folder <id>
    """
    client = _client(ctx)

    for path in files:
        click.echo(f"Uploading {path.name}…", nl=False)
        url = f"{client.base_url}/api/documents/upload"
        headers = client._auth_headers()

        import httpx
        content_type = _guess_content_type(path)
        with path.open("rb") as fh:
            try:
                resp = httpx.post(
                    url,
                    headers=headers,
                    files={"file": (path.name, fh, content_type)},
                    data={"folder_id": folder_id, "skill_id": skill_id},
                    timeout=120.0,
                )
            except httpx.HTTPError as exc:
                click.echo(f" ERROR: {exc}")
                continue

        if resp.status_code >= 400:
            click.echo(f" FAILED ({resp.status_code}): {resp.text}")
            continue

        data = resp.json()
        status = data.get("status", "?")
        blocks = data.get("blocksCount", "?")
        click.echo(f" {status} ({blocks} blocks)")


def _guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    mapping = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".html": "text/html",
        ".htm": "text/html",
        ".epub": "application/epub+zip",
    }
    return mapping.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# aitana docs list
# ---------------------------------------------------------------------------

def _all_docs(client: AIPlatformClient) -> list:
    folders = client.get(_FOLDERS_PATH)
    if not isinstance(folders, list):
        return []
    result = []
    for f in folders:
        fid = f.get("id") or f.get("folderId", "")
        if not fid:
            continue
        fdocs = client.get(f"/api/folders/{fid}/documents")
        if isinstance(fdocs, list):
            result.extend(fdocs)
    return result


@docs.command("list")
@click.option("--folder", "folder_id", default=None, help="Filter by folderId.")
@click.pass_context
def docs_list(ctx: click.Context, folder_id: str | None) -> None:
    """List documents with parse status (all folders or a specific folder)."""
    client = _client(ctx)
    result = client.get(f"/api/folders/{folder_id}/documents") if folder_id else _all_docs(client)
    click.echo(_json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# aitana docs status
# ---------------------------------------------------------------------------

@docs.command("status")
@click.argument("folder_id")
@click.pass_context
def docs_status(ctx: click.Context, folder_id: str) -> None:
    """Show parse progress for a folder (parsed / total)."""
    result = _client(ctx).get(f"/api/folders/{folder_id}/documents")
    if not isinstance(result, list):
        click.echo(_json.dumps(result, indent=2))
        return

    total = len(result)
    parsed = sum(1 for d in result if d.get("parseStatus") == "parsed")
    pending = sum(1 for d in result if d.get("parseStatus") in ("pending", "pending_ai_extraction"))
    failed = sum(1 for d in result if d.get("parseStatus") == "failed")

    click.echo(f"Folder: {folder_id}")
    click.echo(f"  Total:   {total}")
    click.echo(f"  Parsed:  {parsed}")
    click.echo(f"  Pending: {pending}")
    click.echo(f"  Failed:  {failed}")
    if total > 0:
        pct = round(parsed / total * 100)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        click.echo(f"  [{bar}] {pct}%")
