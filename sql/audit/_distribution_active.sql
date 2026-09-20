SELECT r.session_id,r.status,r.command,r.wait_type,r.wait_time,r.cpu_time,r.total_elapsed_time,DB_NAME(r.database_id) AS db_name,LEFT(t.text,240) AS sql_text
FROM sys.dm_exec_requests r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE DB_NAME(r.database_id)='WideWorldImporters_Distribution' AND r.session_id<>@@SPID;
