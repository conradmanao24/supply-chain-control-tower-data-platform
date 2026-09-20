SET NOCOUNT ON;
USE [WideWorldImporters];

IF EXISTS (SELECT 1 FROM sys.triggers WHERE name LIKE '%[_]DataLoad[_]Modify')
   OR (SELECT COUNT(*) FROM sys.tables WHERE temporal_type = 2) < 17
BEGIN
    EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures;
END;
