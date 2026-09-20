# Warehouse Model Contract

Date: 2026-09-17

## Purpose

The `core` PostgreSQL schema is the business-ready analytical warehouse layer. It is intentionally not a 1:1 mirror of WideWorldImporters. Source-aligned data remains in `staging`; dbt transforms that data into explicit dimensions, facts, and the product-stock-group bridge.

## Dimension Contract

### `dim_product`

Business key: `stock_item_id`.

Surrogate key: deterministic hash of entity type, business key, and semantic `valid_from`.

SCD policy: business-attribute-driven. Product temporal history had 671 source versions across 227 products, but audited core product attributes collapse to 227 semantic versions. `CustomFields` and `Tags` are intentionally excluded from the semantic hash because they created temporal noise without changing core analytical interpretation.

### `dim_customer`

Business key: `customer_id`.

SCD policy: SCD2 driven by audited business-meaningful changes. Across 813 customers, the source contains 991 temporal versions. The 178 subsequent versions are all `CreditLimit` changes; audited customer name, category ID, buying-group ID, delivery method, city, payment terms, discount, credit-hold flag, route fields, and postal code did not change across those versions.

`CustomerName` is repeated from the current descriptor because source audit proved no historical name change. Customer-category name is not denormalized into the SCD row because one category label changed historically while customer history stores the stable category ID. This avoids falsely presenting the current label as historically correct.

### `dim_supplier`

Business key: `supplier_id`.

SCD policy: business-attribute-driven. The 26 temporal source rows collapse to 13 semantic versions for 13 suppliers. Supplier-category ID is retained; category label is not denormalized because one category label changed historically.

### `dim_employee`

Business key: `person_id`.

SCD policy: business-attribute-driven over employee name, preferred name, employee flag, and salesperson flag. The 307 temporal source rows collapse to 19 semantic versions for 19 current employees.

### Type-1 reference dimensions

- `dim_geography`: one row per city.
- `dim_delivery_method`: one row per delivery method.
- `dim_transaction_type`: one row per transaction type.
- `dim_package_type`: one row per package type.
- `dim_date`: one row per calendar date required by historical facts and source-backed expected-delivery dates. Current range is 2013-01-01 through 2026-10-05.

## Fact Grain Contract

| Fact | Grain | Baseline Rows |
| --- | --- | ---: |
| `fact_order_line` | one WWI order x stock item | 1,009,327 |
| `fact_sales_line` | one WWI invoice x stock item | 993,477 |
| `fact_inventory_movement` | one stock-item transaction | 1,028,716 |
| `fact_purchase_order_line` | one WWI purchase order x stock item | 35,089 |
| `fact_delivery_event` | one JSON delivery event inside one invoice | 616,062 |
| `fact_customer_transaction` | one customer transaction | 443,041 |
| `fact_supplier_transaction` | one supplier transaction | 9,812 |

The order/invoice/purchase composite grains were audited against source line counts and have zero duplicate `(header_id, stock_item_id)` combinations in the locked baseline.

## SCD Fact-Assignment Rule

Where the source supplies an exact event timestamp, the fact joins to the dimension version valid at that timestamp. This applies to inventory movements and delivery events.

Where WWI exposes only a business date for the fact, the model deterministically assigns the dimension version valid at the end of that business day. This applies to order lines, sales lines, purchase-order lines, customer transactions, and supplier transactions. The rule is explicit because date-only source facts cannot resolve intraday SCD changes.

## Delivery Event Contract

`fact_delivery_event` is parsed directly from `ReturnedDeliveryData.Events`; it does not invent route or shipment events.

Audited baseline events:
- Ready for collection: 308,053
- DeliveryAttempt / Delivered: 277,276
- DeliveryAttempt / status absent: 30,733

The model preserves raw `event_type` and nullable `event_status`. `is_unconfirmed_attempt` is a deterministic flag for `DeliveryAttempt` rows whose source status is absent; it does not rewrite the source status text.

## Product-Stock-Group Bridge

`bridge_product_stock_group` represents the source many-to-many product/stock-group relationship. The source relationship is not temporal, so the bridge maps to the current semantic product version and is not presented as historical membership.

## Telemetry Boundary

Raw telemetry remains authoritative in SQL Server. The PostgreSQL analytical layer retains the five-minute telemetry aggregates and does not duplicate those aggregate rows into another `core` copy merely to rename the layer.

## Validation Contract

The warehouse model validation covers:
- deterministic surrogate-key uniqueness
- required dimension-key non-null checks
- dimension relationship tests
- semantic SCD current-row coverage
- no overlapping semantic SCD intervals
- conditional orphan-key checks
- source-to-core fact and bridge row-count parity
- source-to-core aggregate-measure parity
- customer semantic-SCD row-count parity
- source-backed delivery-event row-count parity