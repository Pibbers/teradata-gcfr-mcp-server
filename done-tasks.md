# done-tasks.md — teradata-gcfr-mcp-server

Completed work log. Most-recent entries first.

---

## 2026-04-02 — Validation, bug fixes, and comprehensive documentation

**Time:** 2026-04-02 (afternoon)

**Major accomplishments:**

1. **Upstream validation** — Analyzed the official `Teradata/teradata-mcp-server` repository (91 KB source, 13 subdirectories, ~30 examples) to identify architectural best practices and lessons learned. Results documented in README "Design validation" section.

2. **Bug fixes:**
   - Fixed query timeout wiring: `GCFR_QUERY_TIMEOUT` now passed to `teradatasql.connect(timeout=...)` in `db.py:_open()`
   - Fixed HTTP mount path: `MCP_PATH` now passed to `mcp.run(mount_path=...)` in `server.py:main()`
   - Created functional tests verifying both fixes work end-to-end

3. **README expansion** — Added ~200 lines of documentation:
   - New "How it works" section (architecture breakdown, 4-layer design, query execution model, transport modes)
   - New "Recent improvements" section highlighting today's fixes
   - New "Available MCP tools" section (22 tools organized by 7 categories)
   - New "Architecture and design patterns" section referencing CLAUDE.md
   - New upstream "Design validation" section with comparison table
   - Expanded troubleshooting guide (6 → 10+ issues with specific fixes)
   - Fixed "Quick start" command (uvx → local clone)
   - Clarified `MCP_HOST`/`MCP_PORT` as read-only (FastMCP limitation)

4. **Documentation updates:**
   - `CLAUDE.md` — Added FastMCP API reference, tool inventory (22 tools), outstanding gaps (pre-ping, request correlation, table DB placeholder)
   - `agents.md` — Added 4 new issues encountered: query timeout, mount path, FastMCP API introspection, dev dependency installation; documented 3 outstanding gaps from upstream validation
   - `done-tasks.md` — This entry

**Issues encountered and resolved:**

| # | Issue | Resolution | Lesson |
|---|---|---|---|
| 1 | FastMCP.run() doesn't accept host/port | Checked actual signature: only transport + mount_path allowed | Always introspect APIs when unsure |
| 2 | Dev tools (ruff, mypy, pytest) not found | Ran `uv pip install -e ".[dev]"` to install optional deps | Consider if dev tools should be mandatory or optional |
| 3 | uv command not in PATH | Used full path `/home/paul/.local/bin/uv` | Shell PATH setup issue |
| 4 | Query timeout config never used | Added timeout param to teradatasql.connect() | Always verify config → code wiring |
| 5 | Mount path setting ignored | Added mount_path param to mcp.run() | Always verify all settings are used |

**Verification gate:**

```
✓ ruff check src/         — All checks passed!
✓ mypy src/               — Success: no issues found (13 files)
✓ pytest tests/unit/ -v   — 76 passed in 0.58s
```

**Files modified:**

- `README.md` — +192 lines, 9 new sections, 10 expanded sections
- `CLAUDE.md` — Added FastMCP API reference, tool inventory, outstanding gaps
- `agents.md` — Added 4 new issues, 3 outstanding gaps from upstream validation
- `src/teradata_gcfr_mcp/db.py` — Added timeout parameter to teradatasql.connect()
- `src/teradata_gcfr_mcp/server.py` — Added mount_path parameter to mcp.run()

**Git commits:**

- `35997f5` — Wire query timeout and mount path to FastMCP
- `040f91b` — Update README with comprehensive documentation

**Related memory file:**

- `/home/paul/.claude/projects/-home-paul-teradata-gcfr-mcp-server/memory/validation_findings.md` — Upstream comparison notes

---

## 2026-03-27 — Diagnostics: uvx invocation error and stdio transport behaviour

**Time:** 2026-03-27

**Tasks:**

1. **Diagnosed `uvx` failure** — User ran `uvx teradata-gcfr-mcp-server`; it
   failed with "not found in package registry". Root cause: `uvx` resolves from
   PyPI; this package is local-only and unpublished. Correct command is
   `uv run teradata-gcfr-mcp-server`. Confirmed with a 10-second timeout run
   (exit 0, no hang).

