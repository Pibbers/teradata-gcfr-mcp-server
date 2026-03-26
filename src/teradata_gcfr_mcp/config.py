"""Configuration for the Teradata GCFR MCP server.

All settings can be overridden via environment variables or a .env file.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Teradata connection                                                   #
    # ------------------------------------------------------------------ #
    DATABASE_URI: str = ""
    """teradata://username:password@host:1025/database"""

    LOGMECH: str = "TD2"
    """Authentication mechanism (TD2, LDAP, TDNEGO, …)."""

    TD_POOL_SIZE: int = 5
    """Number of persistent connections in the pool."""

    TD_MAX_OVERFLOW: int = 10
    """Extra connections allowed beyond pool_size under burst load."""

    TD_POOL_TIMEOUT: int = 30
    """Seconds to wait for a free connection before raising."""

    # ------------------------------------------------------------------ #
    # GCFR database names                                                  #
    # Four separate databases — do NOT collapse into a single GCFR_DATABASE #
    # ------------------------------------------------------------------ #
    GCFR_VIEW_DB: str = "GDEV1V_GCFR"
    """Base view layer — mirrors of all GDEV1T_GCFR registration tables."""

    GCFR_OPR_DB: str = "GDEV1V_OPR"
    """Operational reporting views (GCFR_RV_*) — primary source for most tools."""

    GCFR_UTLFW_DB: str = "GDEV1V_UTLFW"
    """BKEY surrogate-key and BMAP reference-data views."""

    GCFR_TABLE_DB: str = "GDEV1T_GCFR"
    """Physical table database — used ONLY by the health-check tool."""

    # ------------------------------------------------------------------ #
    # Query behaviour                                                       #
    # ------------------------------------------------------------------ #
    GCFR_MAX_ROWS: int = 500
    """Maximum rows any single tool may return."""

    GCFR_QUERY_TIMEOUT: int = 120
    """Per-query timeout in seconds."""

    # ------------------------------------------------------------------ #
    # MCP transport                                                         #
    # ------------------------------------------------------------------ #
    MCP_TRANSPORT: Literal["stdio", "sse", "streamable-http"] = "stdio"
    """stdio | streamable-http | sse"""

    MCP_HOST: str = "127.0.0.1"
    """Bind host for HTTP/SSE transports."""

    MCP_PORT: int = 8001
    """Bind port for HTTP/SSE transports."""

    MCP_PATH: str = "/mcp/"
    """URL path prefix for streamable-http transport."""

    # ------------------------------------------------------------------ #
    # Profiles and logging                                                  #
    # ------------------------------------------------------------------ #
    PROFILE: str = "all"
    """Active tool profile (all | ops | performance | lineage)."""

    LOGGING_LEVEL: str = "WARNING"
    """Python logging level."""

    CONFIG_DIR: str = "."
    """Directory scanned for *_tools.yaml custom tool definitions."""


# Single shared instance imported by the rest of the application.
settings = Settings()
