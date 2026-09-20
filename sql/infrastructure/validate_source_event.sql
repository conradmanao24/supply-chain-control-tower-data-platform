USE [WideWorldImporters];
GO
SET NOCOUNT ON;

SELECT DB_NAME() AS database_name,
       (SELECT is_broker_enabled FROM sys.databases WHERE name = DB_NAME()) AS is_broker_enabled;

SELECT name, type_desc
FROM sys.database_principals
WHERE name IN (N'sct_airflow_reader', N'sct_event_consumer')
ORDER BY name;

SELECT s.name AS schema_name, q.name AS queue_name, q.is_receive_enabled, q.is_enqueue_enabled
FROM sys.service_queues q
JOIN sys.schemas s ON q.schema_id = s.schema_id
WHERE s.name = N'ControlTower'
ORDER BY q.name;

SELECT name
FROM sys.services
WHERE name LIKE N'//SupplyChainControlTower/%'
ORDER BY name;
GO

DECLARE @initiator UNIQUEIDENTIFIER;
DECLARE @target UNIQUEIDENTIFIER;
DECLARE @message_type SYSNAME;
DECLARE @body VARBINARY(MAX);

BEGIN DIALOG CONVERSATION @initiator
    FROM SERVICE [//SupplyChainControlTower/EventIngress]
    TO SERVICE N'//SupplyChainControlTower/EventConsumer'
    ON CONTRACT [//SupplyChainControlTower/EventContract]
    WITH ENCRYPTION = OFF;

SEND ON CONVERSATION @initiator
    MESSAGE TYPE [//SupplyChainControlTower/Event]
    (N'{"event_type":"source_event_smoke_test","schema_version":1}');

WAITFOR (
    RECEIVE TOP (1)
        @target = conversation_handle,
        @message_type = message_type_name,
        @body = message_body
    FROM [ControlTower].[EventConsumerQueue]
), TIMEOUT 5000;

IF @target IS NULL
    THROW 51000, 'Service Broker smoke test message was not received.', 1;

SELECT @message_type AS received_message_type,
       CAST(@body AS NVARCHAR(MAX)) AS received_payload;

END CONVERSATION @target;

DECLARE @cleanup UNIQUEIDENTIFIER;
WAITFOR (
    RECEIVE TOP (1) @cleanup = conversation_handle
    FROM [ControlTower].[EventIngressQueue]
), TIMEOUT 5000;
IF @cleanup IS NOT NULL END CONVERSATION @cleanup;

SELECT (SELECT COUNT(*) FROM [ControlTower].[EventIngressQueue]) AS ingress_queue_rows,
       (SELECT COUNT(*) FROM [ControlTower].[EventConsumerQueue]) AS consumer_queue_rows,
       (SELECT COUNT(*) FROM sys.transmission_queue) AS transmission_queue_rows;
GO