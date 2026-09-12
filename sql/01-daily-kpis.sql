-- M3 silver query. Read curated/publication/current.json first and replace
-- <published_run_id>; never query an unapproved staging run. The crawler
-- normally calls this table silver, but inspect Glue Catalog after a run.
SELECT esp_id,
       event_date,
       COUNT(*) AS samples,
       AVG(flow_rate) AS avg_liquid_rate_m3_day,
       AVG(flow_rate * (1 - water_cut)) AS avg_oil_rate_m3_day,
       AVG(motor_temperature) AS avg_motor_temperature_c,
       MAX(vibration) AS peak_vibration_mm_s
FROM silver
WHERE publication_run_id = '<published_run_id>'
  AND event_date BETWEEN DATE 'YYYY-MM-DD' AND DATE 'YYYY-MM-DD'
GROUP BY esp_id, event_date
ORDER BY event_date, esp_id;

-- Run this separately with and without the event_date predicate and save
-- Athena Statistics.DataScannedInBytes for the M3 partition-pruning gate.
