IF DB_ID(N'WideWorldImporters_Distribution') IS NOT NULL
BEGIN
    ALTER DATABASE [WideWorldImporters_Distribution] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE [WideWorldImporters_Distribution];
END;

RESTORE DATABASE [WideWorldImporters_Distribution]
FROM DISK = N'/var/opt/mssql/data/wwi-full-master-2026-09-15.bak'
WITH
    MOVE N'WWI_Primary' TO N'/var/opt/mssql/data/WWI_Distribution.mdf',
    MOVE N'WWI_UserData' TO N'/var/opt/mssql/data/WWI_Distribution_UserData.ndf',
    MOVE N'WWI_Log' TO N'/var/opt/mssql/data/WWI_Distribution.ldf',
    MOVE N'WWI_InMemory_Data_1' TO N'/var/opt/mssql/data/WWI_Distribution_InMemory_Data_1',
    RECOVERY,
    STATS = 5;
