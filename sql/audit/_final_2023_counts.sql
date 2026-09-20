USE WideWorldImporters_Distribution;
SET NOCOUNT ON;
DECLARE @cutoff date='2023-01-01';
SELECT 'Sales.Orders' table_name, COUNT_BIG(*) total_rows, SUM(CASE WHEN OrderDate>=@cutoff THEN 1 ELSE 0 END) keep_2023plus FROM Sales.Orders
UNION ALL SELECT 'Sales.OrderLines', COUNT_BIG(*), SUM(CASE WHEN o.OrderDate>=@cutoff THEN 1 ELSE 0 END) FROM Sales.OrderLines l JOIN Sales.Orders o ON o.OrderID=l.OrderID
UNION ALL SELECT 'Sales.Invoices', COUNT_BIG(*), SUM(CASE WHEN InvoiceDate>=@cutoff THEN 1 ELSE 0 END) FROM Sales.Invoices
UNION ALL SELECT 'Sales.InvoiceLines', COUNT_BIG(*), SUM(CASE WHEN i.InvoiceDate>=@cutoff THEN 1 ELSE 0 END) FROM Sales.InvoiceLines l JOIN Sales.Invoices i ON i.InvoiceID=l.InvoiceID
UNION ALL SELECT 'Sales.CustomerTransactions', COUNT_BIG(*), SUM(CASE WHEN TransactionDate>=@cutoff THEN 1 ELSE 0 END) FROM Sales.CustomerTransactions
UNION ALL SELECT 'Purchasing.PurchaseOrders', COUNT_BIG(*), SUM(CASE WHEN OrderDate>=@cutoff THEN 1 ELSE 0 END) FROM Purchasing.PurchaseOrders
UNION ALL SELECT 'Purchasing.PurchaseOrderLines', COUNT_BIG(*), SUM(CASE WHEN p.OrderDate>=@cutoff THEN 1 ELSE 0 END) FROM Purchasing.PurchaseOrderLines l JOIN Purchasing.PurchaseOrders p ON p.PurchaseOrderID=l.PurchaseOrderID
UNION ALL SELECT 'Purchasing.SupplierTransactions', COUNT_BIG(*), SUM(CASE WHEN TransactionDate>=@cutoff THEN 1 ELSE 0 END) FROM Purchasing.SupplierTransactions
UNION ALL SELECT 'Warehouse.StockItemTransactions', COUNT_BIG(*), SUM(CASE WHEN TransactionOccurredWhen>=@cutoff THEN 1 ELSE 0 END) FROM Warehouse.StockItemTransactions
UNION ALL SELECT 'Warehouse.VehicleTemperatures', COUNT_BIG(*), SUM(CASE WHEN RecordedWhen>=@cutoff THEN 1 ELSE 0 END) FROM Warehouse.VehicleTemperatures
UNION ALL SELECT 'Warehouse.ColdRoomTemperatures_Archive', COUNT_BIG(*), SUM(CASE WHEN RecordedWhen>=@cutoff THEN 1 ELSE 0 END) FROM Warehouse.ColdRoomTemperatures_Archive;
