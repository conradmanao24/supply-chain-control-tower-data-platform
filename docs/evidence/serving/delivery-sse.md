# Delivery SSE Realtime Refresh

Date: 2026-09-17

## Scope

The Delivery serving page now uses the shared browser EventSource owned by the application shell. It does not create a second polling loop or direct browser connection to WWI.

Relevant SSE messages increment a Delivery refresh signal when they match any of:
- `delivery.changed`
- `deadline.delivery.*`
- `delivery.*` alert rule
- alert payload with `domain=delivery`

The Delivery page reacts to that signal by re-reading `GET /api/delivery/overview` from the project realtime API. Existing UI state is retained; there is no full-page reload and no interval polling.

## Controlled proof

A notification-only proof was sent through PostgreSQL `control_tower_realtime`; no business/current-state row was mutated.

Observed stream:
- `event: update` with `event_type=delivery.changed`
- `event: alert` with `rule_id=delivery.overdue` and `domain=delivery`

Proof file: `docs/evidence/serving/delivery-sse-proof.txt`.

Observed counts:
- delivery update events: 1
- delivery alert events: 1

Final runtime validation:
- frontend production build: PASS
- UI HTTP: 200
- realtime API: `ok`
- database: `ok`
- backend SSE listener: `connected`
- live delivery pending count after proof: 44
- active delivery alerts after proof: 0

## Result

**DELIVERY SSE REALTIME REFRESH: PASS**

Next serving checkpoint: Inventory page.
