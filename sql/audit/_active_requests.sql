SELECT session_id,status,command,percent_complete,wait_type,wait_time,blocking_session_id,DB_NAME(database_id) AS db_name,
       LEFT(REPLACE(REPLACE(t.text,CHAR(13),' '),CHAR(10),' '),300) AS sql_text
FROM sys.dm_exec_requests r CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE session_id > 50 AND session_id <> @@SPID;
