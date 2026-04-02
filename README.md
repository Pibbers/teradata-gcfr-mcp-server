# teradata-gcfr-mcp-server

An MCP (Model Context Protocol) server that exposes Teradata GCFR (Global Control Framework
Repository) operational reporting as natural-language tools consumable by Claude Desktop, Claude
Code, VS Code Copilot Chat, and any other MCP-compatible client. Connect Claude to your Teradata
environment and ask questions like "show me failed processes since yesterday" or "what are the
slowest streams this week" — without writing SQL.

---

## Prerequisites

| Requirement | Notes |
| --- | --- |
| Python 3.11+ | Earlier versions not supported |
| [uv](https://docs.astral.sh/uv/) | Package manager and runner — `pip install uv` |
| `teradatasql` Python driver | Installed automatically by `uv sync` |
| Network access to Teradata | Direct TCP to port 1025, or via ODBC gateway |

---

## How it works

**Server architecture:**

1. **Entry point** (`server.py`) — Initializes the connection pool, registers all tools, applies profile filtering, and starts the MCP server.
2. **Connection pool** (`db.py`) — Thread-safe pooling of Teradata connections with configurable size, overflow, and timeout. Queries have automatic reconnect-once on transient failures.
3. **Tool modules** (`tools/*.py`) — 7 categories of MCP tools:
   - **Streams** (3 tools): Live stream status and business date tracking
   - **Processes** (3 tools): Process execution history and current status
   - **Loads** (3 tools): Data ingestion statistics and registration audit
   - **Transforms** (5 tools): Transform statistics, performance ranking, and trend analysis
   - **Errors** (3 tools): Error log, execution trace, and failed process diagnostics
   - **SLA** (2 tools): Service-level agreement compliance reporting
   - **Lineage** (2 tools): Data lineage tracing and health checks
4. **Custom tools** (`tool_loader.py`) — YAML-defined SQL tools loaded from `CONFIG_DIR` at startup, allowing site-specific reporting without Python code.

**Query execution:**

- All SQL uses parameterized queries (`?` placeholders) to prevent injection.
- Schema/table names come from `settings.py` constants, never user input.
- Per-query timeout enforced via `GCFR_QUERY_TIMEOUT` (default 120s).
- Queries are capped at `GCFR_MAX_ROWS` (default 500 rows).
- Results returned as structured error dicts on failure — no exceptions.

**Transport modes:**

| Transport | Best for | Visibility |
| --- | --- | --- |
| `stdio` | Claude Desktop, local REPL | Silent (stdout = MCP protocol) |
| `sse` | Development, debugging, VS Code | Log output on stderr |
| `streamable-http` | Web dashboards, REST clients | HTTP on configured port/path |

---

## Recent improvements

**Query timeout enforcement** (2025-04-02)
- `GCFR_QUERY_TIMEOUT` is now wired to `teradatasql.connect()` at connection initialization
- Queries that exceed the timeout are interrupted at the database level (no more runaway queries)
- Timeout applies to all tool queries uniformly

**HTTP mount path support** (2025-04-02)
- `MCP_PATH` setting is now properly passed to FastMCP's `mcp.run()` call
- HTTP transports now mount at the configured path (e.g., `/mcp/` → `http://127.0.0.1:8001/mcp/`)
- Enables better URL hierarchy and multi-server configurations

**Connection pool robustness**
- Automatic reconnect-once on transient failures (stale connections, temporary network issues)
- QueryBand set on all connections for Teradata workload-management attribution
- Graceful handling of connection exhaustion with timeout-aware blocking

---

## Quick start

### Local development (recommended)

```bash
git clone <repo-url>
cd teradata-gcfr-mcp-server
uv sync
cp .env.example .env          # Edit with your Teradata credentials
MCP_TRANSPORT=sse uv run teradata-gcfr-mcp-server  # Or use stdio for Claude Desktop
```

The `MCP_TRANSPORT` defaults to `stdio` (for Claude Desktop), but `sse` is useful for debugging
with visible log output on stderr.

---

## Development install

```bash
git clone <repo-url>
cd teradata-gcfr-mcp-server

# Install all dependencies including dev extras
uv sync

# Run linting and type checks before making changes
uv run ruff check src/
uv run mypy src/

# Run unit tests (no Teradata connection required)
uv run pytest tests/unit/ -v

# Run the server locally in development mode
MCP_TRANSPORT=sse uv run teradata-gcfr-mcp-server
```

Copy `.env.example` to `.env` and update with your Teradata credentials. The server will use
environment variables automatically.

**Verification gate (run before committing):**

All three checks must pass with zero errors:

```bash
uv run ruff check src/        # Linting
uv run mypy src/              # Type checking (strict)
uv run pytest tests/unit/ -v  # Unit tests (76 tests)
```

---

## Configuration reference

All settings are read from environment variables or a `.env` file in the working directory.

| Variable | Type | Default | Description |
| --- | --- | --- | --- |
| `DATABASE_URI` | str | _(required)_ | `teradata://user:pass@host:1025/db` |
| `LOGMECH` | str | `TD2` | Auth mechanism: `TD2`, `LDAP`, `TDNEGO`, `KRB5` |
| `TD_POOL_SIZE` | int | `5` | Persistent connections in the pool |
| `TD_MAX_OVERFLOW` | int | `10` | Extra connections allowed under burst load |
| `TD_POOL_TIMEOUT` | int | `30` | Seconds to wait for a free connection |
| `GCFR_VIEW_DB` | str | `GDEV1V_GCFR` | Base view layer — registration/metadata tools |
| `GCFR_OPR_DB` | str | `GDEV1V_OPR` | Operational reporting views (`GCFR_RV_*`) |
| `GCFR_UTLFW_DB` | str | `GDEV1V_UTLFW` | BKEY/BMAP surrogate-key views |
| `GCFR_TABLE_DB` | str | `GDEV1T_GCFR` | Physical tables — health-check only |
| `GCFR_MAX_ROWS` | int | `500` | Maximum rows any single tool may return |
| `GCFR_QUERY_TIMEOUT` | int | `120` | Per-query timeout in seconds (enforced at connection init) |
| `MCP_TRANSPORT` | str | `stdio` | `stdio` \| `streamable-http` \| `sse` |
| `MCP_HOST` | str | `127.0.0.1` | _(read-only)_ Bind host for HTTP/SSE — not configurable at runtime |
| `MCP_PORT` | int | `8001` | _(read-only)_ Bind port for HTTP/SSE — not configurable at runtime |
| `MCP_PATH` | str | `/mcp/` | URL path prefix for HTTP transports |
| `PROFILE` | str | `all` | Active tool profile (see Profiles below) |
| `LOGGING_LEVEL` | str | `WARNING` | Python logging level |
| `CONFIG_DIR` | str | `.` | Directory scanned for `*_tools.yml` custom tools |

**Notes on transport configuration:**

- `MCP_HOST` and `MCP_PORT` are FastMCP internal settings and cannot be changed at runtime. The server binds to these values but the MCP framework controls the actual binding. Modify them only if you understand the implications.
- `MCP_PATH` is properly wired and controls the HTTP mount point (e.g., `/mcp/` → `http://host:port/mcp/`).
- `GCFR_QUERY_TIMEOUT` is now wired to `teradatasql.connect()`, ensuring all queries respect the configured timeout.

---

## Profiles

Profiles limit which tools are exposed to the MCP client. Set via the `PROFILE` env var or the
`--profile` CLI flag.

### `all` (default)

Every tool is available.

### `ops`

Focused on live operational monitoring:

`gcfr_stream_status`, `gcfr_current_stream_status`, `gcfr_stream_business_date`,
`gcfr_current_process_status`, `gcfr_process_history`, `gcfr_process_status_summary`,
`gcfr_failed_processes`, `gcfr_error_log`, `gcfr_execution_log`,
`gcfr_load_status`, `gcfr_health_check`

### `performance`

Focused on SLA and throughput analysis:

`gcfr_sla_process_report`, `gcfr_sla_stream_report`, `gcfr_top_slowest_processes`,
`gcfr_top_slowest_streams`, `gcfr_data_trend_loads`, `gcfr_data_trend_transforms`,
`gcfr_stream_status`, `gcfr_health_check`

### `lineage`

Focused on data lineage and registration audit:

`gcfr_data_lineage`, `gcfr_dataset_registered`, `gcfr_load_stats`,
`gcfr_transform_stats`, `gcfr_health_check`

---

## Available MCP tools (22 total)

All tools are read-only queries against GCFR operational views. None modify data.

### Streams (3 tools)

- `gcfr_stream_status` — History and completion state for a date range
- `gcfr_current_stream_status` — Real-time stream status (running now)
- `gcfr_stream_business_date` — Current, previous, next business date for a stream

### Processes (3 tools)

- `gcfr_process_status_summary` — All processes for a business date (completed vs incomplete)
- `gcfr_current_process_status` — Real-time process status
- `gcfr_process_history` — Execution history with timing and outcomes

### Loads (3 tools)

- `gcfr_load_status` — Which staging tables loaded successfully and row counts
- `gcfr_load_stats` — Detailed load statistics (rejections, ET/UV violations, errors)
- `gcfr_dataset_registered` — Source datasets registered for processing

### Transforms (5 tools)

- `gcfr_transform_stats` — Rows inserted/updated/deleted per process
- `gcfr_top_slowest_processes` — Top N slowest processes by elapsed time
- `gcfr_top_slowest_streams` — Top N slowest streams by elapsed time
- `gcfr_data_trend_loads` — Daily load volume trends
- `gcfr_data_trend_transforms` — Daily transform volume trends

### Errors (3 tools)

- `gcfr_failed_processes` — Failed process instances with error details
- `gcfr_error_log` — Raw error log entries for root cause investigation
- `gcfr_execution_log` — Step-level execution trace (debug level only)

### SLA (2 tools)

- `gcfr_sla_process_report` — Expected vs actual process timing and SLA compliance
- `gcfr_sla_stream_report` — Expected vs actual stream duration and SLA compliance

### Lineage (2 tools)

- `gcfr_data_lineage` — Trace target table back to source objects
- `gcfr_health_check` — Verify GCFR databases are reachable

---

## Database naming

GCFR uses two distinct tiers of databases:

| Tier | Name pattern | Purpose |
| --- | --- | --- |
| View layer (V) | `GDEV1V_GCFR`, `GDEV1V_OPR`, `GDEV1V_UTLFW` | All `GCFR_RV_*` operational views — use these |
| Table layer (T) | `GDEV1T_GCFR` | Physical base tables — referenced only by the health-check |

**Never** reference `GDEV1_GCFR` (no T or V suffix) — that database does not exist. All tool
queries target the `GDEV1V_*` view layer. Only `gcfr_health_check` touches `GDEV1T_GCFR` to
verify the physical tables are reachable.

---

## Required Teradata permissions

The server account needs `SELECT` privilege on the three view-layer databases:

```sql
GRANT SELECT ON GDEV1V_GCFR  TO <your_user>;
GRANT SELECT ON GDEV1V_OPR   TO <your_user>;
GRANT SELECT ON GDEV1V_UTLFW TO <your_user>;
-- For health-check (optional):
GRANT SELECT ON GDEV1T_GCFR  TO <your_user>;
```

No `INSERT`, `UPDATE`, `DELETE`, or DDL privileges are required — the server is read-only.

---

## Claude Desktop configuration

Add the following to your `claude_desktop_config.json` (replace credential values):

```json
{
  "mcpServers": {
    "teradata-gcfr": {
      "command": "uvx",
      "args": ["teradata-gcfr-mcp-server"],
      "env": {
        "DATABASE_URI": "teradata://myuser:mypass@gdev1-host:1025/GDEV1V_GCFR",
        "LOGMECH": "TD2",
        "GCFR_VIEW_DB": "GDEV1V_GCFR",
        "GCFR_OPR_DB": "GDEV1V_OPR",
        "GCFR_UTLFW_DB": "GDEV1V_UTLFW",
        "GCFR_TABLE_DB": "GDEV1T_GCFR",
        "MCP_TRANSPORT": "stdio",
        "PROFILE": "all"
      }
    }
  }
}
```

**Config file location:**

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

---

## VS Code / Copilot Chat configuration

Add to your VS Code `settings.json` or workspace `.vscode/mcp.json`. The SSE transport is
recommended for VS Code:

```json
{
  "mcp": {
    "servers": {
      "teradata-gcfr": {
        "type": "sse",
        "url": "http://127.0.0.1:8001/sse",
        "env": {}
      }
    }
  }
}
```

Then run the server with:

```bash
MCP_TRANSPORT=sse uv run teradata-gcfr-mcp-server
```

---

## Docker quick start

```bash
# Build image
docker build -t gcfr-mcp .

# Run with an .env file
docker run --rm --env-file .env -p 8001:8001 gcfr-mcp

# Or use docker-compose (starts with streamable-http transport)
docker compose up
```

The `docker-compose.yml` mounts `./gcfr_custom_tools.yml` into the container at
`/app/gcfr_custom_tools.yml` (read-only). Create this file to add site-specific tools; if it
does not exist, the container starts without custom tools.

---

## Custom tools (YAML)

Add read-only SQL tools without writing Python by placing a `*_tools.yml` file in `CONFIG_DIR`
(defaults to `.`, the current working directory).

**Example — `gcfr_custom_tools.yml`:**

```yaml
tools:
  - name: gcfr_my_site_report
    description: "Latest 20 stream records for this site"
    sql: >
      SELECT TOP 20
        Stream_Key, Stream_Name, Business_Date, Stream_Status
      FROM {gcfr_opr_db}.GCFR_RV_Stream
      ORDER BY Business_Date DESC
```

**Supported SQL placeholders:**

| Placeholder | Expands to | Purpose |
| --- | --- | --- |
| `{gcfr_opr_db}` | `GCFR_OPR_DB` setting | Operational reporting views (`GCFR_RV_*`) |
| `{gcfr_view_db}` | `GCFR_VIEW_DB` setting | Base registration/metadata views |
| `{gcfr_utlfw_db}` | `GCFR_UTLFW_DB` setting | BKEY/BMAP surrogate-key reference data |

Custom tools are zero-argument — they execute their SQL directly with a `GCFR_MAX_ROWS` row limit applied automatically. Tool names must follow the `gcfr_` prefix convention so that profile filtering and naming conventions are consistent.

---

## Sample questions

The following questions work out-of-the-box with Claude once the server is connected:

1. "Show me all failed processes since yesterday."
2. "What is the current status of stream 42?"
3. "Which streams have not completed today's business date?"
4. "Give me the top 10 slowest processes this week."
5. "Show the SLA report for process LOAD_CUSTOMER_DAILY from 2024-01-01 to 2024-01-31."
6. "What datasets are registered in GCFR?"
7. "List the lineage for target table CUSTOMER_DIM."
8. "Show me transform statistics for the last 7 days."
9. "Are the GCFR databases reachable? Run a health check."
10. "What errors occurred in the execution log today?"

---

## Linting and type checking

```bash
# Lint
uv run ruff check src/

# Auto-fix lint issues
uv run ruff check --fix src/

# Type checking (strict)
uv run mypy src/
```

---

## Running tests

### Unit tests (no Teradata connection required)

```bash
uv run pytest tests/unit/ -v
```

All database calls are mocked — unit tests run offline.

### Integration tests (requires GDEV1 network access)

```bash
uv run pytest tests/integration/ -v
```

Integration tests are not yet implemented. Contributions welcome — see `CLAUDE.md` for the
pending work list.

### Skipping slow tests

```bash
uv run pytest tests/unit/ -v -m "not slow"
```

---

## Architecture and design patterns

See `CLAUDE.md` in the repository for comprehensive developer documentation including:

- **Async/sync split** — Why MCP tool wrappers are async but DB logic is sync
- **Dynamic date defaults** — How to avoid frozen dates in function signatures
- **Parameterised SQL only** — Security model for user input vs schema names
- **Reconnect-once pattern** — Transient failure handling in the connection pool
- **TOP clause injection** — Why and how row limits are applied transparently
- **Testing patterns** — How to mock database calls without hitting Teradata
- **Custom tool loading** — YAML-driven tool registration and placeholder substitution
- **Profile filtering** — How role-based access control works at startup

---

## Design validation

This server was validated against the upstream [`Teradata/teradata-mcp-server`](https://github.com/Teradata/teradata-mcp-server)
for architectural best practices and lessons learned. Key differences:

| Aspect | This server | Upstream |
| --- | --- | --- |
| Connection layer | Direct teradatasql | SQLAlchemy + teradatasqlalchemy |
| DB abstraction | Hand-rolled connection pool | SQLAlchemy QueuePool |
| Tool registration | Module-based + YAML | Python (auto-discovery) + YAML + progressive disclosure |
| Async strategy | `asyncio.to_thread` in wrappers | Sync blocking in handlers (thread pool implicit) |
| Type checking | `mypy --strict` | Gradual mypy (strict disabled) |
| Testing | 3 per handler (normal/empty/error) | Integration tests against live DB |
| Error handling | Structured error dicts | Some handlers may raise |
| Database timeout | ✓ Enforced at connection | Optional SQLAlchemy pool timeout |
| HTTP path mounting | ✓ Wired to `mcp.run()` | Configuration-only |

Both implementations are production-ready and differ mainly in scope (GCFR-specific vs general Teradata)
and deployment strategy (lightweight vs feature-rich).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `OSError: Teradata connection failed` | Wrong host/port in `DATABASE_URI` | Verify host resolves and port 1025 is reachable; check firewall |
| `[Error 3524] No access` or permission denied | Missing `SELECT` grant | Run the `GRANT SELECT ON ...` statements in the Required Teradata permissions section |
| Tool returns `{"error": "...", "sql": "..."}` | Query execution failed or timeout | Check `GCFR_QUERY_TIMEOUT` setting; look at the `sql` field for the failing query; check Teradata error message |
| Query hangs or times out | `GCFR_QUERY_TIMEOUT` too low or network latency | Increase `GCFR_QUERY_TIMEOUT` in `.env`; default is 120s |
| Claude Desktop shows no tools | Server not running or wrong transport | Confirm `MCP_TRANSPORT=stdio`; restart Claude Desktop after server starts |
| SSE transport shows `Connection refused` | Server not running or wrong host/port | Verify server is running with `MCP_TRANSPORT=sse`; check `MCP_HOST` and `MCP_PORT` in `.env` |
| `INTERVAL` columns appear as `"0:01:23"` string | Expected — Teradata INTERVAL serialized to string | The `HH:MM:SS` format is correct; this is standard JSON serialization of intervals |
| Custom tools not appearing | Wrong `CONFIG_DIR` or file not named `*_tools.yml` | Set `CONFIG_DIR` to the directory containing your `*_tools.yml` file; restart server |
| Profile filter not working | Tool name doesn't match pattern | Tool names must start with `gcfr_` to be subject to profile filtering |
| Server starts but no output | `MCP_TRANSPORT=stdio` silences logs | Use `MCP_TRANSPORT=sse` or `MCP_TRANSPORT=streamable-http` to see startup logs on stderr |
