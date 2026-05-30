# Playground Tutor — Fork Scope (v0.1.0 MVP)

**Status**: Planned — pre-fork, awaiting Jesper sign-off on §Open Questions
**Priority**: P1 — first commercial fork of `platform-template`; validates the protocol-first thesis
**Scope**: New product on a downstream fork of `platform-template`
**Dependencies**:
- `platform-template` public fork (Phase 3 of [v6.0.0/SEQUENCE.md](../../../v6.0.0/SEQUENCE.md)) — gate met, fork itself not yet done
- Jesper sign-off on §Open Questions
**Created**: 2026-05-01
**Working name**: "Playground Tutor" — Jesper's brand TBD

## Problem Statement

Jesper (Danish secondary-school STEM teacher) ran an embodied-learning lesson on the playground: groups of 3 students used their phones to talk to an AI tutor while drawing chalk diagrams on the asphalt and working through a paper worksheet of geometry/physics tasks. The bot was a v5 assistant with a custom pedagogy prompt ("ESRU"). The session surfaced concrete failure modes:

1. **Voice input was unusable.** Danish ASR on teenage voices in a noisy outdoor environment, combined with 2-4s STT→LLM→TTS latency, killed conversational flow.
2. **The bot lacked context.** No awareness of which task they were on, which worksheet, which group, what they had already tried. It re-asked questions, gave generic hints, and could not ground responses in the chalk diagrams or the worksheet's data tables.
3. **Teacher could not triage.** Jesper walked from group to group based on noise, not progress. The groups that were stuck silently got the least help.
4. **Photos of chalk diagrams** were the natural input modality, but had no role in the v5 stack.

The v5 platform was the wrong shape for this. v6's protocol-first architecture (skills + ADK + AG-UI + MCP) maps almost directly onto what is needed, which is the reason this doc exists rather than a from-scratch greenfield spec.

## Goals

**Primary:** Ship a 4-6 week MVP that lets Jesper run a publishable lesson with real students by July 2026, where the bot has lesson/task/group context, photo grounding, and Jesper has a live triage dashboard.

**Secondary:** Validate the platform-template thesis — that a new vertical app is "fork the template + a `LessonConfig` extension + two MCP servers + a dashboard," not a from-scratch build.

**Success Metrics:**
- One full classroom-or-playground session with Jesper's students completes without engineering intervention
- Jesper reports the dashboard changed which group he walks to (i.e., stuck-detection surfaces real signal)
- A Danish-speaking student can hear the bot's hint via TTS while looking at their chalk diagram (TTS quality on actual school devices is good enough)
- Photo→hint round-trip <8s on typical school WiFi
- A second lesson on a different topic is configurable in <1 day by editing the lesson config + RAG corpus, with no code changes

**Non-Goals:**
- Voice input (STT) — deferred; revisit only if classroom (not playground) deployment shows demand
- Local model inference — architecturally a swap-out via the agent factory's provider routing; ship with cloud models for v1
- Multi-language UI — Danish only; English/German is config not code, but not a v1 burn
- Persistent student accounts / cross-lesson history — anonymous session codes only
- Native iOS/Android apps — PWA covers the use case; native is a year-2 conversation if at all
- Multi-tenant SaaS — one deployment per school/district/contract

## Axiom Alignment

