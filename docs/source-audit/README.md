# Source Audit

This directory contains source acquisition, restore, audit, simulation, and validation evidence for the Microsoft WideWorldImporters OLTP source.

## Reports

- `source-acquisition.md` - official source acquisition and artifact validation
- `source-runtime-restore.md` - SQL Server runtime, restore, connectivity, and persistence evidence
- `source-audit.md` - schema/table inventory, row counts, PK/FK relationships, date ranges, change behavior, and incremental candidates
- `date-rebase-safety-audit.md` - read-only assessment of the abandoned date-rebase alternative
- `simulation-pilot.md` - controlled WWI simulation pilot
- `source-audit-final.md` - final source state, full catch-up result, baseline freeze, and validation summary

## Selected baseline

The project baseline preserves the full source history:

- operational range: `2013-01-01` through `2026-09-15`
- raw user-table rows: `93,334,276`
- compressed full backup: `1,662,111,744 bytes` (`1.548 GiB`)
- SHA-256: `1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30`
- backup integrity checked with `RESTORE VERIFYONLY WITH CHECKSUM`

The explored 2023-2026 trimmed distribution was not selected. Full history is retained in the canonical baseline.

## Evidence directories

- source-audit query outputs: `evidence/audit/`
- source simulation evidence: `evidence/simulation/`
- final source state: `evidence/simulation/final/final_source_state.txt`

Airflow, PostgreSQL warehouse, and dbt are documented separately from this source-audit boundary.
