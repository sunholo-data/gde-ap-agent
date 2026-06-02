# GDE AP Agent — Design Doc Sequence

Fork of Aitana Platform v6 for the **Google AI Agents Challenge, Track 3** (deadline: 2026-06-05 17:00 PT).

## Design Docs

| # | Document | Priority | Estimate | Status |
|---|----------|----------|----------|--------|
| 1 | [Competition Polish Sprint](./competition-polish-sprint.md) | P0 | 3 days | ✅ Implemented |
| 2 | [GCS Bucket Browser](./gcs-bucket-browser.md) | P0 | 2 days | Planned |

## Timeline

| Date | Milestone |
|------|-----------|
| 2026-06-01 | Competition polish sprint complete (M1–M6 shipped) |
| 2026-06-02 | GCS Bucket Browser design doc written |
| 2026-06-02–03 | GCS Bucket Browser implementation |
| 2026-06-04 | Final testing + submission prep |
| 2026-06-05 17:00 PT | **Submission deadline** |

## What ships in v0.1.0

- 4-skill AP pipeline (ap-orchestrator → docparse → ap-validator → ap-poster)
- Navy + gold AP finance theme, dark mode default
- AG-UI streaming with APPipelineSteps 4-step progress visualizer
- A2UI invoice result card (workspace surface)
- MCP sandbox vendor globe + AP analytics dashboard
- GCS bucket browser with demo invoices + user bucket support
