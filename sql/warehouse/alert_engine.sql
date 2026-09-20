-- alert/exception: Alert & Exception Engine
-- Project-owned alert persistence, rule configuration, lifecycle, and live alert notifications.

CREATE SCHEMA IF NOT EXISTS alert;

CREATE TABLE IF NOT EXISTS alert.engine_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    activated_at timestamptz NOT NULL DEFAULT now(),
    backlog_policy text NOT NULL DEFAULT 'event_touched_only'
        CHECK (backlog_policy IN ('event_touched_only')),
    notes text NOT NULL DEFAULT 'No historical full sweep at go-live; only entities touched by post-activation events are evaluated.'
);

INSERT INTO alert.engine_state(singleton)
VALUES (true)
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS alert.rule_config (
    rule_id text PRIMARY KEY,
    domain text NOT NULL,
    description text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    severity text NOT NULL CHECK (severity IN ('info','warning','critical')),
    source_native boolean NOT NULL DEFAULT false,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert.rule_config_history (
    audit_id bigserial PRIMARY KEY,
    rule_id text NOT NULL REFERENCES alert.rule_config(rule_id),
    actor text NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT now(),
    before_config jsonb NOT NULL,
    after_config jsonb NOT NULL,
    reevaluation_result jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_rule_config_history_rule_time
    ON alert.rule_config_history(rule_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS alert.alerts (
    alert_id bigserial PRIMARY KEY,
    rule_id text NOT NULL REFERENCES alert.rule_config(rule_id),
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info','warning','critical')),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','acknowledged','resolved')),
    opened_at timestamptz NOT NULL DEFAULT now(),
    last_observed_at timestamptz NOT NULL DEFAULT now(),
    acknowledged_at timestamptz NULL,
    acknowledged_by text NULL,
    resolved_at timestamptz NULL,
    resolved_by text NULL,
    observed_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    threshold_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_event_id uuid NULL,
    resolution_reason text NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_active_rule_entity
    ON alert.alerts(rule_id, entity_type, entity_id)
    WHERE status IN ('open','acknowledged');

CREATE INDEX IF NOT EXISTS ix_alert_active_severity
    ON alert.alerts(status, severity, opened_at DESC);
CREATE INDEX IF NOT EXISTS ix_alert_entity
    ON alert.alerts(entity_type, entity_id, opened_at DESC);

CREATE TABLE IF NOT EXISTS alert.alert_history (
    history_id bigserial PRIMARY KEY,
    alert_id bigint NOT NULL REFERENCES alert.alerts(alert_id) ON DELETE CASCADE,
    action text NOT NULL CHECK (action IN ('opened','observed','acknowledged','resolved','reopened')),
    actor text NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_alert_history_alert_time
    ON alert.alert_history(alert_id, occurred_at DESC);

INSERT INTO alert.rule_config(rule_id,domain,description,enabled,severity,source_native,parameters)
VALUES
 ('inventory.negative_stock','inventory','Quantity on hand is below zero.',true,'critical',true,'{}'),
 ('inventory.reorder','inventory','Quantity on hand is at or below the source reorder level.',true,'warning',true,'{}'),
 ('inventory.target_watch','inventory','Deprecated: TargetStockLevel is source typical order quantity, not an on-hand stock threshold.',false,'info',false,'{}'),
 ('fulfillment.overdue','fulfillment','Expected delivery date has passed while picking is incomplete.',true,'warning',true,'{}'),
 ('fulfillment.due_today','fulfillment','Order is due today while picking is incomplete.',true,'warning',true,'{}'),
 ('fulfillment.backorder','fulfillment','Order has a backorder reference.',true,'warning',true,'{}'),
 ('delivery.overdue','delivery','Expected delivery date has passed without delivery completion.',true,'warning',true,'{}'),
 ('delivery.due_today','delivery','Delivery is due today without completion.',true,'warning',true,'{}'),
 ('delivery.receiver_not_present','delivery','Latest delivery-attempt context reports Receiver not present.',true,'warning',true,'{}'),
 ('procurement.overdue_under_received','procurement','Expected delivery date has passed while the PO remains under-received/open.',true,'warning',true,'{}'),
 ('procurement.due_today_under_received','procurement','PO is due today while under-received/open.',true,'warning',true,'{}'),
 ('coldroom.stale','cold_chain','Cold-room sensor has not reported within the configured stale interval.',true,'warning',false,'{"seconds":60}'),
 ('coldroom.offline','cold_chain','Cold-room sensor has not reported within the configured offline interval.',true,'critical',false,'{"seconds":120}'),
 ('coldroom.temperature_warning','cold_chain','Project-owned anomaly warning outside the historical WWI 3.0-5.0 C operating envelope.',true,'warning',false,'{"low":3.0,"high":5.0}'),
 ('coldroom.temperature_critical','cold_chain','Project-owned anomaly critical outside the extended 2.5-5.5 C guard band.',true,'critical',false,'{"low":2.5,"high":5.5}'),
 ('vehicle.stale','cold_chain','Vehicle sensor has not reported within the configured stale interval.',true,'warning',false,'{"seconds":600}'),
 ('vehicle.offline','cold_chain','Vehicle sensor has not reported within the configured offline interval.',true,'critical',false,'{"seconds":1200}'),
 ('vehicle.temperature_warning','cold_chain','Project-owned anomaly warning outside the historical WWI 3.0-5.0 C operating envelope.',true,'warning',false,'{"low":3.0,"high":5.0}'),
 ('vehicle.temperature_critical','cold_chain','Project-owned anomaly critical outside the extended 2.5-5.5 C guard band.',true,'critical',false,'{"low":2.5,"high":5.5}'),
 ('platform.pipeline_failed','platform','Analytical pipeline failure reported by the orchestration layer.',true,'critical',false,'{}'),
 ('platform.data_quality_failed','platform','Data-quality/dbt test failure reported by the analytical pipeline.',true,'critical',false,'{}'),
 ('platform.reconciliation_mismatch','platform','Source-to-warehouse reconciliation mismatch reported by the pipeline.',true,'critical',false,'{}')
ON CONFLICT (rule_id) DO NOTHING;

CREATE OR REPLACE FUNCTION alert.notify_alert_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    payload json;
BEGIN
    payload := json_build_object(
        'event_kind', 'alert',
        'alert_id', NEW.alert_id,
        'rule_id', NEW.rule_id,
        'entity_type', NEW.entity_type,
        'entity_id', NEW.entity_id,
        'severity', NEW.severity,
        'status', NEW.status,
        'opened_at', NEW.opened_at,
        'last_observed_at', NEW.last_observed_at,
        'resolved_at', NEW.resolved_at
    );
    PERFORM pg_notify('control_tower_realtime', payload::text);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_notify_alert_change ON alert.alerts;
CREATE TRIGGER trg_notify_alert_change
AFTER INSERT OR UPDATE OF severity,status,last_observed_at,resolved_at
ON alert.alerts
FOR EACH ROW
EXECUTE FUNCTION alert.notify_alert_change();
