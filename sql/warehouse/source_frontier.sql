CREATE SCHEMA IF NOT EXISTS control;

CREATE TABLE IF NOT EXISTS control.source_frontier (
    source_name text PRIMARY KEY,
    safe_through_cutoff timestamptz NOT NULL,
    basis text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO control.source_frontier (source_name, safe_through_cutoff, basis)
VALUES (
    'WideWorldImporters',
    TIMESTAMPTZ '2026-09-16 00:00:00+00',
    'Official WWI simulation completed through 2026-09-15; full-catchup validation PASS.'
)
ON CONFLICT (source_name) DO UPDATE
SET safe_through_cutoff = EXCLUDED.safe_through_cutoff,
    basis = EXCLUDED.basis,
    updated_at = now()
WHERE control.source_frontier.safe_through_cutoff < EXCLUDED.safe_through_cutoff;
