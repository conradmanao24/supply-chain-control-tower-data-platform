USE WideWorldImporters;
SET NOCOUNT ON;
SELECT s.name AS schema_name,t.name AS table_name,c.name AS column_name,ty.name AS data_type
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE c.name LIKE '%Password%' OR c.name LIKE '%Bank%' OR c.name LIKE '%Phone%' OR c.name LIKE '%Fax%' OR c.name LIKE '%Email%' OR c.name LIKE '%Photo%' OR c.name LIKE '%Credit%'
ORDER BY s.name,t.name,c.column_id;
