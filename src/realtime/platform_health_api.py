from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg2
from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/api/platform-health", tags=["platform-health"])
METADATA_MAX_AGE_HOURS = max(
    1.0,
    float(os.environ.get("PLATFORM_METADATA_MAX_AGE_HOURS", "36")),
)


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


@router.get("/overview")
def overview() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    pipeline_name,
                    last_successful_cutoff,
                    last_successful_run_id,
                    updated_at
                FROM control.pipeline_state
                ORDER BY pipeline_name
                """
            )
            pipelines = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    source_name,
                    safe_through_cutoff,
                    basis,
                    updated_at
                FROM control.source_frontier
                ORDER BY source_name
                """
            )
            frontiers = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT singleton,mode,owner_run_id,acquired_at
                FROM control.processing_guard
                LIMIT 1
                """
            )
            processing_guard = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT singleton,activated_at,backlog_policy,notes
                FROM alert.engine_state
                LIMIT 1
                """
            )
            alert_engine = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                    quality_run_id,
                    airflow_run_id,
                    mode,
                    status,
                    started_at,
                    finished_at,
                    passed_checks,
                    failed_checks,
                    warning_checks,
                    error_message
                FROM quality.run_history
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            latest_quality = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged'))::int AS active,
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged') AND a.severity='critical')::int AS critical,
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged') AND a.severity='warning')::int AS warning,
                    count(*) FILTER (WHERE a.status IN ('open','acknowledged') AND a.severity='info')::int AS info,
                    count(*) FILTER (
                        WHERE a.status IN ('open','acknowledged') AND r.domain='platform'
                    )::int AS platform_active,
                    count(*) FILTER (
                        WHERE a.status IN ('open','acknowledged')
                          AND r.domain='platform'
                          AND a.severity='critical'
                    )::int AS platform_critical
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                """
            )
            alerts = dict(cur.fetchone())

            cur.execute(
                """
                SELECT
                    count(*)::int AS total_events,
                    count(*) FILTER (WHERE occurred_at_utc >= now()-interval '24 hours')::int AS events_24h,
                    count(*) FILTER (
                        WHERE occurred_at_utc >= now()-interval '24 hours'
                          AND processed_at IS NOT NULL
                    )::int AS processed_24h,
                    count(*) FILTER (WHERE processed_at IS NULL)::int AS unprocessed,
                    max(occurred_at_utc) AS latest_event_at,
                    max(processed_at) AS latest_processed_at,
                    coalesce(
                        avg(extract(epoch FROM (processed_at-occurred_at_utc)))
                            FILTER (
                                WHERE occurred_at_utc >= now()-interval '24 hours'
                                  AND processed_at IS NOT NULL
                            ),
                        0
                    )::numeric(12,3) AS avg_processing_lag_seconds,
                    coalesce(
                        max(extract(epoch FROM (processed_at-occurred_at_utc)))
                            FILTER (
                                WHERE occurred_at_utc >= now()-interval '24 hours'
                                  AND processed_at IS NOT NULL
                            ),
                        0
                    )::numeric(12,3) AS max_processing_lag_seconds
                FROM realtime.event_log
                """
            )
            realtime = dict(cur.fetchone())

            cur.execute(
                """
                SELECT processing_result,count(*)::int AS event_count
                FROM realtime.event_log
                GROUP BY processing_result
                ORDER BY event_count DESC,processing_result
                """
            )
            event_results = [dict(row) for row in cur.fetchall()]

    now = datetime.now(timezone.utc)
    pipeline_cutoff = pipelines[0]["last_successful_cutoff"] if pipelines else None
    source_frontier = frontiers[0]["safe_through_cutoff"] if frontiers else None
    pipeline_updated_at = pipelines[0]["updated_at"] if pipelines else None
    frontier_updated_at = frontiers[0]["updated_at"] if frontiers else None
    quality_finished_at = latest_quality.get("finished_at")

    def age_hours(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return round(max(0.0, (now - value).total_seconds() / 3600.0), 3)

    pipeline_age_hours = age_hours(pipeline_updated_at)
    frontier_age_hours = age_hours(frontier_updated_at)
    quality_age_hours = age_hours(quality_finished_at)

    freshness = {
        "max_age_hours": METADATA_MAX_AGE_HOURS,
        "pipeline_age_hours": pipeline_age_hours,
        "frontier_age_hours": frontier_age_hours,
        "quality_age_hours": quality_age_hours,
        "pipeline_fresh": bool(
            pipeline_age_hours is not None
            and pipeline_age_hours <= METADATA_MAX_AGE_HOURS
        ),
        "frontier_fresh": bool(
            frontier_age_hours is not None
            and frontier_age_hours <= METADATA_MAX_AGE_HOURS
        ),
        "quality_fresh": bool(
            quality_age_hours is not None
            and quality_age_hours <= METADATA_MAX_AGE_HOURS
        ),
    }
    freshness["all_fresh"] = bool(
        freshness["pipeline_fresh"]
        and freshness["frontier_fresh"]
        and freshness["quality_fresh"]
    )

    result = {
        "generated_at": datetime.now(timezone.utc),
        "pipeline_cutoff": pipeline_cutoff,
        "source_frontier": source_frontier,
        "watermark_aligned": bool(
            pipeline_cutoff is not None
            and source_frontier is not None
            and pipeline_cutoff == source_frontier
        ),
        "pipelines": pipelines,
        "frontiers": frontiers,
        "processing_guard": processing_guard,
        "alert_engine": alert_engine,
        "latest_quality": latest_quality,
        "freshness": freshness,
        "alerts": alerts,
        "realtime": {
            "total_events": int(realtime["total_events"]),
            "events_24h": int(realtime["events_24h"]),
            "processed_24h": int(realtime["processed_24h"]),
            "unprocessed": int(realtime["unprocessed"]),
            "avg_processing_lag_seconds": float(realtime["avg_processing_lag_seconds"]),
            "max_processing_lag_seconds": float(realtime["max_processing_lag_seconds"]),
            "latest_event_at": realtime["latest_event_at"],
            "latest_processed_at": realtime["latest_processed_at"],
        },
        "event_results": event_results,
    }
    return JSONResponse(content=jsonable_encoder(result))
