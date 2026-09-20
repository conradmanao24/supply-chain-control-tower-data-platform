USE [WideWorldImporters];
GO
SET NOCOUNT ON;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[GetOrderCurrentState]
    @EntityID int
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT o.OrderID, o.CustomerID, o.OrderDate, o.ExpectedDeliveryDate,
           o.IsUndersupplyBackordered, o.BackorderOrderID,
           o.PickingCompletedWhen, o.LastEditedWhen
    FROM Sales.Orders AS o
    WHERE o.OrderID=@EntityID;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[GetDeliveryCurrentState]
    @EntityID int
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT i.InvoiceID, i.OrderID, i.CustomerID, i.DeliveryMethodID,
           i.InvoiceDate, i.DeliveryRun, i.RunPosition,
           i.ReturnedDeliveryData, i.ConfirmedDeliveryTime,
           i.ConfirmedReceivedBy, i.LastEditedWhen
    FROM Sales.Invoices AS i
    WHERE i.InvoiceID=@EntityID;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[GetProcurementCurrentState]
    @EntityID int
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT po.PurchaseOrderID, po.SupplierID, po.OrderDate,
           po.ExpectedDeliveryDate, po.IsOrderFinalized, po.LastEditedWhen,
           ISNULL(a.OrderedOuters,0) AS OrderedOuters,
           ISNULL(a.ReceivedOuters,0) AS ReceivedOuters,
           ISNULL(a.UnderReceivedLineCount,0) AS UnderReceivedLineCount
    FROM Purchasing.PurchaseOrders AS po
    OUTER APPLY
    (
        SELECT SUM(CONVERT(bigint,pol.OrderedOuters)) AS OrderedOuters,
               SUM(CONVERT(bigint,pol.ReceivedOuters)) AS ReceivedOuters,
               SUM(CASE WHEN pol.ReceivedOuters < pol.OrderedOuters THEN 1 ELSE 0 END) AS UnderReceivedLineCount
        FROM Purchasing.PurchaseOrderLines AS pol
        WHERE pol.PurchaseOrderID=po.PurchaseOrderID
    ) AS a
    WHERE po.PurchaseOrderID=@EntityID;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[GetInventoryCurrentState]
    @EntityID int
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT h.StockItemID, si.StockItemName, h.QuantityOnHand,
           h.LastStocktakeQuantity, h.ReorderLevel, h.TargetStockLevel,
           h.LastEditedWhen
    FROM Warehouse.StockItemHoldings AS h
    JOIN Warehouse.StockItems AS si ON si.StockItemID=h.StockItemID
    WHERE h.StockItemID=@EntityID;
END;
GO
CREATE OR ALTER PROCEDURE [ControlTower].[CompleteEventConversation]
    @ConversationHandle uniqueidentifier
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    IF @ConversationHandle IS NOT NULL
        END CONVERSATION @ConversationHandle;
END;
GO
GRANT EXECUTE ON OBJECT::[ControlTower].[GetOrderCurrentState] TO [sct_event_consumer];
GRANT EXECUTE ON OBJECT::[ControlTower].[GetDeliveryCurrentState] TO [sct_event_consumer];
GRANT EXECUTE ON OBJECT::[ControlTower].[GetProcurementCurrentState] TO [sct_event_consumer];
GRANT EXECUTE ON OBJECT::[ControlTower].[GetInventoryCurrentState] TO [sct_event_consumer];
GRANT EXECUTE ON OBJECT::[ControlTower].[CompleteEventConversation] TO [sct_event_consumer];
GO