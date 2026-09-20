-- Required sqlcmd variable supplied by the bootstrap caller:
--   DatabaseName

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_ID(N'$(DatabaseName)') IS NULL
    THROW 51000, 'WideWorldImporters database was not found.', 1;

IF NOT EXISTS (
    SELECT 1
    FROM sys.databases
    WHERE name = N'$(DatabaseName)'
      AND state_desc = N'ONLINE'
)
    THROW 51001, 'WideWorldImporters database is not ONLINE.', 1;

USE [$(DatabaseName)];

DECLARE @RequiredSchemas TABLE (SchemaName sysname PRIMARY KEY);
INSERT INTO @RequiredSchemas (SchemaName)
VALUES
    (N'Application'),
    (N'Purchasing'),
    (N'Sales'),
    (N'Warehouse'),
    (N'DataLoadSimulation');

IF EXISTS (
    SELECT 1
    FROM @RequiredSchemas r
    LEFT JOIN sys.schemas s ON s.name = r.SchemaName
    WHERE s.schema_id IS NULL
)
BEGIN
    SELECT r.SchemaName AS MissingSchema
    FROM @RequiredSchemas r
    LEFT JOIN sys.schemas s ON s.name = r.SchemaName
    WHERE s.schema_id IS NULL;

    THROW 51002, 'One or more required WWI schemas are missing.', 1;
END;

DECLARE @RequiredTables TABLE (
    SchemaName sysname NOT NULL,
    TableName sysname NOT NULL,
    PRIMARY KEY (SchemaName, TableName)
);

INSERT INTO @RequiredTables (SchemaName, TableName)
VALUES
    (N'Sales', N'Customers'),
    (N'Sales', N'Orders'),
    (N'Sales', N'OrderLines'),
    (N'Sales', N'Invoices'),
    (N'Sales', N'InvoiceLines'),
    (N'Sales', N'CustomerTransactions'),
    (N'Purchasing', N'Suppliers'),
    (N'Purchasing', N'PurchaseOrders'),
    (N'Purchasing', N'PurchaseOrderLines'),
    (N'Purchasing', N'SupplierTransactions'),
    (N'Warehouse', N'StockItems'),
    (N'Warehouse', N'StockItemHoldings'),
    (N'Warehouse', N'StockItemTransactions');

IF EXISTS (
    SELECT 1
    FROM @RequiredTables r
    LEFT JOIN sys.schemas s ON s.name = r.SchemaName
    LEFT JOIN sys.tables t ON t.schema_id = s.schema_id AND t.name = r.TableName
    WHERE t.object_id IS NULL
)
BEGIN
    SELECT r.SchemaName, r.TableName
    FROM @RequiredTables r
    LEFT JOIN sys.schemas s ON s.name = r.SchemaName
    LEFT JOIN sys.tables t ON t.schema_id = s.schema_id AND t.name = r.TableName
    WHERE t.object_id IS NULL;

    THROW 51003, 'One or more required WWI tables are missing.', 1;
END;

IF OBJECT_ID(N'DataLoadSimulation.PopulateDataToCurrentDate', N'P') IS NULL
    THROW 51004, 'Official WWI PopulateDataToCurrentDate procedure was not found.', 1;

SELECT
    DB_NAME() AS DatabaseName,
    CAST(SERVERPROPERTY(N'ProductVersion') AS nvarchar(128)) AS SqlServerVersion,
    CAST(SERVERPROPERTY(N'Edition') AS nvarchar(128)) AS SqlServerEdition,
    (SELECT COUNT(*) FROM sys.tables) AS TableCount,
    (SELECT COUNT(*) FROM sys.foreign_keys) AS ForeignKeyCount,
    N'PASS' AS ValidationStatus;
