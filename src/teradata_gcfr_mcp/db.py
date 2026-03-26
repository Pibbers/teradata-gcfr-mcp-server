"""Teradata connection pool and query execution utilities."""

from __future__ import annotations

import logging
import re
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

import teradatasql

from teradata_gcfr_mcp.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def rows_to_json(cursor: Any) -> list[dict[str, Any]]:
    """Convert cursor results to a list of column-name → value dicts.

    Uses ``cursor.description`` for column names so callers never need to
    handle raw tuples.
    """
    cols = [str(col[0]) for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Connection pool
# ---------------------------------------------------------------------------


class TDConnectionPool:
    """Manages a single persistent Teradata connection with lazy init.

    The connection is not opened until the first :meth:`get_connection` call.
    On detected staleness the caller can :meth:`invalidate` the connection so
    the next ``get_connection`` transparently reconnects.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._conn: Any = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """(Re)open a connection using ``DATABASE_URI`` from settings."""
        parsed = urlparse(self._settings.DATABASE_URI)
        host: str = parsed.hostname or ""
        user: str = parsed.username or ""
        password: str = parsed.password or ""

        self._conn = teradatasql.connect(  # type: ignore[no-untyped-call]
            host=host,
            user=user,
            password=password,
            logmech=self._settings.LOGMECH,
        )
        logger.debug("Teradata connection established  host=%s user=%s", host, user)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """Yield a live Teradata connection, connecting lazily on first use."""
        if self._conn is None:
            self._connect()
        yield self._conn

    def invalidate(self) -> None:
        """Discard the cached connection without closing it.

        Use this when the connection is already known to be dead so the next
        :meth:`get_connection` call will transparently reconnect.
        """
        self._conn = None

    def close(self) -> None:
        """Close the underlying connection if one is open."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._conn = None


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------


def execute_query(
    pool: TDConnectionPool,
    sql: str,
    params: list[Any] | None = None,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Execute a parameterised SELECT and return rows as a list of dicts.

    Behaviour contract
    ------------------
    * **TOP injection** – when *max_rows* is given and the SQL does not already
      contain ``SELECT TOP``, a ``TOP N`` clause is injected immediately after
      the first ``SELECT`` keyword.  The integer is embedded directly (not as a
      bind parameter) because Teradata does not allow parametrised TOP values.
    * **Reconnect once** – on the first failure the connection is invalidated
      and the query is retried once.  This transparently handles stale/dropped
      connections without surfacing transient errors to callers.
    * **Never raises** – any remaining exception after the retry is caught and
      returned as ``[{"error": "...", "sql": "..."}]`` so the MCP tool can
      surface a helpful message to Claude instead of crashing the server.

    Security note
    -------------
    User-supplied *values* must always be passed via *params* (``?``
    placeholders).  Schema and table names come from ``config.py`` constants,
    never from user input, so f-string interpolation of those is safe.
    """
    # Inject TOP clause when a row limit is requested
    if max_rows is not None and not re.search(r"(?i)\bSELECT\s+TOP\b", sql):
        sql = re.sub(r"(?i)\bSELECT\b", f"SELECT TOP {max_rows}", sql, count=1)

    logger.debug("execute_query sql=%s", sql)

    last_exc: Exception | None = None

    for attempt in range(2):
        try:
            with pool.get_connection() as conn:
                cur = conn.cursor()
                try:
                    if params is not None:
                        cur.execute(sql, params)
                    else:
                        cur.execute(sql)
                    return rows_to_json(cur)
                finally:
                    cur.close()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0:
                logger.warning(
                    "Query attempt 1 failed (%s); invalidating connection and retrying.",
                    type(exc).__name__,
                )
                pool.invalidate()
            # Second failure falls through to the error return below

    error_msg = str(last_exc) if last_exc is not None else "Unknown error"
    return [{"error": error_msg, "sql": sql}]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_pool: TDConnectionPool | None = None


def get_pool(settings: Settings) -> TDConnectionPool:
    """Return (or create) the module-level singleton :class:`TDConnectionPool`."""
    global _pool
    if _pool is None:
        _pool = TDConnectionPool(settings)
    return _pool
