"""Unit tests for teradata_gcfr_mcp.tool_loader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from teradata_gcfr_mcp.config import Settings
from teradata_gcfr_mcp.server import _apply_profile_filter
from teradata_gcfr_mcp.tool_loader import _substitute_placeholders, load_custom_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YAML_CONTENT = """\
tools:
  - name: gcfr_site_report
    description: "Site-specific stream report"
    sql: "SELECT * FROM {gcfr_opr_db}.GCFR_RV_Stream ORDER BY Business_Date DESC"
"""


def _settings(**overrides: str) -> Settings:
    base = {"DATABASE_URI": "teradata://user:pass@localhost:1025/db"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# test_load_valid_yaml_registers_tools
# ---------------------------------------------------------------------------


def test_load_valid_yaml_registers_tools(tmp_path: Path) -> None:
    """A valid *_tools.yaml file registers exactly one tool and returns count=1."""
    (tmp_path / "site_tools.yaml").write_text(_YAML_CONTENT)

    mcp_instance = FastMCP("test")
    s = _settings(CONFIG_DIR=str(tmp_path))

    with patch("teradata_gcfr_mcp.tool_loader.get_pool") as mock_gp:
        mock_gp.return_value = MagicMock()
        count = load_custom_tools(mcp_instance, s)

    assert count == 1


# ---------------------------------------------------------------------------
# test_missing_config_dir_returns_zero
# ---------------------------------------------------------------------------


def test_missing_config_dir_returns_zero() -> None:
    """Returns 0 without raising when CONFIG_DIR does not exist."""
    mcp_instance = FastMCP("test")
    s = _settings(CONFIG_DIR="/nonexistent/__gcfr_test__")

    count = load_custom_tools(mcp_instance, s)

    assert count == 0


# ---------------------------------------------------------------------------
# test_placeholder_substitution
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# test_yaml_tools_subject_to_profile_filter
# ---------------------------------------------------------------------------


def test_yaml_tools_subject_to_profile_filter(tmp_path: Path) -> None:
    """YAML-loaded tools are removed by _apply_profile_filter when they do not
    match the active profile's patterns.  This verifies that the load-then-filter
    ordering in server.main() correctly covers custom tools."""
    yaml_content = """\
tools:
  - name: gcfr_site_report
    description: "Site-specific report"
    sql: "SELECT * FROM {gcfr_opr_db}.GCFR_RV_Stream"
"""
    (tmp_path / "site_tools.yaml").write_text(yaml_content)

    mcp_instance = FastMCP("test")
    s = _settings(CONFIG_DIR=str(tmp_path))

    with patch("teradata_gcfr_mcp.tool_loader.get_pool") as mock_gp:
        mock_gp.return_value = MagicMock()
        load_custom_tools(mcp_instance, s)

    # Confirm the tool is registered before filtering.
    mgr = getattr(mcp_instance, "_tool_manager", None)
    assert mgr is not None
    tools_before = set(getattr(mgr, "_tools", {}).keys())
    assert "gcfr_site_report" in tools_before

    # Apply a profile that does NOT match gcfr_site_report.
    _apply_profile_filter(mcp_instance, ["gcfr_stream_*", "gcfr_health_check"])

    tools_after = set(getattr(mgr, "_tools", {}).keys())
    assert "gcfr_site_report" not in tools_after, (
        "YAML tool was not removed by profile filter"
    )


@pytest.mark.parametrize(
    ("template", "expected_substr", "absent_substr"),
    [
        (
            "SELECT * FROM {gcfr_opr_db}.SOME_VIEW",
            "GDEV1V_OPR",
            "{gcfr_opr_db}",
        ),
        (
            "SELECT * FROM {gcfr_view_db}.SOME_VIEW",
            "GDEV1V_GCFR",
            "{gcfr_view_db}",
        ),
        (
            "SELECT * FROM {gcfr_utlfw_db}.SOME_VIEW",
            "GDEV1V_UTLFW",
            "{gcfr_utlfw_db}",
        ),
    ],
)
def test_placeholder_substitution(
    template: str,
    expected_substr: str,
    absent_substr: str,
) -> None:
    """All three supported placeholders are expanded to their settings values."""
    s = _settings()
    result = _substitute_placeholders(template, s)
    assert expected_substr in result
    assert absent_substr not in result
