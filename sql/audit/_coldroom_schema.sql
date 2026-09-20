USE WideWorldImporters_Distribution;
SET NOCOUNT ON;
SELECT s.name AS schema_name,t.name AS table_name,t.temporal_type_desc,
       hs.name AS history_schema, ht.name AS history_table
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
LEFT JOIN sys.tables ht ON ht.object_id=t.history_table_id
LEFT JOIN sys.schemas hs ON hs.schema_id=ht.schema_id
WHERE (s.name='Warehouse' AND t.name IN ('ColdRoomTemperatures','ColdRoomTemperatures_Archive','VehicleTemperatures'))
   OR t.history_table_id=OBJECT_ID('Warehouse.ColdRoomTemperatures_Archive');

SELECT c.column_id,c.name,ty.name AS type_name,c.max_length,c.precision,c.scale,c.is_nullable,c.is_identity,c.generated_always_type_desc
FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID('Warehouse.ColdRoomTemperatures_Archive')
ORDER BY c.column_id;
