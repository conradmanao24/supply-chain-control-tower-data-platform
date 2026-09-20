USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET ARITHABORT ON;
SET NUMERIC_ROUNDABORT OFF;
GO

IF OBJECT_ID(N'[ControlTower].[DeadlineSchedule]', N'U') IS NULL
BEGIN
    CREATE TABLE [ControlTower].[DeadlineSchedule]
    (
        [DeadlineID] uniqueidentifier NOT NULL
            CONSTRAINT [DF_ControlTower_DeadlineSchedule_DeadlineID] DEFAULT NEWSEQUENTIALID(),
        [DeadlineKey] nvarchar(200) NOT NULL,
        [DueAtUtc] datetime2(7) NOT NULL,
        [EventType] nvarchar(100) NOT NULL,
        [EntityType] nvarchar(100) NOT NULL,
        [SourceTable] nvarchar(256) NOT NULL,
        [EntityKeys] nvarchar(max) NOT NULL,
        [ConversationHandle] uniqueidentifier NULL,
        [Status] nvarchar(16) NOT NULL,
        [CreatedAtUtc] datetime2(7) NOT NULL
            CONSTRAINT [DF_ControlTower_DeadlineSchedule_CreatedAtUtc] DEFAULT SYSUTCDATETIME(),
        [FiredAtUtc] datetime2(7) NULL,
        [CancelledAtUtc] datetime2(7) NULL,
        [FailedAtUtc] datetime2(7) NULL,
        [LastError] nvarchar(2048) NULL,
        CONSTRAINT [PK_ControlTower_DeadlineSchedule] PRIMARY KEY ([DeadlineID]),
        CONSTRAINT [CK_ControlTower_DeadlineSchedule_Status]
            CHECK ([Status] IN (N'scheduled',N'fired',N'cancelled',N'failed')),
        CONSTRAINT [CK_ControlTower_DeadlineSchedule_EntityKeysJson]
            CHECK (ISJSON([EntityKeys]) = 1)
    );
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'[ControlTower].[DeadlineSchedule]')
      AND name = N'UX_ControlTower_DeadlineSchedule_ActiveKey'
)
    DROP INDEX [UX_ControlTower_DeadlineSchedule_ActiveKey] ON [ControlTower].[DeadlineSchedule];
GO
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'[ControlTower].[DeadlineSchedule]')
      AND name = N'UX_ControlTower_DeadlineSchedule_ConversationHandle'
)
    DROP INDEX [UX_ControlTower_DeadlineSchedule_ConversationHandle] ON [ControlTower].[DeadlineSchedule];
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'[ControlTower].[DeadlineSchedule]')
      AND name = N'IX_ControlTower_DeadlineSchedule_KeyStatus'
)
    CREATE INDEX [IX_ControlTower_DeadlineSchedule_KeyStatus]
        ON [ControlTower].[DeadlineSchedule]([DeadlineKey],[Status]);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'[ControlTower].[DeadlineSchedule]')
      AND name = N'IX_ControlTower_DeadlineSchedule_ConversationHandle'
)
    CREATE INDEX [IX_ControlTower_DeadlineSchedule_ConversationHandle]
        ON [ControlTower].[DeadlineSchedule]([ConversationHandle]);
GO

