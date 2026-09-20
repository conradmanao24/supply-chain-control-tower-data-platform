SET NOCOUNT ON;
USE [WideWorldImporters];

SELECT
    fk.name AS foreign_key_name,
    ps.name AS parent_schema,
    pt.name AS parent_table,
    pc.name AS parent_column,
    rs.name AS referenced_schema,
    rt.name AS referenced_table,
    rc.name AS referenced_column,
    fkc.constraint_column_id AS column_ordinal
FROM sys.foreign_keys AS fk
INNER JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id = fk.object_id
INNER JOIN sys.tables AS pt ON pt.object_id = fk.parent_object_id
INNER JOIN sys.schemas AS ps ON ps.schema_id = pt.schema_id
INNER JOIN sys.columns AS pc ON pc.object_id = pt.object_id AND pc.column_id = fkc.parent_column_id
INNER JOIN sys.tables AS rt ON rt.object_id = fk.referenced_object_id
INNER JOIN sys.schemas AS rs ON rs.schema_id = rt.schema_id
INNER JOIN sys.columns AS rc ON rc.object_id = rt.object_id AND rc.column_id = fkc.referenced_column_id
WHERE pt.is_ms_shipped = 0
ORDER BY ps.name, pt.name, fk.name, fkc.constraint_column_id;
