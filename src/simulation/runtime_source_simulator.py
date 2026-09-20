from __future__ import annotations

import json
import math
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pymssql
import psycopg2


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, value)


POLL_SECONDS = env_int("SIMULATION_POLL_SECONDS", 300)
RETRY_SECONDS = env_int("SIMULATION_RETRY_SECONDS", 60)
CURRENT_DAY_AFTER_HOUR = env_int("SIMULATION_CURRENT_DAY_AFTER_HOUR", 20, 0)
CATCHUP_CHUNK_DAYS = env_int("SIMULATION_CATCHUP_CHUNK_DAYS", 7)
LIVE_ENABLED = env_bool("SIMULATION_LIVE_ENABLED", True)
LIVE_HEARTBEAT_SECONDS = env_int("SIMULATION_LIVE_HEARTBEAT_SECONDS", 300)
LIVE_MAX_SLEEP_SECONDS = env_int("SIMULATION_LIVE_MAX_SLEEP_SECONDS", 5)

COLDROOM_MIN_SECONDS = env_int("SIMULATION_COLDROOM_MIN_SECONDS", 10)
COLDROOM_MAX_SECONDS = env_int("SIMULATION_COLDROOM_MAX_SECONDS", 25)
VEHICLE_MIN_SECONDS = env_int("SIMULATION_VEHICLE_MIN_SECONDS", 45)
VEHICLE_MAX_SECONDS = env_int("SIMULATION_VEHICLE_MAX_SECONDS", 120)

ORDER_MIN_SECONDS = env_int("SIMULATION_ORDER_MIN_SECONDS", 480)
ORDER_MAX_SECONDS = env_int("SIMULATION_ORDER_MAX_SECONDS", 1200)
ORDER_PICK_MIN_SECONDS = env_int("SIMULATION_ORDER_PICK_MIN_SECONDS", 90)
ORDER_PICK_MAX_SECONDS = env_int("SIMULATION_ORDER_PICK_MAX_SECONDS", 300)
DELIVERY_CONFIRM_MIN_SECONDS = env_int("SIMULATION_DELIVERY_CONFIRM_MIN_SECONDS", 120)
DELIVERY_CONFIRM_MAX_SECONDS = env_int("SIMULATION_DELIVERY_CONFIRM_MAX_SECONDS", 420)
PROCUREMENT_MIN_SECONDS = env_int("SIMULATION_PROCUREMENT_MIN_SECONDS", 300)
PROCUREMENT_MAX_SECONDS = env_int("SIMULATION_PROCUREMENT_MAX_SECONDS", 900)
MAX_PENDING_ORDERS = env_int("SIMULATION_MAX_PENDING_ORDERS", 8)

SIM_TZ = ZoneInfo(os.getenv("SIMULATION_TIMEZONE", "Asia/Jakarta"))
SOURCE_NAME = "WideWorldImporters"
RNG = random.Random()


@dataclass
class LiveReferences:
    employees: list[int]
    customers: list[dict[str, int]]
    stock_items: list[dict[str, Any]]


@dataclass
class PendingOrder:
    order_id: int
    due_monotonic: float


@dataclass
class PendingDelivery:
    invoice_id: int
    due_monotonic: float


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def source_connect():
    return pymssql.connect(
        server=os.environ["WWI_HOST"],
        port=int(os.getenv("WWI_PORT", "1433")),
        user=os.getenv("WWI_SIM_USER", "sa"),
        password=os.environ["MSSQL_SA_PASSWORD"],
        database=os.environ.get("WWI_DATABASE", "WideWorldImporters"),
        autocommit=True,
        login_timeout=15,
        timeout=0,
    )


def warehouse_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.getenv("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def drain(cursor) -> None:
    try:
        while cursor.nextset():
            pass
    except Exception:
        pass


def random_delay(min_seconds: int, max_seconds: int) -> float:
    lo = min(min_seconds, max_seconds)
    hi = max(min_seconds, max_seconds)
    return RNG.uniform(lo, hi)


def source_local_now() -> datetime:
    # WWI telemetry timestamps are stored as timezone-naive source-local values.
    return datetime.now(SIM_TZ).replace(tzinfo=None)


def latest_source_business_date(conn) -> tuple[date | None, int | None]:
    # OrderID is sequence-backed and monotonic. This avoids repeatedly scanning
    # the full Orders table just to determine the latest business date.
    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            """
            SELECT TOP (1) OrderDate AS max_order_date, OrderID AS latest_order_id
            FROM Sales.Orders
            ORDER BY OrderID DESC
            """
        )
        row = cur.fetchone()
    if not row:
        return None, None
    return row["max_order_date"], int(row["latest_order_id"])