IF OBJECT_ID(N'[ControlTower].[DeadlineTimerQueue]', N'SQ') IS NULL
    CREATE QUEUE [ControlTower].[DeadlineTimerQueue]
        WITH STATUS = ON, RETENTION = OFF;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.services
    WHERE name = N'//SupplyChainControlTower/DeadlineTimer'
)
    CREATE SERVICE [//SupplyChainControlTower/DeadlineTimer]
        ON QUEUE [ControlTower].[DeadlineTimerQueue]
        ([//SupplyChainControlTower/EventContract]);
GO

CREATE OR ALTER PROCEDURE [ControlTower].[ProcessDeadlineTimerQueue]
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @conversation_handle uniqueidentifier;
    DECLARE @message_type_name sysname;
    DECLARE @deadline_id uniqueidentifier;
    DECLARE @event_type nvarchar(100);
    DECLARE @entity_type nvarchar(100);
    DECLARE @source_table nvarchar(256);
    DECLARE @entity_keys nvarchar(max);

    WHILE 1 = 1
    BEGIN
        SET @conversation_handle = NULL;
        SET @message_type_name = NULL;

        WAITFOR
        (
            RECEIVE TOP (1)
                @conversation_handle = [conversation_handle],
                @message_type_name = [message_type_name]
            FROM [ControlTower].[DeadlineTimerQueue]
        ), TIMEOUT 1000;

        IF @conversation_handle IS NULL BREAK;

        BEGIN TRY
            IF @message_type_name = N'http://schemas.microsoft.com/SQL/ServiceBroker/DialogTimer'
            BEGIN
                SET @deadline_id = NULL;
                SELECT TOP (1)
                    @deadline_id = [DeadlineID],
                    @event_type = [EventType],
                    @entity_type = [EntityType],
                    @source_table = [SourceTable],
                    @entity_keys = [EntityKeys]
                FROM [ControlTower].[DeadlineSchedule]
                WHERE [ConversationHandle] = @conversation_handle
                  AND [Status] = N'scheduled';

                IF @deadline_id IS NOT NULL
                BEGIN
                    EXEC [ControlTower].[PublishBusinessEvent]
                        @EventType = @event_type,
                        @EntityType = @entity_type,
                        @SourceTable = @source_table,
                        @Operation = N'DEADLINE',
                        @EntityKeys = @entity_keys,
                        @RaiseOnError = 1;

                    UPDATE [ControlTower].[DeadlineSchedule]
                    SET [Status] = N'fired',
                        [FiredAtUtc] = SYSUTCDATETIME(),
                        [LastError] = NULL
                    WHERE [DeadlineID] = @deadline_id
                      AND [Status] = N'scheduled';
                END;

                END CONVERSATION @conversation_handle;
            END
            ELSE IF @message_type_name IN
            (
                N'http://schemas.microsoft.com/SQL/ServiceBroker/EndDialog',
                N'http://schemas.microsoft.com/SQL/ServiceBroker/Error'
            )
            BEGIN
                END CONVERSATION @conversation_handle;
            END
            ELSE
            BEGIN
                END CONVERSATION @conversation_handle WITH CLEANUP;
            END;
        END TRY
        BEGIN CATCH
            DECLARE @error nvarchar(2048) = LEFT(ERROR_MESSAGE(), 2048);

            UPDATE [ControlTower].[DeadlineSchedule]
            SET [Status] = N'failed',
                [FailedAtUtc] = SYSUTCDATETIME(),
                [LastError] = @error
            WHERE [ConversationHandle] = @conversation_handle
              AND [Status] = N'scheduled';

            BEGIN TRY
                END CONVERSATION @conversation_handle WITH CLEANUP;
            END TRY
            BEGIN CATCH
            END CATCH;
        END CATCH;
    END;
END;
GO

ALTER QUEUE [ControlTower].[DeadlineTimerQueue]
WITH ACTIVATION
(
    STATUS = ON,
    PROCEDURE_NAME = [ControlTower].[ProcessDeadlineTimerQueue],
    MAX_QUEUE_READERS = 1,
    EXECUTE AS OWNER
);
GO

CREATE OR ALTER PROCEDURE [ControlTower].[ScheduleDeadline]
    @DeadlineKey nvarchar(200),
    @DueAtUtc datetime2(7),
    @EventType nvarchar(100),
    @EntityType nvarchar(100),
    @SourceTable nvarchar(256),
    @EntityKeys nvarchar(max)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    IF NULLIF(LTRIM(RTRIM(@DeadlineKey)), N'') IS NULL
        THROW 51020, 'DeadlineKey is required.', 1;
    IF ISJSON(@EntityKeys) <> 1
        THROW 51021, 'EntityKeys must be valid JSON.', 1;

    DECLARE @old_handle uniqueidentifier;
    DECLARE @new_handle uniqueidentifier;
    DECLARE @timeout_seconds bigint = DATEDIFF_BIG(SECOND, SYSUTCDATETIME(), @DueAtUtc);
    DECLARE @timeout_int int;

    IF @timeout_seconds < 1 SET @timeout_seconds = 1;
    IF @timeout_seconds > 2147483647 SET @timeout_seconds = 2147483647;
    SET @timeout_int = CONVERT(int, @timeout_seconds);

    BEGIN TRAN;

    SELECT TOP (1) @old_handle = [ConversationHandle]
    FROM [ControlTower].[DeadlineSchedule] WITH (UPDLOCK, HOLDLOCK)
    WHERE [DeadlineKey] = @DeadlineKey
      AND [Status] = N'scheduled';

    IF @old_handle IS NOT NULL
    BEGIN
        UPDATE [ControlTower].[DeadlineSchedule]
        SET [Status] = N'cancelled',
            [CancelledAtUtc] = SYSUTCDATETIME()
        WHERE [DeadlineKey] = @DeadlineKey
          AND [Status] = N'scheduled';

        END CONVERSATION @old_handle;
    END;

    BEGIN DIALOG CONVERSATION @new_handle
        FROM SERVICE [//SupplyChainControlTower/DeadlineTimer]
        TO SERVICE N'//SupplyChainControlTower/DeadlineTimer'
        ON CONTRACT [//SupplyChainControlTower/EventContract]
        WITH ENCRYPTION = OFF;

    BEGIN CONVERSATION TIMER (@new_handle)
        TIMEOUT = @timeout_int;

    INSERT [ControlTower].[DeadlineSchedule]
    (
        [DeadlineKey], [DueAtUtc], [EventType], [EntityType],
        [SourceTable], [EntityKeys], [ConversationHandle], [Status]
    )
    VALUES
    (
        @DeadlineKey, @DueAtUtc, @EventType, @EntityType,
        @SourceTable, @EntityKeys, @new_handle, N'scheduled'
    );

    COMMIT;
END;
GO

CREATE OR ALTER PROCEDURE [ControlTower].[CancelDeadline]
    @DeadlineKey nvarchar(200)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @handle uniqueidentifier;

    BEGIN TRAN;
    SELECT TOP (1) @handle = [ConversationHandle]
    FROM [ControlTower].[DeadlineSchedule] WITH (UPDLOCK, HOLDLOCK)
    WHERE [DeadlineKey] = @DeadlineKey
      AND [Status] = N'scheduled';

    IF @handle IS NOT NULL
    BEGIN
        UPDATE [ControlTower].[DeadlineSchedule]
        SET [Status] = N'cancelled',
            [CancelledAtUtc] = SYSUTCDATETIME()
        WHERE [DeadlineKey] = @DeadlineKey
          AND [Status] = N'scheduled';

        END CONVERSATION @handle;
    END;
    COMMIT;
END;
GO
-- Realtime consumer least-privilege access for event-driven deadline maintenance.
IF USER_ID(N'sct_event_consumer') IS NOT NULL
BEGIN
    GRANT EXECUTE ON OBJECT::[ControlTower].[ScheduleDeadline] TO [sct_event_consumer];
    GRANT EXECUTE ON OBJECT::[ControlTower].[CancelDeadline] TO [sct_event_consumer];
END;
GO
