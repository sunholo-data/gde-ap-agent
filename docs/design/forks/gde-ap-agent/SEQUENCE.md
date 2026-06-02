# GDE AP Agent — Design Doc Sequence

Fork of Aitana Platform v6 for the **Google AI Agents Challenge, Track 3** (deadline: 2026-06-05 17:00 PT).

## Design Docs

| # | Document | Priority | Estimate | Status |
|---|----------|----------|----------|--------|
| 1 | [Competition Polish Sprint](./competition-polish-sprint.md) | P0 | 3 days | ✅ Implemented |
| 2 | [GCS Bucket Browser](./gcs-bucket-browser.md) | P0 | 2 days | Planned |
| 3 | [Multi-Agent Inspector UX](./multi-agent-inspector-ux.md) | P0 | 2.5 days | Planned |
| 4 | [Schema-Enforced Structured Extraction](./schema-enforced-extraction.md) | P0 | 1.5 days | Planned |

## Timeline

| Date | Milestone |
|------|-----------|
| 2026-06-01 | Competition polish sprint complete (M1–M6 shipped) |
| 2026-06-02 | GCS Bucket Browser + Multi-Agent Inspector UX + Schema-Enforced Extraction design docs written |
| 2026-06-02–03 | GCS Bucket Browser implementation |
| 2026-06-03–04 | Multi-Agent Inspector UX implementation |
| 2026-06-03–04 | Schema-Enforced Extraction implementation (parallel — pure backend) |
| 2026-06-04 | Final testing + submission prep |
| 2026-06-05 17:00 PT | **Submission deadline** |

## What ships in v0.1.0

- 4-skill AP pipeline (ap-orchestrator → invoice-extractor → ap-validator → ap-poster)
- Navy + gold AP finance theme, dark mode default
- AG-UI streaming with APPipelineSteps 4-step progress visualizer
- A2UI invoice result card (workspace surface)
- MCP sandbox vendor globe + AP analytics dashboard
- GCS bucket browser with demo invoices + user bucket support
- Hub-and-spokes navigation: orchestrator as the only chat tab, three live specialist inspector chips with structured-input-only invocation and an `ap-vendor-kg` MCP App showcase on the validator
- Schema-enforced structured extraction: each specialist's output is JSON Schema-validated server-side via the declarative `metadata.extraction_schema` field in SKILL.md — hard structural guarantees, not prose-followed-by-vibes
