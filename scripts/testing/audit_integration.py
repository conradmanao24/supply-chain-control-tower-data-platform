import os
import json
import pymssql
from datetime import datetime

conn = pymssql.connect(
    server=os.environ['WWI_HOST'],
    port=int(os.environ['WWI_PORT']),
    user=os.environ['WWI_SOURCE_USER'],
    password=os.environ['WWI_SOURCE_PASSWORD'],
    database=os.environ['WWI_DATABASE'],
    autocommit=True,
)
cur = conn.cursor()
cur.execute("""
SELECT p.name AS proc_name,
       prm.parameter_id,
       prm.name AS parameter_name,
       TYPE_NAME(prm.user_type_id) AS data_type
FROM sys.procedures p
JOIN sys.schemas s ON p.schema_id = s.schema_id
LEFT JOIN sys.parameters prm ON p.object_id = prm.object_id
WHERE s.name = N'Integration'
ORDER BY p.name, prm.parameter_id;
""")
rows = cur.fetchall()
procs = {}
for proc_name, parameter_id, parameter_name, data_type in rows:
    procs.setdefault(proc_name, [])
    if parameter_id is not None:
        procs[proc_name].append({
            'id': int(parameter_id),
            'name': parameter_name,
            'type': data_type,
        })

start = datetime(2026, 9, 14)
end = datetime(2026, 9, 15)
report = []
for proc_name, params in procs.items():
    placeholders = ', '.join(f"{p['name']}=%s" for p in params)
    sql = f"EXEC Integration.[{proc_name}] {placeholders}" if placeholders else f"EXEC Integration.[{proc_name}]"
    values = []
    for p in params:
        if p['type'] in ('datetime', 'datetime2', 'date', 'smalldatetime'):
            values.append(start if len(values) == 0 else end)
        else:
            raise RuntimeError(f"Unexpected parameter type for {proc_name}: {p}")
    c2 = conn.cursor()
    c2.execute(sql, tuple(values))
    columns = [d[0] for d in c2.description] if c2.description else []
    count = 0
    sample = None
    while True:
        batch = c2.fetchmany(1000)
        if not batch:
            break
        if sample is None and batch:
            sample = [str(v) if v is not None else None for v in batch[0]]
        count += len(batch)
    report.append({
        'procedure': f'Integration.{proc_name}',
        'parameters': params,
        'window': {'last_cutoff': start.isoformat(), 'new_cutoff': end.isoformat()},
        'columns': columns,
        'row_count': count,
        'sample_row': sample,
    })
    print(f"{proc_name}: rows={count}, columns={len(columns)}")

out = os.environ.get('INGESTION_AUDIT_OUT', '/tmp/integration-audit.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(report, f, indent=2)
print(f"AUDIT_JSON={out}")
conn.close()