SET NOCOUNT ON;
USE [WideWorldImporters];

SELECT
    s.name AS schema_name,
    COUNT(t.object_id) AS table_count
FROM sys.schemas s
LEFT JOIN sys.tables t
    ON t.schema_id = s.schema_id
   AND t.is_ms_shipped = 0
WHERE s.name NOT IN ('sys', 'INFORMATION_SCHEMA')
GROUP BY s.name
HAVING COUNT(t.object_id) > 0
ORDER BY s.name;
