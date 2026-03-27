"""Error investigation MCP tools for GCFR operational reporting."""

from __future__ import annotations

import asyncio
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


def _handle_failed_processes(
    pool: TDConnectionPool,
    settings: Settings,
    date_from: str,
    date_to: str,
    stream_key: str | None,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_FailedProcessDetail"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if stream_key is not None:
        parsed = _parse_stream_key(stream_key)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " AND Stream_Key = ?"
        params.append(parsed)

    if process_name is not None:
        sql += " AND Process_Name = ?"
        params.append(process_name)

    sql += " ORDER BY Business_Date DESC, Process_Name"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


def _handle_error_log(
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

    # Exclude Sql_Text (CLOB) — too large for default output
    sql = (
        f"SELECT Logger_Name, Error_Code, System_Defined_Msg, Calling_API,"
        f" Process_State, Business_Date, Process_Name, Stream_Key,"
        f" Start_Date_Ts, End_Date_Ts"
        f" FROM {settings.GCFR_VIEW_DB}.GCFR_Error_Log"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if process_name is not None:
        sql += " AND Process_Name = ?"
        params.append(process_name)

    sql += " ORDER BY Business_Date DESC, Start_Date_Ts DESC"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


def _handle_execution_log(
    pool: TDConnectionPool,
    settings: Settings,
    date_from: str,
    date_to: str,
    process_name: str | None,
    stream_key: str | None,
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

    # Exclude Sql_Text (CLOB) — offer only if explicitly requested
    sql = (
        f"SELECT Process_Name, Stream_Key, Business_Date, Process_State,"
        f" Step_Name, Step_Status, Start_Date_Ts, End_Date_Ts, Error_Code"
        f" FROM {settings.GCFR_OPR_DB}.GCFR_RV_ExecutionLog"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if process_name is not None:
        sql += " AND Process_Name = ?"
        params.append(process_name)

    if stream_key is not None:
        parsed = _parse_stream_key(stream_key)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " AND Stream_Key = ?"
        params.append(parsed)

    sql += " ORDER BY Business_Date DESC, Start_Date_Ts DESC"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register all error investigation tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_failed_processes(
        date_from: str | None = None,
        date_to: str | None = None,
        stream_key: str | None = None,
        process_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show failed process instances with full error details.

        This is the first tool to use when investigating a batch failure.
        date_from and date_to default to yesterday and today respectively.
        Optionally filter by stream_key and/or process_name.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_failed_processes,
            pool, settings, eff_from, eff_to, stream_key, process_name,
        )

    @mcp.tool()
    async def gcfr_error_log(
        date_from: str | None = None,
        date_to: str | None = None,
        process_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show raw error log entries for root cause investigation.

        Includes the calling API and step where the error occurred.
        Sql_Text (CLOB) is excluded from output — ask separately if needed.
        date_from and date_to default to yesterday and today respectively.
        Optionally filter by process_name.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_error_log, pool, settings, eff_from, eff_to, process_name
        )

    @mcp.tool()
    async def gcfr_execution_log(
        date_from: str | None = None,
        date_to: str | None = None,
        process_name: str | None = None,
        stream_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show step-level execution trace for detailed process debugging.

        Only populated when GCFR is running at debug level 2 or higher.
        Sql_Text (CLOB) is excluded from output — ask separately if needed.
        date_from and date_to default to yesterday and today respectively.
        Optionally filter by process_name and/or stream_key.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_execution_log,
            pool, settings, eff_from, eff_to, process_name, stream_key,
        )
