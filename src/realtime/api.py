from __future__ import annotations

import asyncio
import json
import os
import select
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import psycopg2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor

from realtime.alert_api import router as alert_router
from realtime.control_tower_api import router as control_tower_router
from realtime.fulfillment_api import router as fulfillment_router
from realtime.delivery_api import router as delivery_router
from realtime.inventory_api import router as inventory_router
from realtime.procurement_api import router as procurement_router
from realtime.cold_chain_api import router as cold_chain_router
from realtime.analytics_api import router as analytics_router
from realtime.platform_health_api import router as platform_health_router
from realtime.admin_api import router as admin_router
from realtime.exception_workbench_api import router as exception_workbench_router

CHANNEL = "control_tower_realtime"
KEEPALIVE_SECONDS = max(5, int(os.environ.get("REALTIME_SSE_KEEPALIVE_SECONDS", "15")))


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


class EventHub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.subscribers: set[asyncio.Queue[str]] = set()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.connected = False
        self.last_error: str | None = None

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.thread = threading.Thread(target=self._listen_forever, daemon=True, name="realtime-pg-listener")
        self.thread.start()

    async def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            await asyncio.to_thread(self.thread.join, 6)

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self.subscribers.discard(queue)

    def _fanout(self, payload: str) -> None:
        for queue in list(self.subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _listen_forever(self) -> None:
        while not self.stop_event.is_set():
            conn = None
            try:
                conn = pg_connect()
                conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cur = conn.cursor()
                cur.execute(f"LISTEN {CHANNEL};")
                self.connected = True
                self.last_error = None

                while not self.stop_event.is_set():
                    ready, _, _ = select.select([conn], [], [], 5)
                    if not ready:
                        continue
                    conn.poll()
                    while conn.notifies:
                        notification = conn.notifies.pop(0)
                        if self.loop:
                            self.loop.call_soon_threadsafe(self._fanout, notification.payload)
            except Exception as exc:
                self.connected = False
                self.last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(2)
            finally:
                self.connected = False
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass


hub = EventHub()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()


app = FastAPI(
    title="Supply Chain Control Tower Realtime API",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "REALTIME_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(alert_router)
app.include_router(control_tower_router)
app.include_router(fulfillment_router)
app.include_router(delivery_router)
app.include_router(inventory_router)
app.include_router(procurement_router)
app.include_router(cold_chain_router)
app.include_router(analytics_router)
app.include_router(platform_health_router)
app.include_router(admin_router)
app.include_router(exception_workbench_router)


STATE_MAP = {
    "orders": ("current_order_state", "order_id"),
    "deliveries": ("current_delivery_state", "invoice_id"),
    "procurement": ("current_procurement_state", "purchase_order_id"),
    "inventory": ("current_inventory_state", "stock_item_id"),
    "sensors": ("current_sensor_state", "sensor_key"),
}


@app.get("/health")
def health() -> dict[str, Any]:
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    return {
        "status": "ok",
        "database": "ok",
        "sse_listener": "connected" if hub.connected else "reconnecting",
        "subscribers": len(hub.subscribers),
        "listener_error": hub.last_error,
    }


@app.get("/api/realtime/events")
def recent_events(limit: int = Query(default=50, ge=1, le=200)) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT event_id, schema_version, event_type, entity_type,
                       source_table, operation, occurred_at_utc,
                       processing_result, processed_at
                FROM realtime.event_log
                WHERE processed_at IS NOT NULL
                ORDER BY processed_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return JSONResponse(content=jsonable_encoder(rows))


@app.get("/api/realtime/events/{event_id}")
def event_detail(event_id: str) -> JSONResponse:
    try:
        parsed_event_id = str(uuid.UUID(event_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid event id") from exc

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT event_id, schema_version, event_type, entity_type,
                       source_table, operation, occurred_at_utc, payload,
                       processing_result, processed_at
                FROM realtime.event_log
                WHERE event_id = %s
                """,
                (parsed_event_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return JSONResponse(content=jsonable_encoder(row))


@app.get("/api/realtime/state/{domain}/{entity_id}")
def current_state(domain: str, entity_id: str) -> JSONResponse:
    mapping = STATE_MAP.get(domain)
    if mapping is None:
        raise HTTPException(status_code=404, detail="Unknown realtime domain")

    table, key_column = mapping
    value: Any = entity_id
    if domain != "sensors":
        try:
            value = int(entity_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Entity id must be an integer") from exc

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM realtime.{table} WHERE {key_column} = %s", (value,))
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Current state not found")
    return JSONResponse(content=jsonable_encoder(row))


@app.get("/api/realtime/stream")
async def stream(request: Request) -> StreamingResponse:
    queue = hub.subscribe()

    async def event_stream():
        try:
            ready = json.dumps({"status": "connected", "channel": CHANNEL}, separators=(",", ":"))
            yield f"event: ready\ndata: {ready}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    try:
                        decoded = json.loads(payload)
                        event_id = decoded.get("event_id")
                        event_name = "alert" if decoded.get("event_kind") == "alert" else "update"
                    except Exception:
                        event_id = None
                        event_name = "update"
                    if event_id:
                        yield f"id: {event_id}\nevent: {event_name}\ndata: {payload}\n\n"
                    else:
                        yield f"event: {event_name}\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )











