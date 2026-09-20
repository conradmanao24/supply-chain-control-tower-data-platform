USE WideWorldImporters;
SET NOCOUNT ON;
PRINT '=== FINAL_TABLE_COUNTS ===';
SELECT 'Application.People' table_name, COUNT_BIG(*) rows FROM Application.People UNION ALL
SELECT 'Application.Cities', COUNT_BIG(*) FROM Application.Cities UNION ALL
SELECT 'Sales.Customers', COUNT_BIG(*) FROM Sales.Customers UNION ALL
SELECT 'Warehouse.StockItems', COUNT_BIG(*) FROM Warehouse.StockItems UNION ALL
SELECT 'Purchasing.Suppliers', COUNT_BIG(*) FROM Purchasing.Suppliers UNION ALL
SELECT 'Sales.Orders', COUNT_BIG(*) FROM Sales.Orders UNION ALL
SELECT 'Sales.OrderLines', COUNT_BIG(*) FROM Sales.OrderLines UNION ALL
SELECT 'Sales.Invoices', COUNT_BIG(*) FROM Sales.Invoices UNION ALL
SELECT 'Sales.InvoiceLines', COUNT_BIG(*) FROM Sales.InvoiceLines UNION ALL
SELECT 'Sales.CustomerTransactions', COUNT_BIG(*) FROM Sales.CustomerTransactions UNION ALL
SELECT 'Purchasing.PurchaseOrders', COUNT_BIG(*) FROM Purchasing.PurchaseOrders UNION ALL
SELECT 'Purchasing.PurchaseOrderLines', COUNT_BIG(*) FROM Purchasing.PurchaseOrderLines UNION ALL
SELECT 'Purchasing.SupplierTransactions', COUNT_BIG(*) FROM Purchasing.SupplierTransactions UNION ALL
SELECT 'Warehouse.StockItemTransactions', COUNT_BIG(*) FROM Warehouse.StockItemTransactions UNION ALL
SELECT 'Warehouse.VehicleTemperatures', COUNT_BIG(*) FROM Warehouse.VehicleTemperatures UNION ALL
SELECT 'Warehouse.ColdRoomTemperatures_Archive', COUNT_BIG(*) FROM Warehouse.ColdRoomTemperatures_Archive;

PRINT '=== FINAL_DATE_RANGES ===';
SELECT 'Sales.Orders' table_name, MIN(OrderDate) min_date, MAX(OrderDate) max_date FROM Sales.Orders UNION ALL
SELECT 'Sales.Invoices', MIN(InvoiceDate), MAX(InvoiceDate) FROM Sales.Invoices UNION ALL
SELECT 'Sales.CustomerTransactions', MIN(TransactionDate), MAX(TransactionDate) FROM Sales.CustomerTransactions UNION ALL
SELECT 'Purchasing.PurchaseOrders', MIN(OrderDate), MAX(OrderDate) FROM Purchasing.PurchaseOrders UNION ALL
SELECT 'Purchasing.SupplierTransactions', MIN(TransactionDate), MAX(TransactionDate) FROM Purchasing.SupplierTransactions UNION ALL
SELECT 'Warehouse.StockItemTransactions', MIN(TransactionOccurredWhen), MAX(TransactionOccurredWhen) FROM Warehouse.StockItemTransactions UNION ALL
SELECT 'Warehouse.VehicleTemperatures', MIN(RecordedWhen), MAX(RecordedWhen) FROM Warehouse.VehicleTemperatures UNION ALL
SELECT 'Warehouse.ColdRoomTemperatures_Archive', MIN(RecordedWhen), MAX(RecordedWhen) FROM Warehouse.ColdRoomTemperatures_Archive;

PRINT '=== YEARLY_BUSINESS_COUNTS ===';
WITH y AS (
 SELECT YEAR(OrderDate) yr, COUNT_BIG(*) orders, 0 invoices, 0 purchase_orders FROM Sales.Orders GROUP BY YEAR(OrderDate)
 UNION ALL SELECT YEAR(InvoiceDate),0,COUNT_BIG(*),0 FROM Sales.Invoices GROUP BY YEAR(InvoiceDate)
 UNION ALL SELECT YEAR(OrderDate),0,0,COUNT_BIG(*) FROM Purchasing.PurchaseOrders GROUP BY YEAR(OrderDate)
)
SELECT yr, SUM(orders) orders, SUM(invoices) invoices, SUM(purchase_orders) purchase_orders FROM y GROUP BY yr ORDER BY yr;

PRINT '=== FINAL_HEALTH ===';
SELECT (SELECT COUNT(*) FROM sys.foreign_keys) fk_count,
       (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1) bad_fk_count,
       (SELECT COUNT(*) FROM sys.tables WHERE temporal_type=2) temporal_current_tables,
       (SELECT COUNT(*) FROM sys.tables WHERE temporal_type=1) temporal_history_tables,
       (SELECT COUNT(*) FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%') simulation_triggers;

PRINT '=== FINAL_DB_SIZE ===';
SELECT name,type_desc,CAST(size*8.0/1024 AS decimal(18,2)) allocated_mb FROM sys.database_files ORDER BY file_id;