| # | Axiom | Score | Notes |
|---|-------|-------|-------|
| 1 | INSTANT FEEL | +2 | Photo + TTS hides round-trip latency; AG-UI streaming makes the bot feel responsive on bad WiFi |
| 2 | EARNED TRUST | +2 | Teacher dashboard + guardrail callbacks mean Jesper can trust what the bot says to his students |
| 3 | SKILLS, NOT FEATURES | +2 | Each lesson = one skill (`LessonConfig`); new lessons are config, not code |
| 4 | RIGHT MODEL, RIGHT MOMENT | +1 | Vision needs Gemini Flash / Haiku for cost-per-photo; pure-text turns can be Haiku-tier |
| 5 | GRACEFUL DEGRADATION | +2 | School WiFi is bad. PWA + offline-queue replay are non-negotiable |
| 6 | PROTOCOL OVER CUSTOM | +2 | Lesson context, vision grounding, stuck detection = MCP servers. Code exec = ADK FunctionTool. No bespoke transports |
| 7 | API FIRST | +1 | Teacher dashboard is just another AG-UI subscriber; the API does not change for it |
| 8 | OBSERVABLE BY DEFAULT | +1 | OTEL → Cloud Trace ships with the template; used from day one |
| 9 | SECURE BY CONSTRUCTION | +2 | Anonymous students by design; no PII; teacher-only Firebase auth; photos auto-purge |
| 10 | THIN CLIENT, FAT PROTOCOL | +1 | Pedagogy logic in callbacks/MCP servers; client renders chat + photo + dashboard |
| | **Net Score** | **+16** | Threshold: >= +4 |

## Design

### Repo + branding

**Source:** Fork from `platform-template` (the public template produced by Phase 3 of [v6.0.0/SEQUENCE.md](../../../v6.0.0/SEQUENCE.md)). If the template fork has not shipped when this sprint starts, fall back to forking from `Aitana-Labs/platform` at the `template-fork-base-v6.0.0` tag and running the sanitization script locally — the template fork's pre-work is shared with this fork's branding pass anyway.

**Repo name:** TBD with Jesper. Working name: `playground-tutor`.

**Branding pass (1-2 days), assuming the template's `branding.ts` config-ification has landed:**
- Replace strings in `frontend/src/lib/branding.ts`
- Replace `frontend/public/images/logo/` and favicon
- Replace landing copy in `frontend/src/app/page.tsx` and `<title>`/meta in `layout.tsx`
- Update `frontend/public/manifest.json` (PWA install copy + icons)
- New `cloudbuild.yaml` substitutions (project IDs, Cloud Run service names)
- New GCP project IDs (or one project per env, matching v6 dev/test/prod pattern)

### Lesson data model

A **lesson** is one instance of a `LessonConfig`, which extends the platform's existing `SkillConfig`:

```python
class LessonConfig(SkillConfig):
    worksheet_doc_id: str                           # AILANG-Parse'd document artifact
    canonical_solutions_artifact: str | None        # hidden from student-facing prompt; available to model
    pedagogy_prompt: str                            # teacher-authored
    guardrails: GuardrailRules                      # enforced by callback layer (see below)
    tools_enabled: list[str]                        # vision_grounding, code_exec, lesson_context
    tts_voice: str = "da-DK"
    expected_tasks: list[TaskSpec]                  # for stuck-detection scoring
```

This reuses the platform's existing access control, fork pattern, Firestore persistence, and skill-CRUD UI without modification.

### Group session model — anonymous students

This is net-new auth work. The platform currently uses Firebase auth for everything; students need a different shape:

1. **Teacher** (Firebase-authed) creates a lesson and clicks "Start session" → backend mints a 6-character join code, valid for the lesson period (default 90 min, teacher-configurable).
2. **Each student device** hits `POST /api/proxy/sessions/join` with `{code, group_label}` → backend issues a short-lived signed JWT (claims: `lesson_id`, `group_id`, `session_id`) with no Firebase user record.
3. **ADK session** uses this `session_id` as `user_id` (ADK does not care about the value). Sessions live in the same Vertex AI sessions store as authenticated users.
4. **Firestore rules** for a new `lesson_sessions/{session_id}` collection are gated on the join-code claim, not `auth.uid`. Teachers can read all sessions under their `lesson_id`; students can only read/write their own.
5. **Photos** uploaded under a session land in `gs://<bucket>/lessons/{lesson_id}/sessions/{session_id}/...` with a TTL-based lifecycle rule (default 30 days).

### MCP servers (per-capability)

Three new FastMCP servers, mounted via the template's existing pattern:

