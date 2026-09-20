# Inventory REST Serving

## Scope

Implemented the Inventory business-serving page as the next business serving layer serving area.

## Backend

Endpoint:

`GET /api/inventory/overview`

Source boundary:

- `realtime.current_inventory_state`
- `alert.alerts`
- `alert.rule_config`

The browser does not query WWI directly.

## Current measured serving state

At validation time:

- tracked stock items: 227
- reorder watch: 3
- negative stock: 0
- units on hand: 141,013,721
- healthy items: 224
- active inventory alerts: 0

Priority replenishment items:

- stock item 184 — Shipping carton (Brown) 305x305x305mm — on hand 38 / reorder 50 / target 100
- stock item 203 — Tape dispenser (Black) — on hand 3 / reorder 20 / target 30
- stock item 204 — Tape dispenser (Red) — on hand 4 / reorder 20 / target 30

## Frontend

Added `frontend/src/InventoryPage.tsx` and the Inventory REST contract in `frontend/src/api.ts`.

Page sections:

- KPI strip
- stock-state distribution
- persisted inventory-alert summary
- replenishment priority table
- manual refresh action

The page reuses the locked business serving layer design system and responsive shell.

## Validation

- Inventory API: HTTP 200
- Vite production build: PASS
- Dashboard dev server: HTTP 200
- 1,883 frontend modules transformed successfully

## Boundary

This checkpoint is REST serving only.

Inventory SSE realtime refresh is intentionally deferred to the next small business serving layer batch.
