USE WideWorldImporters_Distribution;
DECLARE @cutoff datetime2(7)='2023-01-01T00:00:00';
SELECT COUNT_BIG(*) AS total_rows,
       SUM(CASE WHEN RecordedWhen>=@cutoff THEN 1 ELSE 0 END) AS keep_by_recorded,
       SUM(CASE WHEN ValidTo>=@cutoff THEN 1 ELSE 0 END) AS keep_by_validto,
       SUM(CASE WHEN RecordedWhen<@cutoff AND ValidTo>=@cutoff THEN 1 ELSE 0 END) AS cross_boundary
FROM Warehouse.ColdRoomTemperatures_Archive;
