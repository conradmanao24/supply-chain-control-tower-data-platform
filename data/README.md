# Local Data Boundary

This directory is reserved for local runtime/source assets that must not be committed to GitHub, such as the downloaded WideWorldImporters backup or other generated data artifacts.

Users are **not** expected to populate this directory manually. The project bootstrap downloads the official WWI backup into `data/wwi/` when it is needed.

The directory itself is documented, while runtime contents are excluded by `.gitignore`.


## Verified local artifacts

These files are local-only and ignored by Git.

### Official Microsoft bootstrap backup

- file: `data/wwi/WideWorldImporters-Full.bak`
- bytes: `127111168`
- SHA-256: `E842BAD6CE02F74F166947E559DAB1B476EDD7EAAE3DA2AB9E3F522F1DD87124`

This artifact is downloaded from the Microsoft SQL Server samples release by the bootstrap scripts.

### Frozen portfolio baseline

- file: `data/baselines/full-master/wwi-full-master-2026-09-15.bak`
- bytes: `1662111744`
- SHA-256: `1F779A53D9AE1E5B90F2C62BA74D3E48E5FED0F75096E5EC798A09ABF04DEE30`
- source coverage: through `2026-09-15`

The baseline is intentionally not stored in Git. Public hosting for this exact artifact is a portfolio-closure task.
