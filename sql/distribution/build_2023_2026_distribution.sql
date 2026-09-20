SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET ARITHABORT ON;
SET NUMERIC_ROUNDABORT OFF;
USE WideWorldImporters_Distribution;
SET NOCOUNT ON;
SET XACT_ABORT ON;
DECLARE @cutoff datetime2(7)='2023-01-01T00:00:00';
DECLARE @rc int;

RAISERROR('DISTRIBUTION_TRIM_START',0,1) WITH NOWAIT;
ALTER DATABASE WideWorldImporters_Distribution SET RECOVERY SIMPLE;
CHECKPOINT;

CREATE TABLE #KeepInvoices (InvoiceID int NOT NULL PRIMARY KEY);
INSERT INTO #KeepInvoices(InvoiceID)
SELECT InvoiceID FROM Sales.Invoices WHERE InvoiceDate>=@cutoff
UNION
SELECT InvoiceID FROM Sales.CustomerTransactions WHERE TransactionDate>=@cutoff AND InvoiceID IS NOT NULL
UNION
SELECT InvoiceID FROM Warehouse.StockItemTransactions WHERE TransactionOccurredWhen>=@cutoff AND InvoiceID IS NOT NULL;

CREATE TABLE #KeepOrders (OrderID int NOT NULL PRIMARY KEY);
INSERT INTO #KeepOrders(OrderID)
SELECT OrderID FROM Sales.Orders WHERE OrderDate>=@cutoff
UNION
SELECT i.OrderID FROM Sales.Invoices i JOIN #KeepInvoices k ON k.InvoiceID=i.InvoiceID WHERE i.OrderID IS NOT NULL;
WHILE 1=1
BEGIN
    INSERT INTO #KeepOrders(OrderID)
    SELECT DISTINCT o.BackorderOrderID
    FROM Sales.Orders o
    JOIN #KeepOrders k ON k.OrderID=o.OrderID
    WHERE o.BackorderOrderID IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM #KeepOrders x WHERE x.OrderID=o.BackorderOrderID);
    IF @@ROWCOUNT=0 BREAK;
END;

CREATE TABLE #KeepPOs (PurchaseOrderID int NOT NULL PRIMARY KEY);
INSERT INTO #KeepPOs(PurchaseOrderID)
SELECT PurchaseOrderID FROM Purchasing.PurchaseOrders WHERE OrderDate>=@cutoff
UNION
SELECT PurchaseOrderID FROM Warehouse.StockItemTransactions WHERE TransactionOccurredWhen>=@cutoff AND PurchaseOrderID IS NOT NULL
UNION
SELECT PurchaseOrderID FROM Purchasing.SupplierTransactions WHERE TransactionDate>=@cutoff AND PurchaseOrderID IS NOT NULL;

