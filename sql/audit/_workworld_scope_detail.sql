USE WideWorldImporters;
SET NOCOUNT ON;
PRINT '=== CORE_COLUMNS ===';
SELECT s.name AS schema_name,t.name AS table_name,c.column_id,c.name AS column_name,ty.name AS data_type
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE (s.name='Sales' AND t.name IN ('Orders','OrderLines','Invoices','InvoiceLines','CustomerTransactions','Customers','SpecialDeals'))
   OR (s.name='Purchasing' AND t.name IN ('PurchaseOrders','PurchaseOrderLines','SupplierTransactions','Suppliers'))
   OR (s.name='Warehouse' AND t.name IN ('StockItemHoldings','StockItemTransactions','StockItems'))
ORDER BY s.name,t.name,c.column_id;

PRINT '=== DELIVERY_METHOD_DISTRIBUTION ===';
SELECT dm.DeliveryMethodName, COUNT_BIG(*) invoices,
       SUM(CASE WHEN i.ConfirmedDeliveryTime IS NULL THEN 1 ELSE 0 END) unconfirmed
FROM Sales.Invoices i JOIN Application.DeliveryMethods dm ON dm.DeliveryMethodID=i.DeliveryMethodID
GROUP BY dm.DeliveryMethodName ORDER BY invoices DESC;

PRINT '=== DELIVERY_PERFORMANCE ===';
SELECT COUNT_BIG(*) AS linked_invoices,
       SUM(CASE WHEN i.ConfirmedDeliveryTime IS NOT NULL THEN 1 ELSE 0 END) confirmed,
       SUM(CASE WHEN i.ConfirmedDeliveryTime IS NOT NULL AND CAST(i.ConfirmedDeliveryTime AS date) <= o.ExpectedDeliveryDate THEN 1 ELSE 0 END) on_or_before_expected,
       SUM(CASE WHEN i.ConfirmedDeliveryTime IS NOT NULL AND CAST(i.ConfirmedDeliveryTime AS date) > o.ExpectedDeliveryDate THEN 1 ELSE 0 END) late,
       AVG(CASE WHEN i.ConfirmedDeliveryTime IS NOT NULL THEN CAST(DATEDIFF(minute,CAST(i.InvoiceDate AS datetime2),i.ConfirmedDeliveryTime) AS float)/1440.0 END) avg_invoice_to_confirmed_days
FROM Sales.Invoices i JOIN Sales.Orders o ON o.OrderID=i.OrderID;

PRINT '=== ORDER_LIFECYCLE ===';
SELECT COUNT_BIG(*) orders,
       SUM(CASE WHEN PickingCompletedWhen IS NULL THEN 1 ELSE 0 END) not_picked,
       SUM(CASE WHEN BackorderOrderID IS NOT NULL THEN 1 ELSE 0 END) backorder_followups,
       AVG(CASE WHEN PickingCompletedWhen IS NOT NULL THEN CAST(DATEDIFF(minute,CAST(OrderDate AS datetime2),PickingCompletedWhen) AS float)/1440.0 END) avg_order_to_pick_days
FROM Sales.Orders;
SELECT SUM(CASE WHEN PickingCompletedWhen IS NULL THEN 1 ELSE 0 END) open_lines,
       SUM(CASE WHEN PickingCompletedWhen IS NOT NULL THEN 1 ELSE 0 END) picked_lines,
       SUM(CASE WHEN Quantity>0 THEN Quantity ELSE 0 END) qty_ordered
FROM Sales.OrderLines;

PRINT '=== PROCUREMENT_PERFORMANCE ===';
SELECT COUNT_BIG(*) AS po_lines,
       SUM(CASE WHEN pol.LastReceiptDate IS NOT NULL THEN 1 ELSE 0 END) received_lines,
       SUM(CASE WHEN pol.LastReceiptDate IS NOT NULL AND pol.LastReceiptDate <= po.ExpectedDeliveryDate THEN 1 ELSE 0 END) received_on_or_before_expected,
       SUM(CASE WHEN pol.LastReceiptDate IS NOT NULL AND pol.LastReceiptDate > po.ExpectedDeliveryDate THEN 1 ELSE 0 END) received_late,
       SUM(CASE WHEN pol.ReceivedOuters < pol.OrderedOuters THEN 1 ELSE 0 END) under_received_lines,
       SUM(CASE WHEN pol.ReceivedOuters > pol.OrderedOuters THEN 1 ELSE 0 END) over_received_lines,
       AVG(CASE WHEN pol.LastReceiptDate IS NOT NULL THEN CAST(DATEDIFF(day,po.OrderDate,pol.LastReceiptDate) AS float) END) avg_po_to_last_receipt_days
FROM Purchasing.PurchaseOrderLines pol JOIN Purchasing.PurchaseOrders po ON po.PurchaseOrderID=pol.PurchaseOrderID;
SELECT s.SupplierID,s.SupplierName,COUNT(DISTINCT po.PurchaseOrderID) AS purchase_orders,
       SUM(CASE WHEN pol.LastReceiptDate IS NOT NULL AND pol.LastReceiptDate > po.ExpectedDeliveryDate THEN 1 ELSE 0 END) late_lines,
       SUM(CASE WHEN pol.ReceivedOuters < pol.OrderedOuters THEN 1 ELSE 0 END) under_received_lines
