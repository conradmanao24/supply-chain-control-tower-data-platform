USE WideWorldImporters;
SET NOCOUNT ON;
PRINT '=== TABLE_INVENTORY ===';
SELECT s.name AS schema_name,t.name AS table_name,
       SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS rows,
       t.temporal_type_desc
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.partitions p ON p.object_id=t.object_id
GROUP BY s.name,t.name,t.temporal_type_desc
ORDER BY s.name,t.name;

PRINT '=== COLUMN_INVENTORY ===';
SELECT s.name AS schema_name,t.name AS table_name,c.column_id,c.name AS column_name,
       ty.name AS data_type,c.max_length,c.precision,c.scale,c.is_nullable,
       c.is_identity,c.generated_always_type_desc
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
ORDER BY s.name,t.name,c.column_id;

PRINT '=== FOREIGN_KEYS ===';
SELECT OBJECT_SCHEMA_NAME(fk.parent_object_id) AS child_schema,
       OBJECT_NAME(fk.parent_object_id) AS child_table,
       pc.name AS child_column,
       OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS parent_schema,
       OBJECT_NAME(fk.referenced_object_id) AS parent_table,
       rc.name AS parent_column,
       fk.name AS fk_name
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
JOIN sys.columns pc ON pc.object_id=fk.parent_object_id AND pc.column_id=fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id=fk.referenced_object_id AND rc.column_id=fkc.referenced_column_id
ORDER BY child_schema,child_table,fk.name;

PRINT '=== REFERENCE_VALUES ===';
SELECT 'Application.TransactionTypes' AS src, TransactionTypeID AS id, TransactionTypeName AS name FROM Application.TransactionTypes ORDER BY id;
SELECT 'Application.DeliveryMethods' AS src, DeliveryMethodID AS id, DeliveryMethodName AS name FROM Application.DeliveryMethods ORDER BY id;
SELECT 'Application.PaymentMethods' AS src, PaymentMethodID AS id, PaymentMethodName AS name FROM Application.PaymentMethods ORDER BY id;
SELECT 'Sales.CustomerCategories' AS src, CustomerCategoryID AS id, CustomerCategoryName AS name FROM Sales.CustomerCategories ORDER BY id;
SELECT 'Purchasing.SupplierCategories' AS src, SupplierCategoryID AS id, SupplierCategoryName AS name FROM Purchasing.SupplierCategories ORDER BY id;
SELECT 'Warehouse.StockGroups' AS src, StockGroupID AS id, StockGroupName AS name FROM Warehouse.StockGroups ORDER BY id;

PRINT '=== BUSINESS_SUMMARY ===';
SELECT COUNT_BIG(*) orders, COUNT_BIG(DISTINCT CustomerID) order_customers, MIN(OrderDate) min_order, MAX(OrderDate) max_order,
       SUM(CASE WHEN BackorderOrderID IS NOT NULL THEN 1 ELSE 0 END) orders_with_backorder_ref,
       SUM(CASE WHEN PickingCompletedWhen IS NULL THEN 1 ELSE 0 END) orders_not_picked
FROM Sales.Orders;
SELECT COUNT_BIG(*) order_lines, COUNT_BIG(DISTINCT StockItemID) products_ordered,
       SUM(Quantity) qty_ordered, SUM(Quantity*UnitPrice) gross_order_value
FROM Sales.OrderLines;
SELECT COUNT_BIG(*) invoices, COUNT_BIG(DISTINCT CustomerID) invoiced_customers,
       SUM(CASE WHEN ConfirmedDeliveryTime IS NULL THEN 1 ELSE 0 END) delivery_not_confirmed,
       MIN(InvoiceDate) min_invoice, MAX(InvoiceDate) max_invoice
FROM Sales.Invoices;
SELECT COUNT_BIG(*) invoice_lines, SUM(Quantity) qty_invoiced, SUM(Quantity*UnitPrice) gross_invoice_value
FROM Sales.InvoiceLines;
SELECT COUNT_BIG(*) po, COUNT_BIG(DISTINCT SupplierID) suppliers_used,
       SUM(CASE WHEN IsOrderFinalized=0 THEN 1 ELSE 0 END) po_open,
       MIN(OrderDate) min_po, MAX(OrderDate) max_po
FROM Purchasing.PurchaseOrders;
SELECT COUNT_BIG(*) po_lines, SUM(OrderedOuters) ordered_outers,
       SUM(CASE WHEN IsOrderLineFinalized=0 THEN 1 ELSE 0 END) po_lines_open
FROM Purchasing.PurchaseOrderLines;
SELECT COUNT_BIG(*) holdings,
       SUM(CASE WHEN QuantityOnHand <= ReorderLevel THEN 1 ELSE 0 END) at_or_below_reorder,
       SUM(CASE WHEN QuantityOnHand < 0 THEN 1 ELSE 0 END) negative_stock
FROM Warehouse.StockItemHoldings;
SELECT COUNT_BIG(*) stock_tx, MIN(TransactionOccurredWhen) min_stock_tx, MAX(TransactionOccurredWhen) max_stock_tx,
       COUNT_BIG(DISTINCT StockItemID) stock_items_moved
FROM Warehouse.StockItemTransactions;
SELECT COUNT_BIG(*) cold_history, COUNT(DISTINCT ColdRoomSensorNumber) cold_sensors,
       MIN(RecordedWhen) min_cold, MAX(RecordedWhen) max_cold,
       MIN(Temperature) min_temp, MAX(Temperature) max_temp, AVG(CAST(Temperature AS float)) avg_temp
FROM Warehouse.ColdRoomTemperatures_Archive;
SELECT COUNT_BIG(*) vehicle_readings, COUNT(DISTINCT VehicleRegistration) vehicles,
       COUNT(DISTINCT ChillerSensorNumber) chiller_sensors,
       MIN(RecordedWhen) min_vehicle, MAX(RecordedWhen) max_vehicle,
       MIN(Temperature) min_temp, MAX(Temperature) max_temp, AVG(CAST(Temperature AS float)) avg_temp
FROM Warehouse.VehicleTemperatures;
