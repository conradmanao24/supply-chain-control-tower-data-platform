import os,json,pymssql,psycopg2
pg=psycopg2.connect(host=os.environ["DWH_HOST"],port=int(os.environ.get("DWH_PORT","5432")),dbname=os.environ["DWH_DB"],user=os.environ["DWH_USER"],password=os.environ["DWH_PASSWORD"])
with pg.cursor() as cur:
    cur.execute("SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name='supply_chain_incremental_pipeline'")
    cutoff=cur.fetchone()[0]
ms=pymssql.connect(server=os.environ["WWI_HOST"],port=int(os.environ.get("WWI_PORT","1433")),user="sa",password=os.environ["MSSQL_SA_PASSWORD"],database=os.environ["WWI_DATABASE"],autocommit=True)
queries={
"order_line":"SELECT COUNT_BIG(*) FROM Sales.OrderLines l JOIN Sales.Orders o ON o.OrderID=l.OrderID WHERE o.OrderDate < CAST(%s AS date)",
"sale_line":"SELECT COUNT_BIG(*) FROM Sales.InvoiceLines l JOIN Sales.Invoices i ON i.InvoiceID=l.InvoiceID WHERE i.InvoiceDate < CAST(%s AS date)",
"inventory_movement":"SELECT COUNT_BIG(*) FROM Warehouse.StockItemTransactions WHERE TransactionOccurredWhen < %s",
"order_state":"SELECT COUNT_BIG(*) FROM Sales.Orders WHERE OrderDate < CAST(%s AS date)",
"invoice_delivery":"SELECT COUNT_BIG(*) FROM Sales.Invoices WHERE InvoiceDate < CAST(%s AS date)",
}
out={"cutoff":str(cutoff)}
m=ms.cursor()
with pg.cursor() as p:
    for name,sql in queries.items():
        m.execute(sql,(cutoff,))
        s=int(m.fetchone()[0])
        p.execute(f"SELECT COUNT(*) FROM staging.{name}")
        t=int(p.fetchone()[0])
        out[name]={"source":s,"target":t,"match":s==t}
print(json.dumps(out,default=str))
ms.close(); pg.close()
