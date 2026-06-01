"""Seeds the LOCAL_MODE in-memory Firestore at backend startup with a tiny
fixture so attendees see a working chat the moment they hit ``localhost:3456``.

Idempotent: only seeds when the target collections are empty. Re-runs (the
backend hot-reloads on every save) are no-ops.

What gets seeded:
- 1 demo user: ``workshop-user`` (matches the stub identity from
  ``auth/local_mode_stub.py``)
- 4 demo skills covering W2 (ADK basics), W6 (A2UI form), W7 (placeholder),
  and the multi-surface A2UI rendering demo (sprint 2.9). Each is owned by
  the workshop-user and marked ``public`` so anyone signed in with the stub
  identity sees them in the skill picker.
- 1 demo parsed Markdown document so the document-analyst skill has
  something to point at.

Only call from inside the LOCAL_MODE startup hook — do NOT use this in
cloud mode, it would write to real Firestore.
"""

from __future__ import annotations

import logging
import time

from config.local_mode import is_local_mode

logger = logging.getLogger(__name__)

# UID of the stub identity (auth/local_mode_stub.py). Keep in sync.
WORKSHOP_USER_UID = "workshop-user"
WORKSHOP_USER_EMAIL = "workshop@local"
WORKSHOP_USER_DISPLAY_NAME = "Workshop Attendee"


def seed_local_fixture() -> None:
    """Seed the in-memory Firestore. Idempotent; safe to call repeatedly."""
    if not is_local_mode():
        logger.debug("seed_local_fixture: LOCAL_MODE off, skipping")
        return

    from db.firestore import get_client

    client = get_client()
    now = time.time()

    # ---- workshop user ---------------------------------------------------
    users = list(client.collection("users").stream())
    if not users:
        client.collection("users").document(WORKSHOP_USER_UID).set(
            {
                "userId": WORKSHOP_USER_UID,
                "email": WORKSHOP_USER_EMAIL,
                "displayName": WORKSHOP_USER_DISPLAY_NAME,
                "createdAt": now,
                "groupTags": ["workshop-attendee"],
            }
        )

    # ---- demo skills -----------------------------------------------------
    skills = list(client.collection("skills").stream())
    if not skills:
        for skill in _demo_skills(now):
            client.collection("skills").document(skill["skillId"]).set(skill)

    # ---- Accounts-Payable multi-agent bundle (GDE Track 3) ---------------
    # Seeded per-skill (not gated on the empty-collection check above) so the
    # AP bundle appears even on a fixture that already has the demo skills.
    _seed_ap_skills(now)

    # ---- demo document ---------------------------------------------------
    documents = list(client.collection("documents").stream())
    if not documents:
        client.collection("documents").document("demo-doc-1").set(
            {
                "documentId": "demo-doc-1",
                "name": "welcome-to-aitana.md",
                "format": "MD",
                "ownerId": WORKSHOP_USER_UID,
                "ownerEmail": WORKSHOP_USER_EMAIL,
                "createdAt": now,
                "parseStatus": "parsed",
                "content": _demo_document_content(),
                "accessControl": {"type": "public"},
            }
        )

    # ---- tool permissions ------------------------------------------------
    # `auth.permissions.can_use_tool()` denies by default when no rule
    # matches the caller. In LOCAL_MODE the workshop-user has no
    # production tool_permissions rule, so the agent fails on the
    # first tool call with "user workshop@local is not permitted to
    # use tool X". Seed a wildcard `*` doc that grants all tools to
    # everyone — LOCAL_MODE is a single-user sandbox, the production
    # permission story is irrelevant here.
    tool_perms = list(client.collection("tool_permissions").stream())
    if not tool_perms:
        client.collection("tool_permissions").document("*").set(
            {
                "type": "wildcard",
                "tools": ["*"],
                "denied": [],
                "note": "LOCAL_MODE wildcard — single-user sandbox; allow everything.",
            }
        )
        # Clear the in-process permission cache so the new wildcard is
        # observable on the very next tool call (no 60s TTL wait). Pre-fix
        # boots will have cached negative results for `(workshop@local, *)`;
        # without this clear, users would see the "blocked" error persist
        # for a minute after the seed wrote the wildcard.
        from auth.permissions import clear_cache as _clear_perm_cache

        _clear_perm_cache()

    counts = client.snapshot_size() if hasattr(client, "snapshot_size") else {}
    logger.info("LOCAL_MODE fixture seeded: %s", counts)


