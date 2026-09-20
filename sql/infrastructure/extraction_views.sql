USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name=N'ControlTowerExtract')
    EXEC(N'CREATE SCHEMA [ControlTowerExtract] AUTHORIZATION [dbo];');
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[OrderState] AS
SELECT OrderID, CustomerID, SalespersonPersonID, PickedByPersonID, ContactPersonID,
       BackorderOrderID, OrderDate, ExpectedDeliveryDate, IsUndersupplyBackordered,
       DeliveryInstructions, PickingCompletedWhen, LastEditedWhen
FROM Sales.Orders;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[InvoiceDelivery] AS
SELECT InvoiceID, CustomerID, BillToCustomerID, OrderID, DeliveryMethodID,
       ContactPersonID, SalespersonPersonID, PackedByPersonID, InvoiceDate,
       IsCreditNote, DeliveryInstructions, TotalDryItems, TotalChillerItems,
       DeliveryRun, RunPosition, ReturnedDeliveryData, ConfirmedDeliveryTime,
       ConfirmedReceivedBy, LastEditedWhen
FROM Sales.Invoices;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[PurchaseOrderState] AS
SELECT PurchaseOrderID, SupplierID, OrderDate, DeliveryMethodID, ContactPersonID,
       ExpectedDeliveryDate, SupplierReference, IsOrderFinalized, LastEditedWhen
FROM Purchasing.PurchaseOrders;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[CustomerCurrent] AS
SELECT c.CustomerID, c.CustomerName, c.BillToCustomerID,
       c.CustomerCategoryID, cc.CustomerCategoryName,
       c.BuyingGroupID, bg.BuyingGroupName,
       c.DeliveryMethodID, c.DeliveryCityID, c.PostalCityID,
       c.CreditLimit, c.AccountOpenedDate, c.StandardDiscountPercentage,
       c.IsStatementSent, c.IsOnCreditHold, c.PaymentDays,
       c.DeliveryRun, c.RunPosition, c.DeliveryPostalCode,
       c.DeliveryLocation.Lat AS DeliveryLatitude,
       c.DeliveryLocation.Long AS DeliveryLongitude,
       c.ValidFrom, c.ValidTo
FROM Sales.Customers AS c
JOIN Sales.CustomerCategories AS cc ON cc.CustomerCategoryID=c.CustomerCategoryID
LEFT JOIN Sales.BuyingGroups AS bg ON bg.BuyingGroupID=c.BuyingGroupID;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[CustomerHistory] AS
SELECT CustomerID, BillToCustomerID, CustomerCategoryID, BuyingGroupID,
       DeliveryMethodID, DeliveryCityID, PostalCityID, CreditLimit,
       AccountOpenedDate, StandardDiscountPercentage, IsStatementSent,
       IsOnCreditHold, PaymentDays, DeliveryRun, RunPosition,
       DeliveryPostalCode, ValidFrom, ValidTo
FROM Sales.Customers FOR SYSTEM_TIME ALL;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[SupplierCurrent] AS
SELECT s.SupplierID, s.SupplierName, s.SupplierCategoryID, sc.SupplierCategoryName,
       s.DeliveryMethodID, s.DeliveryCityID, s.PostalCityID,
       s.SupplierReference, s.PaymentDays, s.DeliveryPostalCode,
       s.DeliveryLocation.Lat AS DeliveryLatitude,
       s.DeliveryLocation.Long AS DeliveryLongitude,
       s.ValidFrom, s.ValidTo
FROM Purchasing.Suppliers AS s
JOIN Purchasing.SupplierCategories AS sc ON sc.SupplierCategoryID=s.SupplierCategoryID;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[SupplierHistory] AS
SELECT SupplierID, SupplierName, SupplierCategoryID, DeliveryMethodID,
       DeliveryCityID, PostalCityID, SupplierReference, PaymentDays,
       DeliveryPostalCode, ValidFrom, ValidTo
FROM Purchasing.Suppliers FOR SYSTEM_TIME ALL;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[ProductCurrent] AS
SELECT si.StockItemID, si.StockItemName, si.SupplierID, sup.SupplierName,
       si.ColorID, col.ColorName,
       si.UnitPackageID, up.PackageTypeName AS UnitPackage,
       si.OuterPackageID, op.PackageTypeName AS OuterPackage,
       si.Brand, si.Size, si.LeadTimeDays, si.QuantityPerOuter,
       si.IsChillerStock, si.Barcode, si.TaxRate, si.UnitPrice,
       si.RecommendedRetailPrice, si.TypicalWeightPerUnit,
       si.CustomFields, si.Tags, si.ValidFrom, si.ValidTo