def fetch_integrity_state(conn) -> dict[str, int]:
    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS temporal_count
            FROM sys.tables
            WHERE temporal_type = 2;

            SELECT COUNT(*) AS sim_trigger_count
            FROM sys.triggers
            WHERE name LIKE '%[_]DataLoad[_]Modify';

            SELECT
                SUM(CASE WHEN is_disabled = 1 THEN 1 ELSE 0 END) AS disabled_fk_count,
                SUM(CASE WHEN is_not_trusted = 1 THEN 1 ELSE 0 END) AS untrusted_fk_count
            FROM sys.foreign_keys;
            """
        )
        temporal = cur.fetchone()
        cur.nextset()
        triggers = cur.fetchone()
        cur.nextset()
        fks = cur.fetchone()

    return {
        "temporal_count": int(temporal["temporal_count"]),
        "sim_trigger_count": int(triggers["sim_trigger_count"]),
        "disabled_fk_count": int(fks["disabled_fk_count"] or 0),
        "untrusted_fk_count": int(fks["untrusted_fk_count"] or 0),
    }


def emergency_repair_temporal_state(conn) -> None:
    """
    Idempotent recovery for an interrupted WWI history simulation.
    """
    statements = [
        """
        DROP TRIGGER IF EXISTS [Warehouse].[TR_Warehouse_ColdRoomTemperatures_DataLoad_Modify];
        UPDATE [Warehouse].[ColdRoomTemperatures]
        SET [ValidFrom] = DATEADD(minute, -1, SYSDATETIME())
        WHERE [ValidFrom] > SYSDATETIME();
        IF NOT EXISTS (
            SELECT 1 FROM sys.periods
            WHERE object_id = OBJECT_ID('Warehouse.ColdRoomTemperatures')
        )
        ALTER TABLE [Warehouse].[ColdRoomTemperatures]
        ADD PERIOD FOR SYSTEM_TIME([ValidFrom], [ValidTo]);
        IF EXISTS (
            SELECT 1 FROM sys.tables
            WHERE object_id = OBJECT_ID('Warehouse.ColdRoomTemperatures')
              AND temporal_type = 0
        )
        ALTER TABLE [Warehouse].[ColdRoomTemperatures]
        SET (SYSTEM_VERSIONING = ON (
            HISTORY_TABLE = [Warehouse].[ColdRoomTemperatures_Archive],
            DATA_CONSISTENCY_CHECK = OFF
        ));
        """,
        """
        DROP TRIGGER IF EXISTS [Warehouse].[TR_Warehouse_Colors_DataLoad_Modify];
        IF NOT EXISTS (
            SELECT 1 FROM sys.periods
            WHERE object_id = OBJECT_ID('Warehouse.Colors')
        )
        ALTER TABLE [Warehouse].[Colors]
        ADD PERIOD FOR SYSTEM_TIME([ValidFrom], [ValidTo]);
        IF EXISTS (
            SELECT 1 FROM sys.tables
            WHERE object_id = OBJECT_ID('Warehouse.Colors')
              AND temporal_type = 0
        )
        ALTER TABLE [Warehouse].[Colors]
        SET (SYSTEM_VERSIONING = ON (
            HISTORY_TABLE = [Warehouse].[Colors_Archive],
            DATA_CONSISTENCY_CHECK = OFF
        ));
        """,
        """
        DROP TRIGGER IF EXISTS [Warehouse].[TR_Warehouse_PackageTypes_DataLoad_Modify];
        IF NOT EXISTS (
            SELECT 1 FROM sys.periods
            WHERE object_id = OBJECT_ID('Warehouse.PackageTypes')
        )
        ALTER TABLE [Warehouse].[PackageTypes]
        ADD PERIOD FOR SYSTEM_TIME([ValidFrom], [ValidTo]);
        IF EXISTS (
            SELECT 1 FROM sys.tables
            WHERE object_id = OBJECT_ID('Warehouse.PackageTypes')
              AND temporal_type = 0
        )
        ALTER TABLE [Warehouse].[PackageTypes]
        SET (SYSTEM_VERSIONING = ON (
            HISTORY_TABLE = [Warehouse].[PackageTypes_Archive],
            DATA_CONSISTENCY_CHECK = OFF
        ));
        """,
        """
        DROP TRIGGER IF EXISTS [Warehouse].[TR_Warehouse_StockGroups_DataLoad_Modify];
        IF NOT EXISTS (
            SELECT 1 FROM sys.periods
            WHERE object_id = OBJECT_ID('Warehouse.StockGroups')
        )
        ALTER TABLE [Warehouse].[StockGroups]
        ADD PERIOD FOR SYSTEM_TIME([ValidFrom], [ValidTo]);
        IF EXISTS (
            SELECT 1 FROM sys.tables
            WHERE object_id = OBJECT_ID('Warehouse.StockGroups')
              AND temporal_type = 0
        )
        ALTER TABLE [Warehouse].[StockGroups]
        SET (SYSTEM_VERSIONING = ON (
            HISTORY_TABLE = [Warehouse].[StockGroups_Archive],
            DATA_CONSISTENCY_CHECK = OFF
        ));
        """,
        """
        DROP TRIGGER IF EXISTS [Warehouse].[TR_Warehouse_StockItems_DataLoad_Modify];
        IF NOT EXISTS (
            SELECT 1 FROM sys.periods
            WHERE object_id = OBJECT_ID('Warehouse.StockItems')
        )
        ALTER TABLE [Warehouse].[StockItems]
        ADD PERIOD FOR SYSTEM_TIME([ValidFrom], [ValidTo]);
        IF EXISTS (
            SELECT 1 FROM sys.tables
            WHERE object_id = OBJECT_ID('Warehouse.StockItems')
              AND temporal_type = 0
        )
        ALTER TABLE [Warehouse].[StockItems]
        SET (SYSTEM_VERSIONING = ON (
            HISTORY_TABLE = [Warehouse].[StockItems_Archive],
            DATA_CONSISTENCY_CHECK = OFF
        ));
        """,
    ]

    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
            drain(cur)

        cur.execute(
            """
            IF OBJECT_ID('DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures') IS NOT NULL
                EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures;
            IF OBJECT_ID('Sequences.ReseedAllSequences') IS NOT NULL
                EXEC Sequences.ReseedAllSequences;
            IF OBJECT_ID('Application.Configuration_ApplyRowLevelSecurity') IS NOT NULL
                EXEC Application.Configuration_ApplyRowLevelSecurity;
            """
        )
        drain(cur)


def validate_integrity(state: dict[str, int]) -> None:
    if state["temporal_count"] != 17:
        raise RuntimeError(f"temporal tables not restored: {state['temporal_count']}/17")
    if state["sim_trigger_count"] != 0:
        raise RuntimeError(f"simulation triggers remain: {state['sim_trigger_count']}")
    if state["disabled_fk_count"] != 0 or state["untrusted_fk_count"] != 0:
        raise RuntimeError(
            "foreign-key state not clean: "
            f"disabled={state['disabled_fk_count']} "
            f"untrusted={state['untrusted_fk_count']}"
        )


def patch_temporal_reactivation_for_runtime(conn) -> str:
    """
    Relax the WWI temporal consistency check for long simulated catch-up runs.

    Do not place the cold-room ValidFrom repair in this procedure: SQL Server
    compiles procedure bodies against the current temporal schema and rejects
    direct writes to GENERATED ALWAYS period columns while versioning is active.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT OBJECT_DEFINITION(OBJECT_ID("
            "'DataLoadSimulation.ReactivateTemporalTablesAfterDataLoad'))"
        )
        row = cur.fetchone()
        original = row[0] if row else None
        if not original:
            raise RuntimeError(
                "DataLoadSimulation.ReactivateTemporalTablesAfterDataLoad "
                "definition unavailable"
            )

        patched, count = re.subn(
            r"DATA_CONSISTENCY_CHECK\s*=\s*ON",
            "DATA_CONSISTENCY_CHECK = OFF",
            original,
            flags=re.IGNORECASE,
        )
        if count < 1:
            raise RuntimeError(
                "temporal reactivation procedure has no consistency marker"
            )

        patched = re.sub(
            r"^\s*CREATE\s+PROCEDURE",
            "ALTER PROCEDURE",
            patched,
            count=1,
            flags=re.IGNORECASE,
        )
        cur.execute(patched)
        drain(cur)

    log(
        "TEMPORAL_REACTIVATION_RUNTIME_PATCH applied "
        f"consistency_markers={count}"
    )
    return original


def restore_temporal_reactivation_definition(conn, original: str) -> None:
    restored = re.sub(
        r"^\s*CREATE\s+PROCEDURE",
        "ALTER PROCEDURE",
        original,
        count=1,
        flags=re.IGNORECASE,
    )
    with conn.cursor() as cur:
        cur.execute(restored)
        drain(cur)
    log("TEMPORAL_REACTIVATION_RUNTIME_PATCH restored")


def patch_daily_process_temporal_guard(conn) -> None:
    """
    Repair future-dated cold-room period values only after WWI has disabled
    temporal versioning. Dynamic SQL defers compilation until that runtime point.
    """
    procedure_name = "DataLoadSimulation.DailyProcessToCreateHistory"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT OBJECT_DEFINITION(OBJECT_ID(%s))",
            (procedure_name,),
        )
        row = cur.fetchone()
        original = row[0] if row else None
        if not original:
            raise RuntimeError(f"{procedure_name} definition unavailable")

        marker = "EXEC DataLoadSimulation.DeactivateTemporalTablesBeforeDataLoad;"
        if marker not in original:
            raise RuntimeError(
                "DailyProcessToCreateHistory temporal-deactivation marker unavailable"
            )

        guard_marker = "RUNTIME_COLDROOM_VALIDFROM_GUARD"
        if guard_marker in original:
            return

        guard = """
    -- RUNTIME_COLDROOM_VALIDFROM_GUARD
    EXEC sys.sp_executesql N'
        UPDATE [Warehouse].[ColdRoomTemperatures]
        SET [ValidFrom] = DATEADD(minute, -1, SYSDATETIME())
        WHERE [ValidFrom] > SYSDATETIME();
    ';

"""
        patched = original.replace(marker, marker + guard, 1)
        patched = re.sub(
            r"^\s*CREATE\s+PROCEDURE",
            "ALTER PROCEDURE",
            patched,
            count=1,
            flags=re.IGNORECASE,
        )
        cur.execute(patched)
        drain(cur)

    log("DAILY_PROCESS_TEMPORAL_GUARD applied")


