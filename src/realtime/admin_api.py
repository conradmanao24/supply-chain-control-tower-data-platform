from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg2
from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
                    count(*)::int AS total_rules,
                    count(*) FILTER (WHERE enabled)::int AS enabled_rules,
                    count(*) FILTER (WHERE NOT enabled)::int AS disabled_rules,
                    count(*) FILTER (WHERE severity='critical')::int AS critical_rules,
                    count(*) FILTER (WHERE severity='warning')::int AS warning_rules,
                    count(*) FILTER (WHERE severity='info')::int AS info_rules,
                    count(*) FILTER (WHERE source_native)::int AS source_native_rules
                FROM alert.rule_config
                """
            )
            summary = dict(cur.fetchone())

            cur.execute(
                """
                SELECT
                    domain,
                    count(*)::int AS total_rules,
                    count(*) FILTER (WHERE enabled)::int AS enabled_rules,
                    count(*) FILTER (WHERE NOT enabled)::int AS disabled_rules,
                    count(*) FILTER (WHERE severity='critical')::int AS critical_rules,
                    count(*) FILTER (WHERE severity='warning')::int AS warning_rules,
                    count(*) FILTER (WHERE severity='info')::int AS info_rules
                FROM alert.rule_config
                GROUP BY domain
                ORDER BY domain
                """
            )
            domains = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    rule_id,
                    domain,
                    description,
                    enabled,
                    severity,
                    source_native,
                    parameters,
                    updated_at
                FROM alert.rule_config
                ORDER BY domain,rule_id
                """
            )
            rules = [dict(row) for row in cur.fetchall()]

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
                SELECT singleton,mode,owner_run_id,acquired_at
                FROM control.processing_guard
                LIMIT 1
                """
            )
            processing_guard = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT audit_id,rule_id,actor,changed_at,before_config,after_config,
                       reevaluation_result
                FROM alert.rule_config_history
                ORDER BY changed_at DESC,audit_id DESC
                LIMIT 100
                """
            )
            recent_changes = [dict(row) for row in cur.fetchall()]

    result = {
        "generated_at": datetime.now(timezone.utc),
        "mode": "rule_management",
        "summary": summary,
        "domains": domains,
        "rules": rules,
        "alert_engine": alert_engine,
        "processing_guard": processing_guard,
        "recent_changes": recent_changes,
    }
    return JSONResponse(content=jsonable_encoder(result))
