USE [WideWorldImporters];
GO
SET NOCOUNT ON;
DECLARE @targets TABLE(schema_name sysname, table_name sysname);
INSERT @targets VALUES
(N'Sales',N'Orders'),(N'Sales',N'Invoices'),(N'Sales',N'Customers'),
(N'Purchasing',N'PurchaseOrders'),(N'Purchasing',N'Suppliers'),
(N'Warehouse',N'StockItems'),(N'Warehouse',N'StockItemHoldings'),(N'Warehouse',N'StockItemStockGroups'),
(N'Warehouse',N'StockGroups'),(N'Warehouse',N'PackageTypes'),
(N'Application',N'People'),(N'Application',N'Cities'),(N'Application',N'StateProvinces'),(N'Application',N'Countries'),
(N'Application',N'DeliveryMethods'),(N'Application',N'TransactionTypes');
SELECT s.name AS schema_name,t.name AS table_name,c.column_id,c.name AS column_name,ty.name AS data_type,c.max_length,c.precision,c.scale,c.is_nullable
FROM @targets x
JOIN sys.schemas s ON s.name=x.schema_name
JOIN sys.tables t ON t.schema_id=s.schema_id AND t.name=x.table_name
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
ORDER BY s.name,t.name,c.column_id;

SELECT COUNT(*) AS customers_total,
       SUM(CASE WHEN BuyingGroupID IS NULL THEN 1 ELSE 0 END) AS customers_without_buying_group,
       SUM(CASE WHEN BuyingGroupID IS NOT NULL THEN 1 ELSE 0 END) AS customers_with_buying_group
FROM Sales.Customers;
GO