"""Unit tests for teradata_gcfr_mcp.tools.lineage."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool
from teradata_gcfr_mcp.tools.lineage import (
    _handle_data_lineage,
    _handle_health_check,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LINEAGE_ROW: dict[str, Any] = {
    "Src_Object_Name_FQ": "GDEV1T_GCFR.CUSTOMER_STG",
    "Src_Kind": "TABLE",
    "Edge_Relationship": "LOADED_FROM",
    "Tgt_Object_Name_FQ": "GDEV1T_GCFR.CUSTOMER_DIM",
    "Tgt_Kind": "TABLE",
    "Crt_Process_Name": "LOAD_CUSTOMER_DAILY",
}

_MOCK_PATH = "teradata_gcfr_mcp.tools.lineage.execute_query"


def _pool_and_settings() -> tuple[TDConnectionPool, Settings]:
    s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    return TDConnectionPool(s), s


# ---------------------------------------------------------------------------
# gcfr_data_lineage
# ---------------------------------------------------------------------------


def test_data_lineage_normal() -> None:
    """Returns lineage rows for the requested target table."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[_LINEAGE_ROW]):
        result = _handle_data_lineage(pool, s, "CUSTOMER_DIM", "2024-01-15")

    assert len(result) == 1
    assert result[0]["Tgt_Object_Name_FQ"] == "GDEV1T_GCFR.CUSTOMER_DIM"
    assert result[0]["Src_Kind"] == "TABLE"
    assert result[0]["Crt_Process_Name"] == "LOAD_CUSTOMER_DAILY"


def test_data_lineage_empty() -> None:
    """Returns empty list when target table has no registered lineage."""
    pool, s = _pool_and_settings()
    with patch(_MOCK_PATH, return_value=[]):
        result = _handle_data_lineage(pool, s, "UNKNOWN_TABLE", "2024-01-15")

    assert result == []


def test_data_lineage_connection_error() -> None:
    """Passes through error dict without raising."""
    pool, s = _pool_and_settings()
    error = [{"error": "connection failed", "sql": "SELECT ..."}]
    with patch(_MOCK_PATH, return_value=error):
        result = _handle_data_lineage(pool, s, "CUSTOMER_DIM", "2024-01-15")

    assert "error" in result[0]


# ---------------------------------------------------------------------------
# gcfr_health_check
# ---------------------------------------------------------------------------


def test_health_check_ok() -> None:
    """Returns status=ok when both database probes succeed."""
    pool, s = _pool_and_settings()
    side_effects = [
        [{"stream_count": 42}],
        [{"view_count": 100}],
    ]
    with patch(_MOCK_PATH, side_effect=side_effects):
        result = _handle_health_check(pool, s)

    assert len(result) == 1
    assert result[0]["status"] == "ok"
    assert result[0]["stream_count"] == 42
    assert result[0]["reporting_view_accessible"] is True
    assert result[0]["gcfr_view_db"] == s.GCFR_VIEW_DB
    assert result[0]["gcfr_opr_db"] == s.GCFR_OPR_DB
    assert "response_time_ms" in result[0]


def test_health_check_view_db_error() -> None:
    """Returns status=error when the view-db probe fails."""
    pool, s = _pool_and_settings()
    side_effects = [
        [{"error": "connection refused", "sql": "SELECT ..."}],
        [{"view_count": 100}],
    ]
    with patch(_MOCK_PATH, side_effect=side_effects):
        result = _handle_health_check(pool, s)

    assert result[0]["status"] == "error"
    assert result[0]["stream_count"] == 0


def test_health_check_opr_db_error() -> None:
    """Returns status=error when the opr-db probe fails."""
    pool, s = _pool_and_settings()
    side_effects = [
        [{"stream_count": 10}],
        [{"error": "connection refused", "sql": "SELECT ..."}],
    ]
    with patch(_MOCK_PATH, side_effect=side_effects):
        result = _handle_health_check(pool, s)

    assert result[0]["status"] == "error"
    assert result[0]["reporting_view_accessible"] is False
    assert result[0]["stream_count"] == 10
