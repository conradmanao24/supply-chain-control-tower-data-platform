SET NOCOUNT ON;

SELECT
    p.name AS procedure_name,
    ISNULL(ps.execution_count, 0) AS execution_count
FROM sys.procedures p
LEFT JOIN sys.dm_exec_procedure_stats ps
  ON ps.database_id = DB_ID()
 AND ps.object_id = p.object_id
WHERE SCHEMA_NAME(p.schema_id) = N'ControlTower'
  AND p.name IN (
      N'GetOrderCurrentState',
      N'GetDeliveryCurrentState',
      N'GetProcurementCurrentState',
      N'GetInventoryCurrentState'
  )
ORDER BY p.name;
GO
