# Domain model and assumptions

ESP = electric submersible pump. This project models three synthetic pumps, not a physical digital twin.

## Units for the capstone

These units are adopted as the documentation contract for existing synthetic numbers; they were previously unspecified and are not calibrated sensor measurements.

| Field | Unit / meaning |
|---|---|
| flow_rate, oil_rate | Cubic metres/day, instantaneous synthetic rate |
| water_cut | Fraction of liquid volume, 0..1 |
| intake_pressure, discharge_pressure, tubing_pressure, casing_pressure | psi |
| intake_temperature, motor_temperature | Degrees Celsius |
| vibration | mm/s, illustrative amplitude without a specified sensor standard |
| motor_current | A |
| pump_frequency | Hz |
| timestamp | UTC observation time |
| status | RUNNING or SHUTDOWN in the current simulator |

Oil rate = liquid flow × (1 - water cut). An average rate is not an integrated volume. For future time-weighted volume, integrate rate × elapsed seconds / 86400, cap gaps and report excluded duration. Do not assume missing readings mean zero production.

## Scenario limitations

Low flow and blockage change multiple signals by explicit script assignments. Mechanical degradation is tick-driven. Gas slug creates a sine wave, while its current alert checks the scenario label. Sensor fault holds temperature constant without measuring stuck-sensor duration. Shutdown is always classified critical even when it could be a planned operational state.

M2 should separate process anomaly, sensor quality and planned shutdown. Record thresholds per pump in reference data, version rules, and avoid scenario-label access in measured detection.

## Data products

Target silver grain: one canonical event per event_id. Target pump dimension: one active metadata record per pump, with future effective dates for changing baselines. Target gold grain: one pump per UTC day per published run.

Customer-facing metrics must distinguish observed sample coverage, valid-event freshness, mean rate and event-derived warning duration. All thresholds and baselines remain synthetic.
