USE WideWorldImporters;
;WITH rc AS (
    SELECT s.name AS schema_name, t.name AS table_name,
           SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS row_count
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id=t.schema_id
    JOIN sys.partitions p ON p.object_id=t.object_id
    GROUP BY s.name,t.name
)
SELECT SUM(row_count) AS total_user_table_rows FROM rc;
SELECT schema_name, SUM(row_count) AS rows FROM rc GROUP BY schema_name ORDER BY rows DESC;