def simulate_chunk(conn, start_date: date, end_date: date) -> None:
    log(f"CATCHUP_CHUNK_START start={start_date} end={end_date}")
    original_reactivation: str | None = None
    try:
        original_reactivation = patch_temporal_reactivation_for_runtime(conn)

        with conn.cursor() as cur:
            cur.execute(
                "EXEC DataLoadSimulation.Configuration_ApplyDataLoadSimulationProcedures"
            )
            drain(cur)

        patch_daily_process_temporal_guard(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                EXEC DataLoadSimulation.DailyProcessToCreateHistory
                    @StartDate=%s,
                    @EndDate=%s,
                    @AverageNumberOfCustomerOrdersPerDay=60,
                    @SaturdayPercentageOfNormalWorkDay=50,
                    @SundayPercentageOfNormalWorkDay=0,
                    @UpdateCustomFields=0,
                    @IsSilentMode=1,
                    @AreDatesPrinted=0
                """,
                (start_date, end_date),
            )
            drain(cur)

        with conn.cursor() as cur:
            cur.execute(
                "EXEC DataLoadSimulation.Configuration_RemoveDataLoadSimulationProcedures"
            )
            drain(cur)

        integrity = fetch_integrity_state(conn)
        validate_integrity(integrity)
        log(
            "CATCHUP_CHUNK_DONE "
            f"start={start_date} end={end_date} "
            f"temporal={integrity['temporal_count']} "
            f"disabled_fk={integrity['disabled_fk_count']} "
            f"untrusted_fk={integrity['untrusted_fk_count']}"
        )
    except Exception:
        log("CATCHUP_CHUNK_ERROR attempting temporal recovery")
        emergency_repair_temporal_state(conn)
        raise
    finally:
        if original_reactivation is not None:
            restore_temporal_reactivation_definition(
                conn,
                original_reactivation,
            )


def completed_business_date_from_frontier() -> date | None:
    """
    Durable authority for the last fully simulated business day.

    This must not be derived from MAX(OrderDate): live partial-day orders can
    legitimately be newer than the last complete WWI DailyProcess day.
    """
    with warehouse_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT safe_through_cutoff
                FROM control.source_frontier
                WHERE source_name=%s
                """,
                (SOURCE_NAME,),
            )
            row = cur.fetchone()

    if not row or row[0] is None:
        return None
    return (row[0] - timedelta(days=1)).date()


