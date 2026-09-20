USE WideWorldImporters;
SELECT COUNT(*) AS total_products FROM Warehouse.StockItems;
SELECT TOP (30)
    StockItemID,
    StockItemName,
    SupplierID,
    Brand,
    Size,
    UnitPrice,
    RecommendedRetailPrice
FROM Warehouse.StockItems
ORDER BY StockItemID;

SELECT TOP (20)
    ol.OrderID,
    ol.StockItemID,
    si.StockItemName,
    ol.Quantity,
    ol.UnitPrice
FROM Sales.OrderLines ol
JOIN Warehouse.StockItems si ON si.StockItemID = ol.StockItemID
ORDER BY ol.OrderID DESC, ol.OrderLineID DESC;