FROM Warehouse.StockItems AS si
JOIN Purchasing.Suppliers AS sup ON sup.SupplierID=si.SupplierID
LEFT JOIN Warehouse.Colors AS col ON col.ColorID=si.ColorID
JOIN Warehouse.PackageTypes AS up ON up.PackageTypeID=si.UnitPackageID
JOIN Warehouse.PackageTypes AS op ON op.PackageTypeID=si.OuterPackageID;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[ProductHistory] AS
SELECT StockItemID, StockItemName, SupplierID, ColorID, UnitPackageID,
       OuterPackageID, Brand, Size, LeadTimeDays, QuantityPerOuter,
       IsChillerStock, Barcode, TaxRate, UnitPrice, RecommendedRetailPrice,
       TypicalWeightPerUnit, CustomFields, Tags, ValidFrom, ValidTo
FROM Warehouse.StockItems FOR SYSTEM_TIME ALL;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[ProductStockGroup] AS
SELECT sg.StockItemStockGroupID, sg.StockItemID, sg.StockGroupID,
       g.StockGroupName, sg.LastEditedWhen
FROM Warehouse.StockItemStockGroups AS sg
JOIN Warehouse.StockGroups AS g ON g.StockGroupID=sg.StockGroupID;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[StockHoldingCurrent] AS
SELECT StockItemID, QuantityOnHand, BinLocation, LastStocktakeQuantity,
       LastCostPrice, ReorderLevel, TargetStockLevel, LastEditedWhen
FROM Warehouse.StockItemHoldings;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[EmployeeCurrent] AS
SELECT PersonID, FullName, PreferredName, IsSalesperson, ValidFrom, ValidTo
FROM Application.People
WHERE IsEmployee=1;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[EmployeeHistory] AS
SELECT PersonID, FullName, PreferredName, IsSalesperson, IsEmployee,
       ValidFrom, ValidTo
FROM Application.People FOR SYSTEM_TIME ALL
WHERE IsEmployee=1;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[GeographyCurrent] AS
SELECT c.CityID, c.CityName, c.StateProvinceID,
       sp.StateProvinceCode, sp.StateProvinceName, sp.SalesTerritory,
       sp.CountryID, co.CountryName, co.Continent, co.Region, co.Subregion,
       c.LatestRecordedPopulation,
       c.Location.Lat AS Latitude, c.Location.Long AS Longitude,
       c.ValidFrom, c.ValidTo
FROM Application.Cities AS c
JOIN Application.StateProvinces AS sp ON sp.StateProvinceID=c.StateProvinceID
JOIN Application.Countries AS co ON co.CountryID=sp.CountryID;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[DeliveryMethodCurrent] AS
SELECT DeliveryMethodID, DeliveryMethodName, ValidFrom, ValidTo
FROM Application.DeliveryMethods;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[TransactionTypeCurrent] AS
SELECT TransactionTypeID, TransactionTypeName, ValidFrom, ValidTo
FROM Application.TransactionTypes;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[PaymentMethodCurrent] AS
SELECT PaymentMethodID, PaymentMethodName, ValidFrom, ValidTo
FROM Application.PaymentMethods;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[PackageTypeCurrent] AS
SELECT PackageTypeID, PackageTypeName, ValidFrom, ValidTo
FROM Warehouse.PackageTypes;
GO

CREATE OR ALTER VIEW [ControlTowerExtract].[StockGroupCurrent] AS
SELECT StockGroupID, StockGroupName, ValidFrom, ValidTo
FROM Warehouse.StockGroups;
GO

GRANT SELECT ON SCHEMA::[ControlTowerExtract] TO [sct_airflow_reader];
GO
CREATE OR ALTER PROCEDURE [ControlTowerExtract].[GetCustomerCurrent]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT CustomerID, CustomerName, BillToCustomerID,
           CustomerCategoryID, CustomerCategoryName,
           BuyingGroupID, BuyingGroupName,
           DeliveryMethodID, DeliveryCityID, PostalCityID,
           CreditLimit, AccountOpenedDate, StandardDiscountPercentage,
           IsStatementSent, IsOnCreditHold, PaymentDays,
           DeliveryRun, RunPosition, DeliveryPostalCode,
           DeliveryLatitude, DeliveryLongitude, ValidFrom, ValidTo
    FROM [ControlTowerExtract].[CustomerCurrent];
