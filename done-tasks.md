# done-tasks.md — teradata-gcfr-mcp-server

Completed work log. Most-recent entries first.

---

## 2026-03-26 — Phase 4: SLA, lineage, health check, custom tool loader, profile filtering

**Files created / modified:**
- `src/teradata_gcfr_mcp/tools/sla.py` — NEW
- `src/teradata_gcfr_mcp/tools/lineage.py` — NEW
- `src/teradata_gcfr_mcp/tool_loader.py` — implemented (was stub)
- `src/teradata_gcfr_mcp/server.py` — updated (sla + lineage registration, profile filter, argparse, load_custom_tools)
- `src/teradata_gcfr_mcp/config.py` — `MCP_TRANSPORT` narrowed to `Literal` type
- `tests/unit/test_sla.py` — NEW (6 tests)
- `tests/unit/test_lineage.py` — NEW (6 tests)
- `tests/unit/test_tool_loader.py` — NEW (5 tests: 2 functional + 3 parametrised)
- `CLAUDE.md` — NEW (project reference document)
- `agents.md` — NEW (agent guidance document)

**Tasks:**
- Implemented `sla.py`: `gcfr_sla_process_report` and `gcfr_sla_stream_report`, both querying `GCFR_RV_SLA*` views with date range filtering. Added `_coerce_intervals()` to convert `timedelta` (INTERVAL DAY TO SECOND) values to `str` for JSON safety.
- Implemented `lineage.py`: `gcfr_data_lineage` querying `GCFR_Object_Lineage` (explicit 6-column SELECT, `UPPER()` filter on target table name); `gcfr_health_check` probing both `GCFR_VIEW_DB` and `GCFR_OPR_DB` and returning a structured status dict with `stream_count`, `reporting_view_accessible`, and `response_time_ms`.
- Implemented `tool_loader.py`: scans `CONFIG_DIR` for `*_tools.yaml` / `*_tools.yml`, substitutes `{gcfr_opr_db}` / `{gcfr_view_db}` / `{gcfr_utlfw_db}` placeholders, dynamically registers zero-argument async tools via `mcp.tool()(fn)`. Exposed `_substitute_placeholders()` as a testable pure function.
- Updated `server.py`: registered sla and lineage modules; added `load_custom_tools()` call; added `--profile` argparse argument (via `parse_known_args`); added `_load_profile_patterns()` reading `profiles.yml` from the package config directory; added `_apply_profile_filter()` pruning non-matching tools from `mcp._tool_manager._tools` post-registration using `fnmatch`.
- Fixed `MCP_TRANSPORT` type in `config.py` from `str` to `Literal["stdio", "sse", "streamable-http"]` to satisfy mypy's `mcp.run(transport=...)` argument check (latent error surfaced by full-src mypy scan).

**Issue fixed:** `mypy src/` revealed that `mcp.run(transport=settings.MCP_TRANSPORT)` failed because `MCP_TRANSPORT` was typed as `str` but the method expects a `Literal`. Fixed in `config.py`.

**Verification gate result:** `ruff check src/` ✓ · `mypy src/` ✓ · `pytest tests/unit/ -v` 74/74 ✓

---

## 2026-03-26 — Phase 3b: loads, transforms, errors tools (11 tools, 27 tests)

**Files created / modified:**
- `src/teradata_gcfr_mcp/tools/loads.py` — implemented (was stub)
- `src/teradata_gcfr_mcp/tools/transforms.py` — implemented (was stub)
- `src/teradata_gcfr_mcp/tools/errors.py` — implemented (was stub)
- `src/teradata_gcfr_mcp/server.py` — updated (loads, transforms, errors registration)
- `tests/unit/test_loads.py` — NEW (9 tests)
- `tests/unit/test_transforms.py` — NEW (15 tests, 5 handlers × 3)
- `tests/unit/test_errors.py` — NEW (9 tests)

