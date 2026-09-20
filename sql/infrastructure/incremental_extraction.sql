USE [WideWorldImporters];
GO

CREATE OR ALTER PROCEDURE [ControlTowerExtract].[GetCustomerCurrentDelta]
    @LastCutoff datetime2(7),
    @NewCutoff datetime2(7)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT *
    FROM [ControlTowerExtract].[CustomerCurrent]
    WHERE ValidFrom > @LastCutoff
      AND ValidFrom <= @NewCutoff
    ORDER BY CustomerID;
END;
GO

CREATE OR ALTER PROCEDURE [ControlTowerExtract].[GetCustomerHistoryDelta]
    @LastCutoff datetime2(7),
    @NewCutoff datetime2(7)
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SELECT *
    FROM [ControlTowerExtract].[CustomerHistory]
    WHERE ValidFrom > @LastCutoff
      AND ValidFrom <= @NewCutoff
    ORDER BY CustomerID, ValidFrom;
END;
GO

GRANT EXECUTE ON OBJECT::[ControlTowerExtract].[GetCustomerCurrentDelta] TO [sct_airflow_reader];
GRANT EXECUTE ON OBJECT::[ControlTowerExtract].[GetCustomerHistoryDelta] TO [sct_airflow_reader];
GO
