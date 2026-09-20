CREATE SCHEMA IF NOT EXISTS control;

CREATE TABLE IF NOT EXISTS control.pipeline_state (
    pipeline_name text PRIMARY KEY,
    last_successful_cutoff timestamptz NOT NULL,
    last_successful_run_id text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control.pipeline_run_history (
    run_id bigserial PRIMARY KEY,
    pipeline_name text NOT NULL,
    airflow_run_id text NOT NULL UNIQUE,
    start_cutoff timestamptz NOT NULL,
    end_cutoff timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('running','success','failed')),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error_message text,
    CONSTRAINT pipeline_run_window_valid CHECK (end_cutoff > start_cutoff),
    CONSTRAINT pipeline_run_finished_consistent CHECK (
      (status = 'running' AND finished_at IS NULL) OR
      (status IN ('success','failed') AND finished_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_pipeline_run_history_pipeline_started
    ON control.pipeline_run_history (pipeline_name, started_at DESC);

INSERT INTO control.pipeline_state (
    pipeline_name,
    last_successful_cutoff,
    last_successful_run_id
)
VALUES (
    'supply_chain_incremental_pipeline',
    TIMESTAMPTZ '2026-09-16 00:00:00+00',
    'manual__2026-09-17T03:20:12.088082+00:00'
)
ON CONFLICT (pipeline_name) DO NOTHING;
