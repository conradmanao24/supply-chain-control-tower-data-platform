USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SELECT 'CustomerCategories' AS object_name, COUNT(*) AS ids_with_name_change
FROM (SELECT CustomerCategoryID FROM Sales.CustomerCategories FOR SYSTEM_TIME ALL GROUP BY CustomerCategoryID HAVING COUNT(DISTINCT CustomerCategoryName)>1) x
UNION ALL
SELECT 'BuyingGroups', COUNT(*)
FROM (SELECT BuyingGroupID FROM Sales.BuyingGroups FOR SYSTEM_TIME ALL GROUP BY BuyingGroupID HAVING COUNT(DISTINCT BuyingGroupName)>1) x
UNION ALL
SELECT 'SupplierCategories', COUNT(*)
FROM (SELECT SupplierCategoryID FROM Purchasing.SupplierCategories FOR SYSTEM_TIME ALL GROUP BY SupplierCategoryID HAVING COUNT(DISTINCT SupplierCategoryName)>1) x;
GO