2. **Diagnosed stdio transport "freeze"** — User reported the server appeared
   hung after `uv run teradata-gcfr-mcp-server`. Root cause: default
   `MCP_TRANSPORT=stdio` suppresses all stderr output (by design in
   `_configure_logging()`) and blocks waiting for MCP messages on stdin. This is
   correct behaviour when launched by an MCP client; it looks frozen in a
   terminal because no client is attached. Resolution: use
   `MCP_TRANSPORT=sse uv run teradata-gcfr-mcp-server` for manual/development
   runs.

**Files modified:**

- `CLAUDE.md` — added "Running the server" section documenting `uv run` vs
  `uvx`, and explaining why stdio mode produces no output
- `agents.md` — added issues 6 (uvx) and 7 (stdio freeze) to the "Issues
  encountered" section

**Verification gate:** not applicable (no source code changed).

---

## 2026-03-27 — Phase 5: gap analysis improvements (asyncio.to_thread, real pool, QueryBand, transport-aware logging, YAML profile filter test)

**Files modified:**

- `src/teradata_gcfr_mcp/db.py` — complete rewrite; `TDConnectionPool` now uses `queue.Queue` + `threading.Lock` for thread safety; lazy `_open()` replaces `_connect()`; QueryBand set on every new connection; `get_connection()` context manager discards connections on exception; overflow connections closed after use; `invalidate()` drains idle queue
- `src/teradata_gcfr_mcp/server.py` — replaced `logging.basicConfig` with `_configure_logging()`; stdio transport → rotating file only; HTTP/SSE → stderr + rotating file
- `src/teradata_gcfr_mcp/tools/streams.py` — added `asyncio.to_thread` wrapping in all three tool handlers
- `src/teradata_gcfr_mcp/tools/processes.py` — same
- `src/teradata_gcfr_mcp/tools/loads.py` — same
- `src/teradata_gcfr_mcp/tools/transforms.py` — same
- `src/teradata_gcfr_mcp/tools/errors.py` — same
- `src/teradata_gcfr_mcp/tools/sla.py` — same
- `src/teradata_gcfr_mcp/tools/lineage.py` — same
- `src/teradata_gcfr_mcp/tool_loader.py` — `_make_tool_fn` updated to use `asyncio.to_thread`
- `tests/unit/test_db.py` — rewritten: `_connect` → `_open`; `_mock_conn(captured)` helper captures SQL; `test_open_sets_query_band` added; pool `get_connection()` used as context manager
- `tests/unit/test_tool_loader.py` — added `test_yaml_tools_subject_to_profile_filter` regression test
- `CLAUDE.md` — updated "Patching the connection pool in db tests" section; removed stale profile-filtering pending item

**Tasks:**

1. **asyncio.to_thread**: Every `_handle_*` call in all 7 tool modules now runs in a thread pool via `await asyncio.to_thread(...)` to avoid blocking the MCP event loop.
2. **Real connection pool**: Replaced single `self._conn` with a `queue.Queue`-based pool supporting `TD_POOL_SIZE` persistent connections + `TD_MAX_OVERFLOW` burst connections. Connections are discarded (not returned) on exception. `TD_POOL_TIMEOUT` gates callers waiting for a free slot.
3. **QueryBand**: `_open()` executes `SET QUERY_BAND = 'ApplicationName=teradata-gcfr-mcp;UtilityName=MCP;' FOR SESSION` on every new connection for Teradata workload-management attribution.
4. **Transport-aware logging**: stdio mode writes to rotating file only (stdout is the MCP wire); HTTP/SSE modes write to both stderr and the rotating file. Log: `teradata-gcfr-mcp.log`, max 10 MiB, 3 backups.
5. **YAML profile filter regression test**: Confirmed YAML-loaded custom tools are pruned by `_apply_profile_filter()` (load-then-filter ordering in `main()` already correct); locked in with `test_yaml_tools_subject_to_profile_filter`.

**Live smoke tests run against GDEV1 (192.168.1.198):**

- 21 tools registered; `health_check` returned ok
- Reconnect-once pattern fired on first attempt, retried successfully (logged as WARNING in `teradata-gcfr-mcp.log`)
- Pool reuse confirmed: second query 395 ms vs first 807 ms
- Pre-existing schema issue discovered (not caused by these changes): `gcfr_top_slowest_processes` / `gcfr_top_slowest_streams` fail with `Column Elapsed_Seconds not found in GDEV1V_OPR.GCFR_RV_LongestRunProcess`

**Verification gate result:** `ruff check src/` ✓ · `mypy src/` ✓ · `pytest tests/unit/ -v` 84/84 ✓

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
