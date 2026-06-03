"""Mint a Firebase ID token for the dedicated smoke user and print it.

Ported from the upstream aitana repo (see docs/ops/auth-smoke-testing.md).
The flow:

  1. firebase_admin uses local ADC to ensure ``whoami-test@aitanalabs.test``
     exists in the target Firebase project, then rotates its password to a
     fresh random string.
  2. Identity Toolkit REST ``signInWithPassword`` exchanges the
     email + new password for a fresh Firebase ID token.
  3. The token is printed to stdout. Pipe it into ``AIPLATFORM_ID_TOKEN``
     for the audited curl / CLI flows.

This is intentionally not a network-mocked unit test — it must talk to
real Identity Platform and Firebase Admin to be useful. Run from a
laptop with ``gcloud auth application-default login`` already done.

Usage::

    cd backend
    uv run python scripts/whoami_smoke.py --env dev > /tmp/token
    AIPLATFORM_ID_TOKEN=$(cat /tmp/token) curl ...

Only ``--env dev`` is wired up for gde-ap-agent (the demo only runs in
dev). Other environments would slot in via the ENVIRONMENTS dict below.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.request

import firebase_admin
from firebase_admin import auth, credentials

SMOKE_EMAIL = "whoami-test@aitanalabs.test"

ENVIRONMENTS: dict[str, dict[str, str]] = {
    # gde-ap-agent only runs in dev. The Web API key is a public client
    # identifier (it appears in every browser bundle) — fine to commit.
    # The key has an HTTP referrer restriction enforced by GCP API keys
    # (see Cloud Console → Credentials), so we send the deployed origin
    # as Referer when calling Identity Toolkit from a non-browser
    # context.
    "dev": {
        "project_id": "multivac-internal-dev",
        # Public Firebase Web API key (also committed in the frontend bundle).
        "api_key": "AIzaSyDEaLobToWuw53VMB68dTvqXoprl6fR7fc",
        "referer": "https://gde-ap-agent-blqtqfexwa-ew.a.run.app",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="dev", choices=sorted(ENVIRONMENTS))
    args = parser.parse_args()
    env = ENVIRONMENTS[args.env]

    # Initialise firebase_admin against the target project. ADC supplies
    # the credential (gcloud auth application-default login on the
    # laptop). Avoid create_custom_token — needs signBlob (see doc).
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {"projectId": env["project_id"]})

    try:
        user = auth.get_user_by_email(SMOKE_EMAIL)
    except auth.UserNotFoundError:
        user = auth.create_user(email=SMOKE_EMAIL, email_verified=True)
        print(f"created smoke user {SMOKE_EMAIL} uid={user.uid}", file=sys.stderr)

    new_password = secrets.token_urlsafe(24)
    auth.update_user(user.uid, password=new_password)

    payload = json.dumps({"email": SMOKE_EMAIL, "password": new_password, "returnSecureToken": True}).encode()
    req = urllib.request.Request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={env['api_key']}",
        data=payload,
        headers={
            "Content-Type": "application/json",
            # Required: the API key has an HTTP-referrer restriction.
            "Referer": env["referer"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"signInWithPassword failed: HTTP {e.code} body={err_body}", file=sys.stderr)
        raise
    token = body["idToken"]
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
