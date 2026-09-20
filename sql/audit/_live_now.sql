USE WideWorldImporters;
SELECT SYSDATETIME() AS db_now, MAX(OrderDate) AS max_order_date, COUNT_BIG(*) AS orders FROM Sales.Orders;
SELECT DATEDIFF(day, MAX(OrderDate), CAST('2026-09-15' AS date)) AS days_remaining FROM Sales.Orders;
SELECT COUNT_BIG(*) AS total_rows FROM (
 SELECT 1 AS x FROM Sales.Orders
 UNION ALL SELECT 1 FROM Sales.OrderLines
 UNION ALL SELECT 1 FROM Sales.Invoices
 UNION ALL SELECT 1 FROM Sales.InvoiceLines
 UNION ALL SELECT 1 FROM Sales.CustomerTransactions
 UNION ALL SELECT 1 FROM Warehouse.StockItemTransactions
 UNION ALL SELECT 1 FROM Warehouse.VehicleTemperatures
 UNION ALL SELECT 1 FROM Warehouse.ColdRoomTemperatures_Archive
 UNION ALL SELECT 1 FROM Purchasing.PurchaseOrders
 UNION ALL SELECT 1 FROM Purchasing.PurchaseOrderLines
 UNION ALL SELECT 1 FROM Purchasing.SupplierTransactions
) t;
SELECT COUNT(*) AS temporal_current_tables FROM sys.tables WHERE temporal_type=2;
SELECT COUNT(*) AS simulation_triggers FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%';
SELECT COUNT(*) AS bad_fks FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1;
