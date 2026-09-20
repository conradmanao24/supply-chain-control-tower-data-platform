USE WideWorldImporters_Distribution;
SET NOCOUNT ON;
SELECT COUNT_BIG(*) AS orders, MIN(OrderDate) min_order, MAX(OrderDate) max_order FROM Sales.Orders;
SELECT COUNT_BIG(*) AS invoices, MIN(InvoiceDate) min_invoice, MAX(InvoiceDate) max_invoice FROM Sales.Invoices;
SELECT COUNT_BIG(*) AS stock_tx, MIN(TransactionOccurredWhen) min_stock, MAX(TransactionOccurredWhen) max_stock FROM Warehouse.StockItemTransactions;
SELECT COUNT_BIG(*) AS vehicle_rows, MIN(RecordedWhen) min_vehicle, MAX(RecordedWhen) max_vehicle FROM Warehouse.VehicleTemperatures;
SELECT COUNT_BIG(*) AS cold_rows, MIN(RecordedWhen) min_cold, MAX(RecordedWhen) max_cold FROM Warehouse.ColdRoomTemperatures_Archive;
SELECT s.name,t.name,t.temporal_type_desc,OBJECT_SCHEMA_NAME(t.history_table_id) history_schema,OBJECT_NAME(t.history_table_id) history_table
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE s.name='Warehouse' AND t.name IN ('ColdRoomTemperatures','ColdRoomTemperatures_Archive');
SELECT COUNT(*) bad_fks FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1;
