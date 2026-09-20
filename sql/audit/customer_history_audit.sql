USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SELECT COUNT(*) AS customers_with_name_change
FROM (
    SELECT CustomerID
    FROM Sales.Customers FOR SYSTEM_TIME ALL
    GROUP BY CustomerID
    HAVING COUNT(DISTINCT CustomerName) > 1
) x;
SELECT COUNT(*) AS customers_with_category_id_change
FROM (
    SELECT CustomerID
    FROM Sales.Customers FOR SYSTEM_TIME ALL
    GROUP BY CustomerID
    HAVING COUNT(DISTINCT CustomerCategoryID) > 1
) x;
SELECT COUNT(*) AS customers_with_buying_group_change
FROM (
    SELECT CustomerID
    FROM Sales.Customers FOR SYSTEM_TIME ALL
    GROUP BY CustomerID
    HAVING COUNT(DISTINCT ISNULL(BuyingGroupID,-1)) > 1
) x;
GO
