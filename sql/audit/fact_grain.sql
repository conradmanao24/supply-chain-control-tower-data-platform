USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SELECT 'OrderLines' AS dataset,
       COUNT_BIG(*) AS rows_total,
       COUNT_BIG(*) - COUNT_BIG(DISTINCT CONCAT(OrderID, ':', StockItemID)) AS duplicate_composite_rows
FROM Sales.OrderLines
UNION ALL
SELECT 'InvoiceLines', COUNT_BIG(*), COUNT_BIG(*) - COUNT_BIG(DISTINCT CONCAT(InvoiceID, ':', StockItemID))
FROM Sales.InvoiceLines
UNION ALL
SELECT 'PurchaseOrderLines', COUNT_BIG(*), COUNT_BIG(*) - COUNT_BIG(DISTINCT CONCAT(PurchaseOrderID, ':', StockItemID))
FROM Purchasing.PurchaseOrderLines;

SELECT COUNT_BIG(*) AS customer_transactions FROM Sales.CustomerTransactions;
SELECT COUNT_BIG(*) AS supplier_transactions FROM Purchasing.SupplierTransactions;
GO