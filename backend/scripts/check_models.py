"""Probe Vertex AI Gemini models for availability + streaming TTFT.

Usage:
    uv run python scripts/check_models.py                    # current SKILL.md set
    uv run python scripts/check_models.py gemini-3.5-flash gemini-3.1-flash-lite
    uv run python scripts/check_models.py --list             # show every Gemini model the project can see

For each model:
  1. Calls generate_content_stream with a short prompt
  2. Measures TTFT (ms to first chunk) and total time
  3. Runs N=3 trials by default (first warms the cache; reports best + mean)
  4. Exits non-zero if any model fails to load — safe to wire into CI later

The "best of 3" metric is what matters for demo perception. The mean
includes any warm-up tax.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Default skill models — kept in sync by scripts/_collect_skill_models below.
SKILL_FILES = [
    "skills/templates/ap-orchestrator/SKILL.md",
    "skills/templates/ap-validator/SKILL.md",
    "skills/templates/ap-poster/SKILL.md",
]


def _collect_skill_models() -> list[tuple[str, str]]:
    """Read the SKILL.md files and pull out (skill_name, model_id) pairs."""
    here = Path(__file__).resolve().parent.parent
    pairs: list[tuple[str, str]] = []
    for rel in SKILL_FILES:
        p = here / rel
        if not p.exists():
            continue
        skill_name = p.parent.name
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("model:"):
                model_id = stripped.split(":", 1)[1].strip()
                pairs.append((skill_name, model_id))
                break
    return pairs


def _make_client():
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "multivac-internal-dev")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    from google import genai

    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ["GOOGLE_CLOUD_LOCATION"],
    )


def list_gemini_models() -> int:
    client = _make_client()
    for m in client.models.list():
        name = m.name or ""
        if "gemini" in name.lower():
            print(name.split("/")[-1])
    return 0


def probe_model(client, model_id: str, trials: int = 3) -> dict:
    """Run ``trials`` streaming calls. Returns {ok, ttft_ms_best, ttft_ms_mean, error}."""
    ttfts: list[float] = []
    error: str | None = None
    for _ in range(trials):
        t0 = time.perf_counter()
        try:
            first_t: float | None = None
            for ev in client.models.generate_content_stream(
                model=model_id,
                contents="Reply with the single word OK.",
            ):
                if first_t is None:
                    first_t = time.perf_counter() - t0
                _ = getattr(ev, "text", None)
            if first_t is not None:
                ttfts.append(first_t * 1000.0)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            break
    if error or not ttfts:
        return {"ok": False, "error": error or "no chunks received"}
    return {
        "ok": True,
        "ttft_ms_best": min(ttfts),
        "ttft_ms_mean": sum(ttfts) / len(ttfts),
        "trials": len(ttfts),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="*", help="Model IDs to test (default: read from SKILL.md set)")
    ap.add_argument("--list", action="store_true", help="List every Gemini model visible to the project and exit")
    ap.add_argument("--trials", type=int, default=3, help="Number of streaming calls per model (default: 3)")
    args = ap.parse_args()

    if args.list:
        return list_gemini_models()

    if args.models:
        targets: list[tuple[str, str]] = [("(arg)", m) for m in args.models]
    else:
        targets = _collect_skill_models()
        if not targets:
            print("No models specified and no SKILL.md files found.", file=sys.stderr)
            return 2

    client = _make_client()
    print(f"Probing {len(targets)} model(s) · {args.trials} trial(s) each\n")
    print(f"{'skill':<22} {'model':<28} {'best':>8} {'mean':>8}  status")
    print("-" * 80)
    any_failed = False
    for skill, model in targets:
        result = probe_model(client, model, trials=args.trials)
        if result["ok"]:
            print(f"{skill:<22} {model:<28} {result['ttft_ms_best']:>6.0f}ms {result['ttft_ms_mean']:>6.0f}ms  OK")
        else:
            any_failed = True
            print(f"{skill:<22} {model:<28} {'':>8} {'':>8}  FAIL — {result['error']}")
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
