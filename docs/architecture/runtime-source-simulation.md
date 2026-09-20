# Runtime Source Simulation

## Purpose

The frozen Microsoft WideWorldImporters baseline remains immutable at **2026-09-15** for reproducibility. The running SQL Server source is a persistent runtime copy that advances from that baseline and then stays operationally alive.

This separates three responsibilities:

- **frozen baseline** = reproducible clean-clone starting point;
- **whole-day catch-up** = recreates every missing complete business day with the official WWI `DataLoadSimulation` procedures;
- **live workload** = produces small source-native operational changes between complete-day catch-ups.

## Runtime service

Docker service: `source-simulator`

Implementation: `src/simulation/runtime_source_simulator.py`

The service starts with Docker and restarts with `unless-stopped`.

At startup it first reads `control.source_frontier`. A fresh warehouse is seeded with:

- source frontier cutoff: `2026-09-16 00:00:00+00`
- completed business data through: **2026-09-15**

If the runtime target is later than the completed frontier, the simulator fills the gap in bounded 7-day chunks. Each chunk:

1. enables the official WWI DataLoadSimulation helpers;
2. creates the missing business-day range;
3. restores the normal WWI temporal state;
4. verifies temporal tables, simulation triggers, and foreign keys;
5. advances `control.source_frontier` only after the chunk passes.

The durable frontier, not `MAX(OrderDate)`, is the authority for completed-day catch-up. This is intentional because live partial-day orders can be newer than the last fully simulated business day.

## Live mode

After catch-up completes, the same service enters event-scheduled live mode.

The default workload is intentionally low-volume:

- cold-room telemetry: one four-sensor batch every **10-25 seconds**;
- vehicle telemetry: one two-sensor batch every **45-120 seconds**;
- new customer order: approximately every **8-20 minutes**;
- simulator-created order picking/invoicing: **90-300 seconds** after creation;
- delivery confirmation: **120-420 seconds** after invoicing;
- purchase-order receipt progress: approximately every **5-15 minutes**.

Live work writes to the **source SQL Server first**. It does not generate random values in the dashboard.

Telemetry is written through:

- `ControlTower.RecordColdRoomTemperaturesAndPublish`
- `ControlTower.RecordVehicleTemperatureAndPublish`

Business activity uses native WWI tables/procedures and the existing event triggers. The normal path is therefore:

`source write -> Service Broker event -> realtime consumer -> current-state projection -> SSE -> dashboard`

This preserves the event-driven contract and avoids high-frequency polling.

## Efficiency model

The live simulator is an event scheduler, not a busy loop.

It:

- sleeps until the next scheduled action;
- checks for a new complete-day gap only every 5 minutes;
- caches bounded customer, employee, and stock-item reference sets;
- reads only recent/targeted source rows for live decisions;
- never scans telemetry history to generate the next reading;
- keeps telemetry state in memory and uses a mean-reverting random walk;
- batches all cold-room sensors into one source call and all vehicle sensors into one source call.

The complete-day analytical frontier is not advanced by live partial-day writes. Those changes reach the operational dashboard through the realtime event path. Airflow processes them analytically after the corresponding full business day is completed and the frontier advances.

## Current-day safety gate

WWI's official whole-day simulator can create temporal timestamps later in the same calendar day. Running it too early can temporarily violate SQL Server temporal reactivation rules.

For that reason the whole-day runtime target is:

- before **20:00 Asia/Jakarta**: previous business date;
- at/after **20:00 Asia/Jakarta**: current business date.

Live workload continues independently of this safety gate.

## Interrupted-run recovery

If a WWI history simulation is interrupted after temporal tables were deactivated, the simulator detects the dirty state before any new whole-day run. A bounded recovery routine restores only the remaining WWI Warehouse temporal tables/triggers, then validates:

- 17 temporal current tables;
- 0 WWI DataLoad modify triggers;
- 0 disabled foreign keys;
- 0 untrusted foreign keys.

The source frontier is never advanced while those guards fail.

## Cutoff semantics

`safe_through_cutoff` is an **exclusive** cutoff.

Example:

- completed business data through: `2026-09-18`
- safe cutoff: `2026-09-19 00:00:00+00`

A live order or sensor reading may exist after that cutoff while the current business day is still incomplete. That does **not** make the partial day analytically safe.

## Downstream processing

The stateful Airflow incremental pipeline is scheduled every 15 minutes:

`*/15 * * * *`

It is normally a no-op while the source frontier has not moved. When the simulator publishes a new complete-day frontier, the next run processes only the new bounded window.

Realtime Service Broker events update the operational projection independently throughout live mode.

## Canonical baseline

The simulator never rewrites `data/baselines/full-master/wwi-full-master-2026-09-15.bak`.

A fresh environment restores the frozen baseline, recreates every missing complete business day, and then automatically transitions into live workload mode.
