USE WideWorldImporters;

WITH c AS (
    SELECT ColdRoomSensorNumber,
           RecordedWhen,
           LAG(RecordedWhen) OVER (PARTITION BY ColdRoomSensorNumber ORDER BY RecordedWhen) AS prev_time
    FROM Warehouse.ColdRoomTemperatures_Archive
    WHERE RecordedWhen >= '2026-09-01' AND RecordedWhen < '2026-09-16'
), cg AS (
    SELECT ColdRoomSensorNumber,
           DATEDIFF(SECOND, prev_time, RecordedWhen) AS gap_seconds
    FROM c
    WHERE prev_time IS NOT NULL
)
SELECT 'ColdRoom' AS telemetry,
       ColdRoomSensorNumber AS sensor,
       COUNT_BIG(*) AS intervals,
       MIN(gap_seconds) AS min_gap_sec,
       AVG(CAST(gap_seconds AS decimal(18,2))) AS avg_gap_sec,
       MAX(gap_seconds) AS max_gap_sec
FROM cg
GROUP BY ColdRoomSensorNumber
ORDER BY sensor;

WITH v AS (
    SELECT VehicleRegistration,
           ChillerSensorNumber,
           RecordedWhen,
           LAG(RecordedWhen) OVER (PARTITION BY VehicleRegistration, ChillerSensorNumber ORDER BY RecordedWhen) AS prev_time
    FROM Warehouse.VehicleTemperatures
    WHERE RecordedWhen >= '2026-09-01' AND RecordedWhen < '2026-09-16'
), vg AS (
    SELECT VehicleRegistration, ChillerSensorNumber,
           DATEDIFF(SECOND, prev_time, RecordedWhen) AS gap_seconds
    FROM v
    WHERE prev_time IS NOT NULL
)
SELECT 'Vehicle' AS telemetry,
       VehicleRegistration,
       ChillerSensorNumber,
       COUNT_BIG(*) AS intervals,
       MIN(gap_seconds) AS min_gap_sec,
       AVG(CAST(gap_seconds AS decimal(18,2))) AS avg_gap_sec,
       MAX(gap_seconds) AS max_gap_sec
FROM vg
GROUP BY VehicleRegistration, ChillerSensorNumber
ORDER BY VehicleRegistration, ChillerSensorNumber;
