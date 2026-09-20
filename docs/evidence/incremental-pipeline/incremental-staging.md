# Incremental Staging Loader

Date: 2026-09-17

## Scope

incremental staging loader implements explicit-window incremental staging updates without introducing persistent watermark/run-state ownership, which remains pipeline-state layer.

## Validation

- fact delta loader uses WWI Integration procedures and replaces only affected primary/business keys
- historical fact rerun is idempotent; total counts remain unchanged
- operational state delta uses LastEditedWhen filters
- stock holding uses bounded diff snapshot
- temporal master/history delta uses ValidFrom and affected-entity validity recalculation
- small current master/reference tables use bounded diff snapshots
- geography current uses changed city IDs from Integration.GetCityUpdates
- telemetry recomputes an overlapping 5-minute bucket window and replaces only affected buckets

### Historical idempotency proof

- order_line: 352 rows replaced; total remains 1,009,327
- sale_line: 343 rows replaced; total remains 993,477
- inventory_movement: 368 rows replaced; total remains 1,028,716
- purchase_line: 35 rows replaced; total remains 35,089
- financial_transaction: 167 rows replaced; total remains 452,853

### State/master proof

- order_state: 122 rows replaced
- invoice_delivery: 113 rows replaced
- purchase_order_state: 8 rows replaced
- stock_holding_current: 0 changed / 0 deleted
- current master/reference snapshots: unchanged rows were not rewritten
- temporal master/history window: no changes in the tested window

### Telemetry idempotency proof

- coldroom_5m: 2,308 buckets replaced; total remains 4,519,296
- vehicle_5m: 432 buckets replaced; total remains 844,776
- coldroom SUM(reading_count): 87,439,552
- vehicle SUM(reading_count): 1,689,502
- min/max preserved at 3.00 / 5.00

## Exit Result

dbt/core incremental refresh dbt/core incremental refresh is not started in this work package.
