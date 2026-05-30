# CLAUDE.md — Backend Development Guidelines

## Setup

```bash
cd backend
make install           # uv sync
source .venv/bin/activate
make dev               # FastAPI on port 1956 with hot-reload
make playground        # ADK dev UI on port 8501
```

**CRITICAL:** Always use `uv run` for backend commands. Never use global `python` or `pip`.

## ADK Architecture

This backend uses Google ADK for agent orchestration. Key files:

- `app.py` — Root agent definition (`google.adk.agents.Agent`)
- `fast_api_app.py` — FastAPI app using `google.adk.cli.fast_api.get_fast_api_app()`
- `adk/agent.py` — Agent factory (creates agents from skill configs)
- `adk/tools.py` — FunctionTool wrappers for existing tools
- `adk/session.py` — Session state ↔ Firestore sync

### ADK Patterns

```python
# Agent definition
from google.adk.agents import Agent

agent = Agent(
    name="skill_name",
    model="gemini-2.5-flash",  # Gemini: string ID. Claude: Claude(). OpenAI: LiteLlm("openai/...")
    instruction="...",
    tools=[my_function_tool],
    sub_agents=[other_skill_agent],
)

# FunctionTool — just a Python function with docstring
def my_tool(query: str) -> str:
    """Search for documents matching a query.

    Args:
        query: The search terms.

    Returns:
        Matching document summaries.
    """
    return do_search(query)

# Testing agents
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

runner = Runner(agent=root_agent, session_service=InMemorySessionService(), app_name="test")
events = list(runner.run(new_message=message, user_id="test", session_id=session.id))
```

## Testing

```bash
make test-fast         # Fast CI tests (skip slow/integration)
make test              # All tests
make eval              # ADK evaluation with evalsets
make lint              # Ruff + codespell
```

## Pre-push checklist — CI parity

CI runs **two** ruff steps (linter + formatter) and pytest. `make lint`
and `make test-fast` together match CI exactly. Before pushing backend
changes, run:

```bash
cd backend
make lint         # ruff check . --diff + ruff format --check . --diff
make test-fast    # pytest tests/ -m "not slow and not integration"
```

To auto-fix formatter complaints: `make format`.

**Don't run `uv run ruff check` directly** — it skips the formatter,
which CI verifies separately. That's how the LOCAL-MODE-AND-FORK sprint
broke dev for 9 commits.

### Ruff version sync

CI installs ruff fresh from `uv.lock` each run (currently `0.15.13`).
Your local `.venv` may have a stale install — `uv sync` does NOT always
replace it. If local `ruff format` disagrees with CI:

```bash
uv pip install --reinstall ruff      # forces refresh from uv.lock
uv run ruff --version                # should match the version in uv.lock
```

### Test Organization
- `tests/unit/` — Pydantic models, utils, pure functions
- `tests/integration/` — Agent tests (require GCP credentials)
- `tests/eval/` — ADK evaluation sets and config
- `tests/api_tests/` — FastAPI endpoint tests
- `tests/tool_tests/` — Individual tool tests

### Adding Tests
- Use `pytest` with `pytest-asyncio` for async tests
- Mark slow tests with `@pytest.mark.slow`
- Mark tests requiring GCP with `@pytest.mark.integration`
- ADK evals go in `tests/eval/evalsets/` as `.evalset.json` files

## Code Style

- **Ruff** for linting and formatting (line-length 120)
- Type hints on all function signatures
- Docstrings with Args/Returns for public functions
- Async/await for all I/O operations
- `logging` module (via `google.cloud.logging` in production)

## Dependencies

- **google-adk** — Agent orchestration, tool execution, sessions, memory
- **fastapi** — HTTP framework
- **google-genai** — Gemini model client
- **anthropic** — Claude model client
- **openai** — OpenAI model client
- **ailang-parse** — Deterministic document parsing (<1s, no LLM tokens)
- **mcp** — Model Context Protocol client
- **httpx** — Async HTTP client

## Deployment

Same Cloud Run services as v5:
- Port: 1956
- Dockerfile: `backend/Dockerfile`
- Uses `uv` for dependency management in container
- ADK artifacts stored in GCS bucket (via `LOGS_BUCKET_NAME` env var)

## Copying v5 Tools

When bringing a tool from v5:
1. Read from `/Users/mark/dev/aitana-labs/frontend/backend/tools/`
2. Remove all Sunholo imports (`from sunholo.*`)
3. Remove LangChain imports
4. Replace `BufferStreamingStdOutCallbackHandler` with ADK callbacks
5. Replace `trace.span()` with OTEL (ADK handles this automatically)
6. Make it a plain async function with typed args + docstring
7. ADK wraps it as a FunctionTool automatically
8. Write tests in `tests/tool_tests/`
