"""Stream status MCP tools for GCFR operational reporting."""

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


def _handle_stream_status(
    pool: TDConnectionPool,
    settings: Settings,
    stream_key: str | None,
    date_from: str,
    date_to: str,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_Stream"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if stream_key is not None:
        parsed = _parse_stream_key(stream_key)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " AND Stream_Key = ?"
        params.append(parsed)

    sql += " ORDER BY Business_Date DESC, Stream_Key"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


def _handle_current_stream_status(
    pool: TDConnectionPool,
    settings: Settings,
    stream_key: str | None,
) -> list[dict[str, Any]]:
    sql = f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_CurrentStream"
    params: list[Any] = []

    if stream_key is not None:
        parsed = _parse_stream_key(stream_key)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " WHERE Stream_Key = ?"
        params.append(parsed)

    sql += " ORDER BY Stream_Key"
    return execute_query(pool, sql, params or None, max_rows=settings.GCFR_MAX_ROWS)


def _handle_stream_business_date(
    pool: TDConnectionPool,
    settings: Settings,
    stream_key: str,
) -> list[dict[str, Any]]:
    parsed = _parse_stream_key(stream_key)
    if isinstance(parsed, dict):
        return [parsed]
    sql = (
        f"SELECT * FROM {settings.GCFR_VIEW_DB}.GCFR_Stream_BusDate"
        " WHERE Stream_Key = ?"
    )
    return execute_query(pool, sql, [parsed], max_rows=settings.GCFR_MAX_ROWS)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register all stream tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_stream_status(
        stream_key: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show stream execution history and completion state for a date range.

        Use this to find out whether a stream ran successfully, is still
        running, or failed for a given business date.  date_from and date_to
        default to yesterday and today respectively when not supplied.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return _handle_stream_status(pool, settings, stream_key, eff_from, eff_to)

    @mcp.tool()
    async def gcfr_current_stream_status(
        stream_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show streams that are actively running RIGHT NOW.

        Use this first when investigating a running or stuck batch.
        Optionally filter to a specific stream by providing stream_key.
        """
        return _handle_current_stream_status(pool, settings, stream_key)

    @mcp.tool()
    async def gcfr_stream_business_date(
        stream_key: str,
    ) -> list[dict[str, Any]]:
        """Show the current, previous, and next business date for a stream.

        Use this to understand where a stream's processing date is set and
        whether it is in sync with the expected calendar date.
        """
        return _handle_stream_business_date(pool, settings, stream_key)
