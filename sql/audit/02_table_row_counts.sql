SET NOCOUNT ON;
USE [WideWorldImporters];

CREATE TABLE #row_counts (
    schema_name sysname NOT NULL,
    table_name sysname NOT NULL,
    row_count bigint NOT NULL
);

DECLARE @sql nvarchar(max) = N'';
SELECT @sql = @sql +
    N'INSERT INTO #row_counts(schema_name, table_name, row_count) SELECT N''' +
    REPLACE(s.name,'''','''''') + N''', N''' + REPLACE(t.name,'''','''''') +
    N''', COUNT_BIG(*) FROM ' + QUOTENAME(s.name) + N'.' + QUOTENAME(t.name) + N';' + CHAR(10)
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE t.is_ms_shipped = 0;

EXEC sys.sp_executesql @sql;

SELECT schema_name, table_name, row_count
FROM #row_counts
ORDER BY row_count DESC, schema_name, table_name;
