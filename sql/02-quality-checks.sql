-- Run after the baseline 504-row seed job, using the project workgroup.
SELECT COUNT(*) AS rows_seen,
       COUNT(DISTINCT esp_id) AS pumps,
       SUM(CASE WHEN event_ts IS NULL THEN 1 ELSE 0 END) AS invalid_timestamps,
       SUM(CASE WHEN water_cut IS NULL OR water_cut < 0 OR water_cut > 1 THEN 1 ELSE 0 END) AS invalid_water_cut,
       SUM(CASE WHEN flow_rate IS NULL OR flow_rate < 0 THEN 1 ELSE 0 END) AS invalid_flow,
       SUM(CASE WHEN oil_rate IS NULL OR ABS(oil_rate - flow_rate * (1 - water_cut)) > 0.000001 THEN 1 ELSE 0 END) AS oil_formula_errors
FROM telemetry;
-- Expected fresh baseline: 504 rows, 3 pumps, all error counts zero.
-- This is an analytical check, not an ingestion quarantine mechanism.
