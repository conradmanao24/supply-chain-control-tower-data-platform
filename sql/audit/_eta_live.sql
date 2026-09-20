USE WideWorldImporters;
SELECT SYSDATETIME() AS db_now, MAX(OrderDate) AS max_order_date, COUNT_BIG(*) AS orders FROM Sales.Orders;
SELECT DATEDIFF(day, MAX(OrderDate), '2026-09-15') AS days_remaining FROM Sales.Orders;
