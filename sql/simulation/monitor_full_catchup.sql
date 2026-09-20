SET NOCOUNT ON;
USE [WideWorldImporters];
SELECT
    CONVERT(varchar(10), MAX(OrderDate), 120) AS max_order_date,
    COUNT_BIG(*) AS order_rows,
    (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2) AS temporal_current_tables,
    (SELECT COUNT(*) FROM sys.triggers WHERE name LIKE '%[_]DataLoad[_]Modify') AS simulation_triggers,
    (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_disabled = 1) AS disabled_foreign_keys,
    (SELECT COUNT(*) FROM sys.foreign_keys WHERE is_not_trusted = 1) AS untrusted_foreign_keys
FROM Sales.Orders;
