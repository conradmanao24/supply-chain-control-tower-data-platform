USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @PilotStartDate date = '20160601';
DECLARE @PilotEndDate date = '20160607';
DECLARE @BeforeMaxOrderDate date = (SELECT MAX(OrderDate) FROM Sales.Orders);
DECLARE @StartedAt datetime2(3) = SYSDATETIME();

IF @BeforeMaxOrderDate <> '20160531'
    THROW 51000, 'Pilot precondition failed: expected MAX(Sales.Orders.OrderDate)=2016-05-31.', 1;

SELECT 'BEFORE' AS state,
       @StartedAt AS captured_at,
       @BeforeMaxOrderDate AS max_order_date,
       (SELECT COUNT_BIG(*) FROM Sales.Orders) AS sales_orders,
       (SELECT COUNT_BIG(*) FROM Sales.OrderLines) AS sales_order_lines,
       (SELECT COUNT_BIG(*) FROM Sales.Invoices) AS sales_invoices,
       (SELECT COUNT_BIG(*) FROM Sales.InvoiceLines) AS sales_invoice_lines,
       (SELECT COUNT_BIG(*) FROM Sales.CustomerTransactions) AS customer_transactions,
       (SELECT COUNT_BIG(*) FROM Purchasing.PurchaseOrders) AS purchase_orders,
       (SELECT COUNT_BIG(*) FROM Purchasing.PurchaseOrderLines) AS purchase_order_lines,
       (SELECT COUNT_BIG(*) FROM Purchasing.SupplierTransactions) AS supplier_transactions,
       (SELECT COUNT_BIG(*) FROM Warehouse.StockItemTransactions) AS stock_item_transactions,
       (SELECT COUNT_BIG(*) FROM Warehouse.VehicleTemperatures) AS vehicle_temperatures,
       (SELECT COUNT_BIG(*) FROM Warehouse.ColdRoomTemperatures_Archive) AS cold_room_archive;

BEGIN TRY
    EXEC DataLoadSimulation.Configuration_ApplyDataLoadSimulationProcedures;

    EXEC DataLoadSimulation.DailyProcessToCreateHistory
        @StartDate = @PilotStartDate,
        @EndDate = @PilotEndDate,
        @AverageNumberOfCustomerOrdersPerDay = 60,
        @SaturdayPercentageOfNormalWorkDay = 50,
        @SundayPercentageOfNormalWorkDay = 0,
        @UpdateCustomFields = 0,
        @IsSilentMode = 1,
        @AreDatesPrinted = 1;

    EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures;
END TRY
BEGIN CATCH
    BEGIN TRY
        EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures;
    END TRY
    BEGIN CATCH
        PRINT N'Cleanup after pilot failure also failed.';
    END CATCH;
    THROW;
END CATCH;

DECLARE @FinishedAt datetime2(3) = SYSDATETIME();
DECLARE @AfterMaxOrderDate date = (SELECT MAX(OrderDate) FROM Sales.Orders);

SELECT 'AFTER' AS state,
       @FinishedAt AS captured_at,
       @AfterMaxOrderDate AS max_order_date,
       DATEDIFF_BIG(millisecond, @StartedAt, @FinishedAt) AS runtime_ms,
       (SELECT COUNT_BIG(*) FROM Sales.Orders) AS sales_orders,
       (SELECT COUNT_BIG(*) FROM Sales.OrderLines) AS sales_order_lines,
       (SELECT COUNT_BIG(*) FROM Sales.Invoices) AS sales_invoices,
       (SELECT COUNT_BIG(*) FROM Sales.InvoiceLines) AS sales_invoice_lines,
       (SELECT COUNT_BIG(*) FROM Sales.CustomerTransactions) AS customer_transactions,
       (SELECT COUNT_BIG(*) FROM Purchasing.PurchaseOrders) AS purchase_orders,
       (SELECT COUNT_BIG(*) FROM Purchasing.PurchaseOrderLines) AS purchase_order_lines,
       (SELECT COUNT_BIG(*) FROM Purchasing.SupplierTransactions) AS supplier_transactions,
       (SELECT COUNT_BIG(*) FROM Warehouse.StockItemTransactions) AS stock_item_transactions,
       (SELECT COUNT_BIG(*) FROM Warehouse.VehicleTemperatures) AS vehicle_temperatures,
       (SELECT COUNT_BIG(*) FROM Warehouse.ColdRoomTemperatures_Archive) AS cold_room_archive;

SELECT YEAR(OrderDate) AS order_year, MONTH(OrderDate) AS order_month, COUNT_BIG(*) AS order_rows
FROM Sales.Orders
WHERE OrderDate BETWEEN @PilotStartDate AND @PilotEndDate
GROUP BY YEAR(OrderDate), MONTH(OrderDate)
ORDER BY order_year, order_month;

SELECT
    (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2) AS temporal_current_tables,
    (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 1) AS temporal_history_tables,
    (SELECT COUNT(*) FROM sys.triggers WHERE is_ms_shipped = 0 AND name LIKE '%_DataLoad_Modify') AS leftover_dataload_triggers,
    (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled = 1) AS disabled_foreign_keys,
    (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_not_trusted = 1) AS untrusted_foreign_keys;

IF @AfterMaxOrderDate <> @PilotEndDate
    THROW 51001, 'Pilot validation failed: MAX(Sales.Orders.OrderDate) did not reach 2016-06-07.', 1;

IF EXISTS (SELECT 1 FROM sys.triggers WHERE is_ms_shipped = 0 AND name LIKE '%_DataLoad_Modify')
    THROW 51002, 'Pilot cleanup failed: DataLoad simulation trigger remains.', 1;

PRINT N'SOURCE SIMULATION CONTROLLED 7-DAY PILOT PASS';
GO
