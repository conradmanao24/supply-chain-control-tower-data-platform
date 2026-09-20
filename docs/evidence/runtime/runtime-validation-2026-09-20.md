# Runtime Validation — 2026-09-20

This record summarizes the final runtime checks performed against the completed local application and data platform.

## Application checks

The validation covered:

- Control Tower
- Fulfillment
- Delivery
- Inventory
- Procurement
- Cold Chain
- Analytics
- Platform Health
- Admin

Checks included navigation, filters, KPI actions, table interactions, detail views, cross-domain routing, pagination, loading/error states, SSE reconnect behavior, 1080p/2K layout behavior, numerical reconciliation, and browser console errors.

## Data pipeline checks

dbt validation:

- **116 / 116 data tests passed**
- 0 warning
- 0 error

Persisted full-mode quality checks:

- **52 passed**
- **0 failed**
- **6 live-source volume warnings**

The warnings were produced by source rows that continued changing beyond the committed analytical snapshot. They did not represent hard reconciliation failures.

## Late-arrival telemetry correction

Full reconciliation identified 12 cold-room readings missing from the final pre-cutoff 5-minute bucket.

The issue occurred when late source rows arrived after frontier publication but carried timestamps before the committed cutoff. The tail refresh was updated to re-read the configured telemetry overlap ending at the committed cutoff.

After the correction:

- the production watermark remained unchanged
- the final bucket matched the source at 23 readings for each of four cold-room sensors
- the 130-month cold-room source-to-staging comparison returned zero mismatched months

## Recovery check

The Docker stack was stopped with `docker compose down` without removing volumes, then recreated with `docker compose up -d`.

Persistent state remained available after restart:

- analytical watermark
- source frontier
- warehouse fact counts
- active alerts
- quality history
- realtime event log

The SQL Server, PostgreSQL, Airflow, realtime API, source simulator, and realtime consumer services recovered. A manual incremental run completed after restart, followed by the next scheduled Airflow incremental run.

Post-restart full quality checks returned **52 passed / 0 failed / 6 live-source warnings**.

## Runtime boundary

The backend and data-platform services are managed by Docker Compose. The Vite frontend is intentionally started separately with `npm run dev`.

## Repository hygiene

- local `.env` excluded from version control
- database backups and runtime data excluded
- frontend `node_modules` and `dist` excluded
- Python caches excluded
- logs, PID files, and runtime artifacts excluded
- no hardcoded credential literals found in the repository scan
- no TODO/FIXME/HACK markers found in the final codebase scan

The code repository excluding local runtime assets is approximately 1.9 MB.
