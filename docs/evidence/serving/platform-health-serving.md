# Platform Health Serving

## Scope

Implemented the Platform Health serving page with REST-backed platform state and refresh through the existing shared browser SSE connection.

No additional EventSource and no interval polling were added.

## Backend

Endpoint:

`GET /api/platform-health/overview`

Source boundary:

- `control.pipeline_state`
- `control.source_frontier`
- `control.processing_guard`
- `alert.engine_state`
- `alert.alerts`
- `quality.run_history`
- `realtime.event_log`

The page also uses the existing `GET /health` endpoint for API/database/SSE-listener health.

## Current measured platform state

At validation time:

- pipeline cutoff: 2026-09-16 00:00:00+00
- source frontier: 2026-09-16 00:00:00+00
- watermark aligned: true
- latest quality gate: PASS
- quality checks: 51 passed / 0 failed
- active alerts: 0
- realtime event-log rows: 23
- events in last 24h: 23
- unprocessed events: 0
- realtime API: OK
- database: OK
- backend SSE listener: connected
- browser SSE subscriber observed: 1
- Control Tower active exceptions: 0

## Frontend

Added `frontend/src/PlatformHealthPage.tsx` and the Platform Health contract in `frontend/src/api.ts`.

Page sections:

- composite platform-health KPI strip
- serving API / database / SSE state
- pipeline cutoff vs source-frontier alignment
- processing guard state
- alert-engine state
- latest quality-gate state
- event-processing result distribution
- manual refresh action

The page receives the shared browser `sseState` and a platform refresh signal. Every existing shared realtime `update` or `alert` event increments this signal, causing a REST refresh without browser reload.

## Controlled SSE proof

A notification-only platform-health event was published to the project-owned PostgreSQL notification channel.

Observed:

```
event: ready

event: update
event_type: platform.health.proof
processing_result: phase11_platform_health_sse_proof
```

The proof did not mutate WWI or project business/current-state data.

Proof artifact:

`docs/evidence/serving/platform-health-sse-proof.txt`

## Validation

- Platform Health API: HTTP 200
- Vite production build: PASS
- dashboard dev server: HTTP 200
- 1,887 frontend modules transformed successfully
- realtime API: OK
- database: OK
- backend SSE listener: connected
- quality gate: PASS
- watermark aligned: true
- unprocessed events: 0
- active alerts: 0

## Result

Platform Health is live and uses the same shared realtime channel as the business-serving pages.
