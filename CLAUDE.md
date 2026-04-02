# CLAUDE.md — teradata-gcfr-mcp-server

Developer and agent reference for the `teradata-gcfr-mcp-server` project.

---

## Project overview

Python MCP server that exposes Teradata GCFR (Global Control Framework Repository)
operational reporting as natural-language tools consumable by Claude.
Target environment: `GDEV1` Teradata.

---

## Toolchain — always use `uv`

```bash
uv sync              # install / sync dependencies
uv run <cmd>         # run any command in the venv
uvx <tool>           # run a one-off tool (e.g. uvx ruff)
```

Never use `pip`, `python -m pip`, or bare `python`. The lock file is `uv.lock`.

---

## Verification gate (run before declaring any work done)

```bash
uv run ruff check src/
uv run mypy src/
uv run pytest tests/unit/ -v
```

All three must pass with zero errors. When asked to implement a specific subset
of files, gate on those files only; when asked to implement everything, gate on
the full `src/` and `tests/unit/`.

---

## Architecture

### Package layout

```
src/teradata_gcfr_mcp/
  config.py          — Settings (pydantic-settings), module-level `settings` singleton
  db.py              — TDConnectionPool, execute_query, get_pool singleton
  server.py          — FastMCP wiring, profile filtering, main()
  tool_loader.py     — YAML-driven dynamic tool registration
  tools/
    streams.py       — 3 tools: stream_status, current_stream_status, stream_business_date
    processes.py     — 3 tools: current_process_status, process_history, process_status_summary
    loads.py         — 3 tools: load_stats, load_status, dataset_registered
    transforms.py    — 5 tools: transform_stats, top_slowest_processes,
                        top_slowest_streams, data_trend_loads, data_trend_transforms
    errors.py        — 3 tools: failed_processes, error_log, execution_log
    sla.py           — 2 tools: sla_process_report, sla_stream_report
    lineage.py       — 2 tools: data_lineage, health_check
  config/
    profiles.yml     — named tool-filter profiles (all, ops, performance, lineage)
    gcfr_tools.yml   — example custom tool definition
```

### Naming convention

Every MCP tool is named `gcfr_<noun_verb>`. The `profiles.yml` patterns rely on
this prefix — do not register tools with other prefixes.

---

## Key design decisions

### Async/sync split

`@mcp.tool()` decorated functions are `async def`. All database work lives in
sync `_handle_*` functions that are called from the async wrappers. This keeps
DB logic testable without MCP machinery.

```python
# Sync, importable, patchable in tests
def _handle_xyz(pool, settings, ...) -> list[dict[str, Any]]: ...

# MCP wrapper — thin closure
def register(mcp, pool, settings):
    @mcp.tool()
    async def gcfr_xyz(...) -> list[dict[str, Any]]:
        return _handle_xyz(pool, settings, ...)
```

### Dynamic date defaults

Never put `date.today()` in a function default argument — it freezes at module
import time. Instead use `str | None = None` and compute inside the function:

```python
eff_from = date_from or (date.today() - timedelta(days=1)).isoformat()
```

### Parameterised SQL only

User-supplied values → `?` placeholders.
Schema/table names from `settings.*_DB` constants → f-string interpolation.
Never interpolate user input into SQL.

### execute_query never raises

Returns `list[dict[str, Any]]` always. Errors come back as:
```python
[{"error": "<message>", "sql": "<injected sql>"}]
```
Tool handlers must propagate these dicts unchanged — do not re-raise.

### Reconnect-once pattern (in db.py)

On first exception: `pool.invalidate()` + retry once. If the retry also fails,
return the error dict. This transparently handles stale connections.

### TOP clause injection (in execute_query)

When `max_rows` is given and `SELECT TOP` is not already present, `execute_query`
injects `TOP N` via regex. For `gcfr_top_slowest_*` tools the `TOP {top_n}` is
baked directly into the SQL string, so `max_rows` is intentionally not passed —
otherwise the injected TOP and the baked TOP would conflict.

---

## Database constants — four distinct settings

| Setting | Default | Used for |
|---|---|---|
| `GCFR_VIEW_DB` | `GDEV1V_GCFR` | Registration tables mirror, Stream_BusDate |
| `GCFR_OPR_DB` | `GDEV1V_OPR` | All `GCFR_RV_*` operational reporting views |
| `GCFR_UTLFW_DB` | `GDEV1V_UTLFW` | BKEY/BMAP surrogate-key views |
| `GCFR_TABLE_DB` | `GDEV1T_GCFR` | Physical tables (health-check only) |

