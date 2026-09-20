# Control Tower REST Serving Proof

Date: 2026-09-17

## Scope

This batch replaces Control Tower preview values with initial live serving data. It intentionally does not add SSE-driven updates yet.

## Backend

Added `GET /api/control-tower/overview` in `src/realtime/control_tower_api.py`.

The endpoint serves project-owned PostgreSQL state only and does not poll WWI from the browser. It returns:
- active alert summary
- open fulfillment count
- pending-delivery count
- inventory reorder/watch count
- procurement under-received count
- cold-room/vehicle sensor tracking summary
- recent active alerts
- analytical watermark/source-frontier alignment
- latest persisted quality-gate state

The existing realtime FastAPI service now includes the Control Tower router and CORS for the local frontend origins `http://127.0.0.1:5173` and `http://localhost:5173`.

## Frontend

Added `frontend/src/api.ts` and converted the Control Tower overview from preview constants to REST-backed initial state.

Current live baseline returned by the serving endpoint during proof:
- active exceptions: 0
- open fulfillment / picking incomplete: 15,472
- pending delivery: 44
- inventory at/below reorder: 3
- procurement open under-received: 2
- cold-room sensors tracked: 4
- vehicle sensors tracked: 2
- analytical watermark aligned with source frontier: true
- latest quality gate: PASS, 57 checks passed, 0 failed

The recent-alert panel shows an explicit healthy empty state when there are no active alerts rather than fabricated alert rows.

## Validation

- realtime API container recreated successfully with new router
- `GET /api/control-tower/overview` returned HTTP 200 with live values
- CORS response allowed `http://127.0.0.1:5173`
- frontend production build passed
- frontend development server returned HTTP 200

## Boundary

This is an initial snapshot contract only. The frontend performs one REST load on mount. No interval polling was introduced. SSE-driven refresh remains the next business serving layer batch.