# Accounts-Payable multi-agent bundle — seeded from the on-disk templates so
# the orchestrator + specialists show up in the LOCAL_MODE picker. Order is
# cosmetic; the orchestrator wires the rest via subSkills.
_AP_SKILL_NAMES = ("ap-orchestrator", "docparse", "ap-validator", "ap-poster")


def _seed_ap_skills(now: float) -> None:
    """Seed the AP skill bundle from disk templates. Idempotent per skill_id.

    Each template is inserted with ``skill_id == slug == name`` (a stable id),
    owned by the workshop user and marked public so it appears in the
    LOCAL_MODE picker. Pinning the id to the name also lets the orchestrator's
    ``subSkills`` resolve directly via ``get_skill`` — and the name-fallback in
    ``adk/agent.py`` covers cloud seeding where ids are random UUIDs.
    """
    from pathlib import Path

    from admin.platform_seed import _parse_template
    from db import firestore as fs

    templates_root = Path(__file__).resolve().parent.parent / "skills" / "templates"
    for name in _AP_SKILL_NAMES:
        skill_md = templates_root / name / "SKILL.md"
        if not skill_md.exists():
            logger.warning("seed_local_fixture: AP template %s missing; skipping", skill_md)
            continue
        if fs.get_document("skills", name) is not None:
            continue
        try:
            parsed = _parse_template(skill_md)
        except Exception as e:
            logger.warning("seed_local_fixture: failed to parse %s: %s", skill_md, e)
            continue
        fs.set_document(
            "skills",
            name,
            {
                "skillId": name,
                "slug": name,
                "name": parsed["name"],
                "displayName": parsed["name"],
                "description": parsed["description"],
                "instructions": parsed["instructions"],
                "skillMetadata": parsed["metadata"],
                "ownerId": WORKSHOP_USER_UID,
                "ownerEmail": WORKSHOP_USER_EMAIL,
                "accessControl": {"type": "public"},
                "tags": ["gde", "accounts-payable"],
                "featured": True,
                "usageCount": 0,
                "createdAt": now,
                "updatedAt": now,
            },
        )


