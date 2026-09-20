USE WideWorldImporters_Distribution;
SET NOCOUNT ON;
DECLARE @cutoff date='2023-01-01';
SELECT
 (SELECT COUNT_BIG(*) FROM Sales.Invoices i JOIN Sales.Orders o ON o.OrderID=i.OrderID WHERE i.InvoiceDate>=@cutoff AND o.OrderDate<@cutoff) AS invoice_to_old_order,
 (SELECT COUNT_BIG(*) FROM Sales.CustomerTransactions ct JOIN Sales.Invoices i ON i.InvoiceID=ct.InvoiceID WHERE ct.TransactionDate>=@cutoff AND i.InvoiceDate<@cutoff) AS customer_tx_to_old_invoice,
 (SELECT COUNT_BIG(*) FROM Warehouse.StockItemTransactions st JOIN Sales.Invoices i ON i.InvoiceID=st.InvoiceID WHERE st.TransactionOccurredWhen>=@cutoff AND i.InvoiceDate<@cutoff) AS stock_tx_to_old_invoice,
 (SELECT COUNT_BIG(*) FROM Warehouse.StockItemTransactions st JOIN Purchasing.PurchaseOrders po ON po.PurchaseOrderID=st.PurchaseOrderID WHERE st.TransactionOccurredWhen>=@cutoff AND po.OrderDate<@cutoff) AS stock_tx_to_old_po,
 (SELECT COUNT_BIG(*) FROM Purchasing.SupplierTransactions st JOIN Purchasing.PurchaseOrders po ON po.PurchaseOrderID=st.PurchaseOrderID WHERE st.TransactionDate>=@cutoff AND po.OrderDate<@cutoff) AS supplier_tx_to_old_po,
 (SELECT COUNT_BIG(*) FROM Sales.Orders o JOIN Sales.Orders bo ON bo.OrderID=o.BackorderOrderID WHERE o.OrderDate>=@cutoff AND bo.OrderDate<@cutoff) AS order_to_old_backorder;

SELECT MIN(o.OrderDate) AS earliest_old_order, MAX(o.OrderDate) AS latest_old_order, COUNT(DISTINCT o.OrderID) AS old_orders_needed
FROM Sales.Invoices i JOIN Sales.Orders o ON o.OrderID=i.OrderID
WHERE i.InvoiceDate>=@cutoff AND o.OrderDate<@cutoff;

SELECT MIN(po.OrderDate) AS earliest_old_po, MAX(po.OrderDate) AS latest_old_po, COUNT(DISTINCT po.PurchaseOrderID) AS old_pos_needed
FROM Purchasing.PurchaseOrders po
WHERE po.OrderDate<@cutoff AND po.PurchaseOrderID IN (
 SELECT PurchaseOrderID FROM Warehouse.StockItemTransactions WHERE TransactionOccurredWhen>=@cutoff AND PurchaseOrderID IS NOT NULL
 UNION
 SELECT PurchaseOrderID FROM Purchasing.SupplierTransactions WHERE TransactionDate>=@cutoff AND PurchaseOrderID IS NOT NULL
);
