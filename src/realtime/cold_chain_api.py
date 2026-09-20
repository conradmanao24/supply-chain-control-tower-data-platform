from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import psycopg2
from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/api/cold-chain", tags=["cold-chain"])

SOURCE_TIMEZONE_NAME = os.environ.get("COLD_CHAIN_SOURCE_TIMEZONE", "Asia/Jakarta")
SOURCE_TIMEZONE = ZoneInfo(SOURCE_TIMEZONE_NAME)
HISTORY_POINTS = max(4, min(30, int(os.environ.get("COLD_CHAIN_HISTORY_POINTS", "12"))))
HISTORY_WINDOW_HOURS = max(1, min(24, int(os.environ.get("COLD_CHAIN_HISTORY_WINDOW_HOURS", "2"))))

DEFAULT_FRESHNESS = {
    "coldroom": {"stale_seconds": 60.0, "offline_seconds": 120.0},
    "vehicle": {"stale_seconds": 600.0, "offline_seconds": 1200.0},
}


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def _source_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=SOURCE_TIMEZONE)
    return value.astimezone(SOURCE_TIMEZONE)


def _rule_seconds(rules: dict[str, dict], rule_id: str, default: float) -> float:
    rule = rules.get(rule_id) or {}
    params = rule.get("parameters") or {}
    value = params.get("seconds")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _temperature_state(
    temperature: float,
    prefix: str,
    rules: dict[str, dict],
) -> tuple[str, bool]:
    warning = rules.get(f"{prefix}.temperature_warning") or {}
    critical = rules.get(f"{prefix}.temperature_critical") or {}

    def configured(rule: dict) -> bool:
        params = rule.get("parameters") or {}
        return bool(rule.get("enabled")) and (
            params.get("low") is not None or params.get("high") is not None
        )

    def outside(rule: dict) -> bool:
        params = rule.get("parameters") or {}
        low = params.get("low")
        high = params.get("high")
        return bool(
            (low is not None and temperature < float(low))
            or (high is not None and temperature > float(high))
        )

    critical_configured = configured(critical)
    warning_configured = configured(warning)
    any_configured = critical_configured or warning_configured

    if critical_configured and outside(critical):
        return "critical", True
    if warning_configured and outside(warning):
        return "warning", True
    if any_configured:
        return "normal", True
    return "not_configured", False


def _history_map(cur) -> dict[str, list[dict]]:
    cur.execute(
        """
        WITH ranked AS (
            SELECT
                sensor_key,
                recorded_when,
                temperature::numeric(10,2) AS temperature,
                row_number() OVER (
                    PARTITION BY sensor_key
                    ORDER BY recorded_when DESC
                ) AS rn
            FROM realtime.sensor_reading_history
            WHERE inserted_at >= now() - (%s * interval '1 hour')
        )
        SELECT sensor_key,recorded_when,temperature
        FROM ranked
        WHERE rn <= %s
        ORDER BY sensor_key,recorded_when ASC
        """,
        (HISTORY_WINDOW_HOURS, HISTORY_POINTS),
    )
    result: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        key = str(row["sensor_key"])
        result.setdefault(key, []).append(
            {
                "recorded_when": _source_aware(row["recorded_when"]),
                "temperature": float(row["temperature"]),
            }
        )
    return result


