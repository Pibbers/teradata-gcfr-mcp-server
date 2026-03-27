"""Unit tests for teradata_gcfr_mcp.db."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import teradatasql  # type: ignore[import-untyped]

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool, execute_query, rows_to_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pool() -> TDConnectionPool:
    return TDConnectionPool(
        Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    )


def _mock_conn(captured: list[str] | None = None) -> MagicMock:
    """Return a mock Teradata connection whose cursor captures executed SQL."""
    mock_cur = MagicMock()
    mock_cur.description = [("Process_Name",)]
    mock_cur.fetchall.return_value = []

    if captured is not None:

        def _capture(sql: str, *args: object) -> None:
            captured.append(sql)

        mock_cur.execute.side_effect = _capture

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn


# ---------------------------------------------------------------------------
# rows_to_json
# ---------------------------------------------------------------------------


def test_rows_to_json_normal() -> None:
    """Cursor with real GCFR column names produces correct list-of-dicts."""
    cursor = MagicMock()
    cursor.description = [
        ("Process_Name",),
        ("Business_Date",),
        ("Stream_Key",),
        ("Load_Status",),
    ]
    cursor.fetchall.return_value = [
        ("LOAD_PROC_01", "2024-01-15", 1, 1),
        ("LOAD_PROC_02", "2024-01-15", 2, 0),
    ]

    result = rows_to_json(cursor)

    assert len(result) == 2
    assert result[0] == {
        "Process_Name": "LOAD_PROC_01",
        "Business_Date": "2024-01-15",
        "Stream_Key": 1,
        "Load_Status": 1,
    }
    assert result[1]["Process_Name"] == "LOAD_PROC_02"
    assert result[1]["Stream_Key"] == 2


def test_rows_to_json_empty() -> None:
    """Empty fetchall returns an empty list without error."""
    cursor = MagicMock()
    cursor.description = [("Rows_Input",), ("Rows_Inserted",), ("Rows_Rejected",)]
    cursor.fetchall.return_value = []

    result = rows_to_json(cursor)

    assert result == []


# ---------------------------------------------------------------------------
# TDConnectionPool — _open sets QueryBand
# ---------------------------------------------------------------------------


def test_open_sets_query_band(mocker: MagicMock) -> None:
    """_open() issues SET QUERY_BAND on every new connection."""
    pool = _pool()
    executed: list[str] = []
    mock_conn = _mock_conn(executed)

    mocker.patch("teradatasql.connect", return_value=mock_conn)

    conn = pool._open()

    assert conn is mock_conn
    assert any("SET QUERY_BAND" in s for s in executed), (
        "QueryBand was not set on new connection"
    )


# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------


def test_execute_query_returns_error_dict_on_connection_failure(
    mocker: MagicMock,
) -> None:
    """When the pool cannot open a connection, execute_query returns an error dict."""
    pool = _pool()

    mocker.patch.object(
        pool,
        "_open",
        side_effect=teradatasql.OperationalError("Connection refused by host"),
    )

    result = execute_query(pool, "SELECT TOP 10 * FROM GDEV1V_OPR.GCFR_RV_Stream")

    assert isinstance(result, list)
    assert len(result) == 1
    assert "error" in result[0]
    assert "sql" in result[0]
    assert "Connection refused" in str(result[0]["error"])


def test_execute_query_injects_top_clause(mocker: MagicMock) -> None:
    """max_rows injects TOP N into the SQL when not already present."""
    pool = _pool()
    captured: list[str] = []
    mocker.patch.object(pool, "_open", return_value=_mock_conn(captured))

    execute_query(pool, "SELECT * FROM GDEV1V_OPR.GCFR_RV_Stream", max_rows=25)

    assert captured, "execute was not called"
    assert any("TOP 25" in s for s in captured)


def test_execute_query_does_not_duplicate_top_clause(mocker: MagicMock) -> None:
    """If SQL already contains SELECT TOP, max_rows does not inject a second one."""
    pool = _pool()
    captured: list[str] = []
    mocker.patch.object(pool, "_open", return_value=_mock_conn(captured))

    execute_query(
        pool, "SELECT TOP 5 * FROM GDEV1V_OPR.GCFR_RV_Stream", max_rows=500
    )

    assert captured
    assert sum(1 for s in captured if "TOP" in s.upper() and "TOP 5" in s) >= 1
    # No second TOP should have been injected
    assert not any(s.upper().count("TOP") > 1 for s in captured)


# ---------------------------------------------------------------------------
# get_pool singleton
# ---------------------------------------------------------------------------


def test_get_pool_singleton() -> None:
    """get_pool returns the same object on repeated calls."""
    import teradata_gcfr_mcp.db as db_module
    from teradata_gcfr_mcp.db import get_pool

    # Reset singleton so this test is self-contained.
    db_module._pool = None

    settings = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    pool_a = get_pool(settings)
    pool_b = get_pool(settings)

    assert pool_a is pool_b

    # Restore clean state for any subsequent tests.
    db_module._pool = None
