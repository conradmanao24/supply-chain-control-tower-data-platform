EXEC [ControlTower].[PublishBusinessEvent]
    @EventType=N'order.changed',
    @EntityType=N'order',
    @SourceTable=N'SSE.Serving.Proof',
    @Operation=N'UPDATE',
    @EntityKeys=N'[{"entity_id":1}]',
    @RaiseOnError=1;
GO
