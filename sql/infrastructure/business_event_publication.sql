USE [WideWorldImporters];
GO
SET NOCOUNT ON;
GO

CREATE OR ALTER PROCEDURE [ControlTower].[PublishBusinessEvent]
    @EventType nvarchar(100),
    @EntityType nvarchar(100),
    @SourceTable nvarchar(256),
    @Operation nvarchar(16),
    @EntityKeys nvarchar(max),
    @RaiseOnError bit = 0
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    IF TRY_CAST(SESSION_CONTEXT(N'sct_disable_event_publish') AS bit) = 1 RETURN;
    IF ISJSON(@EntityKeys) <> 1
    BEGIN
        IF @RaiseOnError = 1 THROW 51020, 'EntityKeys must be valid JSON.', 1;
        RETURN;
    END;
    IF (SELECT is_broker_enabled FROM sys.databases WHERE name = DB_NAME()) <> 1
    BEGIN
        IF @RaiseOnError = 1 THROW 51021, 'Service Broker is disabled.', 1;
        RETURN;
    END;

    DECLARE @dialog uniqueidentifier = NULL;
    DECLARE @payload nvarchar(max);
    DECLARE @event_id uniqueidentifier = NEWID();
    DECLARE @occurred_at datetime2(7) = SYSUTCDATETIME();

    SELECT @payload = (
        SELECT 1 AS schema_version,
               CONVERT(nvarchar(36), @event_id) AS event_id,
               @EventType AS event_type,
               @EntityType AS entity_type,
               @SourceTable AS source_table,
               @Operation AS operation,
               CONVERT(nvarchar(33), @occurred_at, 126) + N'Z' AS occurred_at_utc,
               JSON_QUERY(@EntityKeys) AS entity_keys
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
    );

    BEGIN TRY
        BEGIN DIALOG CONVERSATION @dialog
            FROM SERVICE [//SupplyChainControlTower/EventIngress]
            TO SERVICE N'//SupplyChainControlTower/EventConsumer'
            ON CONTRACT [//SupplyChainControlTower/EventContract]
            WITH ENCRYPTION = OFF;
        SEND ON CONVERSATION @dialog
            MESSAGE TYPE [//SupplyChainControlTower/Event] (@payload);
        END CONVERSATION @dialog;
    END TRY
    BEGIN CATCH
        IF @dialog IS NOT NULL
        BEGIN TRY
            END CONVERSATION @dialog WITH CLEANUP;
        END TRY
        BEGIN CATCH
        END CATCH;
        IF @RaiseOnError = 1 THROW;
    END CATCH;
END;
GO

CREATE OR ALTER TRIGGER [Sales].[trg_SCT_Orders_Event] ON [Sales].[Orders] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT OrderID entity_id FROM inserted UNION SELECT OrderID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'order.changed',N'order',N'Sales.Orders',@op,@keys;
END;
GO
CREATE OR ALTER TRIGGER [Sales].[trg_SCT_OrderLines_Event] ON [Sales].[OrderLines] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT OrderID entity_id FROM inserted UNION SELECT OrderID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'order.changed',N'order',N'Sales.OrderLines',@op,@keys;
END;
GO
CREATE OR ALTER TRIGGER [Sales].[trg_SCT_Invoices_Event] ON [Sales].[Invoices] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT InvoiceID entity_id FROM inserted UNION SELECT InvoiceID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'delivery.changed',N'invoice',N'Sales.Invoices',@op,@keys;
END;
GO
CREATE OR ALTER TRIGGER [Sales].[trg_SCT_InvoiceLines_Event] ON [Sales].[InvoiceLines] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT InvoiceID entity_id FROM inserted UNION SELECT InvoiceID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'delivery.changed',N'invoice',N'Sales.InvoiceLines',@op,@keys;
END;
GO
CREATE OR ALTER TRIGGER [Purchasing].[trg_SCT_PurchaseOrders_Event] ON [Purchasing].[PurchaseOrders] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT PurchaseOrderID entity_id FROM inserted UNION SELECT PurchaseOrderID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'procurement.changed',N'purchase_order',N'Purchasing.PurchaseOrders',@op,@keys;
END;
GO
CREATE OR ALTER TRIGGER [Purchasing].[trg_SCT_PurchaseOrderLines_Event] ON [Purchasing].[PurchaseOrderLines] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT PurchaseOrderID entity_id FROM inserted UNION SELECT PurchaseOrderID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'procurement.changed',N'purchase_order',N'Purchasing.PurchaseOrderLines',@op,@keys;
END;
GO
-- Warehouse.StockItemTransactions uses a clustered columnstore index, so SQL Server does not allow DML triggers on it.
-- Inventory realtime publication is therefore sourced from the current-state table Warehouse.StockItemHoldings.
CREATE OR ALTER TRIGGER [Warehouse].[trg_SCT_StockItemHoldings_Event] ON [Warehouse].[StockItemHoldings] AFTER INSERT, UPDATE, DELETE AS
BEGIN
 SET NOCOUNT ON; IF NOT EXISTS(SELECT 1 FROM inserted) AND NOT EXISTS(SELECT 1 FROM deleted) RETURN;
 DECLARE @op nvarchar(16)=CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN N'UPDATE' WHEN EXISTS(SELECT 1 FROM inserted) THEN N'INSERT' ELSE N'DELETE' END;
 DECLARE @keys nvarchar(max)=(SELECT entity_id FROM (SELECT StockItemID entity_id FROM inserted UNION SELECT StockItemID FROM deleted) k FOR JSON PATH);
 EXEC [ControlTower].[PublishBusinessEvent] N'inventory.changed',N'stock_item',N'Warehouse.StockItemHoldings',@op,@keys;
END;
GO