# Local Data Boundary

This directory is reserved for runtime/source assets that should not be committed to Git history.

Users are **not** expected to populate the required database backups manually. The bootstrap scripts download the required artifacts when they are absent.

## Official Microsoft source backup

Local path:

`data/wwi/WideWorldImporters-Full.bak`

Pinned verification:

- bytes: `127111168`
- SHA-256: `E842BAD6CE02F74F166947E559DAB1B476EDD7EAAE3DA2AB9E3F522F1DD87124`

The source-only bootstrap downloads this artifact from the official Microsoft SQL Server samples release.

## Frozen 2026 portfolio baseline

Local path:

`data/baselines/full-master/wwi-full-master-2026-09-15.bak`

Pinned verification:

- bytes: `1662111744`
- SHA-256: `1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30`
- source coverage: through `2026-09-15`

The file is intentionally excluded from Git history because of its size. It is distributed as the GitHub Release asset:

`v1.0-data-baseline / wwi-full-master-2026-09-15.bak`

`scripts/bootstrap/bootstrap-platform.ps1` downloads and validates this release asset automatically when the local baseline is missing.

The frozen baseline is derived from Microsoft WideWorldImporters. See `THIRD_PARTY_NOTICES.md` and `THIRD_PARTY_LICENSES/MICROSOFT-SQL-SERVER-SAMPLES-MIT.txt`.
