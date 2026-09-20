# Control Tower Frontend

React + TypeScript + Vite frontend for the Supply Chain Control Tower Data Platform.

## Purpose

The UI is the serving layer for two intentionally separate data paths:

- **operational / realtime** state from the project-owned realtime API
- **analytical** warehouse metrics from PostgreSQL/dbt serving endpoints

The browser does not query WideWorldImporters directly.

## Main areas

- Control Tower
- Fulfillment
- Delivery
- Inventory
- Procurement
- Cold Chain
- Analytics
- Platform Health
- Admin

Fulfillment, Delivery, Inventory, and Procurement share a cross-domain Exception Workbench:

```text
exception -> business impact -> evidence -> derived cause -> related records -> timeline
```

Derived causes are deterministic, source-backed, and traceable to the supporting operational evidence.

## Local development

From this directory:

```powershell
npm ci
npm run dev
```

Default local URL:

```text
http://127.0.0.1:5173
```

The realtime API is expected at the project-configured endpoint, normally:

```text
http://127.0.0.1:18000
```

## Production build

```powershell
npm run build
```

The production build is included in the recorded runtime validation.

## Realtime behavior

The frontend uses Server-Sent Events for update notification, with:

- coalesced refresh signals
- active-tab-only operational refresh
- in-flight GET deduplication
- last-good in-memory state while revalidating

This prevents event bursts from turning into duplicate request storms.

## Design constraints

- responsive for 1080p and 2K desktop use
- consistent table/drawer interaction patterns
- no fake buttons or decorative controls presented as functional
- no question-style dashboard headings
- source/warehouse freshness context remains visible where relevant

See the root `README.md` and `docs/evidence/serving/serving-validation.md` for the project documentation and serving validation.
