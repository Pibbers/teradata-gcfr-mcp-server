"""Unit tests for teradata_gcfr_mcp.tools.loads."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.loads import (
    _handle_dataset_registered,
    _handle_load_stats,
    _handle_load_status,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LOAD_STATS_ROW: dict[str, Any] = {
    "Ctl_Id": 101,
    "File_Id": 201,
    "Business_Date": "2024-01-15",
    "Rows_Input": 10000,
    "Rows_Inserted": 9980,
    "Rows_ET": 20,
    "Rows_UV": 0,
    "Load_Status": "SUCC",
}

_LOAD_STATUS_ROW: dict[str, Any] = {
    "Ctl_Id": 101,
    "Business_Date": "2024-01-15",
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Rows_Inserted": 9980,
    "Load_Status": "SUCC",
}

_DATASET_ROW: dict[str, Any] = {
    "Ctl_Id": 101,
    "Business_Date": "2024-01-15",
    "Count_Source": 10000,
    "Count_Target": 10000,
    "File_Extract_Status": "DONE",
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.loads.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_load_stats
# ---------------------------------------------------------------------------


def test_load_stats_normal() -> None:
    """Returns load stats rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_LOAD_STATS_ROW]):
        result = _handle_load_stats(pool, s, "2024-01-15", "2024-01-15", None)

    assert len(result) == 1
    assert result[0]["Ctl_Id"] == 101
    assert result[0]["Rows_Inserted"] == 9980
    assert result[0]["Rows_ET"] == 20


def test_load_stats_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_load_stats(pool, s, "2024-01-15", "2024-01-15", None)

    assert result == []


def test_load_stats_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_load_stats(pool, s, "2024-01-15", "2024-01-15", None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_load_status
# ---------------------------------------------------------------------------


def test_load_status_normal() -> None:
    """Returns load status rows for the requested business date."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_LOAD_STATUS_ROW]):
        result = _handle_load_status(pool, s, "2024-01-15", None)

    assert len(result) == 1
    assert result[0]["Business_Date"] == "2024-01-15"
    assert result[0]["Rows_Inserted"] == 9980


def test_load_status_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_load_status(pool, s, "2024-01-15", None)

    assert result == []


def test_load_status_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_load_status(pool, s, "2024-01-15", None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_dataset_registered
# ---------------------------------------------------------------------------


def test_dataset_registered_normal() -> None:
    """Returns dataset registration rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_DATASET_ROW]):
        result = _handle_dataset_registered(pool, s, "2024-01-15", "2024-01-15", None)

    assert len(result) == 1
    assert result[0]["Ctl_Id"] == 101
    assert result[0]["Count_Source"] == 10000
    assert result[0]["File_Extract_Status"] == "DONE"


def test_dataset_registered_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_dataset_registered(pool, s, "2024-01-15", "2024-01-15", None)

    assert result == []


def test_dataset_registered_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_dataset_registered(pool, s, "2024-01-15", "2024-01-15", None)

    assert "error" in result[0]
