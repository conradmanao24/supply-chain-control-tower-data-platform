USE [WideWorldImporters];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

DECLARE @fire_key nvarchar(200)=N'deadline.fire.probe';
DECLARE @cancel_key nvarchar(200)=N'deadline.cancel.probe';

-- Clean only prior proof ledger rows if a previous interrupted proof left any.
IF EXISTS (SELECT 1 FROM [ControlTower].[DeadlineSchedule] WHERE [DeadlineKey] IN (@fire_key,@cancel_key) AND [Status]=N'scheduled')
BEGIN
    EXEC [ControlTower].[CancelDeadline] @DeadlineKey=@fire_key;
    EXEC [ControlTower].[CancelDeadline] @DeadlineKey=@cancel_key;
END;
DELETE FROM [ControlTower].[DeadlineSchedule]
WHERE [DeadlineKey] IN (@fire_key,@cancel_key)
  AND [Status] <> N'scheduled';

IF (SELECT COUNT(*) FROM [ControlTower].[EventConsumerQueue]) <> 0
    THROW 51030, 'EventConsumerQueue must be empty before deadline/timer proof.', 1;
IF (SELECT COUNT(*) FROM sys.transmission_queue) <> 0
    THROW 51031, 'Transmission queue must be empty before deadline/timer proof.', 1;

DECLARE @fire_due datetime2(7)=DATEADD(SECOND,3,SYSUTCDATETIME());
EXEC [ControlTower].[ScheduleDeadline]
    @DeadlineKey=@fire_key,
    @DueAtUtc=@fire_due,
    @EventType=N'deadline.timer.probe',
    @EntityType=N'probe',
    @SourceTable=N'ControlTower.DeadlineSchedule',
    @EntityKeys=N'[{"probe_id":1}]';

DECLARE @target uniqueidentifier;
DECLARE @message_type sysname;
DECLARE @body varbinary(max);

WAITFOR
(
    RECEIVE TOP (1)
        @target=[conversation_handle],
        @message_type=[message_type_name],
        @body=[message_body]
    FROM [ControlTower].[EventConsumerQueue]
), TIMEOUT 15000;

IF @target IS NULL
    THROW 51032, 'Deadline timer did not publish an event.', 1;

DECLARE @payload nvarchar(max)=CONVERT(nvarchar(max),@body);
IF @message_type <> N'//SupplyChainControlTower/Event'
    THROW 51033, 'Unexpected Service Broker message type.', 1;
IF JSON_VALUE(@payload,N'$.event_type') <> N'deadline.timer.probe'
    THROW 51034, 'Deadline event type mismatch.', 1;
IF JSON_VALUE(@payload,N'$.operation') <> N'DEADLINE'
    THROW 51035, 'Deadline event operation mismatch.', 1;

SELECT @message_type AS received_message_type,
       JSON_VALUE(@payload,N'$.event_type') AS event_type,
       JSON_VALUE(@payload,N'$.operation') AS operation,
       JSON_VALUE(@payload,N'$.source_table') AS source_table;

END CONVERSATION @target;

-- Close the publisher initiator endpoint after target acknowledgement.
DECLARE @ingress_cleanup uniqueidentifier;
WAITFOR
(
    RECEIVE TOP (1) @ingress_cleanup=[conversation_handle]
    FROM [ControlTower].[EventIngressQueue]
), TIMEOUT 5000;
IF @ingress_cleanup IS NOT NULL END CONVERSATION @ingress_cleanup;

IF NOT EXISTS (
    SELECT 1 FROM [ControlTower].[DeadlineSchedule]
    WHERE [DeadlineKey]=@fire_key AND [Status]=N'fired' AND [FiredAtUtc] IS NOT NULL
)
    THROW 51036, 'Deadline ledger did not transition to fired.', 1;

-- Cancellation proof: schedule then immediately cancel. It must never publish.
DECLARE @cancel_due datetime2(7)=DATEADD(SECOND,4,SYSUTCDATETIME());
EXEC [ControlTower].[ScheduleDeadline]
    @DeadlineKey=@cancel_key,
    @DueAtUtc=@cancel_due,
    @EventType=N'deadline.timer.cancelled_probe',
    @EntityType=N'probe',
    @SourceTable=N'ControlTower.DeadlineSchedule',
    @EntityKeys=N'[{"probe_id":2}]';
EXEC [ControlTower].[CancelDeadline] @DeadlineKey=@cancel_key;

SET @target=NULL; SET @message_type=NULL; SET @body=NULL;
WAITFOR
(
    RECEIVE TOP (1)
        @target=[conversation_handle],
        @message_type=[message_type_name],
        @body=[message_body]
    FROM [ControlTower].[EventConsumerQueue]
), TIMEOUT 6000;

IF @target IS NOT NULL
BEGIN
    DECLARE @unexpected nvarchar(max)=CONVERT(nvarchar(max),@body);
    END CONVERSATION @target;
    THROW 51037, 'Cancelled deadline unexpectedly published an event.', 1;
END;

IF NOT EXISTS (
    SELECT 1 FROM [ControlTower].[DeadlineSchedule]
    WHERE [DeadlineKey]=@cancel_key AND [Status]=N'cancelled' AND [CancelledAtUtc] IS NOT NULL
)
    THROW 51038, 'Cancelled deadline ledger state is incorrect.', 1;

WAITFOR DELAY '00:00:01';

DECLARE @timer_queue_rows int=(SELECT COUNT(*) FROM [ControlTower].[DeadlineTimerQueue]);
DECLARE @ingress_rows int=(SELECT COUNT(*) FROM [ControlTower].[EventIngressQueue]);
DECLARE @consumer_rows int=(SELECT COUNT(*) FROM [ControlTower].[EventConsumerQueue]);
DECLARE @transmission_rows int=(SELECT COUNT(*) FROM sys.transmission_queue);
DECLARE @timer_endpoints int=(
    SELECT COUNT(*)
    FROM sys.conversation_endpoints ce
    JOIN sys.services s ON ce.service_id=s.service_id
    WHERE s.name=N'//SupplyChainControlTower/DeadlineTimer'
      AND ce.state_desc NOT IN (N'CLOSED')
);

SELECT N'PASS' AS deadline_timer_proof,
       (SELECT TOP(1) [Status] FROM [ControlTower].[DeadlineSchedule] WHERE [DeadlineKey]=@fire_key ORDER BY [CreatedAtUtc] DESC) AS fired_status,
       (SELECT TOP(1) [Status] FROM [ControlTower].[DeadlineSchedule] WHERE [DeadlineKey]=@cancel_key ORDER BY [CreatedAtUtc] DESC) AS cancelled_status,
       @timer_queue_rows AS timer_queue_rows,
       @ingress_rows AS ingress_queue_rows,
       @consumer_rows AS consumer_queue_rows,
       @transmission_rows AS transmission_queue_rows,
       @timer_endpoints AS open_timer_endpoints;

IF @timer_queue_rows<>0 OR @ingress_rows<>0 OR @consumer_rows<>0 OR @transmission_rows<>0 OR @timer_endpoints<>0
    THROW 51039, 'deadline/timer cleanup/infrastructure guard failed.', 1;

DELETE FROM [ControlTower].[DeadlineSchedule]
WHERE [DeadlineKey] IN (@fire_key,@cancel_key);
GO