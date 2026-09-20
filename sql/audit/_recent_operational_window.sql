USE WideWorldImporters;
DECLARE @asof date=(SELECT MAX(OrderDate) FROM Sales.Orders);
SELECT @asof AS asof_date,
       SUM(CASE WHEN OrderDate>=DATEADD(day,-30,@asof) THEN 1 ELSE 0 END) orders_last_30d,
       SUM(CASE WHEN OrderDate>=DATEADD(day,-30,@asof) AND PickingCompletedWhen IS NULL THEN 1 ELSE 0 END) unpicked_last_30d,
       SUM(CASE WHEN OrderDate>=DATEADD(day,-30,@asof) AND ExpectedDeliveryDate<@asof AND PickingCompletedWhen IS NULL THEN 1 ELSE 0 END) overdue_unpicked_last_30d
FROM Sales.Orders;
SELECT SUM(CASE WHEN i.InvoiceDate>=DATEADD(day,-30,@asof) THEN 1 ELSE 0 END) invoices_last_30d,
       SUM(CASE WHEN i.InvoiceDate>=DATEADD(day,-30,@asof) AND i.ConfirmedDeliveryTime IS NOT NULL AND CAST(i.ConfirmedDeliveryTime AS date)>o.ExpectedDeliveryDate THEN 1 ELSE 0 END) late_last_30d
FROM Sales.Invoices i JOIN Sales.Orders o ON o.OrderID=i.OrderID;
