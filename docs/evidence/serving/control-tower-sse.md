# Control Tower SSE Live Refresh

Date: 2026-09-17

## Scope

This checkpoint connects the React Control Tower overview to the existing realtime SSE stream. The browser still uses REST for the initial/current snapshot, then reacts to `alert` and `update` SSE messages by refreshing project-owned serving data without reloading the page or polling the source.

## Frontend behavior

Implemented in `frontend/src/App.tsx` and `frontend/src/api.ts`:
- `EventSource` connects to `/api/realtime/stream`.
- `ready` / connection open sets browser SSE state to `connected`.
- `alert` and `update` events schedule a short 120 ms coalesced refresh of the Control Tower REST overview and API health.
- native EventSource reconnection is preserved; UI state reports `connecting`, `connected`, `reconnecting`, or `disconnected`.
- theme, sidebar state, selected navigation, and page state are not reset by a realtime refresh.
- there is no interval/setInterval polling loop.

The Control Tower heading and platform-health card expose browser-stream status separately from the backend PostgreSQL LISTEN listener status.

## Controlled SSE proof

Evidence file: `docs/evidence/serving/sse-live-proof.txt`.

A bounded listener was attached to the SSE endpoint. A controlled project platform alert was then opened and resolved through the existing alert API using entity id `phase11_sse_refresh_proof`.

Observed stream:
- `event: ready`
- `event: alert` with status `open`
- `event: alert` with status `resolved`

Observed serving-state transition:
- before proof: active exception state was clear
- alert opened: Control Tower overview reported `active_exceptions=1`
- alert resolved: Control Tower overview returned to `active_exceptions=0`

The raw proof recorded **2 alert SSE events** for the same controlled alert lifecycle.

## Cross-origin browser contract

The SSE endpoint returned:
- HTTP 200
- `content-type: text/event-stream`
- `cache-control: no-cache`
- `x-accel-buffering: no`
- `access-control-allow-origin: http://127.0.0.1:5173`

This matches the local React development origin.

## Build/runtime validation

- frontend production build: PASS
- local UI: HTTP 200
- realtime API: `status=ok`
- PostgreSQL API database check: `ok`
- backend SSE listener: `connected`
- analytical watermark: aligned
- data quality and reconciliation layer quality state: pass

## Cleanup

The controlled synthetic alert and its cascading history were deleted after proof.

Final state:
- synthetic business serving layer SSE proof alerts: 0
- active alerts: 0
- Control Tower active exceptions: 0

## Exit

The Control Tower overview now satisfies the business serving layer live-serving contract for this page:

`REST initial/current snapshot + SSE-triggered refresh, without polling or full-page reload.`
