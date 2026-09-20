-- Required sqlcmd variables supplied by the bootstrap caller:
--   DatabaseName
--   BackupPath

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_ID(N'$(DatabaseName)') IS NOT NULL
BEGIN
    PRINT N'Database $(DatabaseName) already exists. Restore skipped.';
    RETURN;
END;

PRINT N'Verifying backup $(BackupPath)...';
RESTORE VERIFYONLY
FROM DISK = N'$(BackupPath)';

PRINT N'Restoring $(DatabaseName)...';
RESTORE DATABASE [$(DatabaseName)]
FROM DISK = N'$(BackupPath)'
WITH
    MOVE N'WWI_Primary' TO N'/var/opt/mssql/data/WideWorldImporters.mdf',
    MOVE N'WWI_UserData' TO N'/var/opt/mssql/data/WideWorldImporters_UserData.ndf',
    MOVE N'WWI_Log' TO N'/var/opt/mssql/data/WideWorldImporters.ldf',
    MOVE N'WWI_InMemory_Data_1' TO N'/var/opt/mssql/data/WideWorldImporters_InMemory_Data_1',
    RECOVERY,
    STATS = 5;

PRINT N'Restore completed.';
