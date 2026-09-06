# Realtime demonstration

Prerequisites: deploy core, select the same AWS profile/region for CLI and Boto3, optionally confirm the SNS email subscription. Keep another console window open for DynamoDB and CloudWatch.

```powershell
.\scripts\realtime-start.ps1 -DurationMinutes 5 -Scenario low_flow
```

The wrapper creates the stream and both mappings, runs three synthetic pumps, allows a 30-second grace period, then destroys realtime. Core history, state, alerts topic and application logs remain.

| Scenario | What the current generator does | Expected current rule behavior |
|---|---|---|
| normal | Stable noisy signals | No anomaly publish |
| low_flow | Flow below 60, motor temperature above 120 | Warning |
| mechanical | Vibration and current grow with tick | Warning only after thresholds are crossed; use five minutes |
| blockage | High tubing pressure plus low flow/heat | Multiple rule reasons, critical |
| gas_slug | Oscillating pressure/flow | Label-based alert; not measured temporal detection |
| sensor_fault | Temperature fixed at 91 | No stuck-sensor detector exists yet |
| shutdown | Zero flow/current/frequency, SHUTDOWN status | Critical by current rule; planned shutdown context absent |

Thresholds use synthetic units described in [domain notes](10-DOMAIN-NOTES.md). The scenario label currently leaks into the gas-slug rule. Customer evidence must identify this as a scripted demonstration.

## Observe

1. Confirm both event source mappings are enabled before interpreting missing output.
2. Inspect latest-state items for ESP-101/102/103 and compare their timestamp to current run.
3. Inspect raw/realtime objects and application logs.
4. For low_flow, inspect a confirmed SNS notification; unconfirmed email is not a delivery test.
5. Inspect aws/lambda failure payloads if errors occurred.
6. Verify the stream and mappings are gone after the command ends.

Raw objects and DynamoDB items do not prove every producer event arrived. The current table stores measurement values as strings and overwrites unconditionally. Repeated delivery may republish alerts. Both are explicit M1/M2 work.

## Recovery and next tests

If the producer errors or the shell is interrupted, run realtime-stop.ps1. If cleanup fails, inspect CloudFormation events and retry using the original prefix/profile/region. Treat an access-denied response as unknown state, not proof of deletion.

M2 introduces fixture tests for malformed input, duplicate events, out-of-order events, throttling and replay. The integrated gate requires accepted events to reconcile against producer IDs, explicit duplicate/invalid counts and no unexplained loss after a successful drain.
