USE WideWorldImporters;
SELECT GETDATE() AS db_now, MAX(OrderDate) AS max_order_date, COUNT_BIG(*) AS orders FROM Sales.Orders;
SELECT COUNT(*) AS temporal_current_tables FROM sys.tables WHERE temporal_type=2;
SELECT COUNT(*) AS simulation_triggers FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%';
SELECT COUNT(*) AS bad_fks FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1;
