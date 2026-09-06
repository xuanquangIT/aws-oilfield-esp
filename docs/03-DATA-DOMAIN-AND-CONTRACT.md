# Data domain and contract

This document defines what the synthetic ESP data means, where representative real-world signals could originate, and the canonical telemetry contract that the implementation must enforce.

## Domain model and assumptions

ESP = electric submersible pump. This project models three synthetic pumps, not a physical digital twin.

### Reference equipment profile and scope

The telemetry is a **normalized synthetic event**, not a Phoenix xt150 record
format and not a vendor-certified emulator. It combines placeholder signals
that, in a real installation, would arrive from several sources. The downhole
reference is an [SLB Phoenix xt150 Type 1
monitoring system](https://www.slb.com/zh-cn/products-and-services/innovating-in-oil-and-gas/completions/artificial-lift/intelligent-lift/gauges/phoenix-xt150-downhole-monitoring-system)
installed with a [REDA Maximus ESP induction motor](https://www.slb.com/-/media/files/al/product-sheet/reda-maximus-bolt-on-motors-ps.ashx).
The cited motor documentation describes a two-pole, three-phase squirrel-cage
induction motor with direct winding-temperature measurement and a gauge-ready
base compatible with Phoenix monitoring systems.

The Phoenix xt150 PDF lists only intake pressure, intake temperature, motor
winding or oil temperature, vibration, current leakage, and pump-discharge
pressure for Type 1. Therefore it is the reference only for the first four
field groups below and optional `discharge_pressure`. `current_leakage` is a
real Phoenix measurement but is **not currently emitted** by this simulator.
It must not be confused with `motor_current`.

| Event field(s) | Reference source or location | Scope in this simulator |
|---|---|---|
| `intake_pressure`, `intake_temperature` | Downhole intake gauge | Direct-style synthetic observations; no calibration, depth, or hydrostatic model. |
| `discharge_pressure` | Optional downhole discharge gauge | Direct-style synthetic observation; it is present for every event although real installations may omit it. |
| `motor_temperature`, `vibration` | Downhole motor/gauge instrumentation | Direct-style synthetic observations; no sensor accuracy, drift, or failure model. |
| `current_leakage` | Phoenix downhole gauge | Out of scope: documented reference measurement, but absent from the current event schema. |
| `motor_current`, `pump_frequency` | Surface VSD/SCADA | Synthetic electrical feedback/control values, not Phoenix readings; no VSD, cable-loss, phase-imbalance, or motor-curve model. |
| `tubing_pressure`, `casing_pressure` | Usually surface wellhead/annulus instrumentation; completion-specific | Synthetic contextual pressures, not Phoenix gauge claims. |
| `flow_rate`, `water_cut` | Production meter, well test, or virtual-rate calculation | Synthetic production values. They are not claimed to be direct Phoenix measurements; real systems may use a multiphase meter or a calibrated model. |
| `status` | VSD/SCADA operating state | Only `RUNNING` or `SHUTDOWN` in the current generator; it is not a safety-system state model. |
| `scenario` | Simulator metadata | Test label only. It is not a field instrument measurement and must not drive production-style detection rules. |

For real flow-rate and water-cut measurement context, see the [SLB FloWatcher
monitoring system](https://www.slb.com/products-and-services/innovating-in-oil-and-gas/completions/well-completions/permanent-monitoring/permanent-downhole-gauges/flowatcher-monitoring-system),
which describes a specialized system that derives total flow and gas or water
cut from dedicated measurements. This project does not implement that model.

#### Representative source references for the other fields

These are real equipment or workflow examples that explain where the normalized
fields could originate. They are references only: this repository does not
connect to any of them, implement their register maps, or reproduce their
accuracy, sampling rate, alarms, or calibration requirements.

| Normalized field(s) | Real-world reference | Correct demo interpretation |
|---|---|---|
| `motor_current`, `pump_frequency` | A [PowerFlex VFD manual](https://literature.rockwellautomation.com/idc/groups/literature/documents/um/22d-um001_-en-e.pdf) documents output frequency, commanded frequency, and output current as drive monitor values. An [SLB ESP VSD overview](https://www.slb.com/-/media/files/oilfield-review/p30-43-2) explains that VSD frequency controls induction-motor speed. | Surface VSD/SCADA telemetry, not Phoenix gauge data. `pump_frequency` is a command or drive-output value; `motor_current` is a synthetic output-current feedback value. |
| `tubing_pressure`, `casing_pressure` | An [Emerson oil-production case study](https://www.emerson.com/en/measurement-instrumentation/industries/oil-and-gas/oil-production-company-increases-operational-efficiency-by-reducing-time-spent-at-wellsite) lists tubing and casing (annulus) applications for Rosemount 3051S pressure transmitters. | Two independent surface/wellhead pressure channels, not downhole Phoenix measurements. The simulator does not declare a tap location, transmitter range, or signal protocol. |
| `flow_rate`, `water_cut` measured | The [SLB Vx Spectra surface multiphase flowmeter](https://www.slb.com/es/products-and-services/innovating-in-oil-and-gas/reservoir-characterization/reservoir-testing/surface-testing/surface-multiphase-flowmetering/vx-spectra-surface-multiphase-flowmeter) measures multiphase flow for production monitoring and distinguishes oil/water fractions. | Surface production-meter output. `water_cut` is derived from phase fractions; it is not a Phoenix field. |
| `flow_rate`, `water_cut` estimated | An [SLB ESP-gauge virtual-rate workflow](https://www.slb.com/resource-library/technical-paper/al/spe-145542) describes calculating real-time liquid-rate and water-cut trends from downhole gauge data plus a model. | Calculated/estimated production values, not direct measurements. The current simulator does not implement the calibration model. |
| `status`, production event context | [AVEVA Plant SCADA](https://www.aveva.com/content/dam/aveva/documents/onesheet/OneSheet_AVEVA_PlantSCADA-2003R2What%27sNew_24-01.pdf) documents state values that can be represented as alarms or events. | `RUNNING`/`SHUTDOWN` may come from VSD/SCADA state, not a sensor. The simulator has no PLC safety logic or alarm acknowledgement model. |
| `scenario` | No physical sensor equivalent. | Simulator-only injected ground truth, used to test detection. A production system should instead retain separate SCADA `alarm_code`/`operating_mode` and maintenance-event records. |

For a credible customer demonstration, describe the payload as **one normalized
synthetic ESP observation built from representative source lanes**. Do not say
that one device produces every field. A future production-style contract should
add `source_system`, `measurement_kind` (`MEASURED`, `CALCULATED`, `COMMAND`,
or `SIMULATED`), `point_id`, `quality_code`, and a declared unit. Those fields
are not implemented in the current event schema.

#### Explicit business boundary

This capstone demonstrates a synthetic condition-monitoring data pipeline:
produce normalized telemetry, archive it, maintain latest state, detect simple
patterns, and publish alerts. It does **not** model raw Phoenix telemetry,
pump sizing, pump curves, reservoir inflow, multiphase-flow physics, VSD
control algorithms, Modbus/SCADA protocol details, alarm-trip logic, sensor
calibration, or field operating limits. It must not be used to select a pump,
change VSD frequency, or issue a shutdown instruction.

### Units for the capstone

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

### Scenario limitations

Low flow and blockage change multiple signals by explicit script assignments. Mechanical degradation is tick-driven. Gas slug creates a sine wave, while its current alert checks the scenario label. Sensor fault holds temperature constant without measuring stuck-sensor duration. Shutdown is always classified critical even when it could be a planned operational state.

M2 should separate process anomaly, sensor quality and planned shutdown. Record thresholds per pump in reference data, version rules, and avoid scenario-label access in measured detection.

### Data products

Target silver grain: one canonical event per event_id. Target pump dimension: one active metadata record per pump, with future effective dates for changing baselines. Target gold grain: one pump per UTC day per published run.

Customer-facing metrics must distinguish observed sample coverage, valid-event freshness, mean rate and event-derived warning duration. All thresholds and baselines remain synthetic.

## Telemetry contract

### Current wire formats

Realtime JSON contains timestamp, esp_id, scenario, status and the signals defined in the domain model above. Historical CSV contains timestamp, esp_id, flow_rate, water_cut, intake_pressure, discharge_pressure, motor_temperature, motor_current, vibration and status.

Current code does not enforce the target contract below. There is no event_id/schema_version; historical data lacks several realtime fields. Missing values must not be silently interpreted as physical zero.

### Target telemetry v1: M1

| Field | Type / rule |
|---|---|
| schema_version | Integer 1; unknown incompatible versions quarantined |
| event_id | Producer-generated UUID/string; stable across retries/replays |
| timestamp | ISO-8601 UTC with Z; observation/event time |
| ingested_at | Platform-assigned UTC time, separate from event time |
| esp_id | Registered synthetic pump identifier |
| source | historical or realtime |
| run_id | Producer run identity; separate batch/replay execution identities |
| status | RUNNING, SHUTDOWN, UNKNOWN |
| flow_rate, water_cut | Finite numbers; flow >=0; fraction within 0..1 |
| motor_temperature, motor_current, vibration | Finite numbers with declared units; current/vibration >=0 |
| pressure/frequency/other temperature fields | Optional where historical source omits them; preserve null |
| scenario | Optional test label, excluded from production-style rule inputs |

Event identity is not the Kinesis sequence number, which changes when republishing. Historical adapters derive a stable ID from immutable source checksum and row number. Equal event IDs with differing payloads are conflicts, not arbitrary last-writer-wins.

### Validation and evolution

1. Parse JSON/CSV and reject malformed encoding or invalid shape.
2. Validate version, required identity, UTC timestamp and finite numeric values.
3. Validate pump ID and physical/type constraints. Treat unusual but possible operating values as quality flags rather than automatically deleting them.
4. Keep valid late events in raw/silver, but do not allow them to regress latest state.
5. Preserve rejected payload/source reference with rule ID and reason.
6. Add optional fields compatibly; renaming, unit changes and type changes require a new version/adapter.

Future timestamp skew tolerance is a configured rule (proposed five minutes), not yet implemented. A fixed timestamp alone is not a duplicate; event identity decides. Sample intervals and source granularity must be retained for KPI interpretation.

### Storage and lineage target

- raw: immutable input plus source checksum, run manifest and arrival metadata.
- quarantine: rejected content, rule, source pointer, schema version, review outcome.
- silver: canonical typed event, event_id and provenance.
- gold: per-pump/day aggregations with sample coverage and source run.
- publication manifest: selected successful run, input/output counts and quality result.

Proposed conservation rule for a bounded fixture: received = accepted unique + duplicate identical + rejected/conflicting. Track transport failures separately; only acknowledged sends belong to delivered-input reconciliation.

Raw and failure retention currently differ (7/14 days); the target replay window cannot exceed available sources. Export a fixture or extend retention deliberately before promising older recovery.
