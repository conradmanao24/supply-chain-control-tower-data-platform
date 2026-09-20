-- data quality/reconciliation: Data Quality & Reconciliation control-plane persistence.

CREATE SCHEMA IF NOT EXISTS quality;

CREATE TABLE IF NOT EXISTS quality.run_history (
    quality_run_id uuid PRIMARY KEY,
    airflow_run_id text NOT NULL UNIQUE,
    mode text NOT NULL DEFAULT 'full' CHECK (mode IN ('standard','full')),
    status text NOT NULL CHECK (status IN ('running','pass','fail')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    passed_checks integer NOT NULL DEFAULT 0,
    failed_checks integer NOT NULL DEFAULT 0,
    warning_checks integer NOT NULL DEFAULT 0,
    error_message text,
    CONSTRAINT quality_run_finished_consistent CHECK (
        (status='running' AND finished_at IS NULL) OR
        (status IN ('pass','fail') AND finished_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_quality_run_history_started
    ON quality.run_history(started_at DESC);

CREATE TABLE IF NOT EXISTS quality.check_result (
    check_result_id bigserial PRIMARY KEY,
    quality_run_id uuid NOT NULL REFERENCES quality.run_history(quality_run_id) ON DELETE CASCADE,
    check_name text NOT NULL,
    category text NOT NULL CHECK (category IN ('structural','freshness','volume','referential','semantic','reconciliation','source_behavior')),
    severity text NOT NULL CHECK (severity IN ('info','warning','critical')),
    status text NOT NULL CHECK (status IN ('pass','fail','warning')),
    source_value text,
    target_value text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    checked_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (quality_run_id, check_name)
);

CREATE INDEX IF NOT EXISTS ix_quality_check_result_run_status
    ON quality.check_result(quality_run_id,status,category);

CREATE TABLE IF NOT EXISTS quality.known_source_behavior (
    behavior_id text PRIMARY KEY,
    description text NOT NULL,
    preservation_rule text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO quality.known_source_behavior(behavior_id,description,preservation_rule)
VALUES (
    'delivery_attempt_status_absent',
    'WideWorldImporters contains DeliveryAttempt JSON events whose Status property is absent/null.',
    'Preserve event_status as NULL and set is_unconfirmed_attempt=true; never normalize the source status to Delivered or another invented value.'
)
ON CONFLICT (behavior_id) DO UPDATE SET
    description=EXCLUDED.description,
    preservation_rule=EXCLUDED.preservation_rule,
    enabled=true,
    updated_at=now();
