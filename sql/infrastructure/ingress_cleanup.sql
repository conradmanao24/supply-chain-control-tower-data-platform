USE [WideWorldImporters];
GO
SET NOCOUNT ON;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[ProcessEventIngressQueue]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @h uniqueidentifier,@t sysname;
    WHILE 1=1
    BEGIN
        SET @h=NULL; SET @t=NULL;
        WAITFOR (
            RECEIVE TOP(1) @h=conversation_handle,@t=message_type_name
            FROM [ControlTower].[EventIngressQueue]
        ), TIMEOUT 1000;
        IF @h IS NULL BREAK;
        BEGIN TRY
            END CONVERSATION @h;
        END TRY
        BEGIN CATCH
            BEGIN TRY
                END CONVERSATION @h WITH CLEANUP;
            END TRY
            BEGIN CATCH
            END CATCH;
        END CATCH;
    END;
END;
GO
ALTER QUEUE [ControlTower].[EventIngressQueue]
WITH ACTIVATION
(
    STATUS=ON,
    PROCEDURE_NAME=[ControlTower].[ProcessEventIngressQueue],
    MAX_QUEUE_READERS=1,
    EXECUTE AS OWNER
);
GO