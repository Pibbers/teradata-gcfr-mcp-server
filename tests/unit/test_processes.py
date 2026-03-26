"""Unit tests for teradata_gcfr_mcp.tools.processes."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.processes import (
    _handle_current_process_status,
    _handle_process_history,
    _handle_process_status_summary,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PROCESS_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Process_Id": 42,
    "Process_State": 99,
    "Stream_Key": 1,
    "Business_Date": "2024-01-15",
    "Business_Date_Cycle_Num": 1,
}

_HISTORY_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Process_Id": 42,
    "Process_State": 99,
    "Stream_Key": 1,
    "Business_Date": "2024-01-15",
    "Start_Date_Ts": "2024-01-15 02:00:00",
    "End_Date_Ts": "2024-01-15 02:05:00",
    "Tool_Status_Code": "SUCC",
}

_SUMMARY_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Business_Date": "2024-01-15",
    "Process_State": 99,
    "Stream_Key": 1,
    "Completed_Flag": 1,
    "Error_Code": None,
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.processes.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_current_process_status
# ---------------------------------------------------------------------------


def test_current_process_status_normal() -> None:
    """Returns active processes when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_PROCESS_ROW]):
        result = _handle_current_process_status(pool, s, None, None)

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    assert result[0]["Process_State"] == 99


def test_current_process_status_empty() -> None:
    """Returns empty list when no processes are active."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_current_process_status(pool, s, None, None)

    assert result == []


def test_current_process_status_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_current_process_status(pool, s, None, None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_process_history
# ---------------------------------------------------------------------------


def test_process_history_normal() -> None:
    """Returns history rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_HISTORY_ROW]) as mock_eq:
        result = _handle_process_history(pool, s, "2024-01-15", "2024-01-15", None)

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    assert result[0]["Tool_Status_Code"] == "SUCC"
    # Verify both dates appear in params
    call_params = mock_eq.call_args[0][2]
    assert "2024-01-15" in call_params


def test_process_history_empty() -> None:
    """Returns empty list when no history rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_process_history(pool, s, "2024-01-15", "2024-01-15", None)

    assert result == []


def test_process_history_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_process_history(pool, s, "2024-01-15", "2024-01-15", None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_process_status_summary
# ---------------------------------------------------------------------------


def test_process_status_summary_normal() -> None:
    """Returns summary rows for the requested business date."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_SUMMARY_ROW]):
        result = _handle_process_status_summary(pool, s, "2024-01-15")

    assert len(result) == 1
    assert result[0]["Business_Date"] == "2024-01-15"
    assert result[0]["Completed_Flag"] == 1


def test_process_status_summary_empty() -> None:
    """Returns empty list when no processes ran on that date."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_process_status_summary(pool, s, "2024-01-15")

    assert result == []


def test_process_status_summary_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_process_status_summary(pool, s, "2024-01-15")

    assert "error" in result[0]
