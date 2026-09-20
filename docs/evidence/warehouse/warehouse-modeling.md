# Warehouse Modeling

Date: 2026-09-17

## Scope

This checkpoint converts source-aligned PostgreSQL staging data into the dbt `core` warehouse schema. Incremental extraction, pipeline state, operational event publication, alerts, and serving are validated separately.

## Implemented Models

Dimensions:
- `core.dim_product`
- `core.dim_customer`
- `core.dim_supplier`
- `core.dim_employee`
- `core.dim_geography`
- `core.dim_date`
- `core.dim_delivery_method`
- `core.dim_transaction_type`
- `core.dim_package_type`

Bridge:
- `core.bridge_product_stock_group`

Facts:
- `core.fact_order_line`
- `core.fact_sales_line`
- `core.fact_inventory_movement`
- `core.fact_purchase_order_line`
- `core.fact_delivery_event`
- `core.fact_customer_transaction`
- `core.fact_supplier_transaction`

## Business-History Audit

Temporal-to-semantic results:
- product: 671 temporal rows -> 227 semantic rows / 227 entities
- customer: 991 temporal rows -> 991 semantic rows / 813 entities; all 178 subsequent versions are `CreditLimit` changes
- supplier: 26 temporal rows -> 13 semantic rows / 13 entities
- employee: 307 temporal rows -> 19 semantic rows / 19 entities

Additional source audit proved:
- customer-name historical changes: 0 customers
- customer-category-ID historical changes: 0 customers
- buying-group-ID historical changes: 0 customers
- one customer-category label changed historically
- one supplier-category label changed historically

The model therefore retains category IDs without falsely denormalizing current category labels into historical SCD rows.

## Delivery Event Audit

Source-backed JSON events:
- Ready for collection: 308,053
- DeliveryAttempt / Delivered: 277,276
- DeliveryAttempt / source status absent: 30,733
- total: 616,062

`fact_delivery_event` materialized exactly 616,062 rows.

## Final Model Counts

| Model | Rows |
| --- | ---: |
| `dim_product` | 227 |
| `dim_customer` | 991 |
| `dim_supplier` | 13 |
| `dim_employee` | 19 |
| `dim_geography` | 37,940 |
| `dim_date` | 5,026 |
| `dim_delivery_method` | 10 |
| `dim_transaction_type` | 13 |
| `dim_package_type` | 14 |
| `bridge_product_stock_group` | 442 |
| `fact_order_line` | 1,009,327 |
| `fact_sales_line` | 993,477 |
| `fact_inventory_movement` | 1,028,716 |
| `fact_purchase_order_line` | 35,089 |
| `fact_delivery_event` | 616,062 |
| `fact_customer_transaction` | 443,041 |
| `fact_supplier_transaction` | 9,812 |

Current-row SCD coverage:
- product: 227 / 227
- customer: 813 / 813
- supplier: 13 / 13
- employee: 19 / 19

`dim_date` range: 2013-01-01 through 2026-10-05.

## dbt Validation

Final clean build:
- dbt Core: 1.11.15
- dbt-postgres: 1.11.0
- table models: 17
- data tests: 115
- total nodes executed: 132
- PASS: 132
- WARN: 0
- ERROR: 0
- SKIP: 0

Evidence log: `docs/evidence/warehouse/dbt-build-final.log`.

The first full run had one test-harness syntax error because the CTE name `overlaps` collided with PostgreSQL `OVERLAPS`. The model/data results were successful; the test CTE was renamed to `overlap_rows`, the single test passed, and the entire build was rerun to the clean 132/132 result above.

## Reconciliation

`reconcile_core_counts`: passed.

`reconcile_core_measures`: passed.

`scd_current_coverage`: passed.

`scd_no_overlap`: passed.

`conditional_dimension_orphans`: passed.

`customer_semantic_scd`: passed.

All configured uniqueness, non-null, and relationships tests: passed.

## Exit Result

The `core` warehouse produced the recorded model and reconciliation results used by the later incremental pipeline.