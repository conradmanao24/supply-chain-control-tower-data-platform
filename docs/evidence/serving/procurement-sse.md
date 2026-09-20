# Procurement SSE Realtime Refresh

## Scope

Connected the Procurement serving page to the existing shared browser EventSource used by the Control Tower, Fulfillment, Delivery, and Inventory pages.

No interval polling was added.

## Frontend contract

Relevant SSE payloads now increment the Procurement refresh signal when any of the following is observed:

- `event_type = procurement.changed`
- `rule_id` starts with `procurement.`
- `domain = procurement`

The Procurement page receives:

- `sseState`
- `refreshSignal`

When the refresh signal changes, the page reloads `GET /api/procurement/overview` without reloading the browser page.

The page now displays `Live REST + SSE` and exposes the current SSE connection state.

## Controlled proof

A notification-only proof was sent directly to the project-owned PostgreSQL notification channel. It did not mutate WWI or project business/current-state data.

Observed stream:

```
event: ready

event: update
event_type: procurement.changed

event: alert
rule_id: procurement.overdue_under_received
domain: procurement
```

Proof artifact:

`docs/evidence/serving/procurement-sse-proof.txt`

## Final validation

- Vite production build: PASS
- frontend dev server: HTTP 200
- realtime API: OK
- realtime database: OK
- backend SSE listener: connected
- purchase orders in 30-day window: 48
- open POs: 2
- under-received POs: 2
- overdue POs: 0
- active procurement alerts: 0
- Control Tower active exceptions: 0
- latest quality gate: PASS

## Result

Procurement business serving is live-complete for business serving layer:

- REST initial/current snapshot: PASS
- SSE-triggered refresh: PASS
- no browser interval polling
- no browser-to-WWI direct access
