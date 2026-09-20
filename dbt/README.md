# dbt Warehouse Project

This dbt project transforms the reconciled PostgreSQL `staging` schema into the business-facing `core` warehouse.

Implemented models include:

- 9 dimensions
- 7 explicit-grain facts
- 1 product-to-stock-group bridge
- business-attribute-driven SCD logic
- source-to-core count and measure reconciliation
- SCD overlap/current-coverage/orphan-key checks

The latest recorded dbt validation contains **116 data tests**.

See `docs/architecture/warehouse-model-contract.md` and `docs/evidence/warehouse/warehouse-modeling.md` from the repository root.
