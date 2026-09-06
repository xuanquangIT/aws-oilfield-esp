-- Select the project Glue database and enforced Athena workgroup first.
-- Verify the crawler table name is telemetry.
SELECT esp_id, event_date, COUNT(*) AS samples,
       AVG(flow_rate) AS avg_liquid_rate_m3_day,
       AVG(oil_rate) AS avg_oil_rate_m3_day,
       AVG(motor_temperature) AS avg_motor_temperature_c,
       MAX(vibration) AS peak_vibration_mm_s
FROM telemetry
GROUP BY esp_id, event_date
ORDER BY event_date, esp_id;
-- For scan comparisons add WHERE event_date = DATE 'YYYY-MM-DD'
-- using a date actually present in the input. Average rate is not daily volume.
