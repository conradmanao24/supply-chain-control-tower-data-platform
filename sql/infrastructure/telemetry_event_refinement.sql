USE [WideWorldImporters];
GO
SET NOCOUNT ON;
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
    BEGIN
        SET @entity_keys=(
            SELECT s.ColdRoomSensorNumber AS sensor_number,
                   latest.RecordedWhen AS last_recorded_when,
                   latest.Temperature AS latest_temperature,
                   s.reading_count
            FROM (
                SELECT ColdRoomSensorNumber,COUNT(*) AS reading_count
                FROM @SensorReadings
                GROUP BY ColdRoomSensorNumber
            ) AS s
            CROSS APPLY (
                SELECT TOP(1) r.RecordedWhen,r.Temperature
                FROM @SensorReadings AS r
                WHERE r.ColdRoomSensorNumber=s.ColdRoomSensorNumber
                ORDER BY r.RecordedWhen DESC,r.SensorDataListID DESC
            ) AS latest
            FOR JSON PATH
        );
    END;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC [Website].[RecordColdRoomTemperatures] @SensorReadings=@SensorReadings;
        IF @reading_count>0
            EXEC [ControlTower].[PublishTelemetryEvent]
                 @EventType=N'telemetry.coldroom.batch_recorded',
                 @SourceTable=N'Warehouse.ColdRoomTemperatures',
                 @EntityKeys=@entity_keys,
                 @RaiseOnError=1;
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
        BEGIN
            SET @entity_keys=(
                SELECT vehicle_registration,sensor_number,
                       recorded_when AS last_recorded_when,
                       temperature AS latest_temperature,
                       reading_count
                FROM (
                    SELECT JSON_VALUE([value],N'$.properties.rego') AS vehicle_registration,
                           TRY_CONVERT(int,JSON_VALUE([value],N'$.properties.sensor')) AS sensor_number,
                           TRY_CONVERT(datetime2(7),JSON_VALUE([value],N'$.properties.when')) AS recorded_when,
                           TRY_CONVERT(decimal(18,2),JSON_VALUE([value],N'$.properties.temp')) AS temperature,
                           COUNT(*) OVER(PARTITION BY JSON_VALUE([value],N'$.properties.rego'),JSON_VALUE([value],N'$.properties.sensor')) AS reading_count,
                           ROW_NUMBER() OVER(
                               PARTITION BY JSON_VALUE([value],N'$.properties.rego'),JSON_VALUE([value],N'$.properties.sensor')
                               ORDER BY TRY_CONVERT(datetime2(7),JSON_VALUE([value],N'$.properties.when')) DESC
                           ) AS rn
                    FROM OPENJSON(@FullSensorDataArray,N'$.Recordings')
                ) AS p
                WHERE rn=1
                FOR JSON PATH
            );
        END;
    END;
    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC [Website].[RecordVehicleTemperature] @FullSensorDataArray=@FullSensorDataArray;
        IF @reading_count>0
            EXEC [ControlTower].[PublishTelemetryEvent]
                 @EventType=N'telemetry.vehicle.batch_recorded',
                 @SourceTable=N'Warehouse.VehicleTemperatures',
                 @EntityKeys=@entity_keys,
                 @RaiseOnError=1;
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;
END;
GO