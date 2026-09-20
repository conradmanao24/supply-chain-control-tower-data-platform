SET NOCOUNT ON;
USE [WideWorldImporters];

CREATE TABLE #date_ranges (
    schema_name sysname NOT NULL,
    table_name sysname NOT NULL,
    column_name sysname NOT NULL,
    data_type sysname NOT NULL,
    min_value nvarchar(64) NULL,
    max_value nvarchar(64) NULL
);

DECLARE @sql nvarchar(max) = N'';
SELECT @sql = @sql +
    N'INSERT INTO #date_ranges(schema_name, table_name, column_name, data_type, min_value, max_value) ' +
    N'SELECT N''' + REPLACE(s.name,'''','''''') + N''', N''' + REPLACE(t.name,'''','''''') + N''', N''' + REPLACE(c.name,'''','''''') + N''', N''' + REPLACE(ty.name,'''','''''') + N''', ' +
    N'CONVERT(nvarchar(64), MIN(' + QUOTENAME(c.name) + N'), 126), CONVERT(nvarchar(64), MAX(' + QUOTENAME(c.name) + N'), 126) FROM ' + QUOTENAME(s.name) + N'.' + QUOTENAME(t.name) + N';' + CHAR(10)
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.columns c ON c.object_id = t.object_id
JOIN sys.types ty ON ty.user_type_id = c.user_type_id
WHERE t.is_ms_shipped = 0
  AND s.name IN ('Application','Purchasing','Sales','Warehouse')
  AND t.name NOT LIKE '%[_]Archive'
  AND ty.name IN ('date','datetime','datetime2','smalldatetime','datetimeoffset')
  AND (
        c.name LIKE '%Date%'
     OR c.name LIKE '%When%'
     OR c.name LIKE '%Time%'
  );

EXEC sys.sp_executesql @sql;

SELECT schema_name, table_name, column_name, data_type, min_value, max_value
FROM #date_ranges
ORDER BY schema_name, table_name, column_name;
