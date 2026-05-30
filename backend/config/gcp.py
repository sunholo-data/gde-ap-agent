"""GCP project resolution.

Centralises the env-var + ADC fallback chain that was duplicated across
``app.py``, ``fast_api_app.py``, ``db/firestore.py``, and ``adk/session.py``.

Lookup order:
    1. ``GOOGLE_CLOUD_PROJECT`` env var
    2. ``GCP_PROJECT`` env var (legacy v5 name)
    3. ``google.auth.default()`` (Application Default Credentials)
"""

from __future__ import annotations

import os

import google.auth
import google.auth.credentials
import google.auth.exceptions


def resolve_gcp_credentials() -> tuple[google.auth.credentials.Credentials, str | None] | None:
    """Return ``(credentials, adc_project)`` or ``None`` when ADC is unavailable.

    Used by callers that need to inspect the credentials object itself
    (e.g. the startup probe that checks ``credentials.quota_project_id``).
    """
    try:
        creds, adc_project = google.auth.default()
        return creds, adc_project
    except google.auth.exceptions.DefaultCredentialsError:
        return None


def resolve_gcp_project() -> str | None:
    """Return the resolved GCP project ID, or None if unavailable."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if project:
        return project
    resolved = resolve_gcp_credentials()
    return resolved[1] if resolved else None


def require_gcp_project() -> str:
    """Same as :func:`resolve_gcp_project` but raises when unavailable."""
    project = resolve_gcp_project()
    if not project:
        raise RuntimeError(
            "No GCP project available: set GOOGLE_CLOUD_PROJECT, GCP_PROJECT, "
            "or run with ADC (`gcloud auth application-default login`)."
        )
    return project