def _demo_skills(now: float) -> list[dict]:
    """Three demo skills mapped to workshop modules.

    The skill IDs are stable so URLs/docs can reference them deterministically.
    """
    base = {
        "ownerId": WORKSHOP_USER_UID,
        "ownerEmail": WORKSHOP_USER_EMAIL,
        "accessControl": {"type": "public"},
        "skillMetadata": {
            "author": "aitana",
            "version": "1.0",
            "model": "gemini-2.5-flash",
            "tools": [],
            "toolConfigs": {},
            "subSkills": [],
        },
        "tags": ["workshop", "demo"],
        "featured": True,
        "usageCount": 0,
        "createdAt": now,
        "updatedAt": now,
    }
    return [
        {
            **base,
            "skillId": "demo-researcher",
            "slug": "demo-researcher",
            "displayName": "Demo Researcher",
            "name": "demo-researcher",
            "description": (
                "Workshop W2 demo: a plain ADK agent that answers questions "
                "about the platform. Streams via AG-UI, no tools."
            ),
            "instructions": (
                "You are a friendly research assistant introducing workshop "
                "attendees to the AI Protocol Platform. Keep answers short, "
                "cite concrete examples from the codebase when possible, and "
                "always invite the user to try one of the other demo skills "
                "next."
            ),
            "initialMessage": ("Welcome! Ask me anything about the platform, ADK, or the v6 protocol stack."),
        },
        {
            **base,
            "skillId": "demo-form-builder",
            "slug": "demo-form-builder",
            "displayName": "Demo Form Builder",
            "name": "demo-form-builder",
            "description": (
                "Workshop W6 demo: emits A2UI declarative UI. Ask for a form "
                "and it returns a renderable form definition."
            ),
            "instructions": (
                "You build small forms on demand. When the user describes a "
                "form, respond with an A2UI form definition the frontend can "
                "render. Always include name, email, and one custom field."
            ),
            "initialMessage": (
                "Tell me what kind of form to build (e.g. 'event signup' or 'support request') and I'll generate one."
            ),
        },
        {
            **base,
            "skillId": "demo-map-explorer",
            "slug": "demo-map-explorer",
            "displayName": "Demo Map Explorer",
            "name": "demo-map-explorer",
            "description": (
                "Workshop W7 placeholder: in cloud mode, this skill activates "
                "the ext-apps-map MCP server and renders interactive globes. "
                "In LOCAL_MODE the MCP server is disabled — the agent will "
                "describe what it would do."
            ),
            "instructions": (
                "You normally use the show-map MCP tool to render maps in an "
                "iframe. In LOCAL_MODE the MCP server isn't running, so "
                "instead, describe to the user what bounding box you would "
                "show. Keep it under 3 sentences."
            ),
            "initialMessage": (
                "Try: 'show me Copenhagen' — in cloud mode I'd render a real map; here I'll describe what I'd show."
            ),
        },
        # ────────────────────────────────────────────────────────────────────
        # MULTI-SURFACE-A2UI sprint 2.9 — demo skill for the workspace surface
        # ────────────────────────────────────────────────────────────────────
        # `default_surface: workspace` means every send_a2ui_json_to_client
        # tool call this skill emits is routed to the persistent workspace
        # pane instead of rendering inline-in-chat. See
        # docs/integrations/multi-surface-rendering.md for the howto.
        {
            "ownerId": WORKSHOP_USER_UID,
            "ownerEmail": WORKSHOP_USER_EMAIL,
            "accessControl": {"type": "public"},
            "skillMetadata": {
                "author": "aitana",
                "version": "1.0",
                # MULTI-SURFACE-A2UI sprint 2.9 demo — the agent has to emit
                # a verbatim A2UI JSON spec from its system prompt. Flash
                # sometimes drops delimiters on dense literal JSON which
                # fails payload_fixer.py's parse step. Pro is more literal.
                "model": "gemini-2.5-pro",
                "tools": [],
                "toolConfigs": {
                    "a2ui": {
                        "default_surface": "workspace",
                        "default_update_mode": "replace",
                        # Sprint 2.10 — opt this demo skill into the
                        # surface→agent context loop. Without this flag,
                        # POST /api/sessions/{id}/surface-action returns
                        # 403 (default-deny). With it, the agent reads
                        # the dataModel snapshot on every turn AND can
                        # observe user actions via
                        # a2ui_surface_context.{surfaceId}.lastAction.
                        "allow_surface_context_writes": True,
                    },
                },
                "subSkills": [],
            },
            "tags": ["workshop", "demo", "multi-surface"],
            "featured": True,
            "usageCount": 0,
            "createdAt": now,
            "updatedAt": now,
            "skillId": "demo-workspace",
            "slug": "demo-workspace",
            "displayName": "Workspace Demo",
            "name": "demo-workspace",
            "description": (
                "Multi-surface A2UI demo. Emits dashboard components to the "
                "persistent workspace pane instead of inline-in-chat. "
                "Demonstrates the v6.2.0 sprint 2.9 surface routing."
            ),
            "instructions": (
                "You are a workspace surface demo. You have one tool, "
                "`send_a2ui_json_to_client`, which renders A2UI v0.9 messages "
                "in the user's interface. Because this skill is configured with "
                "`default_surface: workspace`, those messages render in the "
                "workspace pane (NOT inline in chat).\n\n"
                "**Wire format — follow the A2UI v0.9 schema between the "
                "`---BEGIN A2UI JSON SCHEMA---` / `---END A2UI JSON SCHEMA---` "
                "markers in your system instructions, and the v0.9 example "
                "shown right after that block. The argument `a2ui_json` is an "
                "ARRAY of messages — `createSurface`, `updateComponents`, "
                "`updateDataModel`. Components are flattened "
                '(`{id, component: "Text", text, ...}`), and the tree root '
                'must have `id: "root"`.**\n\n'
                "## Trigger: 'show me the dashboard' (or 'demo', 'start')\n\n"
                "Render a small dashboard with these five components, in this order, "
                'as children of a Column with `id: "root"`:\n\n'
                "  1. A Text heading with variant `h2` saying `Workspace Surface Demo`.\n"
                "  2. A Text line (variant `h3`) bound to data path `/activeUsers`.\n"
                "  3. A Text line (variant `h3`) bound to data path `/revenue`.\n"
                "  4. A Divider.\n"
                "  5. A Text line bound to data path `/footnote` (use the "
                'default `body` variant — do NOT set `variant: "caption"` '
                "because the v0.9 React SDK currently renders that as the "
                "HTML `<caption>` element, which is only valid inside "
                "`<table>` and triggers a hydration warning).\n\n"
                'Populate the data model with `activeUsers: "42 users online"`, '
                '`revenue: "$1,234 in revenue"`, and `footnote: "Workspace '
                'persists across chat turns. Type refresh to update."`.\n\n'
                'Use `surfaceId: "workspace"` and `catalogId: '
                '"https://a2ui.org/specification/v0_9/basic_catalog.json"` in '
                "the createSurface message.\n\n"
                "After the tool call succeeds, reply briefly in chat: "
                "\"Dashboard rendered in the workspace pane. Try 'refresh' to "
                'update it live."\n\n'
                "## Trigger: 'refresh' / 'update' / 'new data'\n\n"
                "Send ONLY an `updateDataModel` message (same surfaceId, no "
                "createSurface, no updateComponents — the components are still "
                "live on the surface). Invent realistic numbers, e.g. "
                '`activeUsers: "87 users online"`, `revenue: "$5,678 in '
                'revenue"`, `footnote: "Updated. Workspace persists across '
                'chat turns."`. Reply: "Updated! Notice the dashboard stayed in '
                "place — the chat underneath didn't bury it.\"\n\n"
                "## Trigger: questions about current dashboard state\n\n"
                "When the user asks about what's currently on the workspace "
                "dashboard — e.g. 'what's the current revenue?', 'how many "
                "users are online?', 'what does the footnote say?' — DO NOT "
                "call `send_a2ui_json_to_client`. Instead, read the answer "
                "from the `## a2ui_surface_context` block in your system "
                "instructions (the `dataModel` under the `workspace` surface) "
                "and reply with a short, direct sentence. This proves the "
                "workspace → agent context loop: the agent knows what's on "
                "screen without re-invoking the render tool. Sprint 2.10.\n\n"
                "## Anything else\n\n"
                "Briefly explain this skill is a minimal demo of multi-surface "
                "A2UI rendering, and suggest 'show me the dashboard'."
            ),
            "initialMessage": (
                "Hi — I demonstrate the **multi-surface A2UI** feature. "
                "When I emit UI, it lands in the **workspace pane** (left), not "
                'in the chat. Try: **"show me the dashboard"**.'
            ),
        },
        # ────────────────────────────────────────────────────────────────────
        # Sprint 2.10 follow-up — interactive demo for the discrete-action
        # half of the surface → agent context loop.
        # ────────────────────────────────────────────────────────────────────
        # The read-only `demo-workspace` skill proves the continuous channel
        # (forwardedProps.a2ui_surface_state snapshot). This skill renders
        # a form with a Submit Button whose `action.event` fires
        # A2uiClientAction → POST /api/sessions/{id}/surface-action →
        # writes `a2ui_surface_context.workspace.lastAction`. The next
        # agent turn reads it from the system prompt and answers
        # "what did I just submit?" without re-invoking the render tool.
        {
            "ownerId": WORKSHOP_USER_UID,
            "ownerEmail": WORKSHOP_USER_EMAIL,
            "accessControl": {"type": "public"},
            "skillMetadata": {
                "author": "aitana",
                "version": "1.0",
                "model": "gemini-2.5-pro",
                "tools": [],
                "toolConfigs": {
                    "a2ui": {
                        "default_surface": "workspace",
                        "default_update_mode": "replace",
                        # Mandatory for the discrete-action half — without
                        # this the action POST returns 403 default-deny.
                        "allow_surface_context_writes": True,
                    },
                },
                "subSkills": [],
            },
            "tags": ["workshop", "demo", "multi-surface", "interactive"],
            "featured": True,
            "usageCount": 0,
            "createdAt": now,
            "updatedAt": now,
            "skillId": "demo-workspace-interactive",
            "slug": "demo-workspace-interactive",
            "displayName": "Workspace Demo (Interactive)",
            "name": "demo-workspace-interactive",
            "description": (
                "Interactive multi-surface A2UI demo. Renders a form to the "
                "workspace pane; user submits a value via a Button action; "
                "the agent reads the structured action context on the next "
                "turn without re-rendering. Demonstrates the discrete-action "
                "half of the v6.2.0 sprint 2.10 surface→agent loop."
            ),
            "instructions": (
                "You are an INTERACTIVE workspace surface demo. You have one "
                "tool, `send_a2ui_json_to_client`, which renders A2UI v0.9 "
                "messages in the user's workspace pane (NOT inline in chat) "
                "because this skill is configured with "
                "`default_surface: workspace`.\n\n"
                "**Wire format — follow the A2UI v0.9 schema between the "
                "`---BEGIN A2UI JSON SCHEMA---` / `---END A2UI JSON SCHEMA---` "
                "markers in your system instructions, and the v0.9 example "
                "shown right after that block. The argument `a2ui_json` is an "
                "ARRAY of messages — `createSurface`, `updateComponents`, "
                "`updateDataModel`. Components are flattened "
                '(`{id, component: "Button", child: "...", action: {...}}`).**\n\n'
                "## Trigger: 'show me the form' (or 'demo', 'start')\n\n"
                "Render an interactive form in the workspace surface with "
                'these components as children of a Column with `id: "root"`:\n\n'
                "  1. A Text heading (variant `h2`) saying `Interactive Form Demo`.\n"
                "  2. A Text line (default `body` variant) saying `Type "
                "something below and click Submit — the agent will read your "
                "submission on the next turn without re-rendering.`\n"
                '  3. A TextField with `label: "Your message"` and `value` '
                "bound to data path `/formInput`.\n"
                "  4. A Row containing two Buttons:\n"
                '     - Submit Button: `variant: "primary"`, `child` is a '
                'Text component with `text: "Submit"`, `action.event` with '
                '`name: "submit"` and '
                '`context: {value: {path: "/formInput"}}` so the typed value '
                "rides along.\n"
                "     - Reset Button: default variant, `child` is a Text "
                'with `text: "Reset"`, `action.event` with `name: "reset"` '
                "and an empty context.\n\n"
                'Populate the data model with `formInput: ""` (empty initial '
                "value).\n\n"
                'Use `surfaceId: "workspace"` and `catalogId: '
                '"https://a2ui.org/specification/v0_9/basic_catalog.json"` in '
                "the createSurface message.\n\n"
                "After the tool call succeeds, reply briefly in chat: "
                '"Form rendered in the workspace pane. Type something and '
                'click Submit — then ask me what you sent."\n\n'
                "## Trigger: questions about what the user submitted\n\n"
                "When the user asks 'what did I just submit?', 'what was my "
                "last input?', 'what did I click?', or similar — DO NOT call "
                "`send_a2ui_json_to_client`. Read the answer from the "
                "`## a2ui_surface_context` block in your system instructions, "
                "specifically `workspace.lastAction`:\n\n"
                '  - `lastAction.name = "submit"` means they submitted.\n'
                "  - `lastAction.context.value` is the string they typed.\n"
                '  - `lastAction.name = "reset"` means they pressed reset.\n\n'
                "Reply with a short, direct sentence quoting their submitted "
                'value, e.g. "You submitted \\"hello world\\"." This proves '
                "the discrete-action half of the surface→agent context loop: "
                "the agent observes a user gesture in structured form, no "
                "tool re-invoke. Sprint 2.10.\n\n"
                "If no lastAction is present (user hasn't clicked yet), say "
                "\"I don't see a submission yet — type something in the "
                'workspace form and click Submit."\n\n'
                "## Anything else\n\n"
                "Briefly explain this skill is the interactive sibling of "
                "the read-only workspace dashboard demo, and suggest 'show "
                "me the form'."
            ),
            "initialMessage": (
                "Hi — I'm the **interactive** workspace demo. Type "
                '**"show me the form"** to start. After you click Submit, '
                "I'll be able to tell you what you sent — without needing "
                "to re-render anything."
            ),
        },
        # ────────────────────────────────────────────────────────────────────
        # WORKSHOP-HELPER (Path B) — the meta-demo. Answers questions about
        # the platform from the actual docs corpus. RAG via search_workshop_docs
        # which indexes docs/workshop/, docs/integrations/,
        # docs/design/v6.X.Y/implemented/, and docs/talks/ai-ui-protocol-stack.md.
        # Path D (sprint 2.15) will extend this with show-and-tell + cohort
        # bootstrap. v1 is just the RAG skill.
        # ────────────────────────────────────────────────────────────────────
        {
            "ownerId": WORKSHOP_USER_UID,
            "ownerEmail": WORKSHOP_USER_EMAIL,
            "accessControl": {"type": "public"},
            "skillMetadata": {
                "author": "aitana",
                "version": "1.0",
                "model": "gemini-2.5-flash",
                "tools": ["search_workshop_docs"],
                "toolConfigs": {},
                "subSkills": [],
            },
            "tags": ["workshop", "demo", "helper", "rag"],
            "featured": True,
            "usageCount": 0,
            "createdAt": now,
            "updatedAt": now,
            "skillId": "workshop-helper",
            "slug": "workshop-helper",
            "displayName": "Workshop Helper",
            "name": "workshop-helper",
            "description": (
                "The workshop's meta-demo: a skill that answers questions about "
                "the AI Protocol Platform itself, grounded in the real docs corpus. "
                "Uses search_workshop_docs to retrieve from agenda + code tour + "
                "protocol gotchas + every shipped sprint design doc + every fork-"
                "adoption howto. Demonstrates RAG over markdown without any "
                "embedding store."
            ),
            "instructions": (
                "You are the **workshop helper agent**. You guide attendees of the "
                '"Build AI UIs Beyond Chat" workshop. The platform you run on is '
                "the same code attendees are learning — you ARE the meta-demo.\n\n"
                "**You have one tool: `search_workshop_docs(query, max_results)`.**\n\n"
                "## How to use the tool\n\n"
                "For ANY question about the platform, the workshop, the protocols "
                "(AG-UI / A2UI / MCP / A2A / ADK), the sprints, the gotchas, the "
                "fork-adoption patterns, or the workshop agenda — **call "
                "`search_workshop_docs` FIRST**, then synthesise an answer from the "
                "returned snippets.\n\n"
                "Good queries:\n"
                "  - 'AG-UI state one turn behind'\n"
                "  - 'A2UI surface context loop'\n"
                "  - 'iframe context seven gates'\n"
                "  - 'anonymous group auth join code'\n"
                "  - 'budget enforcer protocol'\n"
                "  - 'workshop block 4 sandbox'\n\n"
                "## How to answer\n\n"
                "1. **Cite the file path** from the tool result (e.g. "
                "`docs/design/v6.2.0/implemented/a2ui-surface-context.md`). The "
                "user can click it to read the source.\n"
                "2. **Quote or summarise** the relevant snippet — keep your "
                "answer grounded in what the docs actually say.\n"
                "3. **If the tool returns 'no documents matched'**, say so "
                "explicitly. DO NOT invent facts. A clear 'I don't have that "
                "in my knowledge base — try rephrasing or ask your instructor' "
                "is more valuable than a confident hallucination.\n"
                "4. **Keep answers concise** — the user is in a workshop, not "
                "reading a manual. 2-4 sentences + a citation is usually right.\n"
                "5. **If the user asks 'what is this workshop about?' or "
                "'what's on the agenda'** — call the tool with query 'workshop "
                "agenda blocks' and summarise the agenda.\n\n"
                "## What you know about\n\n"
                "The knowledge base covers:\n"
                "  - The workshop agenda + code tour + protocol gotchas + "
                "    pre-work\n"
                "  - Every shipped v6.0.0, v6.1.0, v6.2.0 sprint design doc "
                "    (with implementation details, axiom scores, success "
                "    metrics, gotchas)\n"
                "  - Fork-adoption howtos for budget enforcement, artefact "
                "    review, tenant attribution, anonymous-group auth, "
                "    channels, multi-surface rendering\n"
                "  - The canonical living talk doc "
                "    (`docs/talks/ai-ui-protocol-stack.md`) with the "
                "    verification log + anti-patterns\n\n"
                "You DON'T have access to operational docs, deployment "
                "internals, customer-specific deployments, or anything "
                "outside `docs/`. If asked, say so."
            ),
            "initialMessage": (
                "Hi — I'm the **workshop helper agent**. I run on the same "
                "platform you're learning about, and I can answer questions "
                "from the real docs (agenda, code tour, protocol gotchas, "
                "shipped sprint designs, fork howtos). Try:\n\n"
                "- *'How does the surface-context loop work?'*\n"
                "- *'What are the seven gates on the iframe-context endpoint?'*\n"
                "- *'What's in block 5 of the agenda?'*\n"
                "- *'Why is AG-UI's state one turn behind?'*\n\n"
                "Answers come from RAG over real docs — I'll cite the path "
                "so you can read the source."
            ),
        },
    ]


def _demo_document_content() -> str:
    return (
        "# Welcome to the AI Protocol Platform\n\n"
        "An open-source, protocol-native AI platform built on Google ADK. "
        "It demonstrates how AG-UI, A2UI, MCP, A2A, and MCP Apps can compose "
        "into a single coherent user experience.\n\n"
        "## Try the demo skills\n\n"
        "- **Demo Researcher** — pure ADK, streaming AG-UI text only\n"
        "- **Demo Form Builder** — emits an A2UI form for the frontend to render\n"
        "- **Demo Map Explorer** — wired to ext-apps-map (cloud mode only)\n\n"
        "Open WORKSHOP.md to see the matching code paths.\n"
    )
