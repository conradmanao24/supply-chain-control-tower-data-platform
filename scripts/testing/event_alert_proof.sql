USE [WideWorldImporters];
GO
SET NOCOUNT ON;
GO

-- Source-data-neutral alert/exception proof: publish change notifications for existing entities only.
-- No authoritative WWI row is modified.
EXEC [ControlTower].[PublishBusinessEvent]
    @EventType=N'inventory.changed',
    @EntityType=N'stock_item',
    @SourceTable=N'AlertEngine.Proof',
    @Operation=N'UPDATE',
    @EntityKeys=N'[{"entity_id":203}]',
    @RaiseOnError=1;

EXEC [ControlTower].[PublishBusinessEvent]
    @EventType=N'order.changed',
    @EntityType=N'order',
    @SourceTable=N'AlertEngine.Proof',
    @Operation=N'UPDATE',
    @EntityKeys=N'[{"entity_id":323483}]',
    @RaiseOnError=1;

EXEC [ControlTower].[PublishBusinessEvent]
    @EventType=N'delivery.changed',
    @EntityType=N'invoice',
    @SourceTable=N'AlertEngine.Proof',
    @Operation=N'UPDATE',
    @EntityKeys=N'[{"entity_id":308002}]',
    @RaiseOnError=1;
GO
