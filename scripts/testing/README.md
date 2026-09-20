# Testing Scripts

This directory contains repository-level smoke, reconciliation, failure-injection, and recovery-proof helpers used during phased validation.

The scripts are intentionally separate from runtime application code.

Current coverage includes:

- source audit helpers
- source/staging reconciliation
- alert explanation and alert-state reconciliation
- failure/restart proofs
- Service Broker / SSE / deadline proofs
- backfill guard and failure-state proofs
- quality-gate failure-signal proof
- bounded source-vs-staging count verification

These helpers expect the documented local Docker runtime and environment variables. They must not embed credentials or depend on untracked machine-specific code.
