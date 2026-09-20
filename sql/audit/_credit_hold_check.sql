USE WideWorldImporters;
SET NOCOUNT ON;
SELECT SUM(CASE WHEN IsOnCreditHold=1 THEN 1 ELSE 0 END) customers_on_credit_hold, COUNT(*) customers FROM Sales.Customers;
SELECT TOP 20 CustomerID,CustomerName,CreditLimit,IsOnCreditHold,PaymentDays FROM Sales.Customers WHERE IsOnCreditHold=1 ORDER BY CustomerID;
