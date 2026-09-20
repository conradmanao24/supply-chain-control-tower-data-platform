# Cold Chain REST Serving

## Scope

Implemented the Cold Chain business-serving page as the next business serving layer serving area.

## Backend

Endpoint:

`GET /api/cold-chain/overview`

Source boundary:

- `realtime.current_sensor_state`
- `alert.alerts`
- `alert.rule_config`

The browser does not query WWI directly.

## Current measured serving state

At validation time:

- tracked sensors: 6
- cold-room sensors: 4
- vehicle sensors: 2
- minimum latest temperature: 3.33 °C
- maximum latest temperature: 4.96 °C
- average latest temperature: 4.22 °C
- active cold-chain alerts: 0
- enabled cold-chain rules: 2
- disabled temperature rules: 2

Latest sensor state includes:

- coldroom:1 — 4.96 °C
- coldroom:2 — 3.33 °C
- coldroom:3 — 3.80 °C
- coldroom:4 — 3.60 °C
- vehicle:WWI-321-A:1 — 4.90 °C
- vehicle:WWI-321-A:2 — 4.70 °C

The configured freshness rules are enabled, while temperature warning/critical rules are disabled because their threshold values are not configured. The UI does not invent temperature limits.

## Frontend

Added `frontend/src/ColdChainPage.tsx` and the Cold Chain REST contract in `frontend/src/api.ts`.

Page sections:

- KPI strip
- sensor-group temperature summary
- monitoring policy / alert state
- latest sensor readings table
- manual refresh action

The page reuses the locked business serving layer design system and responsive shell.

## Validation

- Cold Chain API: HTTP 200
- Vite production build: PASS
- Dashboard dev server: HTTP 200
- 1,885 frontend modules transformed successfully
- realtime API: OK
- realtime database: OK
- backend SSE listener: connected
- Control Tower active exceptions: 0
- latest quality gate: PASS

## Boundary

This checkpoint is REST serving only.

Cold Chain SSE realtime refresh is intentionally deferred to the next small business serving layer batch.
