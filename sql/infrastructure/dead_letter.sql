USE [WideWorldImporters];
GO
SET NOCOUNT ON;
GO
IF OBJECT_ID(N'[ControlTower].[EventDeadLetter]',N'U') IS NULL
BEGIN
    CREATE TABLE [ControlTower].[EventDeadLetter]
    (
        [DeadLetterID] bigint IDENTITY(1,1) NOT NULL CONSTRAINT [PK_ControlTower_EventDeadLetter] PRIMARY KEY,
        [ConversationHandle] uniqueidentifier NULL,
        [MessageTypeName] sysname NOT NULL,
        [MessageBody] nvarchar(max) NULL,
        [ErrorMessage] nvarchar(2048) NOT NULL,
        [FailedAtUtc] datetime2(7) NOT NULL CONSTRAINT [DF_ControlTower_EventDeadLetter_FailedAtUtc] DEFAULT SYSUTCDATETIME(),
        [IsReplayed] bit NOT NULL CONSTRAINT [DF_ControlTower_EventDeadLetter_IsReplayed] DEFAULT 0,
        [ReplayedAtUtc] datetime2(7) NULL
    );
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[DeadLetterEvent]
    @ConversationHandle uniqueidentifier,
    @MessageTypeName sysname,
    @MessageBody nvarchar(max),
    @ErrorMessage nvarchar(2048)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    INSERT [ControlTower].[EventDeadLetter]
        ([ConversationHandle],[MessageTypeName],[MessageBody],[ErrorMessage])
    VALUES
        (@ConversationHandle,@MessageTypeName,@MessageBody,@ErrorMessage);
    IF @ConversationHandle IS NOT NULL
        END CONVERSATION @ConversationHandle;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[ReplayDeadLetter]
    @DeadLetterID bigint
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @body nvarchar(max),@dialog uniqueidentifier;
    SELECT @body=[MessageBody]
    FROM [ControlTower].[EventDeadLetter] WITH (UPDLOCK,HOLDLOCK)
    WHERE [DeadLetterID]=@DeadLetterID AND [IsReplayed]=0;
    IF @body IS NULL THROW 51040,'Dead-letter row not found or already replayed.',1;
    BEGIN DIALOG CONVERSATION @dialog
        FROM SERVICE [//SupplyChainControlTower/EventIngress]
        TO SERVICE N'//SupplyChainControlTower/EventConsumer'
        ON CONTRACT [//SupplyChainControlTower/EventContract]
        WITH ENCRYPTION=OFF;
    SEND ON CONVERSATION @dialog MESSAGE TYPE [//SupplyChainControlTower/Event] (@body);
    END CONVERSATION @dialog;
    UPDATE [ControlTower].[EventDeadLetter]
    SET [IsReplayed]=1,[ReplayedAtUtc]=SYSUTCDATETIME()
    WHERE [DeadLetterID]=@DeadLetterID;
END;
GO
GRANT EXECUTE ON OBJECT::[ControlTower].[DeadLetterEvent] TO [sct_event_consumer];
GO