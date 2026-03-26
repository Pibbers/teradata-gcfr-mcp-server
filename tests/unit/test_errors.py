"""Unit tests for teradata_gcfr_mcp.tools.errors."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.errors import (
    _handle_error_log,
    _handle_execution_log,
    _handle_failed_processes,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FAILED_PROCESS_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Business_Date": "2024-01-15",
    "Process_State": 5,
    "Stream_Key": 1,
    "Error_Code": "ERR-001",
    "System_Defined_Msg": "Connection timeout",
}

_ERROR_LOG_ROW: dict[str, Any] = {
    "Logger_Name": "GCFR_LOAD",
    "Error_Code": "ERR-001",
    "System_Defined_Msg": "Connection timeout",
    "Calling_API": "SP_LOAD_DATA",
    "Process_State": 5,
    "Business_Date": "2024-01-15",
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Stream_Key": 1,
    "Start_Date_Ts": "2024-01-15 02:00:00",
    "End_Date_Ts": "2024-01-15 02:01:00",
}

_EXECUTION_LOG_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Stream_Key": 1,
    "Business_Date": "2024-01-15",
    "Process_State": 5,
    "Step_Name": "EXTRACT_DATA",
    "Step_Status": "FAIL",
    "Start_Date_Ts": "2024-01-15 02:00:00",
    "End_Date_Ts": "2024-01-15 02:01:00",
    "Error_Code": "ERR-001",
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.errors.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_failed_processes
# ---------------------------------------------------------------------------


def test_failed_processes_normal() -> None:
    """Returns failed process rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_FAILED_PROCESS_ROW]):
        result = _handle_failed_processes(
            pool, s, "2024-01-15", "2024-01-15", None, None
        )

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    assert result[0]["Error_Code"] == "ERR-001"
    assert result[0]["System_Defined_Msg"] == "Connection timeout"


def test_failed_processes_empty() -> None:
    """Returns empty list when no failures match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_failed_processes(
            pool, s, "2024-01-15", "2024-01-15", None, None
        )

    assert result == []


def test_failed_processes_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_failed_processes(
            pool, s, "2024-01-15", "2024-01-15", None, None
        )

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_error_log
# ---------------------------------------------------------------------------


def test_error_log_normal() -> None:
    """Returns error log rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_ERROR_LOG_ROW]):
        result = _handle_error_log(pool, s, "2024-01-15", "2024-01-15", None)

    assert len(result) == 1
    assert result[0]["Logger_Name"] == "GCFR_LOAD"
    assert result[0]["Error_Code"] == "ERR-001"
    assert result[0]["Calling_API"] == "SP_LOAD_DATA"
    assert result[0]["System_Defined_Msg"] == "Connection timeout"


def test_error_log_empty() -> None:
    """Returns empty list when no error log entries match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_error_log(pool, s, "2024-01-15", "2024-01-15", None)

    assert result == []


def test_error_log_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_error_log(pool, s, "2024-01-15", "2024-01-15", None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_execution_log
# ---------------------------------------------------------------------------


def test_execution_log_normal() -> None:
    """Returns execution log rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_EXECUTION_LOG_ROW]):
        result = _handle_execution_log(pool, s, "2024-01-15", "2024-01-15", None, None)

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    assert result[0]["Step_Name"] == "EXTRACT_DATA"
    assert result[0]["Step_Status"] == "FAIL"
    assert result[0]["Error_Code"] == "ERR-001"


def test_execution_log_empty() -> None:
    """Returns empty list when no execution log entries match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_execution_log(pool, s, "2024-01-15", "2024-01-15", None, None)

    assert result == []


def test_execution_log_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_execution_log(pool, s, "2024-01-15", "2024-01-15", None, None)

    assert "error" in result[0]
