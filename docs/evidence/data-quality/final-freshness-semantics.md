# Final Freshness Semantics Correction

Date: 2026-09-20

## Why this correction was required

The final quality audit exposed two false freshness failures:

- `order_state`
- `stock_holding_current`

The failures were caused by one freshness rule being applied to two different ingestion contracts.

## Mutable delta current-state datasets

`order_state`, `invoice_delivery`, and `purchase_order_state` are mutable source views loaded incrementally to a committed cutoff.

A row can be extracted before the cutoff and then edited again after the cutoff. The current source view then exposes only the newer `LastEditedWhen`, while staging correctly retains the version observed during the committed window.

Therefore a target timestamp being newer than `MAX(source LastEditedWhen <= watermark)` is not itself a freshness failure.

The corrected gate requires:

- target state must not advance beyond the committed watermark
- a positive source-to-target lag must remain within the configured freshness SLA
- a negative lag is valid when staging contains a committed pre-cutoff state whose source row was edited again after the cutoff

Verified example:

- committed cutoff: `2026-09-20T00:00:00Z`
- staging Order #323955: `2026-09-19T23:59:01.859839`
- same live source row after another update: `2026-09-20T00:02:43.849228`

The staging state is valid for the committed analytical cutoff.

## Full current snapshot dataset

`stock_holding_current` is intentionally refreshed as a full live snapshot during tail refresh.

It is not bounded to the analytical watermark and must therefore be compared to the current live source rather than a source query artificially capped at the watermark.

Final proof:

- source current max: `2026-09-20T00:58:01.629777`
- staging current max: `2026-09-20T00:58:01.629777`

Exact match.

## Late-arrival telemetry closure

A later full-mode audit found one real reconciliation mismatch in cold-room telemetry: SQL Server contained 12 more raw readings than the persisted 5-minute aggregate counts.

The mismatch was isolated to the final `2026-09-19 23:55:00` bucket:

- four cold-room sensors
- 23 raw source readings per sensor
- 20 staged readings per sensor
- difference: 3 readings x 4 sensors = 12 readings

The missing readings arrived after the source frontier had already reached the committed cutoff, but their `RecordedWhen` values were still before that cutoff. The tail-refresh path previously refreshed only the sensor projection when watermark equaled frontier, so the boundary aggregate was not recomputed.

The incremental Airflow DAG was corrected so tail refresh also re-reads the late-arrival telemetry overlap ending at the committed watermark. After rerun, all four sensors contained 23/23 readings through `2026-09-19T23:59:47.416`, and the 130-month cold-room source-to-staging comparison returned zero mismatched months.

## Final quality result

After the freshness-semantic correction and late-arrival telemetry repair:

- dbt tests: **116 / 116 PASS**
- latest full quality gate: **52 PASS / 0 FAIL / 6 WARNING**
- watermark/source frontier alignment: PASS
- staging-to-core count reconciliation: PASS
- staging-to-core measure reconciliation: PASS
- raw telemetry count/min/max reconciliation: PASS
- telemetry freshness and bucket integrity: PASS
- platform data-quality alerts: clear

The six warnings are expected live-source drift between the continuously moving source and the committed analytical snapshot. They are warnings rather than hard reconciliation failures by design.

Latest full quality run:

`manual__2026-09-20T03:16:05.025947+00:00`

Result: **PASS**
