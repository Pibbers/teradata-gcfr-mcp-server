"""Staging load MCP tools for GCFR operational reporting."""

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


def _parse_ctl_id(ctl_id: str) -> int | dict[str, Any]:
    """Convert a ctl_id string to int. Returns an error dict on bad input."""
    try:
        return int(ctl_id)
    except ValueError:
        return {"error": f"Invalid ctl_id {ctl_id!r}: must be a numeric value."}


# ---------------------------------------------------------------------------
# Sync handler functions — testable without MCP machinery
# ---------------------------------------------------------------------------


def _handle_load_stats(
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
        f"SELECT Ctl_Id, File_Id, Business_Date, Process_Name,"
        f" Rows_Input, Rows_Considered, Rows_Not_Considered, Rows_Rejected,"
        f" Rows_Inserted, Rows_ET, Rows_UV, Start_Ts, End_Ts, Load_Status"
        f" FROM {settings.GCFR_OPR_DB}.GCFR_RV_Load"
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


def _handle_load_status(
    pool: TDConnectionPool,
    settings: Settings,
    business_date: str,
    ctl_id: str | None,
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_Load_Status"
        " WHERE Business_Date = ?"
    )
    params: list[Any] = [business_date]

    if ctl_id is not None:
        parsed = _parse_ctl_id(ctl_id)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " AND Ctl_Id = ?"
        params.append(parsed)

    sql += " ORDER BY Process_Name"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


def _handle_dataset_registered(
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
        f"SELECT * FROM {settings.GCFR_OPR_DB}.GCFR_RV_DataSetReg"
        " WHERE Business_Date BETWEEN ? AND ?"
    )
    params: list[Any] = [date_from, date_to]

    if ctl_id is not None:
        parsed = _parse_ctl_id(ctl_id)
        if isinstance(parsed, dict):
            return [parsed]
        sql += " AND Ctl_Id = ?"
        params.append(parsed)

    sql += " ORDER BY Business_Date DESC, Ctl_Id"
    return execute_query(pool, sql, params, max_rows=settings.GCFR_MAX_ROWS)


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------


def register(mcp: FastMCP, pool: TDConnectionPool, settings: Settings) -> None:
    """Register all load tools with the FastMCP server."""

    @mcp.tool()
    async def gcfr_load_stats(
        date_from: str | None = None,
        date_to: str | None = None,
        ctl_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show staging load statistics — row counts, rejections, ET errors, UV violations.

        Key columns: Ctl_Id, File_Id, Business_Date, Process_Name,
        Rows_Input, Rows_Considered, Rows_Not_Considered, Rows_Rejected,
        Rows_Inserted, Rows_ET, Rows_UV, Start_Ts, End_Ts, Load_Status.
        date_from and date_to default to yesterday and today respectively.
        Optionally filter by ctl_id.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_load_stats, pool, settings, eff_from, eff_to, ctl_id
        )

    @mcp.tool()
    async def gcfr_load_status(
        business_date: str | None = None,
        ctl_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show which staging tables loaded successfully for a business date, with row counts.

        Use this to verify all expected feeds have arrived.
        Defaults to today when business_date is not supplied.
        Optionally filter by ctl_id.
        """
        eff_date = business_date or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_load_status, pool, settings, eff_date, ctl_id
        )

    @mcp.tool()
    async def gcfr_dataset_registered(
        date_from: str | None = None,
        date_to: str | None = None,
        ctl_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Show source data sets registered for processing and their file extract status.

        Count_Source vs Count_Target reconciliation is here.
        date_from and date_to default to yesterday and today respectively.
        Optionally filter by ctl_id.
        """
        eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
        eff_to = date_to or date.today().isoformat()
        return await asyncio.to_thread(
            _handle_dataset_registered, pool, settings, eff_from, eff_to, ctl_id
        )
