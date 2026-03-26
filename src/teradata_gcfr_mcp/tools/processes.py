"""Process status MCP tools for GCFR operational reporting."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool, execute_query

_DATE_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(value: str) -> bool:
    return bool(_DATE_RE.match(value))


def _parse_stream_key(stream_key: str) -> int | dict[str, Any]:
    """Convert a stream_key string to int. Returns an error dict on bad input."""
    try:
        return int(stream_key)
    except ValueError:
        return {"error": f"Invalid stream_key {stream_key!r}: must be a numeric value."}


# ---------------------------------------------------------------------------
# Sync handler functions — testable without MCP machinery
# ---------------------------------------------------------------------------


def _handle_current_process_status(
    pool: TDConnectionPool,
    settings: Settings,
    stream_key: str | None,
    process_name: str | None,
) -> list[dict[str, Any]]:
    sql = f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_CurrentProcess"
    conditions: list[str] = []
    params: list[Any] = []

    if stream_key is not None:
        parsed = _parse_stream_key(stream_key)
        if isinstance(parsed, dict):
            return [parsed]
        conditions.append("Stream_Key = ?")
        params.append(parsed)

    if process_name is not None:
        conditions.append("Process_Name = ?")
        params.append(process_name)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY Stream_Key, Process_Name"
    return execute_query(pool, sql, params or None, max_rows=settings.GCFR_MAX_ROWS)


def _handle_process_history(
    pool: TDConnectionPool,
    settings: Settings,
    date_from: str,
    date_to: str,
    process_name: str | None,
) -> list[dict[str, Any]]:
    if not _valid_date(date_from) or not _valid_date(date_to):
        return [
            {
                "error": (
                    "Invalid date format — expected YYYY-MM-DD, "
                    f"got date_from={date_from!r} date_to={date_to!r}"
                )
            }
        ]

    sql = (
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_Process"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if process_name is not None:
        sql += " AND Process_Name = ?"
        params.append(process_name)

    sql += " ORDER BY Business_Date DESC, Process_Name"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


def _handle_process_status_summary(
    pool: TDConnectionPool,
    settings: Settings,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_Process_Status"
        " WHERE Business_Date = ?"
        " ORDER BY Process_Name"
    )
    return execute_query(pool, sql, [business_date], max_rows=settings.GCFR_MAX_ROWS)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register all process tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_current_process_status(
        stream_key: str | None = None,
        process_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show active processes and their current execution step.

        Process_State values: 0=started, 1–98=in progress (restart point),
        99=complete.  Use this to find stuck or long-running processes.
        Filter by stream_key and/or process_name to narrow results.
        """
        return _handle_current_process_status(pool, settings, stream_key, process_name)

    @mcp.tool()
    async def gcfr_process_history(
        date_from: str | None = None,
        date_to: str | None = None,
        process_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show process execution history with timing and outcomes for a date range.

        Use this to understand how long processes took and whether they
        succeeded.  date_from and date_to default to yesterday and today
        respectively when not supplied.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return _handle_process_history(pool, settings, eff_from, eff_to, process_name)

    @mcp.tool()
    async def gcfr_process_status_summary(
        business_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show all processes for a business date — completed vs not completed.

        If a process did not complete, the error message is included.
        Use this for a quick end-of-day sign-off check.
        Defaults to today when business_date is not supplied.
        """
        eff_date = business_date or date.today().isoformat()
        return _handle_process_status_summary(pool, settings, eff_date)