def publish_frontier(max_business_date: date) -> None:
    # Analytical ingestion only advances through complete business days.
    # Live partial-day events travel through the realtime event path instead.
    safe_cutoff = datetime.combine(
        max_business_date + timedelta(days=1),
        dt_time.min,
        tzinfo=timezone.utc,
    )
    basis = (
        f"Official WWI DataLoadSimulation completed through {max_business_date}; "
        "runtime live workload continues through event publication."
    )

    with warehouse_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.source_frontier
                    (source_name, safe_through_cutoff, basis, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (source_name) DO UPDATE
                SET safe_through_cutoff = EXCLUDED.safe_through_cutoff,
                    basis = EXCLUDED.basis,
                    updated_at = now()
                WHERE control.source_frontier.safe_through_cutoff
                      < EXCLUDED.safe_through_cutoff
                """,
                (SOURCE_NAME, safe_cutoff, basis),
            )
        conn.commit()

    log(
        f"FRONTIER_PUBLISHED business_through={max_business_date} "
        f"safe_cutoff={safe_cutoff.isoformat()}"
    )


def runtime_target_date() -> date:
    """
    Whole-day WWI history generation must target a date that is fully in the
    past relative to SQL Server's UTC temporal clock. Runtime live events own
    the current Jakarta business day.
    """
    local_now = datetime.now(SIM_TZ)
    local_candidate = (
        local_now.date()
        if local_now.hour >= CURRENT_DAY_AFTER_HOUR
        else local_now.date() - timedelta(days=1)
    )
    utc_complete_day = datetime.now(timezone.utc).date() - timedelta(days=1)
    return min(local_candidate, utc_complete_day)


def ensure_catchup(conn) -> date:
    integrity = fetch_integrity_state(conn)
    if integrity["temporal_count"] != 17 or integrity["sim_trigger_count"] != 0:
        log(
            "SOURCE_NOT_CLEAN "
            f"temporal={integrity['temporal_count']} "
            f"sim_triggers={integrity['sim_trigger_count']} - repairing"
        )
        emergency_repair_temporal_state(conn)
        integrity = fetch_integrity_state(conn)
    validate_integrity(integrity)

    target_date = runtime_target_date()
    completed_date = completed_business_date_from_frontier()
    source_latest_date, latest_order_id = latest_source_business_date(conn)

    if completed_date is None:
        if source_latest_date is None:
            raise RuntimeError(
                "neither source frontier nor Sales.Orders can establish a baseline"
            )
        completed_date = source_latest_date
        log(
            "FRONTIER_MISSING_FALLBACK "
            f"using_source_date={completed_date}"
        )
        publish_frontier(completed_date)

    if completed_date < target_date:
        log(
            f"CATCHUP_REQUIRED completed_through={completed_date} "
            f"target={target_date} chunk_days={CATCHUP_CHUNK_DAYS}"
        )
        cursor_date = completed_date + timedelta(days=1)
        while cursor_date <= target_date:
            chunk_end = min(
                target_date,
                cursor_date + timedelta(days=CATCHUP_CHUNK_DAYS - 1),
            )
            simulate_chunk(conn, cursor_date, chunk_end)
            publish_frontier(chunk_end)
            completed_date = chunk_end
            cursor_date = chunk_end + timedelta(days=1)

    source_latest_date, latest_order_id = latest_source_business_date(conn)
    log(
        f"SOURCE_READY completed_through={completed_date} "
        f"target={target_date} source_latest_order_date={source_latest_date} "
        f"latest_order_id={latest_order_id}"
    )
    return completed_date


def load_live_references(conn) -> LiveReferences:
    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            """
            SELECT PersonID
            FROM Application.People
            WHERE IsEmployee=1
            ORDER BY PersonID
            """
        )
        employees = [int(row["PersonID"]) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT CustomerID,PrimaryContactPersonID
            FROM Sales.Customers
            WHERE IsOnCreditHold=0
              AND PrimaryContactPersonID IS NOT NULL
            ORDER BY CustomerID
            """
        )
        customers = [
            {
                "customer_id": int(row["CustomerID"]),
                "contact_person_id": int(row["PrimaryContactPersonID"]),
            }
            for row in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT TOP (120)
                si.StockItemID,
                si.StockItemName,
                h.QuantityOnHand
            FROM Warehouse.StockItems si
            JOIN Warehouse.StockItemHoldings h
              ON h.StockItemID=si.StockItemID
            WHERE h.QuantityOnHand >= 100
            ORDER BY h.QuantityOnHand DESC, si.StockItemID
            """
        )
        stock_items = [
            {
                "stock_item_id": int(row["StockItemID"]),
                "description": str(row["StockItemName"]),
                "quantity_on_hand": int(row["QuantityOnHand"]),
            }
            for row in cur.fetchall()
        ]

    if not employees or not customers or not stock_items:
        raise RuntimeError(
            "live reference cache is incomplete: "
            f"employees={len(employees)} customers={len(customers)} "
            f"stock_items={len(stock_items)}"
        )

    log(
        "LIVE_REFERENCE_CACHE "
        f"employees={len(employees)} customers={len(customers)} "
        f"stock_items={len(stock_items)}"
    )
    return LiveReferences(
        employees=employees,
        customers=customers,
        stock_items=stock_items,
    )


def seed_temperature_state(conn) -> tuple[dict[int, float], dict[tuple[str, int], float]]:
    coldroom: dict[int, float] = {}
    vehicles: dict[tuple[str, int], float] = {}

    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            """
            SELECT ColdRoomSensorNumber,Temperature
            FROM Warehouse.ColdRoomTemperatures
            ORDER BY ColdRoomSensorNumber
            """
        )
        for row in cur.fetchall():
            coldroom[int(row["ColdRoomSensorNumber"])] = float(row["Temperature"])

        # VehicleTemperatureID is sequence-backed, so TOP recent rows avoids
        # scanning the 1M+ row telemetry history.
        cur.execute(
            """
            SELECT TOP (24)
                VehicleRegistration,ChillerSensorNumber,Temperature
            FROM Warehouse.VehicleTemperatures
            ORDER BY VehicleTemperatureID DESC
            """
        )
        for row in cur.fetchall():
            key = (str(row["VehicleRegistration"]), int(row["ChillerSensorNumber"]))
            vehicles.setdefault(key, float(row["Temperature"]))

    if not coldroom:
        coldroom = {1: 4.0, 2: 4.0, 3: 4.0, 4: 4.0}
    if not vehicles:
        vehicles = {("WWI-321-A", 1): 4.0, ("WWI-321-A", 2): 4.1}

    return coldroom, vehicles


def next_temperature(current: float, nominal: float = 4.0) -> float:
    # Mean-reverting random walk: visibly alive without an unbounded drift.
    drift = (nominal - current) * 0.18
    noise = RNG.gauss(0.0, 0.12)
    value = current + drift + noise
    return round(min(7.5, max(1.5, value)), 2)


def publish_coldroom_readings(conn, temperatures: dict[int, float]) -> int:
    recorded_when = source_local_now()
    rows: list[tuple[int, datetime, float]] = []

    for sensor in sorted(temperatures):
        value = next_temperature(temperatures[sensor], nominal=4.0)
        temperatures[sensor] = value
        rows.append((sensor, recorded_when, value))

    values_sql = ",".join(["(%s,%s,%s)"] * len(rows))
    params: list[Any] = []
    for row in rows:
        params.extend(row)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            DECLARE @SensorReadings Website.SensorDataList;
            INSERT INTO @SensorReadings
                (ColdRoomSensorNumber,RecordedWhen,Temperature)
            VALUES {values_sql};
            EXEC ControlTower.RecordColdRoomTemperaturesAndPublish
                @SensorReadings=@SensorReadings;
            """,
            tuple(params),
        )
        drain(cur)

    return len(rows)