1. **`lesson_context`** — exposes `current_task()`, `worksheet_excerpt(task_id)`, `group_progress()`, `record_progress(task_id, status)`. Backed by Firestore. Called on every model turn to ground "where are they now."
2. **`vision_grounding`** — wraps photo upload + Gemini Flash vision with the worksheet's expected diagram structure. Returns a *structured* analysis ("ray from H at 30°, ray from G at 45°, intersection at coordinates X") rather than free text. The model uses this as grounded input to its hint, not as raw output.
3. **`stuck_detection`** — passive observer over the last N events (turns, failed attempts, time since last progress signal). Exposes `stuck_score(session_id)` for the dashboard's refresh loop. **Not** wired into the student-facing agent — being aware of its own stuck-score would change the model's behaviour in confusing ways.

Code execution rides on **ADK's existing FunctionTool pattern** (the v5 `code_execution` tool ported in 1A.3 [tools-porting-guide.md](../../../v6.0.0/implemented/tools-porting-guide.md)). No new server.

### Guardrail callback layer

A single `before_model_callback` enforces rules the teacher's prompt cannot override:

- Trim model output to `max_words_per_turn`
- Block multi-question outputs (regex on `?` count) → re-prompt the model "give one question"
- Track failed-attempt counter per task; after `escalate_after_failed_attempts`, force a "raise hand for the teacher" message and ping the dashboard

This protects against the ESRU failure mode: a constrained pedagogy prompt that left the model paralysed when the prompt itself was over-tight.

### Frontend (Next.js 15 + React 19, PWA)

Reuse the template's chat shell. Add:

- **Camera capture component** — `<input type="file" accept="image/*" capture="environment">` with preview + retake. Uploads via the existing artifact-upload pipeline.
- **Group join screen** — single screen: enter join code + group label ("Group Mars"). No login.
- **Chat with TTS** — auto-play bot replies via `window.speechSynthesis` with `lang="da-DK"`, voice fallback chain. Manual replay button per message.
- **Teacher lesson-creation flow** — form-based wrapper over `LessonConfig`. Worksheet upload → AILANG Parse → preview → save. ~2-3 days.
- **Teacher dashboard** — separate route. Subscribes to AG-UI streams for all active sessions under the teacher's lessons. Grid of group cards: group label, current task, last 3 messages, stuck score, photo thumbnails. Auto-refresh every 5s. **~5-7 days; this is the schedule risk.**
- **PWA shell** — `manifest.json` + service worker for offline-first chat queue. ~1 day.

### Architecture map

```
┌────────────────────────────────┐    ┌────────────────────────────────┐
│  Student device (PWA)          │    │  Teacher device (PWA)          │
│  - Join screen                 │    │  - Lesson creation             │
│  - Chat + photo + TTS          │    │  - Live dashboard              │
└────────────┬───────────────────┘    └────────────┬───────────────────┘
             │ AG-UI SSE                            │ AG-UI SSE (multi-sub)
             ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI + ADK, forked from platform-template)              │
│  - Auth: Firebase (teacher) + signed JWT (student)                   │
│  - Skill = LessonConfig                                              │
│  - Agent factory routes Gemini Flash (vision) / Haiku (text)         │
│  - before_model_callback = guardrails                                │
│  - MCP servers: lesson_context, vision_grounding, stuck_detection    │
│  - FunctionTool: code_execution (template-inherited)                 │
└────────────┬─────────────────────────────────────────────────────────┘
             │
   ┌─────────┼──────────┬──────────────────┐
   ▼         ▼          ▼                  ▼
Firestore  Vertex AI  Cloud Storage    AILANG Parse
(lessons,  Sessions   (photos +        (worksheets)
 sessions, (chat      worksheets)
 progress) history)
```

## Implementation Plan

Six-week shape. Each week is a milestone gate; pause for Jesper review at the end of weeks 3 and 5.

