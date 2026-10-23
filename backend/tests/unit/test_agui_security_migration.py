"""Use real protocol models to check the ADK 2 wire and cleanup contract."""

import contextvars

from ag_ui.core import RunAgentInput, RunFinishedEvent, RunStartedEvent, StateDeltaEvent, TextMessageContentEvent

from adk.agui import APP_NAME, stream_agui_events


async def test_wire_preserves_null_patch_and_generator_context():
    owner = contextvars.ContextVar("migration_owner", default="caller")
    cleaned = []

    class Agent:
        async def run(self, run_input):
            token = owner.set("producer")
            try:
                yield RunStartedEvent(thread_id="thread", run_id="run")
                yield TextMessageContentEvent(message_id="answer", delta="Done")
                yield StateDeltaEvent(delta=[{"op": "replace", "path": "/optional", "value": None}])
                yield RunFinishedEvent(thread_id="thread", run_id="run")
            finally:
                owner.reset(token)
                cleaned.append(True)

    run_input = RunAgentInput(thread_id="thread", run_id="run", state={}, messages=[], tools=[], context=[])
    events = [event async for event in stream_agui_events(Agent(), run_input, heartbeat_seconds=0)]
    assert events[0]["type"] == "RUN_STARTED"
    patch = next(event for event in events if event["type"] == "STATE_DELTA")
    assert patch["delta"] == [{"op": "replace", "path": "/optional", "value": None}]
    assert events[-1]["type"] == "RUN_FINISHED"
    assert cleaned == [True]
    assert owner.get() == "caller"
    assert APP_NAME == "gde_ap_agent"
