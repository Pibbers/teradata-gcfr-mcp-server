"""YAML-driven custom tool loader for teradata-gcfr-mcp-server."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.db import TDConnectionPool, execute_query, get_pool

logger = logging.getLogger(__name__)

# Glob patterns to scan; both .yaml and .yml are accepted.
_YAML_PATTERNS = ("*_tools.yaml", "*_tools.yml")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _substitute_placeholders(sql: str, settings: Settings) -> str:
    """Replace {gcfr_*_db} placeholders with values from settings."""
    return sql.format(
        gcfr_opr_db=settings.GCFR_OPR_DB,
        gcfr_view_db=settings.GCFR_VIEW_DB,
        gcfr_utlfw_db=settings.GCFR_UTLFW_DB,
    )


def _make_tool_fn(pool: TDConnectionPool, sql: str, settings: Settings) -> Any:
    """Return a zero-argument async function that executes *sql*."""

    async def _execute() -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            execute_query, pool, sql, max_rows=settings.GCFR_MAX_ROWS
        )

    return _execute


def _load_file(
    mcp: FastMCP,
    pool: TDConnectionPool,
    settings: Settings,
    yaml_path: Path,
) -> int:
    """Parse one YAML file and register its tools. Returns count registered."""
    with yaml_path.open() as fh:
        raw: Any = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        logger.warning("Skipping %s: top-level structure is not a mapping", yaml_path)
        return 0

    tool_defs: Any = raw.get("tools")
    if not isinstance(tool_defs, list):
        logger.warning("Skipping %s: 'tools' key missing or not a list", yaml_path)
        return 0

    count = 0
    for entry in tool_defs:
        if not isinstance(entry, dict):
            continue
        name: Any = entry.get("name")
        description: Any = entry.get("description", "")
        raw_sql: Any = entry.get("sql")

        if not isinstance(name, str) or not isinstance(raw_sql, str):
            logger.warning("Skipping malformed tool entry in %s: %r", yaml_path, entry)
            continue

        try:
            sql = _substitute_placeholders(raw_sql, settings)
        except KeyError as exc:
            logger.warning(
                "Skipping tool %r in %s: unknown placeholder %s", name, yaml_path, exc
            )
            continue

        fn: Any = _make_tool_fn(pool, sql, settings)
        fn.__name__ = name
        fn.__doc__ = str(description)
        mcp.tool()(fn)
        count += 1

    return count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_custom_tools(mcp: FastMCP, settings: Settings) -> int:
    """Load YAML-defined tools from config_dir. Returns count of tools loaded."""
    config_dir = Path(settings.CONFIG_DIR)
    if not config_dir.is_dir():
        logger.warning(
            "CONFIG_DIR %s does not exist or is not a directory — "
            "skipping custom tool loading",
            config_dir,
        )
        return 0

    pool = get_pool(settings)
    total = 0
    for pattern in _YAML_PATTERNS:
        for yaml_file in sorted(config_dir.glob(pattern)):
            n = _load_file(mcp, pool, settings, yaml_file)
            if n:
                logger.info("Loaded %d custom tool(s) from %s", n, yaml_file)
            total += n

    return total
