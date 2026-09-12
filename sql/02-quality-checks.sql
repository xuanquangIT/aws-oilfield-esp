-- M3 silver quality inspection. The authoritative input-accounting values are
-- in staging/m3/<run-id>/quality-report.json; this query checks published
-- canonical rows for the run selected by current.json.
SELECT COUNT(*) AS rows_seen,
       COUNT(DISTINCT event_id) AS distinct_event_ids,
       COUNT(DISTINCT esp_id) AS pumps,
       SUM(CASE WHEN event_ts IS NULL THEN 1 ELSE 0 END) AS invalid_timestamps,
       SUM(CASE WHEN water_cut IS NULL OR water_cut < 0 OR water_cut > 1 THEN 1 ELSE 0 END) AS invalid_water_cut,
       SUM(CASE WHEN flow_rate IS NULL OR flow_rate < 0 THEN 1 ELSE 0 END) AS invalid_flow,
       SUM(CASE WHEN metadata_version IS NULL THEN 1 ELSE 0 END) AS missing_metadata,
       COUNT(DISTINCT source_kind) AS source_kinds
FROM silver
WHERE publication_run_id = '<published_run_id>';
