-- SSE serving: publish committed realtime processing notifications from PostgreSQL.
-- Notifications are emitted only after event_log processing_result is finalized;
-- PostgreSQL delivers NOTIFY messages on transaction commit.

CREATE OR REPLACE FUNCTION realtime.notify_processed_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    notification json;
BEGIN
    IF NEW.processed_at IS NULL THEN
        RETURN NEW;
    END IF;

    notification := json_build_object(
        'event_id', NEW.event_id,
        'schema_version', NEW.schema_version,
        'event_type', NEW.event_type,
        'entity_type', NEW.entity_type,
        'operation', NEW.operation,
        'processing_result', NEW.processing_result,
        'occurred_at_utc', NEW.occurred_at_utc,
        'processed_at', NEW.processed_at
    );

    PERFORM pg_notify('control_tower_realtime', notification::text);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_processed_event ON realtime.event_log;

CREATE TRIGGER trg_notify_processed_event
AFTER UPDATE OF processing_result, processed_at
ON realtime.event_log
FOR EACH ROW
WHEN (NEW.processed_at IS NOT NULL)
EXECUTE FUNCTION realtime.notify_processed_event();
