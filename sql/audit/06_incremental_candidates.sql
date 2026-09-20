SET NOCOUNT ON;
USE [WideWorldImporters];

;WITH table_features AS (
    SELECT
        s.name AS schema_name,
        t.name AS table_name,
        t.object_id,
        MAX(CASE WHEN c.name = 'LastEditedWhen' THEN 1 ELSE 0 END) AS has_last_edited_when,
        MAX(CASE WHEN c.is_identity = 1 THEN 1 ELSE 0 END) AS has_identity,
        MAX(CASE WHEN ty.name IN ('date','datetime','datetime2','smalldatetime','datetimeoffset')
                  AND (c.name LIKE '%Date%' OR c.name LIKE '%When%' OR c.name LIKE '%Time%') THEN 1 ELSE 0 END) AS has_business_time_candidate,
        MAX(CASE WHEN c.name = 'ValidFrom' THEN 1 ELSE 0 END) AS has_valid_from,
        MAX(CASE WHEN c.name = 'ValidTo' THEN 1 ELSE 0 END) AS has_valid_to,
        t.temporal_type_desc
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    JOIN sys.columns c ON c.object_id = t.object_id
    JOIN sys.types ty ON ty.user_type_id = c.user_type_id
    WHERE t.is_ms_shipped = 0
      AND s.name IN ('Application','Purchasing','Sales','Warehouse')
    GROUP BY s.name, t.name, t.object_id, t.temporal_type_desc
), pk_cols AS (
    SELECT
        t.object_id,
        STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal) AS primary_key_columns
    FROM sys.key_constraints kc
    JOIN sys.tables t ON t.object_id = kc.parent_object_id
    JOIN sys.index_columns ic ON ic.object_id = t.object_id AND ic.index_id = kc.unique_index_id
    JOIN sys.columns c ON c.object_id = t.object_id AND c.column_id = ic.column_id
    WHERE kc.type = 'PK'
    GROUP BY t.object_id
), identity_cols AS (
    SELECT object_id, STRING_AGG(name, ',') AS identity_columns
    FROM sys.columns
    WHERE is_identity = 1
    GROUP BY object_id
)
SELECT
    f.schema_name,
    f.table_name,
    COALESCE(pk.primary_key_columns, '') AS primary_key_columns,
    COALESCE(i.identity_columns, '') AS identity_columns,
    f.has_last_edited_when,
    f.has_business_time_candidate,
    f.has_valid_from,
    f.has_valid_to,
    f.temporal_type_desc
FROM table_features f
LEFT JOIN pk_cols pk ON pk.object_id = f.object_id
LEFT JOIN identity_cols i ON i.object_id = f.object_id
WHERE f.table_name NOT LIKE '%[_]Archive'
ORDER BY f.schema_name, f.table_name;
