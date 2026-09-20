# Inventory SSE Realtime Refresh

## Scope

Connected the Inventory serving page to the existing shared browser EventSource used by the Control Tower, Fulfillment, and Delivery pages.

No interval polling was added.

## Frontend contract

Relevant SSE payloads now increment the Inventory refresh signal when any of the following is observed:

- `event_type = inventory.changed`
- `rule_id` starts with `inventory.`
- `domain = inventory`

The Inventory page receives:

- `sseState`
- `refreshSignal`

When the refresh signal changes, the page reloads `GET /api/inventory/overview` without reloading the browser page.

The page now displays `Live REST + SSE` and exposes the current SSE connection state.

## Controlled proof

A notification-only proof was sent directly to the project-owned PostgreSQL notification channel. It did not mutate WWI or project business/current-state data.

Observed stream:

```
event: ready

event: update
event_type: inventory.changed

event: alert
rule_id: inventory.reorder
domain: inventory
```

Proof artifact:

`docs/evidence/serving/inventory-sse-proof.txt`

## Final validation

- Vite production build: PASS
- frontend dev server: HTTP 200
- realtime API: OK
- realtime database: OK
- backend SSE listener: connected
- Inventory endpoint: healthy
- inventory stock items: 227
- reorder watch: 3
- negative stock: 0
- active inventory alerts: 0
- Control Tower active exceptions: 0
- latest quality gate: PASS

## Result

Inventory business serving is live-complete for business serving layer:

- REST initial/current snapshot: PASS
- SSE-triggered refresh: PASS
- no browser interval polling
- no browser-to-WWI direct access
