# Source Acquisition Evidence

## Status

PASS

## Objective

Lock and obtain the official Microsoft WideWorldImporters OLTP source artifact before any database runtime is started.

## Official artifact

- File: `WideWorldImporters-Full.bak`
- Upstream repository: `microsoft/sql-server-samples`
- Release tag: `wide-world-importers-v1.0`
- Official download URL: `https://github.com/microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImporters-Full.bak`
- GitHub release asset size: `127111168` bytes

Microsoft Learn also documents this exact release URL for downloading the Wide World Importers backup before restoring it into SQL Server.

## Local acquisition result

The source artifact was downloaded to the local runtime-data boundary:

`data/wwi/WideWorldImporters-Full.bak`

This file is excluded from version control and will not be committed to the public repository.

Validation result:

- Exists: PASS
- Exact official asset size: PASS (`127111168` bytes)
- SQL Server backup header signature: PASS (`MSSQLBAK`)
- SHA-256: `E842BAD6CE02F74F166947E559DAB1B476EDD7EAAE3DA2AB9E3F522F1DD87124`

The SHA-256 above is a project-pinned fingerprint calculated from the artifact downloaded from the official Microsoft GitHub release. The upstream release metadata did not publish a checksum/digest for this asset at acquisition time.

A full SQL Server `RESTORE VERIFYONLY` is intentionally deferred to source runtime and restore because source acquisition prohibits starting SQL Server.

## Licensing and attribution

Microsoft's `sql-server-samples` repository states that its samples and templates are licensed under the MIT License.

This project does not redistribute the WideWorldImporters backup in GitHub. The clean-clone bootstrap downloads the artifact directly from Microsoft's official release location. Microsoft/WideWorldImporters is treated as an external source dependency, not as project-authored data.

If upstream source code or substantial portions of Microsoft sample material are copied into this repository later, the applicable upstream MIT copyright and permission notice must be preserved.

## Clean-clone acquisition contract

A clean clone will not require a user to search for the dataset manually.

The repository-owned acquisition script:

`scripts/bootstrap/download-wwi.ps1`

will:

1. use the locked official Microsoft release URL by default;
2. download `WideWorldImporters-Full.bak` into `data/wwi/`;
3. verify the expected byte size;
4. verify the `MSSQLBAK` header signature;
5. verify the project-pinned SHA-256 fingerprint;
6. leave the backup outside version control.

Source acquisition does not require Docker or SQL Server to be running.

## Phase boundary

source acquisition is complete when the official artifact exists locally and passes the acquisition checks above.

source runtime and restore may start only after explicit approval. source runtime and restore is responsible for SQL Server runtime, restore, connectivity, and persistence validation.
