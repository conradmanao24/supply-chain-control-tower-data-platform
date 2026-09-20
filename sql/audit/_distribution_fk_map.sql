USE WideWorldImporters;
SET NOCOUNT ON;
SELECT OBJECT_SCHEMA_NAME(fk.parent_object_id)+'.'+OBJECT_NAME(fk.parent_object_id) AS child_table,
       fk.name AS fk_name,
       OBJECT_SCHEMA_NAME(fk.referenced_object_id)+'.'+OBJECT_NAME(fk.referenced_object_id) AS parent_table
FROM sys.foreign_keys fk
WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) IN ('Sales','Purchasing','Warehouse')
   OR OBJECT_SCHEMA_NAME(fk.referenced_object_id) IN ('Sales','Purchasing','Warehouse')
ORDER BY parent_table, child_table;
