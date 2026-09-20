BACKUP DATABASE [WideWorldImporters]
TO DISK = N'/var/opt/mssql/data/wwi-full-master-2026-09-15.bak'
WITH COPY_ONLY, COMPRESSION, CHECKSUM, INIT, STATS = 5;
