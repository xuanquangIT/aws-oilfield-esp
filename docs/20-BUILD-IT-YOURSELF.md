# Build it yourself: learning path

This guide turns the repository from a deployable reference into a learning project. The lifecycle scripts are the last step of each module, not the first. Build or explain one layer, prove it locally, then deploy only that layer in the sandbox.

The goal is not to memorize AWS service names. For each module, be able to explain five things: **input, output, failure behavior, cost driver, and evidence**.

## How to use the reference implementation

Keep this repository intact as the answer key. Work in a copied learning directory or make small, reversible changes one module at a time. Before opening the reference file, write a short design answer in your own words. After implementing, compare your version with the reference and explain every difference.

Do not begin by running all deployment scripts. A successful deploy proves that a template can create resources; it does not prove that you understand the data path, reliability boundaries or trade-offs.

## Module 0: Trace the product before building

Read [architecture](02-ARCHITECTURE.md), then draw the two paths without looking at the diagram:

```text
Historical CSV -> S3 raw/batch -> Glue Spark -> S3 curated Parquet -> Catalog -> Athena
ESP simulator -> Kinesis -> Lambda ingest -> S3 raw/realtime + DynamoDB latest state
ESP simulator -> Kinesis -> Lambda anomaly -> SNS alerts
```

Then inspect [app.py](../app.py), [core stack](../infrastructure/core_stack.py) and [realtime stack](../infrastructure/realtime_stack.py).

**Explain:** Why does the core stack not create Kinesis? Why does realtime reference core rather than the reverse? What stays after a demo ends?

**Pass condition:** You can identify which resources are persistent, which are disposable and why that controls idle cost.

## Module 1: Learn the data contract and producer

Study [data contract](12-DATA-CONTRACT.md) and implement or rewrite the `signal()` function in [simulator/esp_simulator.py](../simulator/esp_simulator.py). Start with `normal`, then add `low_flow` and `shutdown`.

**Build:** A JSON event must contain event time, ESP ID, scenario, operating status and telemetry measurements. Generate three records per tick for ESP-101, ESP-102 and ESP-103.

**Break:** Remove `esp_id`, send an invalid timestamp, or make an event duplicate. Describe what the current implementation does and what M1 must add.

**Prove:** Run `pytest tests/test_simulator.py -q`. Explain why a passing local test does not prove Kinesis delivery.

## Module 2: Build the realtime consumers locally first

Read [stream processor](../src/stream_processor/handler.py) and [anomaly detector](../src/anomaly_detector/handler.py).

**Build:** Decode a Kinesis record, archive it to `raw/realtime/`, and update one DynamoDB latest-state item for each ESP. Separately, classify a normal, warning and critical event and publish only non-normal findings.

**Explain:** The ingest consumer and anomaly consumer independently read the same Kinesis stream. Neither Lambda calls the other. DynamoDB is a current-state view, not the complete history.

**Break:** Consider an S3 failure, duplicated Kinesis delivery and an event that arrives late. State what gets retried, where a failed batch is sent, and which correctness gaps are still open.

**Cost lesson:** The current ingest handler writes one S3 object per event. At 24x7 this is the main cost driver. Design one JSON Lines object per Lambda batch before changing the code.

## Module 3: Build the persistent core as infrastructure

Read [core stack](../infrastructure/core_stack.py) from top to bottom. Recreate these resources in this order:

1. Private S3 bucket with TLS enforcement, SSE-S3 and lifecycle rules.
2. On-demand DynamoDB table keyed by `esp_id`.
3. SNS alert topic.
4. Two 256 MB Lambda functions and seven-day log retention.
5. Glue role, database, Glue Spark job and crawler.
6. Athena workgroup with an enforced 10 MiB scan cutoff.
7. Step Functions state machine that starts the Glue job.
8. Disabled EventBridge daily rule and the monthly budget.

**Prove locally:** Run `cdk synth` and inspect the generated template. The core must contain no Kinesis stream, NAT Gateway or scheduled active ETL.

**Pass condition:** Explain why every retention period, timeout, concurrency value and scan limit exists.

## Module 4: Add the disposable realtime stack