FROM Purchasing.Suppliers s
LEFT JOIN Purchasing.PurchaseOrders po ON po.SupplierID=s.SupplierID
LEFT JOIN Purchasing.PurchaseOrderLines pol ON pol.PurchaseOrderID=po.PurchaseOrderID
GROUP BY s.SupplierID,s.SupplierName ORDER BY purchase_orders DESC;

PRINT '=== INVENTORY_HEALTH ===';
SELECT COUNT(*) stock_items,
       SUM(CASE WHEN QuantityOnHand<=ReorderLevel THEN 1 ELSE 0 END) at_or_below_reorder,
       SUM(CASE WHEN QuantityOnHand<TargetStockLevel THEN 1 ELSE 0 END) below_target,
       SUM(CASE WHEN QuantityOnHand>TargetStockLevel THEN 1 ELSE 0 END) above_target,
       SUM(CASE WHEN QuantityOnHand=0 THEN 1 ELSE 0 END) zero_stock,
       SUM(CAST(QuantityOnHand AS bigint)) total_units_on_hand,
       SUM(CAST(QuantityOnHand AS decimal(19,2))*LastCostPrice) inventory_cost_value
FROM Warehouse.StockItemHoldings;
SELECT TOP 15 si.StockItemID,si.StockItemName,h.QuantityOnHand,h.ReorderLevel,h.TargetStockLevel,h.LastCostPrice,h.BinLocation
FROM Warehouse.StockItemHoldings h JOIN Warehouse.StockItems si ON si.StockItemID=h.StockItemID
ORDER BY (h.QuantityOnHand-h.ReorderLevel) ASC;

PRINT '=== FINANCIAL_EXPOSURE ===';
SELECT COUNT_BIG(*) customer_transactions,
       SUM(OutstandingBalance) customer_outstanding_balance,
       SUM(CASE WHEN OutstandingBalance<>0 THEN 1 ELSE 0 END) customer_open_tx
FROM Sales.CustomerTransactions;
SELECT COUNT_BIG(*) supplier_transactions,
       SUM(OutstandingBalance) supplier_outstanding_balance,
       SUM(CASE WHEN OutstandingBalance<>0 THEN 1 ELSE 0 END) supplier_open_tx
FROM Purchasing.SupplierTransactions;

PRINT '=== PRODUCT_CUSTOMER_COVERAGE ===';
SELECT COUNT(*) products, COUNT(DISTINCT SupplierID) product_suppliers, COUNT(DISTINCT ColorID) colors FROM Warehouse.StockItems;
SELECT cc.CustomerCategoryName,COUNT(*) customers FROM Sales.Customers c JOIN Sales.CustomerCategories cc ON cc.CustomerCategoryID=c.CustomerCategoryID GROUP BY cc.CustomerCategoryName ORDER BY customers DESC;
SELECT sg.StockGroupName,COUNT(DISTINCT sisg.StockItemID) products FROM Warehouse.StockItemStockGroups sisg JOIN Warehouse.StockGroups sg ON sg.StockGroupID=sisg.StockGroupID GROUP BY sg.StockGroupName ORDER BY products DESC;

PRINT '=== TELEMETRY_INTERVALS ===';
WITH x AS (
 SELECT ColdRoomSensorNumber,RecordedWhen,LAG(RecordedWhen) OVER(PARTITION BY ColdRoomSensorNumber ORDER BY RecordedWhen) prev
 FROM Warehouse.ColdRoomTemperatures_Archive WHERE RecordedWhen>='2026-09-01'
)
SELECT ColdRoomSensorNumber,COUNT(*) readings,
       AVG(CAST(DATEDIFF(second,prev,RecordedWhen) AS float)) avg_gap_seconds,
       MAX(DATEDIFF(second,prev,RecordedWhen)) max_gap_seconds
FROM x WHERE prev IS NOT NULL GROUP BY ColdRoomSensorNumber ORDER BY ColdRoomSensorNumber;
WITH x AS (
 SELECT VehicleRegistration,ChillerSensorNumber,RecordedWhen,LAG(RecordedWhen) OVER(PARTITION BY VehicleRegistration,ChillerSensorNumber ORDER BY RecordedWhen) prev
 FROM Warehouse.VehicleTemperatures WHERE RecordedWhen>='2026-09-01'
)
SELECT VehicleRegistration,ChillerSensorNumber,COUNT(*) readings,
       AVG(CAST(DATEDIFF(second,prev,RecordedWhen) AS float)) avg_gap_seconds,
       MAX(DATEDIFF(second,prev,RecordedWhen)) max_gap_seconds
FROM x WHERE prev IS NOT NULL GROUP BY VehicleRegistration,ChillerSensorNumber ORDER BY VehicleRegistration,ChillerSensorNumber;
