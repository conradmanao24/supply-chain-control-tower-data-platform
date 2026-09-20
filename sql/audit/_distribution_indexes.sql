USE WideWorldImporters_Distribution;
SET NOCOUNT ON;
SELECT s.name AS schema_name,t.name AS table_name,i.index_id,i.name AS index_name,i.type_desc,i.is_primary_key,
       STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal) AS key_columns
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.indexes i ON i.object_id=t.object_id AND i.index_id>0
JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id AND ic.is_included_column=0
JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
WHERE (s.name='Warehouse' AND t.name IN ('ColdRoomTemperatures_Archive','VehicleTemperatures','StockItemTransactions'))
   OR (s.name='Sales' AND t.name IN ('Orders','OrderLines','Invoices','InvoiceLines','CustomerTransactions'))
   OR (s.name='Purchasing' AND t.name IN ('PurchaseOrders','PurchaseOrderLines','SupplierTransactions'))
GROUP BY s.name,t.name,i.index_id,i.name,i.type_desc,i.is_primary_key
ORDER BY s.name,t.name,i.index_id;
