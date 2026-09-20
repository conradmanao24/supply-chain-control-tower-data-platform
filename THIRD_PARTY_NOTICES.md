# Third-Party Notices

## Microsoft WideWorldImporters

This project uses Microsoft WideWorldImporters from the Microsoft `sql-server-samples` repository as the operational source dataset.

Upstream repository:
`https://github.com/microsoft/sql-server-samples`

Official source artifact:
`WideWorldImporters-Full.bak`

The official Microsoft source is downloaded directly by `scripts/bootstrap/download-wwi.ps1`.

The project's frozen 2026 portfolio baseline is derived from that sample database by the project-owned simulation workflow. It is distributed separately as a GitHub Release asset rather than committed to Git history.

Microsoft's license notice is included at:

`THIRD_PARTY_LICENSES/MICROSOFT-SQL-SERVER-SAMPLES-MIT.txt`

## Frontend dependencies

Frontend runtime/build dependencies are declared in `frontend/package.json` and `frontend/package-lock.json` and retain their respective upstream licenses.

No third-party dashboard template files or design-source packages are redistributed in this repository.