END;
GO

CREATE OR ALTER PROCEDURE [ControlTowerExtract].[GetCustomerHistory]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT CustomerID, BillToCustomerID, CustomerCategoryID, BuyingGroupID,
           DeliveryMethodID, DeliveryCityID, PostalCityID, CreditLimit,
           AccountOpenedDate, StandardDiscountPercentage, IsStatementSent,
           IsOnCreditHold, PaymentDays, DeliveryRun, RunPosition,
           DeliveryPostalCode, ValidFrom, ValidTo
    FROM [ControlTowerExtract].[CustomerHistory];
END;
GO

GRANT EXECUTE ON OBJECT::[ControlTowerExtract].[GetCustomerCurrent] TO [sct_airflow_reader];
GRANT EXECUTE ON OBJECT::[ControlTowerExtract].[GetCustomerHistory] TO [sct_airflow_reader];
GO
CREATE OR ALTER PROCEDURE [ControlTowerExtract].[GetReconciliationCounts]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT dataset, row_count
    FROM (
        SELECT N'order_line' AS dataset, COUNT_BIG(*) AS row_count FROM Sales.OrderLines
        UNION ALL SELECT N'sale_line', COUNT_BIG(*) FROM Sales.InvoiceLines
        UNION ALL SELECT N'inventory_movement', COUNT_BIG(*) FROM Warehouse.StockItemTransactions
        UNION ALL SELECT N'purchase_line', COUNT_BIG(*) FROM Purchasing.PurchaseOrderLines
        UNION ALL SELECT N'financial_transaction',
            (SELECT COUNT_BIG(*) FROM Sales.CustomerTransactions) +
            (SELECT COUNT_BIG(*) FROM Purchasing.SupplierTransactions)
        UNION ALL SELECT N'order_state', COUNT_BIG(*) FROM Sales.Orders
        UNION ALL SELECT N'invoice_delivery', COUNT_BIG(*) FROM Sales.Invoices
        UNION ALL SELECT N'purchase_order_state', COUNT_BIG(*) FROM Purchasing.PurchaseOrders
        UNION ALL SELECT N'customer_current', COUNT_BIG(*) FROM Sales.Customers
        UNION ALL SELECT N'customer_history', COUNT_BIG(*) FROM Sales.Customers FOR SYSTEM_TIME ALL
        UNION ALL SELECT N'supplier_current', COUNT_BIG(*) FROM Purchasing.Suppliers
        UNION ALL SELECT N'supplier_history', COUNT_BIG(*) FROM Purchasing.Suppliers FOR SYSTEM_TIME ALL
        UNION ALL SELECT N'product_current', COUNT_BIG(*) FROM Warehouse.StockItems
        UNION ALL SELECT N'product_history', COUNT_BIG(*) FROM Warehouse.StockItems FOR SYSTEM_TIME ALL
        UNION ALL SELECT N'product_stock_group', COUNT_BIG(*) FROM Warehouse.StockItemStockGroups
        UNION ALL SELECT N'stock_holding_current', COUNT_BIG(*) FROM Warehouse.StockItemHoldings
        UNION ALL SELECT N'employee_current', COUNT_BIG(*) FROM Application.People WHERE IsEmployee=1
        UNION ALL SELECT N'employee_history', COUNT_BIG(*) FROM Application.People FOR SYSTEM_TIME ALL WHERE IsEmployee=1
        UNION ALL SELECT N'geography_current', COUNT_BIG(*) FROM Application.Cities
        UNION ALL SELECT N'delivery_method_current', COUNT_BIG(*) FROM Application.DeliveryMethods
        UNION ALL SELECT N'transaction_type_current', COUNT_BIG(*) FROM Application.TransactionTypes
        UNION ALL SELECT N'payment_method_current', COUNT_BIG(*) FROM Application.PaymentMethods
        UNION ALL SELECT N'package_type_current', COUNT_BIG(*) FROM Warehouse.PackageTypes
        UNION ALL SELECT N'stock_group_current', COUNT_BIG(*) FROM Warehouse.StockGroups
    ) AS counts;
END;
GO
GRANT EXECUTE ON OBJECT::[ControlTowerExtract].[GetReconciliationCounts] TO [sct_airflow_reader];
GO