Read [realtime stack](../infrastructure/realtime_stack.py).

**Build:** Create one provisioned Kinesis shard with 24-hour retention. Add two event-source mappings, each with batch size 10, a two-second batching window, bounded retry/record-age values and an S3 on-failure destination.

**Critical design exercise:** Keep Kinesis permissions and event-source mappings in the realtime stack. The core must never reference a disposable stream; otherwise deleting realtime would create a circular dependency or break core deployment.

**Prove locally:** Run `pytest tests/test_infrastructure.py -q` and explain the assertions that enforce the core/realtime boundary.

## Module 5: Build batch analytics

Read [batch transformation](../src/batch/transform.py), [batch runbook](05-BATCH-ANALYTICS.md), and the two SQL files under `sql/`.

**Build:** Transform raw historical CSV into partitioned Parquet under `curated/telemetry/`. Then create the catalog metadata and run a KPI query in Athena.

**Explain:** Parquet and partition filtering reduce Athena scan cost. The current batch lane does not yet reconcile realtime data with historical data; do not claim that it does.

**Prove in AWS:** Seed, upload and run the batch workflow. Record Glue runtime, crawler runtime, row counts and Athena bytes scanned.

## Module 6: Orchestration, operating states and cost

Read [cost control](03-COST-CONTROL.md), [monthly cost estimate](18-MONTHLY-COST-ESTIMATE.md), [operations](07-OPERATIONS.md), and [operating time estimate](19-OPERATING-TIME-ESTIMATE.md).

**Build:** Deploy core once, use the realtime stack only during a short demo, then delete it. Keep a separate written definition for these states:

| State | Meaning | Proof |
|---|---|---|
| Local | No AWS resources invoked | Local tests and synth only |
| Parked | Core retained; realtime absent | No stream or mappings; residual storage recorded |
| Demo | Realtime deployed for a bounded scenario | Fresh latest state, raw object and controlled alert evidence |
| Reset | Both stacks and project data deleted | Explicit `-DeleteData`, then residual-resource inspection |

**Cost lesson:** A budget notifies after spend; it does not terminate a stream. The current script's `finally` cleanup is helpful but cannot survive a lost laptop or expired credentials. Cloud-owned expiry is planned M4 work.

## Module 7: Customer product and dashboard

Read [dashboard design](17-REALTIME-WEB-DASHBOARD.md), [portfolio story](09-PORTFOLIO.md), and [acceptance evidence](14-ACCEPTANCE-EVIDENCE.md).

The required local-first dashboard is not implemented yet. Build it only after the data-contract and reconciliation work are solid. It should read the three allow-listed DynamoDB items through a localhost API, cache for 10–15 seconds, fetch approved KPI JSON from S3 by version, and never query Athena per browser refresh.

**Pass condition:** The UI distinguishes `fresh`, `stale` and `unavailable`, exposes no credentials or raw records, and a customer rehearsal records its request count, freshness and cleanup.

## Recommended learning cadence

| Session | Focus | End with |
|---|---|---|
| 1 | Modules 0–1 | Drawn dataflow and passing simulator tests |
| 2 | Module 2 | Your explanation of replay, duplicate and failure behavior |
| 3 | Modules 3–4 | Synthesized stacks and infrastructure tests |
| 4 | Module 5 | First batch run record and Athena scan evidence |
| 5 | Module 6 | One bounded realtime rehearsal, park verification and cost record |
| 6+ | Module 7 and M1–M5 | Complete product gates, dashboard and customer rehearsal |

## Final self-check

Do not call the project understood until you can answer these without reading the code:

1. What happens to one ESP event from producer through archive, latest state and alert?
2. Why are Kinesis and its mappings disposable while S3 and DynamoDB are core?
3. What creates most cost at 24x7 load, and what implementation change reduces it?
4. What evidence distinguishes an AWS deployment success from an end-to-end data correctness claim?
5. What data is lost when realtime is parked or the whole project is reset?
6. What remains incomplete before presenting this as a finished customer data product?

Use [DEA-C01 mapping](06-DEA-C01-MAPPING.md) after each module to connect the implementation decision to exam domains. The mapping organizes learning; it is not a claim of exam readiness.
