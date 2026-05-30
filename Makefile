.PHONY: dev dev-local proxy-check logs help cli-install cli-reinstall cli-uninstall cli-doctor cli-selftest-mock cli-selftest-live cli-selftest

# Launch backend (port 1956) + frontend (port 3000) for local development.
# Logs stream to stdout; Ctrl-C stops both.
dev:
	@chmod +x scripts/dev.sh
	@scripts/dev.sh

# Launch backend + frontend in LOCAL_MODE (no GCP creds needed for Firestore
# / Vertex Sessions / Cloud Trace; in-memory Firestore auto-seeds the demo
# skills incl. "Workspace Demo" for the MULTI-SURFACE-A2UI demo).
# Model auth still required — set GOOGLE_API_KEY in backend/.env.
# See WORKSHOP.md for the full tier-1 quickstart.
dev-local:
	@chmod +x scripts/dev-local.sh
	@scripts/dev-local.sh

# Smoke-test the frontend→backend proxy bridge locally.
# Starts both servers, probes /api/proxy/health, then exits.
proxy-check:
	@chmod +x scripts/try-proxy-local.sh
	@scripts/try-proxy-local.sh

logs:
	@scripts/logs.sh

# --- CLI lifecycle ---

# Install the `aiplatform` CLI as a global uv tool. Idempotent: --force
# overwrites any prior install (e.g. the legacy `aitana` / `aitana-cli`
# binary). After this completes, `aiplatform --help` works from anywhere.
cli-install:
	@uv tool install --force ./cli
	@echo "Installed: $$(which aiplatform 2>/dev/null || echo '(not on PATH — check ~/.local/bin)')"

# Remove any prior install of this CLI under any historical name.
# Useful when migrating from the pre-2026-04-28 `aitana` binary.
cli-uninstall:
	@-uv tool uninstall aitana-cli 2>/dev/null
	@-uv tool uninstall aitana     2>/dev/null
	@-uv tool uninstall aiplatform 2>/dev/null
	@echo "Removed any previously installed aitana/aiplatform CLI tool."

# Clean reinstall: remove all historical names then install fresh.
cli-reinstall: cli-uninstall cli-install

# Verify the installed CLI matches the source. Catches the symptom that
# led to the 2026-04-28 rename (broken global binary pointing at a stale
# package layout).
cli-doctor:
	@if ! command -v aiplatform >/dev/null 2>&1; then \
	  echo "aiplatform not on PATH. Run: make cli-install"; exit 1; \
	fi
	@aiplatform --version || { echo "aiplatform installed but broken — run: make cli-reinstall"; exit 1; }

# --- CLI self-test ---

# Mock-backend smoke: boots a tiny SSE server on 127.0.0.1:0, runs the
# real `aiplatform skill probe` binary as a subprocess against it, and
# asserts the printed table. No GCP credentials, no network, no live
# backend. The transport-level safety net respx-mocked tests can't be.
cli-selftest-mock:
	@chmod +x scripts/cli-selftest-mock.sh
	@scripts/cli-selftest-mock.sh

# Live-backend smoke. Requires `make dev` running on :1956 + AIPLATFORM_ID_TOKEN
# + AIPLATFORM_SELFTEST_SKILL_ID (or pass the skill id as the first arg).
# Skips cleanly with exit 0 when any prereq is missing — safe for CI.
cli-selftest-live:
	@chmod +x scripts/cli-selftest-live.sh
	@scripts/cli-selftest-live.sh

# Combined self-test: mock smoke (always runs), then live smoke (skipped
# cleanly if backend or auth missing). Single command for "is the CLI
# wired up correctly" — the entry point future agents/teammates use.
cli-selftest:
	@echo "▶ mock smoke …"
	@$(MAKE) --no-print-directory cli-selftest-mock
	@echo
	@echo "▶ live smoke …"
	@$(MAKE) --no-print-directory cli-selftest-live
	@echo
	@echo "✓ aiplatform CLI self-test complete."

help:
	@echo "make dev                — start backend (1956) + frontend (3456) — cloud mode (real GCP/Vertex)"
	@echo "make dev-local          — start backend + frontend in LOCAL_MODE (no GCP creds, in-memory Firestore)"
	@echo "make logs               — stream backend logs (OTEL noise filtered out)"
	@echo "make proxy-check        — smoke-test the proxy bridge (CI helper)"
	@echo
	@echo "make cli-install        — install the aiplatform CLI as a global uv tool"
	@echo "make cli-reinstall      — clean reinstall (uninstalls historical aitana names first)"
	@echo "make cli-doctor         — verify the installed aiplatform CLI is wired correctly"
	@echo "make cli-selftest       — run mock + live smokes (live skips cleanly if no backend)"
	@echo "make cli-selftest-mock  — offline end-to-end (real binary, mock SSE backend)"
	@echo "make cli-selftest-live  — diagnostic against running \`make dev\` backend"
