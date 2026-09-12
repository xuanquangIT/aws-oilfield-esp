# Local validation

Revision: M3 local implementation, checked 2026-09-12 on Windows with Python 3.12.14, Node.js 24.11.1, aws-cdk-lib 2.267.0 and local CDK CLI 2.1140.0.

## Observed results

| Check | Result | Scope |
|---|---|---|
| Python tests | 37 passed | Contract, simulator, M2 stream/alert behavior, M3 manifest/dedup/conflict accounting and infrastructure assertions |
| Stack synthesis | Passed for core and realtime | Actual references, no dependency cycle, compatible installed CLI |
| Infrastructure assertions | Passed | Core has no stream/import of realtime; realtime has one shard/two mappings; retry/failure destination and selected cost/security settings |
| PowerShell syntax | Passed | All scripts parsed |
| Native failure wrapper | Passed | A local Python process returning exit 7 causes a terminating error |
| Realtime cleanup behavior | Four mocked paths passed | Success, deploy error, producer error, cleanup error; cloud calls replaced |
| Reset guard | Passed | No data deletion without explicit -DeleteData |
| Batch sequencing | Three mocked paths passed | Manifest creation, success, workflow failure and crawler failure; stale previous crawler success is not accepted |
| M3 manifest and identity | Four pure-Python checks passed | Stable manifest hash, identical redelivery dedupe, conflicting event ID rejection and invalid-row accounting; no Spark/AWS runtime |
| Documentation | 21 Markdown files / 57 local links checked | File existence and unresolved citation markers; not external-link availability or factual completeness |
| Package installation | Completed | Python venv and pinned local CDK; npm reported zero vulnerabilities for its two-package tree |

The aggregate command is scripts/validate.ps1. The final batch change was verified by the targeted PowerShell checks after the aggregate run. Synthesis used disabled context lookups/CLI telemetry. The CLI notes that optional feature flags remain unconfigured; cross-stack reference strength is explicitly strong.

## Findings recovered during validation

- Existing Athena resource/output construct ID collision prevented synthesis; fixed while retaining the output key.
- Guessed Lambda names replaced with actual references and realtime-owned IAM.
- Checked local CLI options and removed an unsupported synth --all option.
- Crawler polling distinguishes the newly started crawl from an old successful crawl.

## Not validated

M1/M2 have separate documented AWS smoke evidence in the runbook, but this local report does not re-prove it. M3 has not been deployed or run in AWS: Glue Spark execution, manifest read/write permissions, crawler/catalog discovery, publication pointer, Athena SQL/partition bytes, mixed-source reconciliation, rerun/backfill, and actual billing remain unverified.

CI configuration is present but has not run on GitHub. Batch/stream handlers still have the limitations listed in PROJECT-STATUS.md. No M3 cloud integration or customer-ready release claim follows from these offline results.
