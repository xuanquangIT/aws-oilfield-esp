# Local validation

Revision: 0.2.0, checked 2026-09-05 on Windows with Python 3.12.14, Node.js 24.11.1, aws-cdk-lib 2.267.0 and local CDK CLI 2.1140.0.

## Observed results

| Check | Result | Scope |
|---|---|---|
| Python tests | 5 passed | Three simulator behaviors plus two infrastructure/budget tests |
| Stack synthesis | Passed for core and realtime | Actual references, no dependency cycle, compatible installed CLI |
| Infrastructure assertions | Passed | Core has no stream/import of realtime; realtime has one shard/two mappings; retry/failure destination and selected cost/security settings |
| PowerShell syntax | Passed | All scripts parsed |
| Native failure wrapper | Passed | A local Python process returning exit 7 causes a terminating error |
| Realtime cleanup behavior | Four mocked paths passed | Success, deploy error, producer error, cleanup error; cloud calls replaced |
| Reset guard | Passed | No data deletion without explicit -DeleteData |
| Batch sequencing | Three mocked paths passed | Success, workflow failure, crawler failure; stale previous crawler success is not accepted |
| Documentation | 28 Markdown files / 54 local links checked | File existence and unresolved citation markers; not external-link availability or factual completeness |
| Package installation | Completed | Python venv and pinned local CDK; npm reported zero vulnerabilities for its two-package tree |

The aggregate command is scripts/validate.ps1. The final batch change was verified by the targeted PowerShell checks after the aggregate run. Synthesis used disabled context lookups/CLI telemetry. The CLI notes that optional feature flags remain unconfigured; cross-stack reference strength is explicitly strong.

## Findings recovered during validation

- Existing Athena resource/output construct ID collision prevented synthesis; fixed while retaining the output key.
- Guessed Lambda names replaced with actual references and realtime-owned IAM.
- Checked local CLI options and removed an unsupported synth --all option.
- Crawler polling distinguishes the newly started crawl from an old successful crawl.

## Not validated

AWS create/update/delete/recreate, effective IAM permissions, event source readiness, Glue Spark execution, Athena SQL execution, SNS email delivery, failure-destination delivery, measured latency, complete stream drain and actual billing have not been run.

CI configuration is present but has not run on GitHub; this directory was not a Git repository. Batch/stream handlers still have the limitations listed in PROJECT-STATUS.md. No cloud integration or customer-ready release claim follows from these offline results.
