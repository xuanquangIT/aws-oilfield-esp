# Customer demo and portfolio

## Positioning

**Cost-Aware Offshore ESP Data Platform**

A synthetic equipment surveillance case connecting live telemetry with historical analytical quality, designed to be reconstructed on demand and parked with a small storage footprint.

Until the integrated release gates pass, describe this as a prototype with a reviewed delivery plan. After M5 passes, support each stronger claim with a run record.

## Business narrative

An operations analyst needs to find abnormal pumps quickly, then determine whether the change persists over time. A data engineer must make that view trustworthy despite duplicated messages, missing readings, delayed uploads and reruns.

Three deliverables make the story tangible:

1. An operational view showing each pump's latest valid observation and data age.
2. A daily analytical view showing flow/oil-rate trends, coverage and quality.
3. A recovery and cost receipt showing replay correctness and teardown.

These are Phase 1 deliverables; the current code offers DynamoDB/SNS inspection and basic Athena output, while dashboard code remains unimplemented. Phase 1 is not complete until the local-first web dashboard shows latest state and published KPI summaries and passes its acceptance gate. The optional CloudFront-hosted profile is not required for Phase 1 completion. See the [dashboard design](17-REALTIME-WEB-DASHBOARD.md).

## 12-minute rehearsal

Deploy and warm up before the meeting; show recorded deployment timing instead of waiting for CloudFormation live.

| Time | Demonstration | Evidence |
|---|---|---|
| 0-2 min | Business problem, architecture and operating modes | Diagram + current run ID |
| 2-5 min | Normal to low-flow contrast, latest-state freshness | Dashboard card + API response + alert + raw event |
| 5-8 min | Same events in batch history and daily KPIs | Dashboard KPI panel + reconciliation counts + SQL result |
| 8-10 min | Duplicate, invalid and late event; controlled replay | DQ/recovery output with expected counts |
| 10-12 min | Park runtime; explain residual storage and bill | Stream absence + cost worksheet |

M2/M3 recovery and reconciliation must exist before performing the full storyboard. For the current foundation, show only low_flow -> state/SNS/raw, then separate historical batch SQL and explain the remaining integration.

## Acceptance targets, not achieved claims

At three events/second, target p95 producer timestamp to latest-state observation <=15 seconds, zero unexplained accepted-event loss after drain, no backward state movement, and identical gold results on rerun. Measure producer clock quality and include invalid/duplicate accounting.

Use flow deficit relative to a synthetic baseline as an analytical signal. Do not translate it into avoided downtime, revenue savings or real production loss without validated operating context.

## Customer package

Deliver architecture/ADRs, the local web dashboard, short recording, redacted run record, SQL output, recovery evidence, cost assumptions versus measured bill, and a rebuild guide. Publish sanitized screenshots or a recording for an always-available portfolio; keep the local dashboard and live AWS runtime off when unnecessary. Deploy the hosted dashboard profile only when an external customer URL is explicitly needed.

Do not claim production offshore control, predictive-maintenance ML, field-proven alarm accuracy, real customer telemetry or a guaranteed zero bill. Include the source data's synthetic provenance.
