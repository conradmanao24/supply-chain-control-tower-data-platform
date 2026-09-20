-- backfill - controlled historical backfill state.
-- Backfills are isolated from the production analytical watermark.

CREATE SCHEMA IF NOT EXISTS control;

CREATE TABLE IF NOT EXISTS control.processing_guard (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    mode text NULL CHECK (mode IN ('incremental','backfill')),
    owner_run_id text NULL,
    acquired_at timestamptz NULL,
    CONSTRAINT processing_guard_consistent CHECK (
        (mode IS NULL AND owner_run_id IS NULL AND acquired_at IS NULL)
        OR
        (mode IS NOT NULL AND owner_run_id IS NOT NULL AND acquired_at IS NOT NULL)
    )
);

INSERT INTO control.processing_guard(singleton)
VALUES (true)
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS control.backfill_run_history (
    backfill_run_id bigserial PRIMARY KEY,
    airflow_run_id text NOT NULL UNIQUE,
    start_cutoff timestamptz NOT NULL,
    end_cutoff timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('running','success','failed')),
    production_watermark_before timestamptz NOT NULL,
    production_watermark_after timestamptz NULL,
    source_frontier_at_start timestamptz NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    error_message text NULL,
    verification jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT backfill_window_valid CHECK (end_cutoff > start_cutoff),
    CONSTRAINT backfill_finished_consistent CHECK (
        (status='running' AND finished_at IS NULL AND production_watermark_after IS NULL)
        OR
        (status IN ('success','failed') AND finished_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_backfill_run_history_started
    ON control.backfill_run_history(started_at DESC);
CREATE INDEX IF NOT EXISTS ix_backfill_run_history_window
    ON control.backfill_run_history(start_cutoff,end_cutoff,status);
