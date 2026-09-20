USE WideWorldImporters;
SELECT s.name AS schema_name,
       SUM(CASE WHEN p.index_id IN (0,1) THEN p.rows ELSE 0 END) AS rows
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.partitions p ON p.object_id=t.object_id
GROUP BY s.name
ORDER BY rows DESC;
