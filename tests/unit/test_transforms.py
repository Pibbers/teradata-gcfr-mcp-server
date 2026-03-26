"""Unit tests for teradata_gcfr_mcp.tools.transforms."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.transforms import (
    _handle_data_trend_loads,
    _handle_data_trend_transforms,
    _handle_top_slowest_processes,
    _handle_top_slowest_streams,
    _handle_transform_stats,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TRANSFORM_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Business_Date": "2024-01-15",
    "Rows_Inserted": 5000,
    "Rows_Updated": 200,
    "Rows_Deleted": 10,
}

_SLOWEST_PROCESS_ROW: dict[str, Any] = {
    "Process_Name": "LOAD_CUSTOMER_DAILY",
    "Business_Date": "2024-01-15",
    "Elapsed_Seconds": 3600,
    "Stream_Key": 1,
}

_SLOWEST_STREAM_ROW: dict[str, Any] = {
    "Stream_Key": 1,
    "Stream_Name": "DAILY_LOAD",
    "Business_Date": "2024-01-15",
    "Elapsed_Seconds": 7200,
}

_TREND_LOAD_ROW: dict[str, Any] = {
    "Business_Date": "2024-01-15",
    "Total_Rows_Input": 100000,
    "Total_Rows_Inserted": 99500,
}

_TREND_TRANSFORM_ROW: dict[str, Any] = {
    "Business_Date": "2024-01-15",
    "Total_Rows_Inserted": 50000,
    "Total_Rows_Updated": 1000,
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.transforms.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_transform_stats
# ---------------------------------------------------------------------------


def test_transform_stats_normal() -> None:
    """Returns transform rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_TRANSFORM_ROW]):
        result = _handle_transform_stats(pool, s, "2024-01-15", "2024-01-15", None)

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    assert result[0]["Rows_Inserted"] == 5000
    assert result[0]["Rows_Updated"] == 200
    assert result[0]["Rows_Deleted"] == 10


def test_transform_stats_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_transform_stats(pool, s, "2024-01-15", "2024-01-15", None)

    assert result == []


def test_transform_stats_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_transform_stats(pool, s, "2024-01-15", "2024-01-15", None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_top_slowest_processes
# ---------------------------------------------------------------------------


def test_top_slowest_processes_normal() -> None:
    """Returns slowest process rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_SLOWEST_PROCESS_ROW]):
        result = _handle_top_slowest_processes(pool, s, "2024-01-15", 10)

    assert len(result) == 1
    assert result[0]["Process_Name"] == "LOAD_CUSTOMER_DAILY"
    assert result[0]["Elapsed_Seconds"] == 3600


def test_top_slowest_processes_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_top_slowest_processes(pool, s, "2024-01-15", 10)

    assert result == []


def test_top_slowest_processes_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_top_slowest_processes(pool, s, "2024-01-15", 10)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_top_slowest_streams
# ---------------------------------------------------------------------------


def test_top_slowest_streams_normal() -> None:
    """Returns slowest stream rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_SLOWEST_STREAM_ROW]):
        result = _handle_top_slowest_streams(pool, s, "2024-01-15", 5)

    assert len(result) == 1
    assert result[0]["Stream_Key"] == 1
    assert result[0]["Elapsed_Seconds"] == 7200


def test_top_slowest_streams_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_top_slowest_streams(pool, s, "2024-01-15", 5)

    assert result == []


def test_top_slowest_streams_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_top_slowest_streams(pool, s, "2024-01-15", 5)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_data_trend_loads
# ---------------------------------------------------------------------------


def test_data_trend_loads_normal() -> None:
    """Returns daily load trend rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_TREND_LOAD_ROW]):
        result = _handle_data_trend_loads(pool, s, "2024-01-15", "2024-01-15")

    assert len(result) == 1
    assert result[0]["Business_Date"] == "2024-01-15"
    assert result[0]["Total_Rows_Input"] == 100000


def test_data_trend_loads_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_data_trend_loads(pool, s, "2024-01-15", "2024-01-15")

    assert result == []


def test_data_trend_loads_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_data_trend_loads(pool, s, "2024-01-15", "2024-01-15")

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_data_trend_transforms
# ---------------------------------------------------------------------------


def test_data_trend_transforms_normal() -> None:
    """Returns daily transform trend rows when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_TREND_TRANSFORM_ROW]):
        result = _handle_data_trend_transforms(pool, s, "2024-01-15", "2024-01-15")

    assert len(result) == 1
    assert result[0]["Business_Date"] == "2024-01-15"
    assert result[0]["Total_Rows_Inserted"] == 50000


def test_data_trend_transforms_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_data_trend_transforms(pool, s, "2024-01-15", "2024-01-15")

    assert result == []


def test_data_trend_transforms_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_data_trend_transforms(pool, s, "2024-01-15", "2024-01-15")

    assert "error" in result[0]
