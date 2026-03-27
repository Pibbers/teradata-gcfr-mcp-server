"""Transform statistics MCP tools for GCFR operational reporting."""

from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool, execute_query

_DATE_RE: re.Pattern[str] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_TOP_N_MIN = 1
_TOP_N_MAX = 50


def _valid_date(value: str) -> bool:
    return bool(_DATE_RE.match(value))


def _parse_ctl_id(ctl_id: str) -> int | dict[str, Any]:
    """Convert a ctl_id string to int. Returns an error dict on bad input."""
    try:
        return int(ctl_id)
    except ValueError:
        return {"error": f"Invalid ctl_id {ctl_id!r}: must be a numeric value."}


def _validate_top_n(top_n: int) -> dict[str, Any] | None:
    """Return an error dict if top_n is out of range, else None."""
    if not (_TOP_N_MIN <= top_n <= _TOP_N_MAX):
        return {
            "error": (
                f"Invalid top_n {top_n!r}: must be an integer between "
                f"{_TOP_N_MIN} and {_TOP_N_MAX}."
            )
        }
    return None


# ---------------------------------------------------------------------------
# Sync handler functions — testable without MCP machinery
# ---------------------------------------------------------------------------


def _handle_transform_stats(
    pool: TDConnectionPool,
    settings: Settings,
    date_from: str,
    date_to: str,
    ctl_id: str | None,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_Transform"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if ctl_id is not None:
        parsed = _parse_ctl_id(ctl_id)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " AND Ctl_Id = ?"
        params.append(parsed)

    sql += " ORDER BY Business_Date DESC, Process_Name"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


def _handle_top_slowest_processes(
    pool: TDConnectionPool,
    settings: Settings,
    business_date: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if not _valid_date(business_date):
        return [
            {
                "error": (
                    f"Invalid date format — expected YYYY-MM-DD, got {business_date!r}"
                )
            }
        ]

    err = _validate_top_n(top_n)
    if err is not None:
        return [err]

    sql = (
        f"SELECT TOP {top_n} * FROM {settings.GCFR_OPR_DB}.GCFR_RV_LongestRunProcess"
        " WHERE Business_Date = ?"
        " ORDER BY Elapsed_Seconds DESC"
    )
    return execute_query(pool, sql, [business_date])


def _handle_top_slowest_streams(
    pool: TDConnectionPool,
    settings: Settings,
    business_date: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if not _valid_date(business_date):
        return [
            {
                "error": (
                    f"Invalid date format — expected YYYY-MM-DD, got {business_date!r}"
                )
            }
        ]

    err = _validate_top_n(top_n)
    if err is not None:
        return [err]

    sql = (
        f"SELECT TOP {top_n} * FROM {settings.GCFR_OPR_DB}.GCFR_RV_LongestRunStream"
        " WHERE Business_Date = ?"
        " ORDER BY Elapsed_Seconds DESC"
    )
    return execute_query(pool, sql, [business_date])


def _handle_data_trend_loads(
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_LoadSumByBusDate"
        " WHERE Business_Date BETWEEN ? AND ?"
        " ORDER BY Business_Date DESC"
    )
    return execute_query(pool, sql, [date_from, date_to], max_rows=settings.GCFR_MAX_ROWS)


def _handle_data_trend_transforms(
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_TfmSumByBusDate"
        " WHERE Business_Date BETWEEN ? AND ?"
        " ORDER BY Business_Date DESC"
    )
    return execute_query(pool, sql, [date_from, date_to], max_rows=settings.GCFR_MAX_ROWS)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register all transform tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_transform_stats(
        date_from: str | None = None,
        date_to: str | None = None,
        ctl_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show transformation statistics — rows inserted, updated, and deleted per process.

        Use this to verify data movement through the warehouse.
        date_from and date_to default to yesterday and today respectively.
        Optionally filter by ctl_id.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_transform_stats, pool, settings, eff_from, eff_to, ctl_id
        )

    @mcp.tool()
    async def gcfr_top_slowest_processes(
        business_date: str | None = None,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Show the N slowest processes by elapsed duration for a business date.

        Use this to identify performance bottlenecks.
        top_n must be between 1 and 50 (default 10).
        Defaults to today when business_date is not supplied.
        """
        eff_date = business_date or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_top_slowest_processes, pool, settings, eff_date, top_n
        )

    @mcp.tool()
    async def gcfr_top_slowest_streams(
        business_date: str | None = None,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Show the N slowest streams by elapsed duration.

        top_n must be between 1 and 50 (default 10).
        Defaults to today when business_date is not supplied.
        """
        eff_date = business_date or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_top_slowest_streams, pool, settings, eff_date, top_n
        )

    @mcp.tool()
    async def gcfr_data_trend_loads(
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show daily load volume trends — total rows loaded per business date.

        Use this to spot unusual volume changes.
        date_from and date_to default to yesterday and today respectively.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_data_trend_loads, pool, settings, eff_from, eff_to
        )

    @mcp.tool()
    async def gcfr_data_trend_transforms(
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show daily transform volume trends by business date.

        date_from and date_to default to yesterday and today respectively.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_data_trend_transforms, pool, settings, eff_from, eff_to
        )
