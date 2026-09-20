import os
import sys
from decimal import Decimal
import pymssql
import psycopg2

ms = pymssql.connect(
    server=os.environ['WWI_HOST'], port=int(os.environ['WWI_PORT']),
    user=os.environ['WWI_SOURCE_USER'], password=os.environ['WWI_SOURCE_PASSWORD'],
    database=os.environ['WWI_DATABASE'], autocommit=True,
)
pg = psycopg2.connect(
    host=os.environ['DWH_HOST'], port=int(os.environ['DWH_PORT']),
    dbname=os.environ['DWH_DB'], user=os.environ['DWH_USER'], password=os.environ['DWH_PASSWORD'],
)
errors=[]

mcur=ms.cursor(); mcur.execute('EXEC ControlTowerExtract.GetReconciliationCounts')
source_counts={name:int(count) for name,count in mcur.fetchall()}
pcur=pg.cursor()
for name, expected in source_counts.items():
    pcur.execute(f'SELECT COUNT(*) FROM staging.{name}')
    actual=int(pcur.fetchone()[0])
    status='PASS' if actual==expected else 'FAIL'
    print(f'{status} {name}: source={expected} target={actual}')
    if actual != expected: errors.append(f'{name} count mismatch')

# Cold-room raw -> aggregate preservation
mcur.execute('''
SELECT COUNT_BIG(*), MIN(Temperature), MAX(Temperature), MIN(RecordedWhen), MAX(RecordedWhen)
FROM (
  SELECT Temperature, RecordedWhen FROM Warehouse.ColdRoomTemperatures_Archive
  UNION ALL
  SELECT Temperature, RecordedWhen FROM Warehouse.ColdRoomTemperatures
) x
''')
cold_raw_count,cold_min,cold_max,cold_first,cold_last=mcur.fetchone()
pcur.execute('''
SELECT COUNT(*), COALESCE(SUM(reading_count),0), MIN(min_temperature), MAX(max_temperature),
       MIN(bucket_start), MAX(bucket_start),
       COUNT(*) FILTER (WHERE NOT (min_temperature <= avg_temperature AND avg_temperature <= max_temperature)),
       COUNT(*) FILTER (WHERE reading_count <= 0),
       COUNT(*) FILTER (WHERE EXTRACT(MINUTE FROM bucket_start)::int % 5 <> 0 OR EXTRACT(SECOND FROM bucket_start) <> 0),
       COUNT(*) FILTER (WHERE max_gap_seconds < 0)
FROM staging.coldroom_5m
''')
cold=pcur.fetchone()
print(f'coldroom buckets={cold[0]} raw_readings={cold_raw_count} summed_readings={cold[1]} source_min={cold_min} agg_min={cold[2]} source_max={cold_max} agg_max={cold[3]}')
if int(cold[1]) != int(cold_raw_count): errors.append('coldroom reading_count reconciliation')
if Decimal(cold[2]) != Decimal(cold_min): errors.append('coldroom min preservation')
if Decimal(cold[3]) != Decimal(cold_max): errors.append('coldroom max preservation')
if any(int(v) != 0 for v in cold[6:]): errors.append(f'coldroom aggregate invariant failure {cold[6:]}')

# Vehicle raw -> aggregate preservation
mcur.execute('SELECT COUNT_BIG(*), MIN(Temperature), MAX(Temperature), MIN(RecordedWhen), MAX(RecordedWhen) FROM Warehouse.VehicleTemperatures')
veh_raw_count,veh_min,veh_max,veh_first,veh_last=mcur.fetchone()
pcur.execute('''
SELECT COUNT(*), COALESCE(SUM(reading_count),0), MIN(min_temperature), MAX(max_temperature),
       MIN(bucket_start), MAX(bucket_start),
       COUNT(*) FILTER (WHERE NOT (min_temperature <= avg_temperature AND avg_temperature <= max_temperature)),
       COUNT(*) FILTER (WHERE reading_count <= 0),
       COUNT(*) FILTER (WHERE EXTRACT(MINUTE FROM bucket_start)::int % 5 <> 0 OR EXTRACT(SECOND FROM bucket_start) <> 0),
       COUNT(*) FILTER (WHERE max_gap_seconds < 0)
FROM staging.vehicle_5m
''')
veh=pcur.fetchone()
print(f'vehicle buckets={veh[0]} raw_readings={veh_raw_count} summed_readings={veh[1]} source_min={veh_min} agg_min={veh[2]} source_max={veh_max} agg_max={veh[3]}')
if int(veh[1]) != int(veh_raw_count): errors.append('vehicle reading_count reconciliation')
if Decimal(veh[2]) != Decimal(veh_min): errors.append('vehicle min preservation')
if Decimal(veh[3]) != Decimal(veh_max): errors.append('vehicle max preservation')
if any(int(v) != 0 for v in veh[6:]): errors.append(f'vehicle aggregate invariant failure {veh[6:]}')

# Privacy/minimization guard: no forbidden sensitive column names in staging.
pcur.execute("""
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema='staging'
  AND lower(column_name) ~ '(password|bank_account|email|phone|fax|photo|internal_comment)'
ORDER BY table_name,column_name
""")
forbidden=pcur.fetchall()
print('sensitive_columns_found=', forbidden)
if forbidden: errors.append('sensitive staging columns present')

ms.close(); pg.close()
if errors:
    print('INGESTION_RECONCILIATION=FAIL')
    for e in errors: print(' -',e)
    sys.exit(1)
print('INGESTION_RECONCILIATION=PASS')