def publish_vehicle_readings(
    conn,
    temperatures: dict[tuple[str, int], float],
) -> int:
    recorded_when = source_local_now()
    recordings = []

    for (vehicle, sensor) in sorted(temperatures):
        value = next_temperature(temperatures[(vehicle, sensor)], nominal=4.1)
        temperatures[(vehicle, sensor)] = value
        recordings.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [-89.7600464, 50.4742420],
                },
                "properties": {
                    "rego": vehicle,
                    "sensor": sensor,
                    "when": recorded_when.isoformat(timespec="seconds"),
                    "temp": value,
                },
            }
        )

    body = json.dumps({"Recordings": recordings}, separators=(",", ":"))
    with conn.cursor() as cur:
        cur.execute(
            """
            EXEC ControlTower.RecordVehicleTemperatureAndPublish
                @FullSensorDataArray=%s
            """,
            (body,),
        )
        drain(cur)

    return len(recordings)


def create_live_order(conn, refs: LiveReferences) -> int:
    customer = RNG.choice(refs.customers)
    employee = RNG.choice(refs.employees)
    salesperson = RNG.choice(refs.employees)
    line_count = RNG.randint(1, min(3, len(refs.stock_items)))
    selected = RNG.sample(refs.stock_items, line_count)

    local_now = datetime.now(SIM_TZ)
    expected = local_now.date() + timedelta(days=RNG.randint(1, 5))
    # WWI CustomerPurchaseOrderNumber is nvarchar(20).
    po_number = f"L{local_now:%y%m%d%H%M%S}{RNG.randint(100,999)}"

    line_values = []
    line_params: list[Any] = []
    for item in selected:
        line_values.append("(%s,%s,%s,%s)")
        line_params.extend(
            (
                1,
                item["stock_item_id"],
                item["description"],
                RNG.randint(1, 6),
            )
        )

    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            f"""
            DECLARE @Orders Website.OrderList;
            DECLARE @OrderLines Website.OrderLineList;

            INSERT INTO @Orders
                (OrderReference,CustomerID,ContactPersonID,ExpectedDeliveryDate,
                 CustomerPurchaseOrderNumber,IsUndersupplyBackordered,
                 Comments,DeliveryInstructions)
            VALUES (1,%s,%s,%s,%s,0,N'Runtime live workload',N'Runtime simulator');

            INSERT INTO @OrderLines
                (OrderReference,StockItemID,[Description],Quantity)
            VALUES {",".join(line_values)};

            EXEC Website.InsertCustomerOrders
                @Orders=@Orders,
                @OrderLines=@OrderLines,
                @OrdersCreatedByPersonID=%s,
                @SalespersonPersonID=%s;

            SELECT CONVERT(int,current_value) AS order_id
            FROM sys.sequences
            WHERE object_id=OBJECT_ID(N'Sequences.OrderID');
            """,
            (
                customer["customer_id"],
                customer["contact_person_id"],
                expected,
                po_number,
                *line_params,
                employee,
                salesperson,
            ),
        )
        row = cur.fetchone()

    if not row:
        raise RuntimeError("live order created but OrderID could not be resolved")
    return int(row["order_id"])


