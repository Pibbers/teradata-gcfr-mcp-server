"""Unit tests for teradata_gcfr_mcp.db."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import teradatasql  # type: ignore[import-untyped]


# ---------------------------------------------------------------------------
# rows_to_json
# ---------------------------------------------------------------------------


def test_rows_to_json_normal() -> None:
    """Cursor with real GCFR column names produces correct list-of-dicts."""
    from teradata_gcfr_mcp.db import rows_to_json

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
    from teradata_gcfr_mcp.db import rows_to_json

    cursor = MagicMock()
    cursor.description = [("Rows_Input",), ("Rows_Inserted",), ("Rows_Rejected",)]
    cursor.fetchall.return_value = []

    result = rows_to_json(cursor)

    assert result == []


# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------


def test_execute_query_returns_error_dict_on_connection_failure(mocker: MagicMock) -> None:
    """When the pool cannot connect, execute_query returns an error dict, not an exception."""
    from teradata_gcfr_mcp.config import Settings
    from teradata_gcfr_mcp.db import TDConnectionPool, execute_query

    settings = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    pool = TDConnectionPool(settings)

    # Simulate a persistent connection failure (both attempts will fail)
    mocker.patch.object(
        pool,
        "_connect",
        side_effect=teradatasql.OperationalError("Connection refused by host"),
    )

    sql = "SELECT TOP 10 * FROM GDEV1V_OPR.GCFR_RV_Stream"
    result = execute_query(pool, sql)

    assert isinstance(result, list)
    assert len(result) == 1
    error_row = result[0]
    assert "error" in error_row
    assert "sql" in error_row
    assert "Connection refused" in str(error_row["error"])


def test_execute_query_injects_top_clause() -> None:
    """max_rows injects TOP N into the SQL when not already present."""
    from teradata_gcfr_mcp.config import Settings
    from teradata_gcfr_mcp.db import TDConnectionPool, execute_query

    settings = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    pool = TDConnectionPool(settings)

    captured: list[str] = []

    # Intercept the execute call to see the rewritten SQL
    def fake_connect() -> None:
        mock_cur = MagicMock()
        mock_cur.description = [("Process_Name",)]
        mock_cur.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        def fake_execute(sql: str, *args: object) -> None:
            captured.append(sql)

        mock_cur.execute.side_effect = fake_execute
        pool._conn = mock_conn

    pool._connect = fake_connect  # type: ignore[method-assign]
    execute_query(pool, "SELECT * FROM GDEV1V_OPR.GCFR_RV_Stream", max_rows=25)

    assert captured, "execute was not called"
    assert "TOP 25" in captured[0]


def test_execute_query_does_not_duplicate_top_clause() -> None:
    """If SQL already contains SELECT TOP, max_rows does not inject a second one."""
    from teradata_gcfr_mcp.config import Settings
    from teradata_gcfr_mcp.db import TDConnectionPool, execute_query

    settings = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    pool = TDConnectionPool(settings)

    captured: list[str] = []

    def fake_connect() -> None:
        mock_cur = MagicMock()
        mock_cur.description = [("Process_Name",)]
        mock_cur.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        def fake_execute(sql: str, *args: object) -> None:
            captured.append(sql)

        mock_cur.execute.side_effect = fake_execute
        pool._conn = mock_conn

    pool._connect = fake_connect  # type: ignore[method-assign]
    execute_query(pool, "SELECT TOP 5 * FROM GDEV1V_OPR.GCFR_RV_Stream", max_rows=500)

    assert captured
    assert captured[0].upper().count("TOP") == 1


# ---------------------------------------------------------------------------
# get_pool singleton
# ---------------------------------------------------------------------------


def test_get_pool_singleton() -> None:
    """get_pool returns the same object on repeated calls."""
    import teradata_gcfr_mcp.db as db_module
    from teradata_gcfr_mcp.config import Settings
    from teradata_gcfr_mcp.db import get_pool

    # Reset singleton so this test is self-contained
    db_module._pool = None

    settings = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
    pool_a = get_pool(settings)
    pool_b = get_pool(settings)

    assert pool_a is pool_b

    # Restore clean state for any subsequent tests
    db_module._pool = None