**Never** collapse these into a single `GCFR_DATABASE` setting.
**Never** reference `GDEV1_*` user databases or `GDEV1T_*` physical tables
from tool queries — only the `GDEV1V_*` view layer.

### Important view name: lineage

The lineage view is `GCFR_Object_Lineage` (no `RV_` prefix, no `RT_` prefix).
It lives in `GCFR_OPR_DB`. Do not guess `GCFR_RV_Object_Lineage` or
`GCFR_RT_Object_Lineage` — both are wrong.

---

## Writing a new tool module

1. Copy the pattern from any existing tool module.
2. Write `_handle_*` sync functions first.
3. Write `register(mcp, pool, settings)` with `@mcp.tool()` async wrappers.
4. Add the module to `server.py` imports and call `<module>.register(...)` inside `main()`.
5. Write unit tests — 3 per handler (normal / empty / connection_error).
6. Patch `teradata_gcfr_mcp.tools.<module>.execute_query`, not `db.execute_query`.
7. Run the verification gate.

---

## INTERVAL DAY TO SECOND handling (SLA tools)

The Teradata driver may return INTERVAL columns as `datetime.timedelta`. MCP
cannot serialise timedelta to JSON. The SLA module has a `_coerce_intervals()`
helper that converts any `timedelta` values in result rows to `str`. Apply it
to any tool that returns duration/interval columns.

---

## Custom YAML tools (tool_loader.py)

- Scan `settings.CONFIG_DIR` for `*_tools.yaml` and `*_tools.yml` files.
- Supported placeholders in SQL: `{gcfr_opr_db}`, `{gcfr_view_db}`, `{gcfr_utlfw_db}`.
- `_substitute_placeholders(sql, settings)` is the pure function that does substitution — import it directly in tests to verify expansion without registering a live tool.
- Each tool is a zero-argument async function registered via `mcp.tool()(fn)`.

---

## Profile filtering (server.py)

- `settings.PROFILE` (env var `PROFILE`) selects the active profile; default `"all"`.
- `--profile <name>` CLI arg overrides `settings.PROFILE`.
- Profiles are defined in `src/teradata_gcfr_mcp/config/profiles.yml` using `fnmatch` glob patterns.
- `_apply_profile_filter()` removes non-matching tools from `mcp._tool_manager._tools` post-registration. It uses `getattr` with `Any` typing to access FastMCP internals safely under mypy strict.
- Profile filtering only runs when `active_profile != "all"`.

---

## mypy strict — known issues and fixes

| Issue | Fix |
|---|---|
| `teradatasql.connect()` is untyped | `# type: ignore[no-untyped-call]` on that call only |
| `mcp.run(transport=str)` type mismatch | `MCP_TRANSPORT` typed as `Literal["stdio", "sse", "streamable-http"]` in config.py |
| `yaml.safe_load()` returns `Any` | Explicit `isinstance()` guards before indexing |
| FastMCP `_tool_manager` private attr | `getattr(..., None)` with `Any` type annotation |

---

## Testing patterns

### Patching execute_query

Always patch at the module's own import path, not the source:

```python
# CORRECT
with patch("teradata_gcfr_mcp.tools.streams.execute_query", ...):

# WRONG — won't intercept calls made from streams.py
with patch("teradata_gcfr_mcp.db.execute_query", ...):
```

### Health check — two sequential calls

Use `side_effect` (list) to return different values on consecutive calls:

```python
with patch(_MOCK_PATH, side_effect=[[{"stream_count": 42}], [{"view_count": 100}]]):
```

### Creating Settings in tests

```python
s = Settings(DATABASE_URI="teradata://user:pass@localhost:1025/db")
```

`TDConnectionPool.__init__` only stores settings; it does not connect.
The connection is lazy — safe to create in unit tests.

### Patching the connection pool in db tests

The pool now uses `_open()` (returns a connection object) instead of the old
`_connect()` (set `self._conn`).  Patch `_open` to inject a mock connection:

```python
mocker.patch.object(pool, "_open", return_value=mock_conn)   # success path
mocker.patch.object(pool, "_open", side_effect=SomeError())  # failure path
```

