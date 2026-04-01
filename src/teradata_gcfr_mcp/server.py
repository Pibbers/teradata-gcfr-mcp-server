"""MCP server entry point for teradata-gcfr-mcp-server."""

from __future__ import annotations

import argparse
import fnmatch
import logging
import logging.handlers
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

from teradata_gcfr_mcp.config import settings
from teradata_gcfr_mcp.db import get_pool
from teradata_gcfr_mcp.tool_loader import load_custom_tools
from teradata_gcfr_mcp.tools import (
    errors,
    lineage,
    loads,
    processes,
    sla,
    streams,
    transforms,
)

logger = logging.getLogger(__name__)

mcp: FastMCP = FastMCP("teradata-gcfr-mcp-server")

# Profiles file shipped alongside this module.
_PROFILES_PATH = Path(__file__).parent / "config" / "profiles.yml"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

_LOG_FMT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_LOG_FILE = "teradata-gcfr-mcp.log"
_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB
_LOG_BACKUP_COUNT = 3


def _configure_logging(level_str: str, transport: str) -> None:
    """Set up logging with transport-aware handlers.

    * **stdio** – logs go to a rotating file only.  stdout is the MCP wire
      protocol; writing to stderr inside a stdio session creates noise for the
      MCP client.
    * **sse / streamable-http** – logs go to both stderr (visible to the
      operator) and the same rotating file.
    """
    level = getattr(logging, level_str.upper(), logging.WARNING)
    fmt = logging.Formatter(_LOG_FMT)
    root = logging.getLogger()
    root.setLevel(level)

    if transport != "stdio":
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def _load_profile_patterns(profile_name: str) -> list[str]:
    """Return the fnmatch patterns for *profile_name* from profiles.yml."""
    try:
        with _PROFILES_PATH.open() as fh:
            raw: Any = yaml.safe_load(fh)
    except OSError:
        logger.warning("Could not read profiles file %s", _PROFILES_PATH)
        return ["gcfr_*"]

    if not isinstance(raw, dict):
        return ["gcfr_*"]

    profile_data: Any = raw.get(profile_name)
    if not isinstance(profile_data, dict):
        logger.warning("Unknown profile %r — registering all tools", profile_name)
        return ["gcfr_*"]

    patterns: Any = profile_data.get("tool", ["gcfr_*"])
    return list(patterns) if isinstance(patterns, list) else ["gcfr_*"]


def _apply_profile_filter(mcp_server: FastMCP, patterns: list[str]) -> None:
    """Remove tools from *mcp_server* whose names do not match any pattern."""
    mgr: Any = getattr(mcp_server, "_tool_manager", None)
    if mgr is None:
        logger.debug("_tool_manager not found; skipping profile filter")
        return
    tools_dict: dict[str, Any] = getattr(mgr, "_tools", {})
    to_remove = [
        name
        for name in list(tools_dict.keys())
        if not any(fnmatch.fnmatch(name, pat) for pat in patterns)
    ]
    for name in to_remove:
        del tools_dict[name]
    if to_remove:
        logger.info("Profile filter removed %d tool(s): %s", len(to_remove), to_remove)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Initialise the connection pool, register all tools, and start the server."""
    # Allow --profile to override settings.PROFILE without conflicting with
    # any args FastMCP itself may parse.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--profile", default=None)
    args, _ = parser.parse_known_args()

    active_profile = args.profile or settings.PROFILE

    _configure_logging(settings.LOGGING_LEVEL, settings.MCP_TRANSPORT)

    pool = get_pool(settings)

    # Register every tool module unconditionally; profile filter prunes below.
    streams.register(mcp, pool, settings)
    processes.register(mcp, pool, settings)
    loads.register(mcp, pool, settings)
    transforms.register(mcp, pool, settings)
    errors.register(mcp, pool, settings)
    sla.register(mcp, pool, settings)
    lineage.register(mcp, pool, settings)

    # Load site-specific YAML tools.
    n_custom = load_custom_tools(mcp, settings)
    if n_custom:
        logger.info("Custom tools loaded: %d", n_custom)

    # Apply profile filter (no-op for "all").
    if active_profile != "all":
        patterns = _load_profile_patterns(active_profile)
        _apply_profile_filter(mcp, patterns)

    mcp.run(
        transport=settings.MCP_TRANSPORT,
        mount_path=settings.MCP_PATH,
    )


if __name__ == "__main__":
    main()
