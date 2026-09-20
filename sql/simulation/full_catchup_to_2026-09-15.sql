SET NOCOUNT ON;
SET XACT_ABORT ON;
USE [WideWorldImporters];

DECLARE @ExpectedCurrentMaxOrderDate date = '20160607';
DECLARE @TargetDate date = '20260915';
DECLARE @CurrentMaxOrderDate date = (SELECT MAX(OrderDate) FROM Sales.Orders);
DECLARE @StartDate date;
DECLARE @CursorDate date;
DECLARE @ChunkEnd date;
DECLARE @Message nvarchar(4000);

IF @CurrentMaxOrderDate <> @ExpectedCurrentMaxOrderDate
BEGIN
    THROW 51000, 'Full catch-up precondition failed: expected MAX(Sales.Orders.OrderDate)=2016-06-07.', 1;
END;

IF (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2) <> 17
BEGIN
    THROW 51000, 'Full catch-up precondition failed: expected 17 active system-versioned temporal tables.', 1;
END;

IF EXISTS (SELECT 1 FROM sys.triggers WHERE name LIKE '%[_]DataLoad[_]Modify')
BEGIN
    THROW 51000, 'Full catch-up precondition failed: leftover DataLoad simulation triggers detected.', 1;
END;

SET @StartDate = DATEADD(day, 1, @CurrentMaxOrderDate);
SET @CursorDate = @StartDate;

SET @Message = CONCAT('FULL CATCH-UP START | ', CONVERT(varchar(10), @StartDate, 120), ' -> ', CONVERT(varchar(10), @TargetDate, 120));
RAISERROR(@Message, 10, 1) WITH NOWAIT;

BEGIN TRY
    EXEC DataLoadSimulation.Configuration_ApplyDataLoadSimulationProcedures;

    WHILE @CursorDate <= @TargetDate
    BEGIN
        SET @ChunkEnd = EOMONTH(@CursorDate);
        IF @ChunkEnd > @TargetDate SET @ChunkEnd = @TargetDate;

        SET @Message = CONCAT('CHUNK START | ', CONVERT(varchar(10), @CursorDate, 120), ' -> ', CONVERT(varchar(10), @ChunkEnd, 120));
        RAISERROR(@Message, 10, 1) WITH NOWAIT;

        EXEC DataLoadSimulation.DailyProcessToCreateHistory
            @StartDate = @CursorDate,
            @EndDate = @ChunkEnd,
            @AverageNumberOfCustomerOrdersPerDay = 60,
            @SaturdayPercentageOfNormalWorkDay = 50,
            @SundayPercentageOfNormalWorkDay = 0,
            @UpdateCustomFields = 0,
            @IsSilentMode = 1,
            @AreDatesPrinted = 0;

        SET @Message = CONCAT('CHUNK DONE  | ', CONVERT(varchar(10), @CursorDate, 120), ' -> ', CONVERT(varchar(10), @ChunkEnd, 120));
        RAISERROR(@Message, 10, 1) WITH NOWAIT;

        SET @CursorDate = DATEADD(day, 1, @ChunkEnd);
    END;

    EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures;
END TRY
BEGIN CATCH
    DECLARE @OriginalErrorNumber int = ERROR_NUMBER();
    DECLARE @OriginalErrorMessage nvarchar(4000) = ERROR_MESSAGE();

    RAISERROR('FULL CATCH-UP ERROR | attempting official WWI simulation cleanup', 10, 1) WITH NOWAIT;

    BEGIN TRY
        IF EXISTS (SELECT 1 FROM sys.triggers WHERE name LIKE '%[_]DataLoad[_]Modify')
           OR (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2) < 17
        BEGIN
            EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures;
        END;
    END TRY
    BEGIN CATCH
        DECLARE @CleanupError nvarchar(4000) = ERROR_MESSAGE();
        SET @Message = CONCAT('CLEANUP ERROR | ', @CleanupError);
        RAISERROR(@Message, 10, 1) WITH NOWAIT;
    END CATCH;

    SET @Message = CONCAT('ORIGINAL ERROR ', @OriginalErrorNumber, ' | ', @OriginalErrorMessage);
    RAISERROR(@Message, 16, 1);
    RETURN;
END CATCH;

DECLARE @FinalMaxOrderDate date = (SELECT MAX(OrderDate) FROM Sales.Orders);
DECLARE @TemporalCount int = (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2);
DECLARE @SimulationTriggerCount int = (SELECT COUNT(*) FROM sys.triggers WHERE name LIKE '%[_]DataLoad[_]Modify');
DECLARE @DisabledFKCount int = (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled = 1);
DECLARE @UntrustedFKCount int = (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_not_trusted = 1);

IF @FinalMaxOrderDate <> @TargetDate
BEGIN
    THROW 51000, 'Full catch-up validation failed: MAX(Sales.Orders.OrderDate) did not reach target date.', 1;
END;
IF @TemporalCount <> 17
BEGIN
    THROW 51000, 'Full catch-up validation failed: temporal tables were not fully restored.', 1;
END;
IF @SimulationTriggerCount <> 0
BEGIN
    THROW 51000, 'Full catch-up validation failed: simulation triggers remain active.', 1;
END;
IF @DisabledFKCount <> 0 OR @UntrustedFKCount <> 0
BEGIN
    THROW 51000, 'Full catch-up validation failed: foreign-key integrity state is not clean.', 1;
END;

SELECT
    @StartDate AS simulation_start_date,
    @TargetDate AS simulation_target_date,
    @FinalMaxOrderDate AS final_max_order_date,
    @TemporalCount AS temporal_current_tables,
    @SimulationTriggerCount AS simulation_triggers,
    @DisabledFKCount AS disabled_foreign_keys,
    @UntrustedFKCount AS untrusted_foreign_keys;

SELECT 'Sales.Orders' AS object_name, COUNT_BIG(*) AS row_count, MIN(OrderDate) AS min_date, MAX(OrderDate) AS max_date FROM Sales.Orders
UNION ALL
SELECT 'Sales.Invoices', COUNT_BIG(*), MIN(InvoiceDate), MAX(InvoiceDate) FROM Sales.Invoices
UNION ALL
SELECT 'Sales.CustomerTransactions', COUNT_BIG(*), MIN(TransactionDate), MAX(TransactionDate) FROM Sales.CustomerTransactions
UNION ALL
SELECT 'Purchasing.PurchaseOrders', COUNT_BIG(*), MIN(OrderDate), MAX(OrderDate) FROM Purchasing.PurchaseOrders
UNION ALL
SELECT 'Purchasing.SupplierTransactions', COUNT_BIG(*), MIN(TransactionDate), MAX(TransactionDate) FROM Purchasing.SupplierTransactions
UNION ALL
SELECT 'Warehouse.StockItemTransactions', COUNT_BIG(*), MIN(CAST(TransactionOccurredWhen AS date)), MAX(CAST(TransactionOccurredWhen AS date)) FROM Warehouse.StockItemTransactions
UNION ALL
SELECT 'Warehouse.VehicleTemperatures', COUNT_BIG(*), MIN(CAST(RecordedWhen AS date)), MAX(CAST(RecordedWhen AS date)) FROM Warehouse.VehicleTemperatures
UNION ALL
SELECT 'Warehouse.ColdRoomTemperatures_Archive', COUNT_BIG(*), MIN(CAST(RecordedWhen AS date)), MAX(CAST(RecordedWhen AS date)) FROM Warehouse.ColdRoomTemperatures_Archive;

RAISERROR('FULL CATCH-UP PASS | target 2026-09-15 reached and validation passed', 10, 1) WITH NOWAIT;
