# Realtime Service Boundary

Status: **DEFINED - NOT IMPLEMENTED**

The operational event plane is intentionally separated from the analytical Airflow/dbt path.

## Input

The realtime backend will consume small project-owned events from SQL Server Service Broker through `ControlTower.EventConsumerQueue` using the dedicated `sct_event_consumer` principal.

## Responsibilities

The backend will eventually:

- consume committed database events
- resolve current operational state
- evaluate configured alert rules
- maintain current-state projections and alert lifecycle state
- push server-to-browser updates using Server-Sent Events (SSE)
- accept acknowledgement/configuration actions through REST

## Non-Responsibilities

The realtime backend will not:

- run analytical ETL
- replace Airflow
- calculate warehouse marts
- perform heavy joins inside SQL Server triggers
- call browsers or HTTP endpoints directly from database triggers
- edit authoritative WWI business data

## Event Publication Boundary

Disk-based business tables may later use lightweight DML triggers that publish only a small event envelope.

Memory-optimized telemetry tables require their separately validated interpreted write/publish wrapper path rather than a generalized trigger pattern.

Time-driven exceptions such as overdue orders and stale sensors require deadline/timer events. They are not implemented by repeatedly polling source tables merely to discover that time has passed.

## Phase Boundary

source and event integration creates and validates only the messaging/access infrastructure. Business triggers, telemetry wrappers, deadline timers, alert evaluation, projections, SSE endpoints, and frontend behavior are explicitly deferred to later phases.