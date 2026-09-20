USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @before bigint=(SELECT COUNT_BIG(*) FROM [Warehouse].[VehicleTemperatures]);
IF EXISTS (SELECT 1 FROM [Warehouse].[VehicleTemperatures] WHERE VehicleRegistration=N'SCT-6B-PROBE')
    DELETE FROM [Warehouse].[VehicleTemperatures] WHERE VehicleRegistration=N'SCT-6B-PROBE';
SET @before=(SELECT COUNT_BIG(*) FROM [Warehouse].[VehicleTemperatures]);

IF (SELECT COUNT(*) FROM [ControlTower].[EventIngressQueue])<>0 OR
   (SELECT COUNT(*) FROM [ControlTower].[EventConsumerQueue])<>0 OR
   (SELECT COUNT(*) FROM sys.transmission_queue)<>0
    THROW 51000,'Telemetry wrapper proof requires empty Broker queues.',1;

DECLARE @payload nvarchar(1000)=N'{"Recordings":[{"type":"Feature","geometry":{"type":"Point","coordinates":[0.0,0.0]},"properties":{"rego":"SCT-6B-PROBE","sensor":99,"when":"2026-09-15T23:59:59","temp":4.25}}]}';
EXEC [ControlTower].[RecordVehicleTemperatureAndPublish] @FullSensorDataArray=@payload;

IF (SELECT COUNT(*) FROM [Warehouse].[VehicleTemperatures] WHERE VehicleRegistration=N'SCT-6B-PROBE' AND ChillerSensorNumber=99 AND RecordedWhen=CONVERT(datetime2(7),N'2026-09-15T23:59:59'))<>1
    THROW 51000,'Vehicle wrapper did not write exactly one probe reading.',1;

DECLARE @target uniqueidentifier,@message_type sysname,@body varbinary(max);
WAITFOR (
    RECEIVE TOP(1) @target=conversation_handle,@message_type=message_type_name,@body=message_body
    FROM [ControlTower].[EventConsumerQueue]
), TIMEOUT 5000;
IF @target IS NULL THROW 51000,'Telemetry event not received.',1;
DECLARE @event nvarchar(max)=CONVERT(nvarchar(max),@body);
IF JSON_VALUE(@event,N'$.event_type')<>N'telemetry.vehicle.batch_recorded'
    THROW 51000,'Unexpected telemetry event type.',1;
IF JSON_VALUE(@event,N'$.entity_type')<>N'telemetry'
    THROW 51000,'Unexpected telemetry entity type.',1;
IF JSON_VALUE(@event,N'$.source_table')<>N'Warehouse.VehicleTemperatures'
    THROW 51000,'Unexpected telemetry source table.',1;
IF @event NOT LIKE N'%SCT-6B-PROBE%'
    THROW 51000,'Probe identity missing from telemetry event.',1;

SELECT @message_type AS received_message_type,@event AS received_payload;
END CONVERSATION @target;
DECLARE @cleanup uniqueidentifier;
WAITFOR (RECEIVE TOP(1) @cleanup=conversation_handle FROM [ControlTower].[EventIngressQueue]),TIMEOUT 5000;
IF @cleanup IS NOT NULL END CONVERSATION @cleanup;

DELETE FROM [Warehouse].[VehicleTemperatures]
WHERE VehicleRegistration=N'SCT-6B-PROBE' AND ChillerSensorNumber=99 AND RecordedWhen=CONVERT(datetime2(7),N'2026-09-15T23:59:59');

DECLARE @cold [Website].[SensorDataList];
EXEC [ControlTower].[RecordColdRoomTemperaturesAndPublish] @SensorReadings=@cold;

DECLARE @after bigint=(SELECT COUNT_BIG(*) FROM [Warehouse].[VehicleTemperatures]);
IF @after<>@before THROW 51000,'Vehicle row count did not return to baseline.',1;
IF EXISTS (SELECT 1 FROM [Warehouse].[VehicleTemperatures] WHERE VehicleRegistration=N'SCT-6B-PROBE')
    THROW 51000,'Synthetic vehicle probe row remains after cleanup.',1;
IF (SELECT COUNT(*) FROM [ControlTower].[EventIngressQueue])<>0 OR
   (SELECT COUNT(*) FROM [ControlTower].[EventConsumerQueue])<>0 OR
   (SELECT COUNT(*) FROM sys.transmission_queue)<>0
    THROW 51000,'Broker queues were not clean after telemetry proof.',1;

SELECT N'PASS' AS telemetry_wrapper_proof,@before AS vehicle_rows_before,@after AS vehicle_rows_after,
       (SELECT COUNT(*) FROM [ControlTower].[EventIngressQueue]) AS ingress_queue_rows,
       (SELECT COUNT(*) FROM [ControlTower].[EventConsumerQueue]) AS consumer_queue_rows,
       (SELECT COUNT(*) FROM sys.transmission_queue) AS transmission_queue_rows;
GO