USE WideWorldImporters;
SELECT MAX(OrderDate) AS max_order_date, DATEDIFF(day,MAX(OrderDate),'2026-09-15') AS days_remaining FROM Sales.Orders;
SELECT COUNT(*) AS temporal_current_tables FROM sys.tables WHERE temporal_type=2;
SELECT COUNT(*) AS sim_triggers FROM sys.triggers WHERE name LIKE 'DataLoadSimulation%';
