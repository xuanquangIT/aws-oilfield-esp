# Batch analytics

## Existing runnable path

The seed generator creates seven days × 24 hourly samples × three pumps = **504 rows**. It uses current UTC time and random flow values, so repeated generation does not yield the same checksum.

```powershell
.\.venv\Scripts\python.exe scripts/seed-batch-data.py
.\scripts\upload-batch.ps1
.\scripts\run-batch.ps1
```

Current input is raw/batch/historical.csv. Glue casts the fixed CSV schema, parses event timestamps, derives UTC-date intent and oil_rate = flow_rate × (1 - water_cut), and overwrites curated/telemetry partitioned by event_date. The current Spark timezone is not explicitly configured; M3 must set it to UTC.

The wrapper waits for the state machine and then the crawler. A wrapper timeout does not cancel AWS jobs. Inspect remote execution before retrying. Concurrent batch sessions are unsupported.

## Query

List catalog tables and obtain the configured workgroup:

```powershell
. ./scripts/common.ps1
$db = Get-CoreOutput 'GlueDatabaseName'
$wg = Get-CoreOutput 'AthenaWorkGroup'
Invoke-Checked aws @('glue','get-tables','--database-name',$db,'--query','TableList[].Name','--output','table')
```

In Athena select that workgroup and database. The expected crawler table is telemetry; verify it before using [daily SQL](../sql/01-daily-kpis.sql) or [quality SQL](../sql/02-quality-checks.sql). Replace the table name if necessary. A query failing the 10 MiB workgroup limit is a guardrail event, not a reason to switch to an unrestricted workgroup.

Expected fresh-input checks: 504 rows, 3 pumps, no null parsed event times, water_cut within 0..1, oil_rate = 0.65 × flow_rate within numerical tolerance. Since generation spans a rolling seven-day interval, it can touch eight UTC calendar dates; do not assert exactly seven date partitions.

## Analytical interpretation

Average oil_rate is a rate, not daily oil volume. Production volume requires time-weighted integration and a sampling-gap policy. Current hourly synthetic samples support descriptive comparisons only.

## M3 target

- Read historical CSV and validated realtime JSON under the same versioned contract.
- Join a small pump dimension: field, rated capacity, installation date, operating limits and baseline liquid rate.
- Separate valid and quarantined rows; record input = accepted + rejected + duplicate counts.
- Keep source URI, event_id, ingestion time, schema version and batch run ID for lineage.
- Deduplicate by event_id, enforce deterministic conflict handling, set Spark timezone UTC.
- Write run-scoped silver/gold output, quality check it, then publish a catalog pointer.
- Reprocess selected affected dates for late data/backfill; never overwrite unrelated successful partitions.
- Produce daily pump KPIs: sample coverage, average flow/oil rate, warning duration with gap cap, missing-data minutes, relative flow deficit.
- Compare unpartitioned CSV scans with partition-filtered Parquet using measured Athena bytes scanned.

For this small dataset, begin with explicit catalog tables and partition registration in the workflow. Keep crawler execution as a separate learning exercise. Iceberg MERGE/time travel belongs in an optional M6 lab until update/concurrency requirements justify its maintenance.