def pick_and_invoice_order(
    conn,
    order_id: int,
    refs: LiveReferences,
) -> int | None:
    actor = RNG.choice(refs.employees)

    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            "SELECT TOP (1) InvoiceID FROM Sales.Invoices WHERE OrderID=%s",
            (order_id,),
        )
        existing = cur.fetchone()
        if existing:
            return int(existing["InvoiceID"])

        cur.execute(
            """
            UPDATE Sales.OrderLines
            SET PickedQuantity=Quantity,
                PickingCompletedWhen=SYSDATETIME(),
                LastEditedBy=%s,
                LastEditedWhen=SYSDATETIME()
            WHERE OrderID=%s
              AND PickingCompletedWhen IS NULL;

            UPDATE Sales.Orders
            SET PickedByPersonID=%s,
                PickingCompletedWhen=SYSDATETIME(),
                LastEditedBy=%s,
                LastEditedWhen=SYSDATETIME()
            WHERE OrderID=%s
              AND PickingCompletedWhen IS NULL;

            DECLARE @OrdersToInvoice Website.OrderIDList;
            INSERT INTO @OrdersToInvoice(OrderID) VALUES (%s);

            EXEC Website.InvoiceCustomerOrders
                @OrdersToInvoice=@OrdersToInvoice,
                @PackedByPersonID=%s,
                @InvoicedByPersonID=%s;

            SELECT TOP (1) InvoiceID
            FROM Sales.Invoices
            WHERE OrderID=%s
            ORDER BY InvoiceID DESC;
            """,
            (
                actor,
                order_id,
                actor,
                actor,
                order_id,
                order_id,
                actor,
                actor,
                order_id,
            ),
        )

        while cur.description is None and cur.nextset():
            pass
        row = cur.fetchone() if cur.description is not None else None

    return int(row["InvoiceID"]) if row else None


