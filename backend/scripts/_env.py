"""Tiny helper for backend/scripts/* — pin the GCP project for a target env.

The scripts in this directory (``seed_mcp_servers.py``, ``seed_skills.py``,
``check_models.py``) talk to Firestore + Vertex via google-cloud client
libraries. Those libraries pick a project from ``GOOGLE_CLOUD_PROJECT`` /
``GCP_PROJECT`` env vars BEFORE we've had a chance to import
``db.firestore`` and pass it explicitly. If the caller's shell has a
stale project pinned (eg. a prior ``gcloud config set project`` for
another environment), the script silently writes to the wrong tenant.

``pin_project_for_env("dev")`` exports the right env var BEFORE
``db.firestore`` reads it. Call as the first action in every script
that mutates project-scoped state.

Mapping is identical to the cloudbuild.yaml substitution — dev runs
against ``multivac-internal-dev``. Test / prod targets are added when
those environments cut.
"""

from __future__ import annotations

import os

_ENV_PROJECTS = {
    "dev": "multivac-internal-dev",
    # test / prod when they cut — until then, fail loudly rather than
    # default to dev and have someone silently seed prod.
}


def pin_project_for_env(env: str) -> None:
    """Export GCP project env vars for the given env name.

    Idempotent — calling twice in the same process is a no-op. Raises
    ValueError on an unknown env so a typo doesn't silently seed the
    wrong tenant.
    """
    project = _ENV_PROJECTS.get(env)
    if project is None:
        raise ValueError(f"pin_project_for_env: unknown env {env!r}; known envs: {sorted(_ENV_PROJECTS)}")
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GCP_PROJECT"] = project
    # The agent factory uses PLATFORM_DEFAULT_PROJECT as a fallback when
    # GOOGLE_CLOUD_PROJECT isn't set; mirror it here so module-import
    # ordering can't trip us up.
    os.environ["PLATFORM_DEFAULT_PROJECT"] = project