SELECT 'KEEP_COUNTS' AS marker,
       (SELECT COUNT(*) FROM #KeepOrders) AS keep_orders,
       (SELECT COUNT(*) FROM #KeepInvoices) AS keep_invoices,
       (SELECT COUNT(*) FROM #KeepPOs) AS keep_pos;

DELETE il FROM Sales.InvoiceLines il WHERE NOT EXISTS (SELECT 1 FROM #KeepInvoices k WHERE k.InvoiceID=il.InvoiceID);
RAISERROR('InvoiceLines trimmed',0,1) WITH NOWAIT;
DELETE ct FROM Sales.CustomerTransactions ct WHERE ct.TransactionDate<@cutoff;
RAISERROR('CustomerTransactions trimmed',0,1) WITH NOWAIT;
DELETE st FROM Warehouse.StockItemTransactions st WHERE st.TransactionOccurredWhen<@cutoff;
RAISERROR('StockItemTransactions trimmed',0,1) WITH NOWAIT;
DELETE st FROM Purchasing.SupplierTransactions st WHERE st.TransactionDate<@cutoff;
RAISERROR('SupplierTransactions trimmed',0,1) WITH NOWAIT;
DELETE ol FROM Sales.OrderLines ol WHERE NOT EXISTS (SELECT 1 FROM #KeepOrders k WHERE k.OrderID=ol.OrderID);
RAISERROR('OrderLines trimmed',0,1) WITH NOWAIT;
DELETE pol FROM Purchasing.PurchaseOrderLines pol WHERE NOT EXISTS (SELECT 1 FROM #KeepPOs k WHERE k.PurchaseOrderID=pol.PurchaseOrderID);
RAISERROR('PurchaseOrderLines trimmed',0,1) WITH NOWAIT;
DELETE i FROM Sales.Invoices i WHERE NOT EXISTS (SELECT 1 FROM #KeepInvoices k WHERE k.InvoiceID=i.InvoiceID);
RAISERROR('Invoices trimmed',0,1) WITH NOWAIT;
DELETE o FROM Sales.Orders o WHERE NOT EXISTS (SELECT 1 FROM #KeepOrders k WHERE k.OrderID=o.OrderID);
RAISERROR('Orders trimmed',0,1) WITH NOWAIT;
DELETE po FROM Purchasing.PurchaseOrders po WHERE NOT EXISTS (SELECT 1 FROM #KeepPOs k WHERE k.PurchaseOrderID=po.PurchaseOrderID);
RAISERROR('PurchaseOrders trimmed',0,1) WITH NOWAIT;
CHECKPOINT;

RAISERROR('VehicleTemperatures trim start',0,1) WITH NOWAIT;
WHILE 1=1
BEGIN
    DELETE TOP (100000) FROM Warehouse.VehicleTemperatures WHERE RecordedWhen<@cutoff;
    SET @rc=@@ROWCOUNT;
    IF @rc=0 BREAK;
    RAISERROR('Vehicle batch deleted: %d',0,1,@rc) WITH NOWAIT;
END;
CHECKPOINT;

RAISERROR('ColdRoom temporal history trim start',0,1) WITH NOWAIT;
ALTER TABLE Warehouse.ColdRoomTemperatures SET (SYSTEM_VERSIONING = OFF);
WHILE 1=1
BEGIN
    SET @rc=0;
    EXEC sys.sp_executesql
        N'DELETE TOP (1000000) FROM Warehouse.ColdRoomTemperatures_Archive WHERE ValidTo<@p_cutoff; SET @p_deleted=@@ROWCOUNT;',
        N'@p_cutoff datetime2(7), @p_deleted int OUTPUT',
        @p_cutoff=@cutoff, @p_deleted=@rc OUTPUT;
    IF @rc=0 BREAK;
    RAISERROR('ColdRoom history batch deleted: %d',0,1,@rc) WITH NOWAIT;
    CHECKPOINT;
END;
ALTER TABLE Warehouse.ColdRoomTemperatures
SET (SYSTEM_VERSIONING = ON (HISTORY_TABLE = Warehouse.ColdRoomTemperatures_Archive, DATA_CONSISTENCY_CHECK = ON));
CHECKPOINT;

RAISERROR('Compact affected disk indexes',0,1) WITH NOWAIT;
ALTER INDEX ALL ON Sales.Orders REBUILD;
ALTER INDEX ALL ON Sales.OrderLines REBUILD;
ALTER INDEX ALL ON Sales.Invoices REBUILD;
ALTER INDEX ALL ON Sales.InvoiceLines REBUILD;
ALTER INDEX ALL ON Sales.CustomerTransactions REBUILD;
ALTER INDEX ALL ON Purchasing.PurchaseOrders REBUILD;
ALTER INDEX ALL ON Purchasing.PurchaseOrderLines REBUILD;
ALTER INDEX ALL ON Purchasing.SupplierTransactions REBUILD;
ALTER INDEX ALL ON Warehouse.StockItemTransactions REBUILD;
CHECKPOINT;

RAISERROR('DISTRIBUTION_TRIM_DONE',0,1) WITH NOWAIT;
SELECT MAX(OrderDate) AS max_order_date, COUNT_BIG(*) AS orders FROM Sales.Orders;
SELECT COUNT_BIG(*) AS coldroom_history FROM Warehouse.ColdRoomTemperatures_Archive;
SELECT COUNT_BIG(*) AS vehicle_temperatures FROM Warehouse.VehicleTemperatures;
SELECT COUNT(*) AS bad_fks FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1;
SELECT COUNT(*) AS temporal_current_tables FROM sys.tables WHERE temporal_type=2;
SELECT COUNT(*) AS simulation_triggers FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%';



