USE WideWorldImporters;
SET NOCOUNT ON;

PRINT '=== FINAL_SOURCE_STATE ===';
SELECT SYSDATETIME() AS captured_at,
       MAX(OrderDate) AS max_order_date,
       COUNT_BIG(*) AS total_orders
FROM Sales.Orders;

PRINT '=== TOTAL_USER_TABLE_ROWS ===';
;WITH rc AS (
    SELECT t.object_id,
           SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS row_count
    FROM sys.tables t
    JOIN sys.partitions p ON p.object_id=t.object_id
    GROUP BY t.object_id
)
SELECT SUM(row_count) AS total_user_table_rows FROM rc;

PRINT '=== ROWS_BY_SCHEMA ===';
SELECT s.name AS schema_name,
       SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS rows
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.partitions p ON p.object_id=t.object_id
GROUP BY s.name
ORDER BY rows DESC;

PRINT '=== CORE_DATE_RANGES ===';
SELECT 'Sales.Orders' AS table_name, MIN(OrderDate) AS min_date, MAX(OrderDate) AS max_date, COUNT_BIG(*) AS rows FROM Sales.Orders
UNION ALL SELECT 'Sales.Invoices', MIN(InvoiceDate), MAX(InvoiceDate), COUNT_BIG(*) FROM Sales.Invoices
UNION ALL SELECT 'Purchasing.PurchaseOrders', MIN(OrderDate), MAX(OrderDate), COUNT_BIG(*) FROM Purchasing.PurchaseOrders
UNION ALL SELECT 'Warehouse.StockItemTransactions', MIN(TransactionOccurredWhen), MAX(TransactionOccurredWhen), COUNT_BIG(*) FROM Warehouse.StockItemTransactions;

PRINT '=== CONSTRAINT_STATE ===';
SELECT (SELECT COUNT(*) FROM sys.key_constraints WHERE type='PK') AS pk_count,
       (SELECT COUNT(*) FROM sys.foreign_keys) AS fk_count,
       (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1) AS bad_fk_count,
       (SELECT COUNT(*) FROM sys.tables WHERE temporal_type=2) AS temporal_current_tables,
       (SELECT COUNT(*) FROM sys.tables WHERE temporal_type=1) AS temporal_history_tables,
       (SELECT COUNT(*) FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%') AS simulation_triggers;

PRINT '=== DATABASE_SIZE_MB ===';
SELECT name, type_desc,
       CAST(size*8.0/1024 AS decimal(18,2)) AS allocated_mb,
       CASE WHEN type_desc='ROWS' THEN CAST(FILEPROPERTY(name,'SpaceUsed')*8.0/1024 AS decimal(18,2)) END AS used_mb
FROM sys.database_files
ORDER BY file_id;

PRINT '=== TOP_TABLES_BY_ROWS ===';
SELECT TOP (15)
       s.name + '.' + t.name AS table_name,
       SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS rows
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.partitions p ON p.object_id=t.object_id
GROUP BY s.name,t.name
ORDER BY rows DESC;
