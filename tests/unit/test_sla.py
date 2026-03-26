"""Unit tests for teradata_gcfr_mcp.tools.sla."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.sla import (
    _handle_sla_process_report,
    _handle_sla_stream_report,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SLA_PROCESS_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Business_Date": "2024-01-15",
    "SLA_Start_Time": "02:00:00",
    "SLA_End_Time": "04:00:00",
    "Actual_Start_Time": "02:05:00",
    "Actual_End_Time": "04:10:00",
    "SLA_Run_Duration": timedelta(hours=2),
    "Actual_Run_Duration": timedelta(hours=2, minutes=5),
    "SLA_Met_Flag": 0,
}

_SLA_STREAM_ROW: dict[str, Any] = {
    "Stream_Key": 1,
    "Stream_Name": "DAILY_LOAD",
    "Business_Date": "2024-01-15",
    "SLA_Duration": timedelta(hours=4),
    "Actual_Duration": timedelta(hours=4, minutes=20),
    "SLA_Met_Flag": 0,
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.sla.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_sla_process_report
# ---------------------------------------------------------------------------


def test_sla_process_report_normal() -> None:
    """Returns SLA process rows and converts timedelta fields to str."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_SLA_PROCESS_ROW]):
        result = _handle_sla_process_report(pool, s, "2024-01-15", "2024-01-15")

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    # timedelta values must be coerced to str
    assert isinstance(result[0]["SLA_Run_Duration"], str)
    assert isinstance(result[0]["Actual_Run_Duration"], str)


def test_sla_process_report_empty() -> None:
    """Returns empty list when no SLA rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_sla_process_report(pool, s, "2024-01-15", "2024-01-15")

    assert result == []


def test_sla_process_report_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_sla_process_report(pool, s, "2024-01-15", "2024-01-15")

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_sla_stream_report
# ---------------------------------------------------------------------------


def test_sla_stream_report_normal() -> None:
    """Returns SLA stream rows and converts timedelta fields to str."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_SLA_STREAM_ROW]):
        result = _handle_sla_stream_report(pool, s, "2024-01-15", "2024-01-15")

    assert len(result) == 1
    assert result[0]["Stream_Key"] == 1
    assert isinstance(result[0]["SLA_Duration"], str)
    assert isinstance(result[0]["Actual_Duration"], str)


def test_sla_stream_report_empty() -> None:
    """Returns empty list when no SLA stream rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_sla_stream_report(pool, s, "2024-01-15", "2024-01-15")

    assert result == []


def test_sla_stream_report_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_sla_stream_report(pool, s, "2024-01-15", "2024-01-15")

    assert "error" in result[0]