### Week 1 — Fork + branding + lesson model
- Fork from `platform-template` (or sanitized base if template fork is still pending)
- Branding pass (logo, copy, manifest, cloudbuild substitutions)
- `LessonConfig` Pydantic model + Firestore schema + REST shape (extends `SkillConfig`)
- New GCP project bootstrap (or new env in shared infra, decided with Jesper)

### Week 2 — Anonymous sessions + photo input
- Join-code minting + signed-JWT auth path
- `lesson_sessions` Firestore collection + rules (gated on code claim, not `auth.uid`)
- Adversarial test of session isolation (`make verify-rules` adapted)
- Camera capture component on PWA
- Photo upload through existing artifact pipeline + TTL lifecycle rule
- **Gate:** student joins by code, sends photo, agent receives it as a grounded artifact

### Week 3 — Lesson context + vision grounding + code exec
- `lesson_context` MCP server (Firestore-backed)
- `vision_grounding` MCP server (Gemini Flash + worksheet context)
- ADK FunctionTool wiring for `code_execution` (template-inherited)
- AILANG Parse for sample worksheet → Firestore + RAG embedding
- **Gate (Jesper review #1):** student sends photo of chalk diagram, agent grounds against worksheet, calls code exec to verify geometry, returns hint

### Week 4 — Guardrails + TTS + lesson creation UI
- `before_model_callback` enforcing word count + one-question + escalation
- Browser SpeechSynthesis TTS with Danish voice fallback chain
- **TTS device-quality spike** (2 hours, on actual school iPads/Androids if available; queue ElevenLabs/Azure Neural fallback if browser quality is unacceptable)
- Teacher lesson-creation form + worksheet upload UI

### Week 5 — Teacher dashboard + stuck-detection
- `stuck_detection` MCP server with baseline heuristic ("3 turns no progress, or repeated phrasing")
- Multi-session AG-UI subscription pattern on dashboard
- Group-card grid with task / last 3 messages / stuck score / photo thumbnails
- Auto-refresh loop, 5s
- **Gate (Jesper review #2):** Jesper looks at the dashboard during a dry-run and reports whether the stuck signal is useful

### Week 6 — PWA shell + classroom test + polish
- PWA manifest + service worker + offline message queue
- Production deploy + smoke probe
- Live test with Jesper, ideally on a real (small) lesson with a few students
- Bug fix + polish
- **Gate (launch):** post-mortem with Jesper, decide go/no-go on a wider classroom rollout

### Risk register

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Teacher dashboard sprawls past 7 days | High | Cap at MVP feature list; replay/playback explicitly out of scope |
| Danish TTS quality on school devices is poor | Medium | Spike on real devices week 4; ElevenLabs/Azure Neural fallback ready |
| Stuck-detection heuristic is noisy | Medium | Conservative threshold; let Jesper tune via lesson config; instrument for calibration |
| School WiFi worse than expected | Medium | PWA service worker caches chat; offline queue replays on reconnect |
| Anonymous-session Firestore rules have a hole | High | Adversarial curl tests with forged JWT claims; rules-runner test from `make verify-rules` adapted |
| Photo retention does not satisfy Danish GDPR-for-minors | Medium | Confirm with Jesper / school's data controller before launch; default 30-day TTL with no cross-lesson retention |
| Template fork still not done when sprint starts | Medium | Fall back to forking from `Aitana-Labs/platform` at `template-fork-base-v6.0.0` + running sanitization script locally |
| Vision grounding mis-reads chalk diagrams | Medium | Structured prompt + worksheet context; instrument false-positive rate; degrade gracefully ("can't see clearly, try another angle") |

## Migration & Rollout

No migration — this is a new product. Rollout:

1. **Internal dry-run** with Jesper, no students, on a fake lesson
2. **Single classroom**, single lesson, with Jesper present
3. **Single playground session** (the original use case)
4. Iterate on stuck-detection + dashboard based on Jesper's feedback
5. **Second lesson** (different topic, same teacher) to validate "new lesson is config not code"

Rollback: each environment is independent; rollback = redeploy previous Cloud Run revision.

## Testing Strategy

- **Unit:** `LessonConfig` validation, guardrail callback, stuck-detection heuristic
- **Integration:** anonymous session join flow, photo upload + grounding round-trip, multi-session AG-UI subscription
- **Eval:** ADK evalset with sample lesson + sample student transcripts; rubric scores hint quality + guardrail adherence + grounding-in-photo
- **Adversarial:** cross-session read attempts via curl with forged JWT claims (rules runner)
- **Device:** TTS quality on iPad (school standard) + Android Chrome; week 4 spike

## Security Considerations

- **No PII for students** by design. Only `session_id`, `group_label`, photos.
- **Photos** auto-purge after configurable TTL (default 30d) via bucket lifecycle rule.
- **Student JWTs** are short-lived (lesson duration only, default 90 min); cannot be reused across sessions.
- **Teacher Firebase auth** uses the template's existing pattern — domain allowlist, role tags.
- **Firestore rules** enforce session-code ownership. Adversarial test before launch.
- **GDPR-for-minors:** confirm data controller (Jesper? school? municipality?) before launch. Auto-purge is the cleanest story. Document in a privacy note for Jesper to share with the school.

## Open Questions

### For Jesper

1. **Photo retention.** Default 30-day auto-purge OK, or shorter (per-lesson)?
2. **Stuck-detection rules.** Is "3 turns without progress, or repeated phrasing" a reasonable starting heuristic? Specific signal in mind?
3. **Dashboard scope.** Live-only sufficient for MVP, or need replay/scrub for post-lesson reflection?
4. **TTS voice.** Browser-default Danish voice, or willing to pay for ElevenLabs / Azure Neural?
5. **Lesson creation UX.** Will Jesper himself author lesson configs, or do we need a non-technical authoring flow for colleagues?
6. **Worksheet input format.** Always a teacher-uploaded PDF? Or Word / Google Docs / paper-photographed?
7. **Branding.** Repo name + product name + logo direction.
8. **Hosting.** Run on Aitana-Labs GCP infra (subcontract style) or the school district's own GCP / Azure tenancy?
9. **Pricing model.** One-time contract, ongoing SaaS, or open-source under sponsorship?
10. **Data controller.** Who is GDPR-responsible for photos and chat content?

### For Mark

1. **Fork timing.** Wait for `platform-template` (Phase 3 of v6.0.0) before forking this, or fork now from `Aitana-Labs/platform` at the `template-fork-base-v6.0.0` tag? **Recommendation: do the template fork first.** Phase 3 has been deferred to mid-to-late May; this contract force-functions it. Pre-work (env vars + `branding.ts` + `.env.example`) is shared between both forks anyway.
2. **NDA / IP.** Is the contract structured so the platform-derived code stays Aitana-Labs IP, or does the client own the fork? Affects whether bug fixes flow back upstream.
3. **Workshop tie-in.** Could this fork *be* the July workshop demo (a real working customer fork)? Stronger story than a synthetic example.

## Related Documents

- [Template split strategy](../../../v6.0.0/template-split-strategy.md) — fork mechanics this depends on
- [v6.0.0 SEQUENCE.md](../../../v6.0.0/SEQUENCE.md) — Phase 3 (template fork) status
- [Auth and permissions](../../../v6.0.0/implemented/auth-and-permissions.md) — pattern this extends with anonymous JWTs
- [Streaming and protocols](../../../v6.0.0/implemented/streaming-and-protocols.md) — AG-UI multi-sub pattern the dashboard relies on
- [Skills data model](../../../v6.0.0/implemented/skills-data-model.md) — `LessonConfig` extends `SkillConfig`
- [Tools porting guide](../../../v6.0.0/implemented/tools-porting-guide.md) — `code_execution` FunctionTool reused
- [Workshop tracker](../../../talks/ai-ui-protocol-stack.md) — July 2026 demo target
