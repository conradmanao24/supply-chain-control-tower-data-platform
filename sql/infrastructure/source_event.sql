:setvar DatabaseName "WideWorldImporters"

USE [master];
GO

IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'sct_airflow_reader')
    ALTER LOGIN [sct_airflow_reader] WITH PASSWORD = '$(SCT_READER_PASSWORD)', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    CREATE LOGIN [sct_airflow_reader] WITH PASSWORD = '$(SCT_READER_PASSWORD)', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
GO

IF EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'sct_event_consumer')
    ALTER LOGIN [sct_event_consumer] WITH PASSWORD = '$(SCT_EVENT_PASSWORD)', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
ELSE
    CREATE LOGIN [sct_event_consumer] WITH PASSWORD = '$(SCT_EVENT_PASSWORD)', CHECK_POLICY = ON, CHECK_EXPIRATION = OFF;
GO

IF (SELECT is_broker_enabled FROM sys.databases WHERE name = N'$(DatabaseName)') = 0
BEGIN
    ALTER DATABASE [WideWorldImporters] SET ENABLE_BROKER WITH ROLLBACK IMMEDIATE;
END;
GO

USE [WideWorldImporters];
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ControlTower')
    EXEC(N'CREATE SCHEMA [ControlTower] AUTHORIZATION [dbo];');
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'sct_airflow_reader')
    CREATE USER [sct_airflow_reader] FOR LOGIN [sct_airflow_reader];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'sct_event_consumer')
    CREATE USER [sct_event_consumer] FOR LOGIN [sct_event_consumer];
GO

GRANT CONNECT TO [sct_airflow_reader];
GRANT EXECUTE ON SCHEMA::[Integration] TO [sct_airflow_reader];
GRANT SELECT ON OBJECT::[Warehouse].[ColdRoomTemperatures] TO [sct_airflow_reader];
GRANT SELECT ON OBJECT::[Warehouse].[ColdRoomTemperatures_Archive] TO [sct_airflow_reader];
GRANT SELECT ON OBJECT::[Warehouse].[VehicleTemperatures] TO [sct_airflow_reader];
GO

GRANT CONNECT TO [sct_event_consumer];
GO

IF NOT EXISTS (SELECT 1 FROM sys.service_message_types WHERE name = N'//SupplyChainControlTower/Event')
    CREATE MESSAGE TYPE [//SupplyChainControlTower/Event] VALIDATION = NONE;
GO

IF NOT EXISTS (SELECT 1 FROM sys.service_contracts WHERE name = N'//SupplyChainControlTower/EventContract')
    CREATE CONTRACT [//SupplyChainControlTower/EventContract]
        ([//SupplyChainControlTower/Event] SENT BY INITIATOR);
GO

IF OBJECT_ID(N'[ControlTower].[EventIngressQueue]', N'SQ') IS NULL
    CREATE QUEUE [ControlTower].[EventIngressQueue] WITH STATUS = ON, RETENTION = OFF;
GO
IF OBJECT_ID(N'[ControlTower].[EventConsumerQueue]', N'SQ') IS NULL
    CREATE QUEUE [ControlTower].[EventConsumerQueue] WITH STATUS = ON, RETENTION = OFF;
GO

IF NOT EXISTS (SELECT 1 FROM sys.services WHERE name = N'//SupplyChainControlTower/EventIngress')
    CREATE SERVICE [//SupplyChainControlTower/EventIngress]
        ON QUEUE [ControlTower].[EventIngressQueue]
        ([//SupplyChainControlTower/EventContract]);
GO
IF NOT EXISTS (SELECT 1 FROM sys.services WHERE name = N'//SupplyChainControlTower/EventConsumer')
    CREATE SERVICE [//SupplyChainControlTower/EventConsumer]
        ON QUEUE [ControlTower].[EventConsumerQueue]
        ([//SupplyChainControlTower/EventContract]);
GO

GRANT RECEIVE ON [ControlTower].[EventConsumerQueue] TO [sct_event_consumer];
GO