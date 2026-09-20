from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime
from decimal import Decimal

import pymssql
import psycopg2
from psycopg2.extras import Json

from realtime.alerts import evaluate_event
from realtime.deadlines import sync_event_deadlines

EVENT_MESSAGE = "//SupplyChainControlTower/Event"
END_DIALOG = "http://schemas.microsoft.com/SQL/ServiceBroker/EndDialog"
BROKER_ERROR = "http://schemas.microsoft.com/SQL/ServiceBroker/Error"
WAIT_MS = max(1000, int(os.environ.get("REALTIME_WAIT_TIMEOUT_MS", "30000")))
MAX_ATTEMPTS = max(1, int(os.environ.get("REALTIME_EVENT_MAX_ATTEMPTS", "3")))
RELIABILITY_LOCK_KEY = 807008
HISTORY_RETENTION_HOURS = max(1, int(os.environ.get("COLD_CHAIN_HISTORY_RETENTION_HOURS", "24")))
HISTORY_PRUNE_INTERVAL_SECONDS = max(60, int(os.environ.get("COLD_CHAIN_HISTORY_PRUNE_INTERVAL_SECONDS", "900")))
_history_last_prune = 0.0


def sql_connect():
    return pymssql.connect(
        server=os.environ["WWI_HOST"],
        port=int(os.environ.get("WWI_PORT", "1433")),
        user=os.environ["WWI_EVENT_USER"],
        password=os.environ["WWI_EVENT_PASSWORD"],
        database=os.environ["WWI_DATABASE"],
        autocommit=False,
        login_timeout=10,
        timeout=max(35, WAIT_MS // 1000 + 10),
    )


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def decode_body(body):
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    if isinstance(body, (bytes, bytearray, memoryview)):
        raw = bytes(body)
        for enc in ("utf-16le", "utf-8"):
            try:
                return raw.decode(enc).rstrip("\x00")
            except UnicodeDecodeError:
                pass
    return str(body)


def iso_dt(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def receive_one(conn):
    cur = conn.cursor(as_dict=True)
    cur.execute(
        f"""
        WAITFOR (
            RECEIVE TOP (1)
                conversation_handle,
                message_type_name,
                message_body
            FROM [ControlTower].[EventConsumerQueue]
        ), TIMEOUT {WAIT_MS}
        """
    )
    return cur.fetchone()


def complete_conversation(conn, handle):
    cur = conn.cursor()
    cur.execute("EXEC [ControlTower].[CompleteEventConversation] @ConversationHandle=%s", (handle,))


def source_row(conn, proc: str, entity_id: int):
    cur = conn.cursor(as_dict=True)
    cur.execute(f"EXEC [ControlTower].[{proc}] @EntityID=%s", (int(entity_id),))
    return cur.fetchone()


def upsert_order(pg, row, event_id):
    if row is None:
        return
    pg.execute("""
        INSERT INTO realtime.current_order_state
        (order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,backorder_order_id,picking_completed_when,last_edited_when,source_event_id,refreshed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (order_id) DO UPDATE SET
          customer_id=EXCLUDED.customer_id,order_date=EXCLUDED.order_date,
          expected_delivery_date=EXCLUDED.expected_delivery_date,
          is_undersupply_backordered=EXCLUDED.is_undersupply_backordered,
          backorder_order_id=EXCLUDED.backorder_order_id,
          picking_completed_when=EXCLUDED.picking_completed_when,
          last_edited_when=EXCLUDED.last_edited_when,
          source_event_id=EXCLUDED.source_event_id,refreshed_at=now()
    """, (row['OrderID'],row['CustomerID'],row['OrderDate'],row['ExpectedDeliveryDate'],row['IsUndersupplyBackordered'],row['BackorderOrderID'],row['PickingCompletedWhen'],row['LastEditedWhen'],event_id))


def upsert_delivery(pg, row, event_id):
    if row is None:
        return
    returned = None
    if row['ReturnedDeliveryData']:
        returned = Json(json.loads(row['ReturnedDeliveryData']))
    pg.execute("""
        INSERT INTO realtime.current_delivery_state
        (invoice_id,order_id,customer_id,delivery_method_id,invoice_date,delivery_run,run_position,returned_delivery_data,confirmed_delivery_time,confirmed_received_by,last_edited_when,source_event_id,refreshed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (invoice_id) DO UPDATE SET
          order_id=EXCLUDED.order_id,customer_id=EXCLUDED.customer_id,
          delivery_method_id=EXCLUDED.delivery_method_id,invoice_date=EXCLUDED.invoice_date,
          delivery_run=EXCLUDED.delivery_run,run_position=EXCLUDED.run_position,
          returned_delivery_data=EXCLUDED.returned_delivery_data,
          confirmed_delivery_time=EXCLUDED.confirmed_delivery_time,
          confirmed_received_by=EXCLUDED.confirmed_received_by,
          last_edited_when=EXCLUDED.last_edited_when,source_event_id=EXCLUDED.source_event_id,
          refreshed_at=now()
    """, (row['InvoiceID'],row['OrderID'],row['CustomerID'],row['DeliveryMethodID'],row['InvoiceDate'],row['DeliveryRun'],row['RunPosition'],returned,row['ConfirmedDeliveryTime'],row['ConfirmedReceivedBy'],row['LastEditedWhen'],event_id))


def upsert_procurement(pg, row, event_id):
    if row is None:
        return
    pg.execute("""
        INSERT INTO realtime.current_procurement_state
        (purchase_order_id,supplier_id,order_date,expected_delivery_date,is_order_finalized,ordered_outers,received_outers,under_received_line_count,last_edited_when,source_event_id,refreshed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (purchase_order_id) DO UPDATE SET
          supplier_id=EXCLUDED.supplier_id,order_date=EXCLUDED.order_date,
          expected_delivery_date=EXCLUDED.expected_delivery_date,
          is_order_finalized=EXCLUDED.is_order_finalized,
          ordered_outers=EXCLUDED.ordered_outers,received_outers=EXCLUDED.received_outers,
          under_received_line_count=EXCLUDED.under_received_line_count,
          last_edited_when=EXCLUDED.last_edited_when,source_event_id=EXCLUDED.source_event_id,
          refreshed_at=now()
    """, (row['PurchaseOrderID'],row['SupplierID'],row['OrderDate'],row['ExpectedDeliveryDate'],row['IsOrderFinalized'],row['OrderedOuters'],row['ReceivedOuters'],row['UnderReceivedLineCount'],row['LastEditedWhen'],event_id))


def upsert_inventory(pg, row, event_id):
    if row is None:
        return
    pg.execute("""
        INSERT INTO realtime.current_inventory_state
        (stock_item_id,stock_item_name,quantity_on_hand,last_stocktake_quantity,reorder_level,target_stock_level,last_edited_when,source_event_id,refreshed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (stock_item_id) DO UPDATE SET
          stock_item_name=EXCLUDED.stock_item_name,quantity_on_hand=EXCLUDED.quantity_on_hand,
          last_stocktake_quantity=EXCLUDED.last_stocktake_quantity,reorder_level=EXCLUDED.reorder_level,
          target_stock_level=EXCLUDED.target_stock_level,last_edited_when=EXCLUDED.last_edited_when,
          source_event_id=EXCLUDED.source_event_id,refreshed_at=now()
    """, (row['StockItemID'],row['StockItemName'],row['QuantityOnHand'],row['LastStocktakeQuantity'],row['ReorderLevel'],row['TargetStockLevel'],row['LastEditedWhen'],event_id))


def upsert_sensor(pg, event_type, key, event_id):
    if event_type.startswith('telemetry.coldroom.'):
        sensor_type='coldroom'; vehicle=None; sensor=int(key['sensor_number']); sensor_key=f'coldroom:{sensor}'
    else:
        sensor_type='vehicle'; vehicle=str(key['vehicle_registration']); sensor=int(key['sensor_number']); sensor_key=f'vehicle:{vehicle}:{sensor}'
    recorded=iso_dt(key.get('last_recorded_when') or key.get('recorded_when'))
    temperature=key.get('latest_temperature')
    if recorded is None or temperature is None:
        return False
    temperature_decimal=Decimal(str(temperature))
    pg.execute("""
        INSERT INTO realtime.sensor_reading_history
        (sensor_key,sensor_type,vehicle_registration,sensor_number,recorded_when,temperature,source_event_id,inserted_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (sensor_key,recorded_when) DO NOTHING
    """, (sensor_key,sensor_type,vehicle,sensor,recorded,temperature_decimal,event_id))
    pg.execute("""
        INSERT INTO realtime.current_sensor_state
        (sensor_key,sensor_type,vehicle_registration,sensor_number,recorded_when,temperature,reading_count,value_basis,source_event_id,refreshed_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'event_latest',%s,now())
        ON CONFLICT (sensor_key) DO UPDATE SET
          recorded_when=EXCLUDED.recorded_when,temperature=EXCLUDED.temperature,
          reading_count=EXCLUDED.reading_count,value_basis='event_latest',
          source_event_id=EXCLUDED.source_event_id,refreshed_at=now()
        WHERE realtime.current_sensor_state.recorded_when <= EXCLUDED.recorded_when
    """, (sensor_key,sensor_type,vehicle,sensor,recorded,temperature_decimal,key.get('reading_count'),event_id))
    return True


def maybe_prune_sensor_history(pg):
    global _history_last_prune
    now_monotonic=time.monotonic()
    if now_monotonic - _history_last_prune < HISTORY_PRUNE_INTERVAL_SECONDS:
        return
    pg.execute(
        """
        DELETE FROM realtime.sensor_reading_history
        WHERE inserted_at < now() - (%s * interval '1 hour')
        """,
        (HISTORY_RETENTION_HOURS,),
    )
    _history_last_prune=now_monotonic


def process_event(sql_conn, pg_conn, payload):
    event_id=str(uuid.UUID(payload['event_id']))
    with pg_conn:
        pg=pg_conn.cursor()
        pg.execute("SELECT pg_advisory_xact_lock(%s)", (RELIABILITY_LOCK_KEY,))
        pg.execute("""
            INSERT INTO realtime.event_log
            (event_id,schema_version,event_type,entity_type,source_table,operation,occurred_at_utc,payload,processing_result)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'processing')
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
        """, (event_id,int(payload['schema_version']),payload['event_type'],payload['entity_type'],payload['source_table'],payload['operation'],payload['occurred_at_utc'],Json(payload)))
        if pg.fetchone() is None:
            return 'duplicate'
        event_type=payload['event_type']
        keys=payload.get('entity_keys') or []
        result='processed'
        mapping={
            'order.changed':('GetOrderCurrentState','order_id',upsert_order,'current_order_state'),
            'delivery.changed':('GetDeliveryCurrentState','invoice_id',upsert_delivery,'current_delivery_state'),
            'procurement.changed':('GetProcurementCurrentState','purchase_order_id',upsert_procurement,'current_procurement_state'),
            'inventory.changed':('GetInventoryCurrentState','stock_item_id',upsert_inventory,'current_inventory_state'),
        }
        if event_type in mapping:
            proc,pk,fn,table=mapping[event_type]
            for item in keys:
                entity_id=item.get('entity_id')
                if entity_id is None:
                    continue
                row=source_row(sql_conn,proc,int(entity_id))
                if row is None:
                    pg.execute(f'DELETE FROM realtime.{table} WHERE {pk}=%s',(int(entity_id),))
                else:
                    fn(pg,row,event_id)
        elif event_type.startswith('telemetry.coldroom.') or event_type.startswith('telemetry.vehicle.'):
            updated=sum(1 for item in keys if upsert_sensor(pg,event_type,item,event_id))
            maybe_prune_sensor_history(pg)
            result=f'sensor_projection:{updated}'
        elif payload.get('operation')=='DEADLINE':
            result='deadline_signal'
        else:
            result='ignored'
        evaluate_event(pg, payload)
        pg.execute("UPDATE realtime.event_log SET processing_result=%s,processed_at=now() WHERE event_id=%s",(result,event_id))
        return result


def dead_letter(conn, handle, message_type, body_text, error_message):
    cur=conn.cursor()
    cur.execute(
        "EXEC [ControlTower].[DeadLetterEvent] @ConversationHandle=%s,@MessageTypeName=%s,@MessageBody=%s,@ErrorMessage=%s",
        (handle,message_type,body_text,str(error_message)[:2048]),
    )


def main():
    print(f'REALTIME_CONSUMER_START wait_ms={WAIT_MS} max_attempts={MAX_ATTEMPTS}',flush=True)
    while True:
        sql_conn=None
        try:
            sql_conn=sql_connect()
            while True:
                msg=receive_one(sql_conn)
                if not msg:
                    sql_conn.commit()
                    continue
                handle=msg['conversation_handle']; message_type=msg['message_type_name']
                if message_type == EVENT_MESSAGE:
                    body_text=decode_body(msg['message_body'])
                    last_error=None
                    processed=False
                    payload=None
                    for attempt in range(1,MAX_ATTEMPTS+1):
                        pg_conn=None
                        try:
                            payload=json.loads(body_text)
                            pg_conn=pg_connect()
                            result=process_event(sql_conn,pg_conn,payload)
                            sync_event_deadlines(sql_conn,pg_conn,payload)
                            complete_conversation(sql_conn,handle)
                            sql_conn.commit()
                            print(f"EVENT_PROCESSED id={payload.get('event_id')} type={payload.get('event_type')} result={result} attempt={attempt}",flush=True)
                            processed=True
                            break
                        except Exception as exc:
                            last_error=exc
                            if pg_conn:
                                try: pg_conn.rollback()
                                except Exception: pass
                            if attempt < MAX_ATTEMPTS:
                                print(
                                    f"EVENT_RETRY id={payload.get('event_id') if isinstance(payload, dict) else None} "
                                    f"type={payload.get('event_type') if isinstance(payload, dict) else None} "
                                    f"attempt={attempt} error={type(exc).__name__}: {exc}",
                                    file=sys.stderr,
                                    flush=True,
                                )
                                time.sleep(min(2*attempt,5))
                        finally:
                            if pg_conn:
                                try: pg_conn.close()
                                except Exception: pass
                    if not processed:
                        dead_letter(sql_conn,handle,message_type,body_text,last_error)
                        sql_conn.commit()
                        print(f'DEAD_LETTERED type={message_type} error={type(last_error).__name__}: {last_error}',file=sys.stderr,flush=True)
                elif message_type in (END_DIALOG,BROKER_ERROR):
                    complete_conversation(sql_conn,handle)
                    sql_conn.commit()
                else:
                    complete_conversation(sql_conn,handle)
                    sql_conn.commit()
                    print(f'UNKNOWN_BROKER_MESSAGE type={message_type}',flush=True)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            if sql_conn:
                try: sql_conn.rollback()
                except Exception: pass
            print(f'CONSUMER_ERROR {type(exc).__name__}: {exc}',file=sys.stderr,flush=True)
            time.sleep(2)
        finally:
            if sql_conn:
                try: sql_conn.close()
                except Exception: pass

if __name__=='__main__':
    main()


