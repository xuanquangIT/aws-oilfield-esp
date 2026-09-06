# Acceptance and evidence

## Evidence levels

- Offline: unit tests, source checks and synthesized CloudFormation.
- AWS smoke: specific service deployment and a bounded observed operation.
- Integrated: producer -> storage/state -> batch -> published KPI with reconciled IDs/counts.
- Rehearsed: integrated run plus fault recovery, cleanup, rebuild and observed costs.

Never promote a lower level by renaming a report. Record not_run/unknown for missing checks, not pass.

## Release checklist

| Gate | Required result |
|---|---|
| G0 Foundation | Local tests + synth; core independent of realtime; checked script exits |
| G1 Contract | Valid/invalid/evolution fixtures have exact expected results |
| G2 Realtime | Duplicate/out-of-order/retry tests; no backward latest state; alert dedupe semantics documented |
| G3 Batch | Unified data, zero unexplained count gap, deterministic rerun, unaffected backfill dates unchanged |
| G4 Security | Positive and negative permissions tested with intended principals |
| G5 Recovery | Failure payload replay and failed publication preserve prior result |
| G6 Lifecycle | Normal cleanup plus laptop-loss expiry; no running stream/jobs after deadline |
| G7 Rebuild | Export/reset/recreate/restore or regenerate succeeds twice with lockfiles |
| G8 Customer | KPI report, observed p95 freshness and scan bytes, redacted recording |
| G9 Cost | Usage worksheet plus later bill, residual resource inventory, assumptions stated |
| G10 Dashboard | Localhost-only web dashboard, no browser credentials, allow-listed API, cache/stale-state behavior and measured 60-minute rehearsal; hosted profile optional |

Target latency is <=15 seconds p95 at approximately three records/second. Measure end-to-end by polling the latest-state view and joining producer timestamps; Lambda duration alone is not end-to-end freshness. Set clock synchronization and polling interval in evidence.

## Failure fixtures

Include malformed JSON, missing ID, invalid numeric value, incompatible schema, repeated event, older event, transient throttle, denied storage, failed batch and process interruption. Each fixture needs expected accepted/rejected counts, recovery action and teardown.

A clean run should prove acknowledged producer IDs reconcile after drain. On failed runs, explicitly distinguish producer-unacknowledged events, validation rejects, duplicates, archive success, latest-state exclusion for old events and failed delivery destinations.

## Run artifacts

Start from [cloud run template](../evidence/templates/cloud-run.json). Save under evidence/runs/<run-id>/ (ignored by Git). Include source hashes/commit when available, dependency locks, account/region privately, start/end, stack events, input manifest, Lambda metrics, Glue/crawler execution IDs, SQL results and scanned bytes, cleanup read-backs and cost status.

Only publish a redacted copy. Do not fabricate a run ID, cost, screenshot or service success to complete the template.

Current evidence: [local validation](../evidence/LOCAL-VALIDATION.md). Cloud acceptance remains not_run until actual AWS operations are completed.
