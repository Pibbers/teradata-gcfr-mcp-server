"""Unit tests for teradata_gcfr_mcp.tools.streams."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.streams import (
    _handle_current_stream_status,
    _handle_stream_business_date,
    _handle_stream_status,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_STREAM_ROW: dict[str, Any] = {
    "Stream_Key": 1,
    "Stream_Id": 100,
    "Business_Date": "2024-01-15",
    "Processing_Flag": 0,
    "Business_Date_Cycle_Num": 1,
    "Stream_Name": "DAILY_LOAD",
}

_BUSDATE_ROW: dict[str, Any] = {
    "Stream_Key": 1,
    "Cycle_Freq_Code": 1,
    "Business_Date": "2024-01-15",
    "Next_Business_Date": "2024-01-16",
    "Prev_Business_Date": "2024-01-14",
    "Processing_Flag": 0,
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.streams.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_stream_status
# ---------------------------------------------------------------------------


def test_stream_status_normal() -> None:
    """Returns rows correctly when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_STREAM_ROW]) as mock_eq:
        result = _handle_stream_status(pool, s, None, "2024-01-15", "2024-01-15")

    assert len(result) == 1
    assert result[0]["Stream_Key"] == 1
    assert result[0]["Business_Date"] == "2024-01-15"
    # Verify a date-range query was built (params have both dates)
    call_params = mock_eq.call_args[0][2]
    assert call_params[0] == "2024-01-15"
    assert call_params[1] == "2024-01-15"


def test_stream_status_empty() -> None:
    """Returns empty list when no rows match."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_stream_status(pool, s, None, "2024-01-15", "2024-01-15")

    assert result == []


def test_stream_status_connection_error() -> None:
    """Passes through error dict from execute_query without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_stream_status(pool, s, None, "2024-01-15", "2024-01-15")

    assert "error" in result[0]
    assert result[0]["error"] == "connection failed"


# ---------------------------------------------------------------------------
# gcfr_current_stream_status
# ---------------------------------------------------------------------------


def test_current_stream_status_normal() -> None:
    """Returns active streams when execute_query succeeds."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_STREAM_ROW]):
        result = _handle_current_stream_status(pool, s, None)

    assert len(result) == 1
    assert result[0]["Stream_Key"] == 1


def test_current_stream_status_empty() -> None:
    """Returns empty list when no streams are active."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_current_stream_status(pool, s, None)

    assert result == []


def test_current_stream_status_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_current_stream_status(pool, s, None)

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_stream_business_date
# ---------------------------------------------------------------------------


def test_stream_business_date_normal() -> None:
    """Returns business date row for the requested stream."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_BUSDATE_ROW]):
        result = _handle_stream_business_date(pool, s, "1")

    assert len(result) == 1
    assert result[0]["Business_Date"] == "2024-01-15"
    assert result[0]["Next_Business_Date"] == "2024-01-16"
    assert result[0]["Prev_Business_Date"] == "2024-01-14"


def test_stream_business_date_empty() -> None:
    """Returns empty list when stream_key is not found."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_stream_business_date(pool, s, "99")

    assert result == []


def test_stream_business_date_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_stream_business_date(pool, s, "1")

    assert "error" in result[0]
