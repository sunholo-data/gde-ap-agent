---
name: ap-pipeline
description: >
  Deterministic Accounts-Payable processing pipeline. Walks Extract →
  Validate → Post in sequence via ADK's SequentialAgent. No LLM at the
  workflow level — the order is code, not prose. Use as a sub-skill of
  ap-orchestrator; not intended for direct user invocation.
display_name: AP Pipeline (Workflow)
metadata:
  author: aitana
  version: "0.1"
  # WORKFLOW-PIPELINE: the field that flips create_agent from LlmAgent
  # to google.adk.agents.SequentialAgent. No model needed — ADK walks
  # sub_agents in Python, not by asking a model what to do next.
  agentType: sequential
  # Pipeline order. SequentialAgent runs each in turn, passing session
  # state forward. Each specialist's schema-enforced output (ap_invoice,
  # ap_verdict, ap_posting_record) flows through state["app:..."] for
  # the next specialist to read.
  subSkills:
    - invoice-extractor
    - ap-validator
    - ap-poster
---

This skill has no instruction body. A SequentialAgent has no model — it
walks its `sub_agents` deterministically. The "workflow" lives in code
(see `google.adk.agents.sequential_agent.SequentialAgent`), not in a
prompt that could be ignored.

The intake gate (`backend/adk/agent.py::_make_intake_gate`) short-circuits
the pipeline with a friendly message when session state has no document
loaded — graceful degradation, no confused output when a user invokes
the pipeline without context.

See [docs/design/forks/gde-ap-agent/multi-agent-workflow-pipeline.md](../../../../docs/design/forks/gde-ap-agent/multi-agent-workflow-pipeline.md)
for the full design rationale, protocol-stack mapping, and submission
narrative.
