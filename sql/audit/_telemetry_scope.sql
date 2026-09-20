USE WideWorldImporters;
SELECT s.name AS schema_name,t.name AS table_name,c.column_id,c.name AS column_name,TYPE_NAME(c.user_type_id) AS data_type
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id
WHERE (s.name='Warehouse' AND t.name IN ('VehicleTemperatures','ColdRoomTemperatures','ColdRoomTemperatures_Archive'))
ORDER BY t.name,c.column_id;

SELECT fk.name AS fk_name,
       OBJECT_SCHEMA_NAME(fk.parent_object_id)+'.'+OBJECT_NAME(fk.parent_object_id) AS child_table,
       pc.name AS child_column,
       OBJECT_SCHEMA_NAME(fk.referenced_object_id)+'.'+OBJECT_NAME(fk.referenced_object_id) AS parent_table,
       rc.name AS parent_column
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fk.object_id=fkc.constraint_object_id
JOIN sys.columns pc ON pc.object_id=fkc.parent_object_id AND pc.column_id=fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id=fkc.referenced_object_id AND rc.column_id=fkc.referenced_column_id
WHERE fk.parent_object_id IN (OBJECT_ID('Warehouse.VehicleTemperatures'),OBJECT_ID('Warehouse.ColdRoomTemperatures'),OBJECT_ID('Warehouse.ColdRoomTemperatures_Archive'))
   OR fk.referenced_object_id IN (OBJECT_ID('Warehouse.VehicleTemperatures'),OBJECT_ID('Warehouse.ColdRoomTemperatures'),OBJECT_ID('Warehouse.ColdRoomTemperatures_Archive'));

SELECT TOP 10 * FROM Warehouse.VehicleTemperatures ORDER BY RecordedWhen DESC;
SELECT TOP 10 * FROM Warehouse.ColdRoomTemperatures ORDER BY RecordedWhen DESC;