def confirm_delivery(conn, invoice_id: int, refs: LiveReferences) -> bool:
    actor = RNG.choice(refs.employees)
    receiver = f"Runtime receiver {RNG.randint(1, 20)}"

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE Sales.Invoices
            SET ReturnedDeliveryData=
                    JSON_MODIFY(
                        JSON_MODIFY(
                            COALESCE(ReturnedDeliveryData,N'{"Events":[]}'),
                            N'$.DeliveredWhen',
                            CONVERT(nvarchar(33),SYSDATETIME(),126)
                        ),
                        N'$.ReceivedBy',
                        %s
                    ),
                LastEditedBy=%s,
                LastEditedWhen=SYSDATETIME()
            WHERE InvoiceID=%s
              AND ConfirmedDeliveryTime IS NULL
            """,
            (receiver, actor, invoice_id),
        )
        changed = cur.rowcount

    return changed > 0


def receive_procurement(conn, refs: LiveReferences) -> dict[str, int] | None:
    with conn.cursor(as_dict=True) as cur:
        cur.execute(
            """
            SELECT TOP (1)
                po.PurchaseOrderID,
                po.SupplierID,
                pol.PurchaseOrderLineID,
                pol.StockItemID,
                pol.OrderedOuters,
                pol.ReceivedOuters,
                si.QuantityPerOuter
            FROM Purchasing.PurchaseOrders po
            JOIN Purchasing.PurchaseOrderLines pol
              ON pol.PurchaseOrderID=po.PurchaseOrderID
            JOIN Warehouse.StockItems si
              ON si.StockItemID=pol.StockItemID
            WHERE po.IsOrderFinalized=0
              AND pol.ReceivedOuters < pol.OrderedOuters
            ORDER BY po.PurchaseOrderID DESC, pol.PurchaseOrderLineID
            """
        )
        row = cur.fetchone()

    if not row:
        return None

    remaining = int(row["OrderedOuters"]) - int(row["ReceivedOuters"])
    fraction = RNG.uniform(0.08, 0.22)
    delta_outers = max(
        1,
        min(remaining, 500, int(math.ceil(remaining * fraction))),
    )
    quantity_units = delta_outers * int(row["QuantityPerOuter"])
    actor = RNG.choice(refs.employees)

    with conn.cursor() as cur:
        cur.execute(
            """
            SET XACT_ABORT ON;
            BEGIN TRY
                BEGIN TRAN;

                UPDATE Purchasing.PurchaseOrderLines
                SET ReceivedOuters=ReceivedOuters + %s,
                    LastReceiptDate=CONVERT(date,SYSDATETIME()),
                    IsOrderLineFinalized=
                        CASE WHEN ReceivedOuters + %s >= OrderedOuters THEN 1 ELSE 0 END,
                    LastEditedBy=%s,
                    LastEditedWhen=SYSDATETIME()
                WHERE PurchaseOrderLineID=%s
                  AND ReceivedOuters < OrderedOuters;

                UPDATE Warehouse.StockItemHoldings
                SET QuantityOnHand=QuantityOnHand + %s,
                    LastEditedBy=%s,
                    LastEditedWhen=SYSDATETIME()
                WHERE StockItemID=%s;

                INSERT Warehouse.StockItemTransactions
                    (StockItemTransactionID,StockItemID,TransactionTypeID,
                     CustomerID,InvoiceID,SupplierID,PurchaseOrderID,
                     TransactionOccurredWhen,Quantity,LastEditedBy,LastEditedWhen)
                VALUES
                    (NEXT VALUE FOR Sequences.TransactionID,
                     %s,
                     (SELECT TransactionTypeID
                      FROM Application.TransactionTypes
                      WHERE TransactionTypeName=N'Stock Receipt'),
                     NULL,NULL,%s,%s,
                     SYSDATETIME(),%s,%s,SYSDATETIME());

                IF NOT EXISTS (
                    SELECT 1
                    FROM Purchasing.PurchaseOrderLines
                    WHERE PurchaseOrderID=%s
                      AND ReceivedOuters < OrderedOuters
                )
                UPDATE Purchasing.PurchaseOrders
                SET IsOrderFinalized=1,
                    LastEditedBy=%s,
                    LastEditedWhen=SYSDATETIME()
                WHERE PurchaseOrderID=%s;

                COMMIT;
            END TRY
            BEGIN CATCH
                IF XACT_STATE()<>0 ROLLBACK;
                THROW;
            END CATCH;
            """,
            (
                delta_outers,
                delta_outers,
                actor,
                int(row["PurchaseOrderLineID"]),
                quantity_units,
                actor,
                int(row["StockItemID"]),
                int(row["StockItemID"]),
                int(row["SupplierID"]),
                int(row["PurchaseOrderID"]),
                quantity_units,
                actor,
                int(row["PurchaseOrderID"]),
                actor,
                int(row["PurchaseOrderID"]),
            ),
        )
        drain(cur)

    return {
        "purchase_order_id": int(row["PurchaseOrderID"]),
        "stock_item_id": int(row["StockItemID"]),
        "received_outers": delta_outers,
        "quantity_units": quantity_units,
    }


def run_live(conn) -> None:
    refs = load_live_references(conn)
    coldroom_temps, vehicle_temps = seed_temperature_state(conn)

    now = time.monotonic()
    next_coldroom = now + random_delay(1, min(COLDROOM_MAX_SECONDS, 3))
    next_vehicle = now + random_delay(2, min(VEHICLE_MAX_SECONDS, 6))
    next_order = now + random_delay(ORDER_MIN_SECONDS, ORDER_MAX_SECONDS)
    next_procurement = now + random_delay(PROCUREMENT_MIN_SECONDS, PROCUREMENT_MAX_SECONDS)
    next_catchup_check = now + POLL_SECONDS
    next_heartbeat = now + LIVE_HEARTBEAT_SECONDS

    pending_orders: dict[int, PendingOrder] = {}
    pending_deliveries: dict[int, PendingDelivery] = {}
    counters = {
        "coldroom_rows": 0,
        "vehicle_rows": 0,
        "orders_created": 0,
        "orders_invoiced": 0,
        "deliveries_confirmed": 0,
        "procurement_receipts": 0,
    }

    log(
        "LIVE_MODE_STARTED "
        f"coldroom={COLDROOM_MIN_SECONDS}-{COLDROOM_MAX_SECONDS}s "
        f"vehicle={VEHICLE_MIN_SECONDS}-{VEHICLE_MAX_SECONDS}s "
        f"orders={ORDER_MIN_SECONDS}-{ORDER_MAX_SECONDS}s "
        f"procurement={PROCUREMENT_MIN_SECONDS}-{PROCUREMENT_MAX_SECONDS}s"
    )

    while True:
        now = time.monotonic()

        if now >= next_catchup_check:
            completed_date = completed_business_date_from_frontier()
            target = runtime_target_date()
            if completed_date is None or completed_date < target:
                log(
                    f"LIVE_PAUSE_FOR_CATCHUP completed_through={completed_date} "
                    f"target={target}"
                )
                ensure_catchup(conn)
                refs = load_live_references(conn)
                coldroom_temps, vehicle_temps = seed_temperature_state(conn)
                log("LIVE_RESUMED_AFTER_CATCHUP")
            next_catchup_check = time.monotonic() + POLL_SECONDS

        if now >= next_coldroom:
            counters["coldroom_rows"] += publish_coldroom_readings(
                conn, coldroom_temps
            )
            next_coldroom = time.monotonic() + random_delay(
                COLDROOM_MIN_SECONDS, COLDROOM_MAX_SECONDS
            )

        if now >= next_vehicle:
            counters["vehicle_rows"] += publish_vehicle_readings(
                conn, vehicle_temps
            )
            next_vehicle = time.monotonic() + random_delay(
                VEHICLE_MIN_SECONDS, VEHICLE_MAX_SECONDS
            )

        if now >= next_order:
            if len(pending_orders) < MAX_PENDING_ORDERS:
                order_id = create_live_order(conn, refs)
                pending_orders[order_id] = PendingOrder(
                    order_id=order_id,
                    due_monotonic=time.monotonic()
                    + random_delay(ORDER_PICK_MIN_SECONDS, ORDER_PICK_MAX_SECONDS),
                )
                counters["orders_created"] += 1
                log(f"LIVE_ORDER_CREATED order_id={order_id}")
            next_order = time.monotonic() + random_delay(
                ORDER_MIN_SECONDS, ORDER_MAX_SECONDS
            )

        due_orders = [
            item
            for item in pending_orders.values()
            if item.due_monotonic <= now
        ]
        for item in due_orders[:1]:
            invoice_id = pick_and_invoice_order(conn, item.order_id, refs)
            pending_orders.pop(item.order_id, None)
            if invoice_id is not None:
                pending_deliveries[invoice_id] = PendingDelivery(
                    invoice_id=invoice_id,
                    due_monotonic=time.monotonic()
                    + random_delay(
                        DELIVERY_CONFIRM_MIN_SECONDS,
                        DELIVERY_CONFIRM_MAX_SECONDS,
                    ),
                )
                counters["orders_invoiced"] += 1
                log(
                    f"LIVE_ORDER_INVOICED order_id={item.order_id} "
                    f"invoice_id={invoice_id}"
                )

        due_deliveries = [
            item
            for item in pending_deliveries.values()
            if item.due_monotonic <= now
        ]
        for item in due_deliveries[:1]:
            if confirm_delivery(conn, item.invoice_id, refs):
                counters["deliveries_confirmed"] += 1
                log(f"LIVE_DELIVERY_CONFIRMED invoice_id={item.invoice_id}")
            pending_deliveries.pop(item.invoice_id, None)

        if now >= next_procurement:
            result = receive_procurement(conn, refs)
            if result:
                counters["procurement_receipts"] += 1
                log(
                    "LIVE_PROCUREMENT_RECEIPT "
                    f"po={result['purchase_order_id']} "
                    f"stock_item={result['stock_item_id']} "
                    f"outers={result['received_outers']} "
                    f"units={result['quantity_units']}"
                )
            next_procurement = time.monotonic() + random_delay(
                PROCUREMENT_MIN_SECONDS, PROCUREMENT_MAX_SECONDS
            )

        if now >= next_heartbeat:
            log(
                "LIVE_HEARTBEAT "
                + " ".join(f"{key}={value}" for key, value in counters.items())
                + f" pending_orders={len(pending_orders)}"
                + f" pending_deliveries={len(pending_deliveries)}"
            )
            next_heartbeat = time.monotonic() + LIVE_HEARTBEAT_SECONDS

        due_times = [
            next_coldroom,
            next_vehicle,
            next_order,
            next_procurement,
            next_catchup_check,
            next_heartbeat,
        ]
        due_times.extend(item.due_monotonic for item in pending_orders.values())
        due_times.extend(
            item.due_monotonic for item in pending_deliveries.values()
        )
        next_due = min(due_times)
        sleep_for = min(
            LIVE_MAX_SLEEP_SECONDS,
            max(0.25, next_due - time.monotonic()),
        )
        time.sleep(sleep_for)


def run_catchup_only() -> None:
    while True:
        with source_connect() as conn:
            ensure_catchup(conn)
        time.sleep(POLL_SECONDS)


def main() -> int:
    log(
        "RUNTIME_SOURCE_SIMULATOR_STARTED "
        f"timezone={SIM_TZ.key} live_enabled={LIVE_ENABLED} "
        f"catchup_check={POLL_SECONDS}s chunk_days={CATCHUP_CHUNK_DAYS} "
        f"current_day_after_hour={CURRENT_DAY_AFTER_HOUR}"
    )

    while True:
        try:
            if not LIVE_ENABLED:
                run_catchup_only()
                return 0

            with source_connect() as conn:
                ensure_catchup(conn)
                run_live(conn)

        except KeyboardInterrupt:
            log("RUNTIME_SOURCE_SIMULATOR_STOPPED")
            return 0
        except Exception as exc:
            log(
                "RUNTIME_SOURCE_SIMULATOR_RETRY "
                f"error={type(exc).__name__}: {exc}"
            )
            time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