**Tasks:**
- Implemented `loads.py`: `gcfr_load_stats` (explicit column SELECT from `GCFR_RV_Load`), `gcfr_load_status` (`GCFR_RV_Load_Status` by business date), `gcfr_dataset_registered` (`GCFR_RV_DataSetReg`). All support optional `ctl_id` filter.
- Implemented `transforms.py`: `gcfr_transform_stats`, `gcfr_top_slowest_processes`, `gcfr_top_slowest_streams` (top_n validated 1–50, TOP baked into SQL to avoid double-injection), `gcfr_data_trend_loads` (`GCFR_RV_LoadSumByBusDate`), `gcfr_data_trend_transforms` (`GCFR_RV_TfmSumByBusDate`).
- Implemented `errors.py`: `gcfr_failed_processes` (`GCFR_RV_FailedProcessDetail`), `gcfr_error_log` (`GCFR_VIEW_DB.GCFR_Error_Log`, explicit column list excluding `Sql_Text` CLOB), `gcfr_execution_log` (`GCFR_RV_ExecutionLog`, excludes `Sql_Text`).

**Issue fixed:** Ruff E501 on a long docstring first line in `loads.py` — shortened the summary line to stay under 100 characters.

**Verification gate result:** `ruff check` ✓ · `mypy` ✓ · `pytest` 33/33 ✓

---

## 2026-03-26 — Phase 3a: streams and processes tools (6 tools, 18 tests)

**Files created / modified:**
- `src/teradata_gcfr_mcp/tools/streams.py` — implemented
- `src/teradata_gcfr_mcp/tools/processes.py` — implemented
- `src/teradata_gcfr_mcp/server.py` — updated (streams + processes registration)
- `tests/unit/test_streams.py` — NEW (9 tests)
- `tests/unit/test_processes.py` — NEW (9 tests)

**Tasks:**
- Established the `_handle_*` + `register()` pattern used by all subsequent tool modules.
- `streams.py`: `gcfr_stream_status`, `gcfr_current_stream_status`, `gcfr_stream_business_date` (using `GCFR_VIEW_DB.GCFR_Stream_BusDate`).
- `processes.py`: `gcfr_current_process_status`, `gcfr_process_history`, `gcfr_process_status_summary`.
- Introduced `_parse_stream_key()` helper (string → int, returns error dict on failure) used across streams and processes.

**Verification gate result:** `ruff check` ✓ · `mypy` ✓ · `pytest` 18/18 ✓

---

## 2026-03-26 — Phase 2: db.py implementation (6 tests)

**Files created / modified:**
- `src/teradata_gcfr_mcp/db.py` — implemented
- `tests/unit/test_db.py` — NEW (6 tests)

**Tasks:**
- `TDConnectionPool`: lazy connect on first `get_connection()`, `invalidate()`, `close()`.
- `rows_to_json()`: cursor → list of dicts using `cursor.description` for column names.
- `execute_query()`: TOP injection via regex, reconnect-once pattern, never-raises contract, returns `[{"error": "...", "sql": "..."}]` on failure.
- `get_pool()`: module-level singleton.

**Issues fixed:**
- mypy `unused-ignore` error: `teradatasql` ships partial stubs so `# type: ignore[import-untyped]` on the import line was redundant and mypy flagged it. Removed the comment from the import; added `# type: ignore[no-untyped-call]` on the `teradatasql.connect()` call only.

**Verification gate result:** `ruff check` ✓ · `mypy` ✓ · `pytest` 6/6 ✓

---

## 2026-03-26 — Phase 1: project scaffold

**Files created:**
- `pyproject.toml` — hatchling build, uv toolchain, ruff + mypy + pytest config
- `src/teradata_gcfr_mcp/__init__.py`
- `src/teradata_gcfr_mcp/config.py` — `Settings` (pydantic-settings), four GCFR DB constants, `MCP_TRANSPORT`, `PROFILE`, `CONFIG_DIR`
- `src/teradata_gcfr_mcp/db.py` — stub
- `src/teradata_gcfr_mcp/server.py` — stub
- `src/teradata_gcfr_mcp/tool_loader.py` — stub
- `src/teradata_gcfr_mcp/tools/__init__.py`
- `src/teradata_gcfr_mcp/tools/{streams,processes,loads,transforms,errors,sla,lineage}.py` — stubs
- `src/teradata_gcfr_mcp/config/profiles.yml` — four profiles: all, ops, performance, lineage
- `src/teradata_gcfr_mcp/config/gcfr_tools.yml` — example custom tools file
- `.env.example`
- `.gitignore`
- `README.md` — placeholder (required by hatchling)
- `tests/unit/conftest.py` — stub

**Issue fixed:** `uv sync` failed with `OSError: Readme file does not exist: README.md` because hatchling requires the file declared as `readme =` to exist on disk. Created a minimal placeholder.
