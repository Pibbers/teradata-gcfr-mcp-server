"""Teradata connection pool and query execution utilities."""

from __future__ import annotations

import logging
import queue
import re
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

import teradatasql

from teradata_gcfr_mcp.config import Settings

logger = logging.getLogger(__name__)

# QueryBand set on every new connection for Teradata workload-management attribution.
_QUERY_BAND = "ApplicationName=teradata-gcfr-mcp;UtilityName=MCP;"


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
    """Thread-safe Teradata connection pool.

    Maintains up to ``TD_POOL_SIZE`` idle connections.  Under burst load up to
    ``TD_POOL_SIZE + TD_MAX_OVERFLOW`` connections may exist simultaneously.
    If all connections are busy the caller blocks for up to ``TD_POOL_TIMEOUT``
    seconds before a :exc:`TimeoutError` is raised.

    Connections are opened lazily on first use.  Every new connection has
    ``QUERY_BAND`` set for Teradata workload-management attribution.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._idle: queue.Queue[Any] = queue.Queue()
        self._total = 0
        self._max_size = settings.TD_POOL_SIZE + settings.TD_MAX_OVERFLOW
        self._lock = threading.Lock()
        self._timeout = float(settings.TD_POOL_TIMEOUT)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open(self) -> Any:
        """Open and return a new Teradata connection with QueryBand set."""
        parsed = urlparse(self._settings.DATABASE_URI)
        conn = teradatasql.connect(  # type: ignore[no-untyped-call]
            host=parsed.hostname or "",
            user=parsed.username or "",
            password=parsed.password or "",
            logmech=self._settings.LOGMECH,
            timeout=self._settings.GCFR_QUERY_TIMEOUT,
        )
        cur = conn.cursor()  # type: ignore[no-untyped-call]
        try:
            cur.execute(f"SET QUERY_BAND = '{_QUERY_BAND}' FOR SESSION")
        finally:
            cur.close()
        logger.debug(
            "Teradata connection opened  host=%s user=%s",
            parsed.hostname,
            parsed.username,
        )
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """Yield a live Teradata connection from the pool.

        The connection is returned to the idle pool when the ``with`` block
        exits normally.  On exception the connection is discarded so a
        potentially broken connection is never reused.
        """
        conn: Any = None

        # 1. Try to grab an idle connection without blocking.
        try:
            conn = self._idle.get_nowait()
        except queue.Empty:
            pass

        # 2. No idle connection — create one if under the size limit.
        if conn is None:
            with self._lock:
                if self._total < self._max_size:
                    self._total += 1
                    should_create = True
                else:
                    should_create = False

            if should_create:
                try:
                    conn = self._open()
                except Exception:
                    with self._lock:
                        self._total -= 1
                    raise
            else:
                # 3. Pool saturated — wait for a connection to be returned.
                try:
                    conn = self._idle.get(timeout=self._timeout)
                except queue.Empty:
                    raise TimeoutError(
                        f"No Teradata connection available after {self._timeout:.0f}s"
                    ) from None

        healthy = False
        try:
            yield conn
            healthy = True
        finally:
            if healthy:
                # Return to idle pool; discard overflow connections after use.
                try:
                    self._idle.put_nowait(conn)
                except queue.Full:
                    with self._lock:
                        self._total -= 1
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
            else:
                # Connection may be broken — discard it.
                with self._lock:
                    self._total -= 1
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    def invalidate(self) -> None:
        """Drain all idle connections.

        Call this when a query fails to clear potentially stale connections
        so the next acquisition opens fresh ones.
        """
        while True:
            try:
                conn = self._idle.get_nowait()
                with self._lock:
                    self._total -= 1
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
            except queue.Empty:
                break

    def close(self) -> None:
        """Drain and close all idle connections."""
        self.invalidate()


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
    * **Reconnect once** – on the first failure the connection is discarded and
      ``invalidate()`` drains stale idle connections, then the query is retried
      once with a fresh connection.
    * **Never raises** – any remaining exception after the retry is caught and
      returned as ``[{"error": "...", "sql": "..."}]`` so the MCP tool can
      surface a helpful message to Claude instead of crashing the server.

    Security note
    -------------
    User-supplied *values* must always be passed via *params* (``?``
    placeholders).  Schema and table names come from ``config.py`` constants,
    never from user input, so f-string interpolation of those is safe.
    """
    # Inject TOP clause when a row limit is requested.
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
                    "Query attempt 1 failed (%s); invalidating pool and retrying.",
                    type(exc).__name__,
                )
                pool.invalidate()

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
