USE [WideWorldImporters];
SET NOCOUNT ON;

SELECT 'Sales.Orders' AS object_name, MIN(OrderDate) AS min_date, MAX(OrderDate) AS max_date, COUNT_BIG(*) AS rows_in_window
FROM Sales.Orders WHERE OrderDate >= '20160601'
UNION ALL
SELECT 'Sales.Invoices', MIN(InvoiceDate), MAX(InvoiceDate), COUNT_BIG(*)
FROM Sales.Invoices WHERE InvoiceDate >= '20160601'
UNION ALL
SELECT 'Sales.CustomerTransactions', MIN(TransactionDate), MAX(TransactionDate), COUNT_BIG(*)
FROM Sales.CustomerTransactions WHERE TransactionDate >= '20160601'
UNION ALL
SELECT 'Purchasing.PurchaseOrders', MIN(OrderDate), MAX(OrderDate), COUNT_BIG(*)
FROM Purchasing.PurchaseOrders WHERE OrderDate >= '20160601'
UNION ALL
SELECT 'Purchasing.SupplierTransactions', MIN(TransactionDate), MAX(TransactionDate), COUNT_BIG(*)
FROM Purchasing.SupplierTransactions WHERE TransactionDate >= '20160601'
UNION ALL
SELECT 'Warehouse.StockItemTransactions', MIN(CAST(TransactionOccurredWhen AS date)), MAX(CAST(TransactionOccurredWhen AS date)), COUNT_BIG(*)
FROM Warehouse.StockItemTransactions WHERE TransactionOccurredWhen >= '20160601'
UNION ALL
SELECT 'Warehouse.VehicleTemperatures', MIN(CAST(RecordedWhen AS date)), MAX(CAST(RecordedWhen AS date)), COUNT_BIG(*)
FROM Warehouse.VehicleTemperatures WHERE RecordedWhen >= '20160601'
ORDER BY object_name;

SELECT OrderDate, COUNT_BIG(*) AS orders
FROM Sales.Orders
WHERE OrderDate >= '20160601'
GROUP BY OrderDate
ORDER BY OrderDate;

SELECT
    (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2) AS temporal_current_tables,
    (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 1) AS temporal_history_tables,
    (SELECT COUNT(*) FROM sys.triggers WHERE is_ms_shipped = 0 AND name LIKE '%_DataLoad_Modify') AS leftover_dataload_triggers,
    (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled = 1) AS disabled_foreign_keys,
    (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_not_trusted = 1) AS untrusted_foreign_keys;
