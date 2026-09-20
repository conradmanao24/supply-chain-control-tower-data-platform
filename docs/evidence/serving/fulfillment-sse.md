# Fulfillment SSE Realtime Refresh

Date: 2026-09-17

## Scope

Connect the Fulfillment serving page to the existing shared browser SSE stream without introducing interval polling or a second browser-to-source path.

## Implementation

- Reused the single application-shell `EventSource` connection to `/api/realtime/stream`.
- Added fulfillment-aware event routing in the shell.
- Fulfillment refreshes when the shared stream carries:
  - `order.changed`
  - `deadline.fulfillment.*`
  - alert `rule_id` beginning with `fulfillment.`
  - alert payload with `domain=fulfillment`
- Fulfillment page receives the shared SSE connection state and a refresh signal from the shell.
- Refreshes call the existing project-owned REST serving endpoint `/api/fulfillment/overview`.
- No interval polling was added.
- Theme, navigation, and page state remain application-shell state and are not reset by the data refresh.

## Controlled SSE Proof

A controlled PostgreSQL `NOTIFY` proof was used so the stream path could be tested without mutating business state.

The live stream received:

1. `event: update` with `event_type=order.changed`
2. `event: alert` with `rule_id=fulfillment.overdue` and `domain=fulfillment`

Proof capture:
`docs/evidence/serving/fulfillment-sse-proof.txt`

Measured proof result:
- order update events captured: 1
- fulfillment alert events captured: 1

## Final Validation

- frontend production build: PASS
- local UI: HTTP 200
- realtime API: `status=ok`
- warehouse connectivity: `database=ok`
- backend SSE listener: `connected`
- Fulfillment REST state after proof:
  - open orders: 170
  - overdue: 167
  - due at source frontier: 3
  - backorders: 170
  - active fulfillment alerts: 0
- final global active alerts: 0

The proof used notification-only synthetic payloads; no source/current-state/business rows were changed and no synthetic alert row remained.

**FULFILLMENT LIVE SERVING: passed.**
