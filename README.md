# GDE AP Agent

**AI-Powered Accounts Payable** — autonomous multi-agent invoice processing on Google ADK.

Built for the [Google for Startups AI Agents Challenge, Track 3](./SUBMISSION.md). Live demo: https://gde-ap-agent-blqtqfexwa-ew.a.run.app

> Built on the open-source [ai-protocol-platform](https://github.com/sunholo-data/ai-protocol-platform) template (Skills + AG-UI + A2UI + MCP Apps + A2A on Google ADK).
>
> 🚀 **New here?** Start with [**WORKSHOP.md**](./WORKSHOP.md) — clone, set
> `LOCAL_MODE=1`, run `make dev`, working chat UI in under 30 minutes with
> zero GCP credentials.

## AP Agent Pipeline

```
ap-orchestrator (Gemini 2.5 Pro)
    ↓ docparse      — invoice field extraction
    ↓ ap-validator  — grounded validation vs vendor master + POs
    ↓ ap-poster     — post clean or escalate exceptions
```

**Visual features**: Navy+gold AP theme · live pipeline step visualizer · A2UI invoice review card · MCP App vendor globe · MCP App analytics dashboard · per-specialist **Audit View** with live chips, history, structured-input runs, and an `ap-vendor-kg` MCP App showcasing AG-UI + A2UI + MCP Apps together

**One pipeline, four cooperating agents.** Drop an invoice — the orchestrator delegates extraction, validation, and posting, then returns a single audit-ready decision. Each specialist&apos;s work is observable live via the Audit View chip + side panel.

See [SUBMISSION.md](./SUBMISSION.md) for full details and live demo URL.

## Quick Start

### Backend
```bash
cd backend
make install
make dev          # API on port 1956
make playground   # ADK dev UI on port 8501
```

### Frontend
```bash
cd frontend
npm install
npm run dev       # Next.js on port 3000
```

## API Reference

The backend exposes a self-documenting API:

- **Interactive docs**: http://localhost:1956/docs (Swagger UI — all routes, try them live)
- **OpenAPI JSON**: http://localhost:1956/openapi.json — pipe to `jq '.paths | keys'` to list all routes
- **Skill invocation** (AG-UI streaming): `POST /api/skill/{skill_id}/stream`
- **Bare ADK routes** (dev only): exposed by `get_fast_api_app(web=True)` — use the skill route above in production

> **ADK `app_name` gotcha:** The canonical app name is `aitana_platform` (the `APP_NAME` constant in
> `backend/adk/agui.py`). The dev UI's `/list-apps` historically returned filesystem directory names —
> this version returns the correct `APP_NAME`. Never derive `app_name` from `/list-apps` paths in code;
> always import the `APP_NAME` constant.

## Architecture

```
platform/
├── frontend/     # Next.js 14 + React 18 + AG-UI + A2UI + MCP Apps
├── backend/      # FastAPI + Google ADK
├── cli/          # `aiplatform` CLI
├── docs/         # Design documents
└── firestore.rules
```

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines.

See [docs/design/v5.0.0/migration-to-v6.md](docs/design/v5.0.0/migration-to-v6.md) for the full migration plan.
