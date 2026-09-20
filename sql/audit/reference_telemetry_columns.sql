USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SELECT s.name AS schema_name,t.name AS table_name,c.column_id,c.name AS column_name,ty.name AS data_type
FROM sys.schemas s
JOIN sys.tables t ON t.schema_id=s.schema_id
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE (s.name=N'Warehouse' AND t.name IN (N'ColdRoomTemperatures',N'ColdRoomTemperatures_Archive',N'VehicleTemperatures'))
   OR (s.name=N'Application' AND t.name=N'PaymentMethods')
   OR (s.name=N'Sales' AND t.name IN (N'CustomerCategories',N'BuyingGroups'))
   OR (s.name=N'Purchasing' AND t.name=N'SupplierCategories')
   OR (s.name=N'Warehouse' AND t.name=N'Colors')
ORDER BY s.name,t.name,c.column_id;
GO