@router.get("/overview")
def overview() -> JSONResponse:
    now_utc = datetime.now(timezone.utc)

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    sensor_key,
                    sensor_type,
                    vehicle_registration,
                    sensor_number,
                    recorded_when,
                    temperature::numeric(10,2) AS temperature,
                    reading_count,
                    value_basis,
                    refreshed_at
                FROM realtime.current_sensor_state
                ORDER BY
                    CASE WHEN sensor_type='coldroom' THEN 0 ELSE 1 END,
                    vehicle_registration NULLS FIRST,
                    sensor_number
                """
            )
            raw_sensors = [dict(row) for row in cur.fetchall()]
            history_by_sensor = _history_map(cur)

            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged'))::int AS active,
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged') AND a.severity='critical')::int AS critical,
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged') AND a.severity='warning')::int AS warning,
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged') AND a.severity='info')::int AS info
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE r.domain='cold_chain'
                """
            )
            alert_summary = dict(cur.fetchone())

            cur.execute(
                """
                SELECT rule_id,description,severity,enabled,source_native,parameters
                FROM alert.rule_config
                WHERE domain='cold_chain'
                ORDER BY rule_id
                """
            )
            rule_rows = [dict(row) for row in cur.fetchall()]

    rules = {row["rule_id"]: row for row in rule_rows}
    sensors = []

    for raw in raw_sensors:
        sensor_key = str(raw["sensor_key"])
        sensor_type = str(raw["sensor_type"])
        prefix = "coldroom" if sensor_type == "coldroom" else "vehicle"
        defaults = DEFAULT_FRESHNESS[prefix]
        stale_seconds = _rule_seconds(
            rules,
            f"{prefix}.stale",
            defaults["stale_seconds"],
        )
        offline_seconds = _rule_seconds(
            rules,
            f"{prefix}.offline",
            defaults["offline_seconds"],
        )

        recorded_local = _source_aware(raw["recorded_when"])
        if recorded_local is None:
            age_seconds = None
            freshness_state = "unknown"
        else:
            age_seconds = max(
                0.0,
                (now_utc - recorded_local.astimezone(timezone.utc)).total_seconds(),
            )
            if age_seconds > offline_seconds:
                freshness_state = "offline"
            elif age_seconds > stale_seconds:
                freshness_state = "stale"
            else:
                freshness_state = "fresh"

        temperature = float(raw["temperature"])
        temperature_state, temperature_configured = _temperature_state(
            temperature,
            prefix,
            rules,
        )

        if freshness_state == "offline":
            operational_state = "offline"
        elif freshness_state == "stale":
            operational_state = "stale"
        elif temperature_state == "critical":
            operational_state = "temperature_critical"
        elif temperature_state == "warning":
            operational_state = "temperature_warning"
        elif freshness_state == "fresh":
            operational_state = "healthy"
        else:
            operational_state = "unknown"

        history = list(history_by_sensor.get(sensor_key, []))
        if not history or (
            recorded_local is not None
            and history[-1]["recorded_when"] != recorded_local
        ):
            history.append(
                {
                    "recorded_when": recorded_local,
                    "temperature": temperature,
                }
            )
        history = history[-HISTORY_POINTS:]

        previous_temperature = (
            float(history[-2]["temperature"]) if len(history) >= 2 else None
        )
        temperature_delta = (
            round(temperature - previous_temperature, 2)
            if previous_temperature is not None
            else None
        )
        if temperature_delta is None or abs(temperature_delta) < 0.01:
            movement = "steady"
        elif temperature_delta > 0:
            movement = "rising"
        else:
            movement = "falling"

        sensors.append(
            {
                **raw,
                "recorded_when": recorded_local,
                "temperature": temperature,
                "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
                "freshness_state": freshness_state,
                "operational_state": operational_state,
                "stale_after_seconds": stale_seconds,
                "offline_after_seconds": offline_seconds,
                "temperature_state": temperature_state,
                "temperature_thresholds_configured": temperature_configured,
                "previous_temperature": previous_temperature,
                "temperature_delta": temperature_delta,
                "movement": movement,
                "history": history,
            }
        )

    state_rank = {
        "offline": 0,
        "stale": 1,
        "temperature_critical": 2,
        "temperature_warning": 3,
        "unknown": 4,
        "healthy": 5,
    }
    sensors.sort(
        key=lambda item: (
            state_rank.get(item["operational_state"], 9),
            -abs(item["temperature_delta"] or 0),
            -(item["age_seconds"] or 0),
            item["sensor_key"],
        )
    )

    total = len(sensors)
    fresh = sum(1 for item in sensors if item["freshness_state"] == "fresh")
    stale = sum(1 for item in sensors if item["freshness_state"] == "stale")
    offline = sum(1 for item in sensors if item["freshness_state"] == "offline")
    attention = sum(1 for item in sensors if item["operational_state"] != "healthy")
    temperature_evaluated = sum(
        1 for item in sensors if item["temperature_thresholds_configured"]
    )

    groups = []
    for sensor_type in ("coldroom", "vehicle"):
        items = [item for item in sensors if item["sensor_type"] == sensor_type]
        if not items:
            continue
        prefix = "coldroom" if sensor_type == "coldroom" else "vehicle"
        defaults = DEFAULT_FRESHNESS[prefix]
        latest = max(
            (item["recorded_when"] for item in items if item["recorded_when"] is not None),
            default=None,
        )
        groups.append(
            {
                "sensor_type": sensor_type,
                "sensor_count": len(items),
                "fresh_count": sum(1 for item in items if item["freshness_state"] == "fresh"),
                "stale_count": sum(1 for item in items if item["freshness_state"] == "stale"),
                "offline_count": sum(1 for item in items if item["freshness_state"] == "offline"),
                "attention_count": sum(1 for item in items if item["operational_state"] != "healthy"),
                "latest_recorded_when": latest,
                "stale_after_seconds": _rule_seconds(
                    rules,
                    f"{prefix}.stale",
                    defaults["stale_seconds"],
                ),
                "offline_after_seconds": _rule_seconds(
                    rules,
                    f"{prefix}.offline",
                    defaults["offline_seconds"],
                ),
                "temperature_thresholds_configured": any(
                    item["temperature_thresholds_configured"] for item in items
                ),
            }
        )

    latest_recorded_when = max(
        (item["recorded_when"] for item in sensors if item["recorded_when"] is not None),
        default=None,
    )
    latest_age_seconds = (
        max(
            0.0,
            (now_utc - latest_recorded_when.astimezone(timezone.utc)).total_seconds(),
        )
        if latest_recorded_when is not None
        else None
    )

    result = {
        "generated_at": now_utc,
        "source_timezone": SOURCE_TIMEZONE_NAME,
        "latest_recorded_when": latest_recorded_when,
        "kpis": {
            "total_sensors": total,
            "coldroom_sensors": sum(1 for item in sensors if item["sensor_type"] == "coldroom"),
            "vehicle_sensors": sum(1 for item in sensors if item["sensor_type"] == "vehicle"),
            "fresh_sensors": fresh,
            "stale_sensors": stale,
            "offline_sensors": offline,
            "attention_sensors": attention,
            "temperature_evaluated_sensors": temperature_evaluated,
            "latest_age_seconds": round(latest_age_seconds, 3)
            if latest_age_seconds is not None
            else None,
        },
        "sensor_groups": groups,
        "sensors": sensors,
        "alert_summary": alert_summary,
        "rules": rule_rows,
        "monitoring": {
            "freshness_status_source": "latest sensor timestamp vs configured freshness policy",
            "persisted_alerts_are_separate": True,
            "temperature_thresholds_configured": temperature_evaluated > 0,
            "history_window_hours": HISTORY_WINDOW_HOURS,
            "history_points": HISTORY_POINTS,
        },
    }
    return JSONResponse(content=jsonable_encoder(result))
