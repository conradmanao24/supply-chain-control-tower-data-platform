# Telemetry Publish Wrapper Evidence

## Objective

Provide an event-driven telemetry write path for WWI memory-optimized telemetry without adding DML triggers to those tables.

## Source audit

- `Warehouse.ColdRoomTemperatures` is memory-optimized.
- `Warehouse.VehicleTemperatures` is memory-optimized.
- Official WWI write procedures are `Website.RecordColdRoomTemperatures` and `Website.RecordVehicleTemperature`.
- `Website.RecordColdRoomTemperatures` accepts `Website.SensorDataList`.
- `Website.RecordVehicleTemperature` accepts `nvarchar(1000)` containing `$.Recordings` JSON.
- No SQL module calls those procedures internally; the write call is application/workload driven.

## Project-owned wrapper

`sql/infrastructure/telemetry_publish_wrapper.sql` provisions:

- `ControlTower.PublishTelemetryEvent`
- `ControlTower.RecordColdRoomTemperaturesAndPublish`
- `ControlTower.RecordVehicleTemperatureAndPublish`

The wrappers call the official WWI procedure first and publish one batched Service Broker notification only for non-empty telemetry input. They do not attach triggers to memory-optimized telemetry tables.

## End-to-end proof

A single controlled synthetic vehicle reading was submitted through `ControlTower.RecordVehicleTemperatureAndPublish`.

Observed event:

- message type: `//SupplyChainControlTower/Event`
- event type: `telemetry.vehicle.batch_recorded`
- entity type: `telemetry`
- source table: `Warehouse.VehicleTemperatures`
- probe identity was present in the event payload

The synthetic source row was then removed.

Integrity after cleanup:

- VehicleTemperatures before: `1,689,502`
- VehicleTemperatures after: `1,689,502`
- synthetic probe rows remaining: `0`
- EventIngressQueue rows: `0`
- EventConsumerQueue rows: `0`
- transmission queue rows: `0`

The Cold Room wrapper was executed with an empty `Website.SensorDataList` and produced no false event.

Proof script: `scripts/testing/telemetry_wrapper_proof.sql`.

## Result

Telemetry can enter the event plane through a project-owned wrapper around the official WWI write procedures without table polling or telemetry-table triggers.