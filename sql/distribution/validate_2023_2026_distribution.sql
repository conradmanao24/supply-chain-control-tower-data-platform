SET NOCOUNT ON;

USE WideWorldImporters;
PRINT '=== ORIGINAL_SOURCE_GUARD ===';
SELECT MAX(OrderDate) AS max_order_date, COUNT_BIG(*) AS orders FROM Sales.Orders;
;WITH rc AS (
 SELECT t.object_id,SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS row_count
 FROM sys.tables t JOIN sys.partitions p ON p.object_id=t.object_id GROUP BY t.object_id
)
SELECT SUM(row_count) AS total_user_table_rows FROM rc;

USE WideWorldImporters_Distribution;
PRINT '=== DISTRIBUTION_CORE_COUNTS ===';
SELECT 'Sales.Orders' AS table_name, COUNT_BIG(*) AS rows, MIN(OrderDate) AS min_date, MAX(OrderDate) AS max_date FROM Sales.Orders
UNION ALL SELECT 'Sales.Invoices', COUNT_BIG(*), MIN(InvoiceDate), MAX(InvoiceDate) FROM Sales.Invoices
UNION ALL SELECT 'Sales.CustomerTransactions', COUNT_BIG(*), MIN(TransactionDate), MAX(TransactionDate) FROM Sales.CustomerTransactions
UNION ALL SELECT 'Purchasing.PurchaseOrders', COUNT_BIG(*), MIN(OrderDate), MAX(OrderDate) FROM Purchasing.PurchaseOrders
UNION ALL SELECT 'Purchasing.SupplierTransactions', COUNT_BIG(*), MIN(TransactionDate), MAX(TransactionDate) FROM Purchasing.SupplierTransactions
UNION ALL SELECT 'Warehouse.StockItemTransactions', COUNT_BIG(*), MIN(TransactionOccurredWhen), MAX(TransactionOccurredWhen) FROM Warehouse.StockItemTransactions
UNION ALL SELECT 'Warehouse.VehicleTemperatures', COUNT_BIG(*), MIN(RecordedWhen), MAX(RecordedWhen) FROM Warehouse.VehicleTemperatures
UNION ALL SELECT 'Warehouse.ColdRoomTemperatures_Archive', COUNT_BIG(*), MIN(RecordedWhen), MAX(RecordedWhen) FROM Warehouse.ColdRoomTemperatures_Archive;

PRINT '=== REFERENTIAL_CLOSURE_EXCEPTIONS ===';
SELECT COUNT_BIG(*) AS pre2023_orders_retained FROM Sales.Orders WHERE OrderDate<'2023-01-01';
SELECT COUNT_BIG(*) AS pre2023_pos_retained FROM Purchasing.PurchaseOrders WHERE OrderDate<'2023-01-01';
SELECT COUNT_BIG(*) AS pre2023_invoices_retained FROM Sales.Invoices WHERE InvoiceDate<'2023-01-01';
SELECT COUNT_BIG(*) AS coldroom_boundary_rows FROM Warehouse.ColdRoomTemperatures_Archive WHERE RecordedWhen<'2023-01-01' AND ValidTo>='2023-01-01';

PRINT '=== CONSTRAINT_TEMPORAL_STATE ===';
SELECT (SELECT COUNT(*) FROM sys.foreign_keys) AS fk_count,
       (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1) AS bad_fk_count,
       (SELECT COUNT(*) FROM sys.tables WHERE temporal_type=2) AS temporal_current_tables,
       (SELECT COUNT(*) FROM sys.tables WHERE temporal_type=1) AS temporal_history_tables,
       (SELECT COUNT(*) FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%') AS simulation_triggers;

PRINT '=== DISTRIBUTION_TOTAL_ROWS ===';
;WITH rc AS (
 SELECT t.object_id,SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS row_count
 FROM sys.tables t JOIN sys.partitions p ON p.object_id=t.object_id GROUP BY t.object_id
)
SELECT SUM(row_count) AS total_user_table_rows FROM rc;

PRINT '=== DATABASE_SIZE_MB ===';
SELECT name,type_desc,CAST(size*8.0/1024 AS decimal(18,2)) AS allocated_mb,
       CASE WHEN type_desc='ROWS' THEN CAST(FILEPROPERTY(name,'SpaceUsed')*8.0/1024 AS decimal(18,2)) END AS used_mb
FROM sys.database_files ORDER BY file_id;

PRINT '=== CHECK_CONSTRAINTS ===';
DBCC CHECKCONSTRAINTS WITH ALL_CONSTRAINTS;
PRINT '=== CHECKDB_PHYSICAL_ONLY ===';
DBCC CHECKDB (N'WideWorldImporters_Distribution') WITH PHYSICAL_ONLY, NO_INFOMSGS;
