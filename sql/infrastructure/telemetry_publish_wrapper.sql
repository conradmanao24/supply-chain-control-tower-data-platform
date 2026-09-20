USE [WideWorldImporters];
GO
SET NOCOUNT ON;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[PublishTelemetryEvent]
    @EventType nvarchar(100),
    @SourceTable nvarchar(256),
    @EntityKeys nvarchar(max),
    @RaiseOnError bit = 1
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    EXEC [ControlTower].[PublishBusinessEvent]
        @EventType=@EventType,
        @EntityType=N'telemetry',
        @SourceTable=@SourceTable,
        @Operation=N'UPSERT',
        @EntityKeys=@EntityKeys,
        @RaiseOnError=@RaiseOnError;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[RecordColdRoomTemperaturesAndPublish]
    @SensorReadings [Website].[SensorDataList] READONLY
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @reading_count int=(SELECT COUNT(*) FROM @SensorReadings);
    DECLARE @entity_keys nvarchar(max)=N'[]';
    IF @reading_count>0
        SET @entity_keys=(SELECT ColdRoomSensorNumber AS sensor_number,MIN(RecordedWhen) AS first_recorded_when,MAX(RecordedWhen) AS last_recorded_when,COUNT(*) AS reading_count FROM @SensorReadings GROUP BY ColdRoomSensorNumber FOR JSON PATH);
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC [Website].[RecordColdRoomTemperatures] @SensorReadings=@SensorReadings;
        IF @reading_count>0
            EXEC [ControlTower].[PublishTelemetryEvent] @EventType=N'telemetry.coldroom.batch_recorded',@SourceTable=N'Warehouse.ColdRoomTemperatures',@EntityKeys=@entity_keys,@RaiseOnError=1;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[RecordVehicleTemperatureAndPublish]
    @FullSensorDataArray nvarchar(1000)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @entity_keys nvarchar(max)=N'[]';
    DECLARE @reading_count int=0;
    IF ISJSON(@FullSensorDataArray)=1
    BEGIN
        SELECT @reading_count=COUNT(*) FROM OPENJSON(@FullSensorDataArray,N'$.Recordings');
        IF @reading_count>0
            SET @entity_keys=(SELECT JSON_VALUE([value],N'$.properties.rego') AS vehicle_registration,TRY_CONVERT(int,JSON_VALUE([value],N'$.properties.sensor')) AS sensor_number,JSON_VALUE([value],N'$.properties.when') AS recorded_when FROM OPENJSON(@FullSensorDataArray,N'$.Recordings') FOR JSON PATH);
    END;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC [Website].[RecordVehicleTemperature] @FullSensorDataArray=@FullSensorDataArray;
        IF @reading_count>0
            EXEC [ControlTower].[PublishTelemetryEvent] @EventType=N'telemetry.vehicle.batch_recorded',@SourceTable=N'Warehouse.VehicleTemperatures',@EntityKeys=@entity_keys,@RaiseOnError=1;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
GO