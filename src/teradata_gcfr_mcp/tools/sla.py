"""SLA reporting MCP tools for GCFR operational reporting."""

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


def _coerce_intervals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert timedelta values (INTERVAL DAY TO SECOND) to str."""
    return [
        {k: str(v) if isinstance(v, timedelta) else v for k, v in row.items()}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Sync handler functions — testable without MCP machinery
# ---------------------------------------------------------------------------


def _handle_sla_process_report(
    pool: TDConnectionPool,
    settings: Settings,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_SLAProcess"
        " WHERE Business_Date BETWEEN ? AND ?"
        " ORDER BY Business_Date DESC, Process_Name"
    )
    rows = execute_query(pool, sql, [date_from, date_to], max_rows=settings.GCFR_MAX_ROWS)
    return _coerce_intervals(rows)


def _handle_sla_stream_report(
    pool: TDConnectionPool,
    settings: Settings,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_SLAStream"
        " WHERE Business_Date BETWEEN ? AND ?"
        " ORDER BY Business_Date DESC, Stream_Key"
    )
    rows = execute_query(pool, sql, [date_from, date_to], max_rows=settings.GCFR_MAX_ROWS)
    return _coerce_intervals(rows)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register all SLA tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_sla_process_report(
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Compare expected vs actual process start time, end time, and duration.

        Shows whether SLAs were met. SLA_Run_Duration is returned as a
        formatted string (INTERVAL DAY TO SECOND).
        date_from and date_to default to yesterday and today respectively.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_sla_process_report, pool, settings, eff_from, eff_to
        )

    @mcp.tool()
    async def gcfr_sla_stream_report(
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Compare expected vs actual stream duration SLAs.

        SLA duration fields are returned as formatted strings.
        date_from and date_to default to yesterday and today respectively.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_sla_stream_report, pool, settings, eff_from, eff_to
        )
