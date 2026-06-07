"""A2A `message/send` invocation surface — mounted at /a2a.

Pairs with `protocols.a2a` (discovery card). This module mounts ADK's
`to_a2a()` Starlette adapter on the FastAPI app so peer agents can POST
strict A2A v0.2 JSON-RPC (`message/send`, `tasks/get`,
`message/sendSubscribe`) and have it execute through our existing
ADK agent + the same backing services (artifact / session / memory).

Why bridge instead of write our own:
  ADK ships `google.adk.a2a.utils.agent_to_a2a.to_a2a` which returns a
  full Starlette A2A server using the `a2a-sdk` `A2AStarletteApplication`
  internally. We get `message/send`, `message/sendSubscribe`,
  `tasks/get`, `tasks/cancel`, and push-notification config RPCs for free
  by passing it our `BaseAgent` + a pre-built `Runner` + the `AgentCard`
  we already author by hand in `protocols.a2a._build_card_model`.

Why we pass our own card:
  ADK's `AgentCardBuilder` would auto-derive a card from the agent's
  metadata and lose our 7 extension descriptors (a2ui-*, mcp-apps-v1,
  adk-workflow-v1), our `protocolVersion: "0.2.0"`, and our hand-tuned
  skill descriptions. Passing `agent_card=` keeps the discovery card
  (served at `/.well-known/agent.json`) and the mounted A2A card
  (served at `/a2a/.well-known/agent.json` by ADK) byte-identical —
  Discovery Engine / Gemini Enterprise see one card, not two.

Why one runner:
  `to_a2a(runner=...)` accepts a pre-built Runner. We construct it
  from the same `get_session_service` / `get_memory_service` /
  `get_artifact_service` singletons the AG-UI surface
  (`adk.agui.build_agui_adk_agent`) uses, so A2A invocations and AG-UI
  invocations share the same session storage on Vertex Agent Engine
  (when `AGENT_ENGINE_ID` is set). OpenTelemetry traces, BigQuery
  logging, and chat history are uniform across the two surfaces.

Stability note: `to_a2a` is decorated `@a2a_experimental` in
google-adk. Pin the dep version and re-verify on minor bumps.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.runners import Runner

from adk.agui import APP_NAME

if TYPE_CHECKING:
    from google.adk.agents import BaseAgent
    from starlette.applications import Starlette

logger = logging.getLogger(__name__)


def _build_runner(agent: BaseAgent) -> Runner:
    """Construct a Runner with our singleton backing services.

    Imports `adk.session` lazily so importing this module doesn't pull
    Vertex SDK initialisation into hot startup paths (test isolation,
    fast CLI boot). Same lazy pattern as `adk.agui.build_agui_adk_agent`.
    """
    from adk.session import (
        get_artifact_service,
        get_memory_service,
        get_session_service,
    )

    return Runner(
        app_name=APP_NAME,
        agent=agent,
        session_service=get_session_service(),
        memory_service=get_memory_service(),
        artifact_service=get_artifact_service(),
    )


def build_a2a_app(
    agent: BaseAgent,
    base_url: str,
) -> Starlette:
    """Build the Starlette sub-app that handles A2A JSON-RPC invocation.

    Returns a Starlette app suitable for `fast_api_app.mount("/a2a", ...)`.
    The mounted app exposes (paths relative to the mount):
      - `POST /` — A2A JSON-RPC entry point (`message/send`,
        `message/sendSubscribe`, `tasks/get`, `tasks/cancel`, etc.)
      - `GET /.well-known/agent.json` — the same card as the root
        `/.well-known/agent.json` (built from `_build_card_model`)
      - `GET /.well-known/agent-card.json` — A2A v0.3 spec card path
        (same content; the a2a-sdk serves both for backward compat)

    Args:
        agent: The ADK agent to expose for A2A invocation. v1 wires the
            `ap-orchestrator` here — its existing SequentialAgent pipeline
            handles specialist routing internally, so one A2A endpoint
            covers the full AP flow.
        base_url: The public-facing base URL of the deployed app (e.g.
            `https://gde-ap-agent-...run.app`). The card advertises
            `<base_url>/a2a` as the invocation URL — peers POST there.
    """
    # Lazy import: protocols.a2a's discovery surface should stay light;
    # only the invocation surface needs the AgentCard pydantic model.
    from protocols.a2a import _build_card_model

    agent_card = _build_card_model(base_url)
    runner = _build_runner(agent)

    logger.info(
        "a2a_invocation.build_a2a_app: mounting A2A surface for agent=%s, card.url=%s",
        agent.name,
        agent_card.url,
    )

    # to_a2a returns a Starlette app. FastAPI is built on Starlette, so
    # `app.mount("/a2a", ...)` accepts this as a sub-app.
    return to_a2a(agent, runner=runner, agent_card=agent_card)
