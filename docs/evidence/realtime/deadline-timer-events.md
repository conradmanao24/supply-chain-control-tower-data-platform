# Deadline / Timer Events

## Objective

Add deadline-driven event publication without repeated source-table polling.

## Design

deadline/timer events uses SQL Server Service Broker conversation timers. A deadline is scheduled once in project-owned metadata, SQL Server waits internally, and queue activation runs only when the timer message becomes due.

Project-owned objects:

- `ControlTower.DeadlineSchedule`
- `ControlTower.DeadlineTimerQueue`
- `//SupplyChainControlTower/DeadlineTimer`
- `ControlTower.ScheduleDeadline`
- `ControlTower.CancelDeadline`
- `ControlTower.ProcessDeadlineTimerQueue`

A timer event is a due signal, not an alert conclusion. Current-state evaluation and alert lifecycle remain downstream scope.

## Proof

A controlled proof scheduled `deadline.phase6c.probe` three seconds in the future. Service Broker activation published the event to `ControlTower.EventConsumerQueue` with operation `DEADLINE` and the ledger transitioned to `fired`.

A second timer was scheduled and immediately cancelled. No consumer event was emitted and its ledger transitioned to `cancelled`.

Final cleanup checks:

- DeadlineTimerQueue rows: `0`
- EventIngressQueue rows: `0`
- EventConsumerQueue rows: `0`
- transmission queue rows: `0`
- open timer conversation endpoints: `0`
- temporary proof ledger rows: `0`

Proof script: `scripts/testing/deadline_timer_proof.sql`.

## Notes

The first DDL iteration used filtered indexes, which imposed SQL Server SET-option requirements on every DML session. Those were replaced with regular supporting indexes; active-deadline serialization is handled inside `ScheduleDeadline` using transaction locking (`UPDLOCK`, `HOLDLOCK`).