### pytest-asyncio

Configured with `asyncio_mode = "auto"` in `pyproject.toml` — no `@pytest.mark.asyncio`
decorator needed on async test functions.

---

## Running the server

```bash
# Correct — uses the local project venv
uv run teradata-gcfr-mcp-server

# With SSE transport (visible stderr output, HTTP on :8000)
MCP_TRANSPORT=sse uv run teradata-gcfr-mcp-server
```

**`uvx teradata-gcfr-mcp-server` will fail** — `uvx` resolves from PyPI and this
package is not published there. Always use `uv run`.

**stdio transport looks frozen** — this is expected. `stdio` mode suppresses all
stderr output (stdout is the MCP wire protocol). The server is alive and waiting
for a client to send messages on stdin. Use `MCP_TRANSPORT=sse` when you want
visible log output during development or manual testing.

---

## Pending work (as of 2026-04-02)

### Fixed (2026-04-02)

- ✅ Query timeout wiring — `GCFR_QUERY_TIMEOUT` now passed to `teradatasql.connect(timeout=...)`
- ✅ HTTP mount path — `MCP_PATH` now passed to `mcp.run(mount_path=...)`

### Outstanding (priority order)

1. **Pool pre-ping** — Test connection liveness before handing to caller. Currently only reconnect-once on failure. Implement `_test_conn()` and call before `yield` in `get_connection()`.

2. **Request correlation** — Add request IDs to log lines for debugging multiplexed queries. Use `RequestContextMiddleware` pattern from upstream (capture headers, generate IDs, propagate in logs).

3. **{gcfr_table_db} placeholder** — Add `"gcfr_table_db": settings.GCFR_TABLE_DB` to `_substitute_placeholders()` in `tool_loader.py` so custom YAML tools can target physical tables.

4. **Integration tests** (`tests/integration/`) — live connection tests against GDEV1

5. **MCP smoke tests** (`tests/run_mcp_tests.py`) — MCP protocol validation

6. **Dockerfile + docker-compose.yml** — containerization

7. **Fix `Elapsed_Seconds` column** in `transforms.py` — `GCFR_RV_LongestRunProcess` and `GCFR_RV_LongestRunStream` do not have this column; run `SHOW VIEW` against GDEV1 to find actual elapsed-time column name, then update `_handle_top_slowest_processes` and `_handle_top_slowest_streams`

---

## FastMCP API reference (2026-04-02)

### `mcp.run(transport, mount_path=None)`

**Signature:** `mcp.run(transport: Literal["stdio", "sse", "streamable-http"] = "stdio", mount_path: str | None = None) -> None`

**Parameters:**
- `transport` — MCP wire protocol transport (stdio = stdin/stdout, sse = HTTP SSE, streamable-http = HTTP)
- `mount_path` — URL path prefix for HTTP transports (e.g., `/mcp/` → `http://host:port/mcp/`)

**Notes:**
- `MCP_HOST` and `MCP_PORT` settings cannot be changed at runtime — they are FastMCP internals and the framework controls binding. These settings exist for reference but do not affect the actual bind address.
- Only `mount_path` is configurable post-initialization; transport must be chosen before `main()` returns.

---

## Tool inventory (as of 2026-04-02)

**22 total MCP tools** across 7 categories:

| Category | Count | Tools | Views |
|---|---|---|---|
| Streams | 3 | status, current_status, business_date | `GCFR_RV_Stream`, `GCFR_Stream_BusDate` |
| Processes | 3 | current_status, history, status_summary | `GCFR_RV_Process*` |
| Loads | 3 | stats, status, dataset_registered | `GCFR_RV_Load*`, `GCFR_RV_DataSetReg` |
| Transforms | 5 | stats, top_slowest_processes, top_slowest_streams, trend_loads, trend_transforms | `GCFR_RV_Transform`, `GCFR_RV_LongestRun*`, `GCFR_RV_*SumByBusDate` |
| Errors | 3 | failed_processes, error_log, execution_log | `GCFR_RV_FailedProcessDetail`, `GCFR_Error_Log`, `GCFR_RV_ExecutionLog` |
| SLA | 2 | process_report, stream_report | `GCFR_RV_SLAProcess`, `GCFR_RV_SLAStream` |
| Lineage | 2 | data_lineage, health_check | `GCFR_Object_Lineage` (health checks both view DBs) |

---
