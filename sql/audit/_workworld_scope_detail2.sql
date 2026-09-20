USE WideWorldImporters;
SET NOCOUNT ON;
PRINT '=== OPEN_ORDER_AGING ===';
SELECT YEAR(OrderDate) yr, COUNT_BIG(*) open_orders, MIN(OrderDate) oldest, MAX(OrderDate) newest
FROM Sales.Orders WHERE PickingCompletedWhen IS NULL GROUP BY YEAR(OrderDate) ORDER BY yr;
SELECT TOP 15 DATEDIFF(day,OrderDate,'2026-09-15') age_days, OrderID,CustomerID,OrderDate,ExpectedDeliveryDate,BackorderOrderID
FROM Sales.Orders WHERE PickingCompletedWhen IS NULL ORDER BY age_days DESC;

PRINT '=== STOCK_MOVEMENT_TYPES ===';
SELECT tt.TransactionTypeName,COUNT_BIG(*) tx_count,SUM(sit.Quantity) net_quantity,SUM(ABS(sit.Quantity)) gross_quantity
FROM Warehouse.StockItemTransactions sit JOIN Application.TransactionTypes tt ON tt.TransactionTypeID=sit.TransactionTypeID
GROUP BY tt.TransactionTypeName ORDER BY tx_count DESC;

PRINT '=== CUSTOMER_TX_TYPES ===';
SELECT tt.TransactionTypeName,COUNT_BIG(*) tx_count,SUM(ct.TransactionAmount) amount,SUM(ct.OutstandingBalance) outstanding
FROM Sales.CustomerTransactions ct JOIN Application.TransactionTypes tt ON tt.TransactionTypeID=ct.TransactionTypeID
GROUP BY tt.TransactionTypeName ORDER BY tx_count DESC;

PRINT '=== SUPPLIER_TX_TYPES ===';
SELECT tt.TransactionTypeName,COUNT_BIG(*) tx_count,SUM(st.TransactionAmount) amount,SUM(st.OutstandingBalance) outstanding
FROM Purchasing.SupplierTransactions st JOIN Application.TransactionTypes tt ON tt.TransactionTypeID=st.TransactionTypeID
GROUP BY tt.TransactionTypeName ORDER BY tx_count DESC;

PRINT '=== SALES_TERRITORY ===';
SELECT sp.SalesTerritory,COUNT(DISTINCT c.CustomerID) customers,COUNT_BIG(DISTINCT o.OrderID) orders,SUM(ol.Quantity*ol.UnitPrice) order_value
FROM Sales.Customers c
JOIN Application.Cities ci ON ci.CityID=c.DeliveryCityID
JOIN Application.StateProvinces sp ON sp.StateProvinceID=ci.StateProvinceID
LEFT JOIN Sales.Orders o ON o.CustomerID=c.CustomerID
LEFT JOIN Sales.OrderLines ol ON ol.OrderID=o.OrderID
GROUP BY sp.SalesTerritory ORDER BY order_value DESC;

PRINT '=== PRODUCT_GROUP_DEMAND ===';
SELECT sg.StockGroupName,COUNT(DISTINCT sisg.StockItemID) products,SUM(ol.Quantity) qty_ordered,SUM(ol.Quantity*ol.UnitPrice) order_value
FROM Warehouse.StockGroups sg
JOIN Warehouse.StockItemStockGroups sisg ON sisg.StockGroupID=sg.StockGroupID
JOIN Sales.OrderLines ol ON ol.StockItemID=sisg.StockItemID
GROUP BY sg.StockGroupName ORDER BY order_value DESC;

PRINT '=== SENSOR_VARIABILITY_SEP2026 ===';
SELECT ColdRoomSensorNumber,COUNT_BIG(*) readings,AVG(CAST(Temperature AS float)) avg_temp,STDEV(CAST(Temperature AS float)) stdev_temp,MIN(Temperature) min_temp,MAX(Temperature) max_temp
FROM Warehouse.ColdRoomTemperatures_Archive WHERE RecordedWhen>='2026-09-01' GROUP BY ColdRoomSensorNumber ORDER BY ColdRoomSensorNumber;
SELECT VehicleRegistration,ChillerSensorNumber,COUNT_BIG(*) readings,AVG(CAST(Temperature AS float)) avg_temp,STDEV(CAST(Temperature AS float)) stdev_temp,MIN(Temperature) min_temp,MAX(Temperature) max_temp
FROM Warehouse.VehicleTemperatures WHERE RecordedWhen>='2026-09-01' GROUP BY VehicleRegistration,ChillerSensorNumber ORDER BY VehicleRegistration,ChillerSensorNumber;
