"""Data lineage and health-check MCP tools for GCFR."""

from __future__ import annotations

import re
import time
from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool, execute_query

_DATE_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(value: str) -> bool:
    return bool(_DATE_RE.match(value))


# ---------------------------------------------------------------------------
# Sync handler functions — testable without MCP machinery
# ---------------------------------------------------------------------------


def _handle_data_lineage(
    pool: TDConnectionPool,
    settings: Settings,
    target_table: str,
    business_date: str,
) -> list[dict[str, Any]]:
    if not _valid_date(business_date):
        return [
            {
                "error": (
                    f"Invalid date format — expected YYYY-MM-DD, got {business_date!r}"
                )
            }
        ]

    sql = (
        f"SELECT Src_Object_Name_FQ, Src_Kind, Edge_Relationship,"
        f" Tgt_Object_Name_FQ, Tgt_Kind, Crt_Process_Name"
        f" FROM {settings.GCFR_OPR_DB}.GCFR_Object_Lineage"
        " WHERE UPPER(Tgt_Object_Name) = UPPER(?)"
        " AND Business_Date = ?"
        " ORDER BY Src_Object_Name_FQ"
    )
    return execute_query(
        pool, sql, [target_table, business_date], max_rows=settings.GCFR_MAX_ROWS
    )


def _handle_health_check(
    pool: TDConnectionPool,
    settings: Settings,
) -> list[dict[str, Any]]:
    t_start = time.monotonic()

    result1 = execute_query(
        pool,
        f"SELECT COUNT(*) AS stream_count"
        f" FROM {settings.GCFR_VIEW_DB}.GCFR_Stream_BusDate",
    )
    view_db_ok = bool(result1 and "error" not in result1[0])
    stream_count = 0
    if view_db_ok:
        raw = result1[0].get("stream_count", 0)
        stream_count = int(raw) if raw is not None else 0

    result2 = execute_query(
        pool,
        f"SELECT COUNT(*) AS view_count"
        f" FROM {settings.GCFR_OPR_DB}.GCFR_RV_Stream",
    )
    reporting_view_accessible = bool(result2 and "error" not in result2[0])

    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    status = "ok" if (view_db_ok and reporting_view_accessible) else "error"

    return [
        {
            "status": status,
            "gcfr_view_db": settings.GCFR_VIEW_DB,
            "gcfr_opr_db": settings.GCFR_OPR_DB,
            "stream_count": stream_count,
            "reporting_view_accessible": reporting_view_accessible,
            "response_time_ms": elapsed_ms,
        }
    ]


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register lineage and health-check tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_data_lineage(
        target_table: str,
        business_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Trace a target table back to its source objects.

        Shows the full lineage chain with edge relationships.
        Returns: Src_Object_Name_FQ, Src_Kind, Edge_Relationship,
        Tgt_Object_Name_FQ, Tgt_Kind, Crt_Process_Name.
        Defaults to today when business_date is not supplied.
        """
        eff_date = business_date or date.today().isoformat()
        return _handle_data_lineage(pool, settings, target_table, eff_date)

    @mcp.tool()
    async def gcfr_health_check() -> list[dict[str, Any]]:
        """Verify the MCP server can reach both GCFR view databases.

        Run this first if tools are returning errors.
        Returns status, database names, stream_count, and response_time_ms.
        """
        return _handle_health_check(pool, settings)
