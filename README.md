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

## Quick start

```bash
uvx teradata-gcfr-mcp-server
```

This downloads and runs the server in an isolated environment. For production use, set your
connection details via environment variables or a `.env` file (see Configuration below).

---

## Development install

```bash
git clone <repo-url>
cd teradata-gcfr-mcp-server

# Install all dependencies including dev extras
uv sync

# Confirm tests pass before making changes
uv run pytest tests/unit/ -v

# Run the server locally (stdio transport, reads from .env)
uv run teradata-gcfr-mcp-server
```

Copy `.env.example` to `.env` and fill in your Teradata credentials before running.

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
| `GCFR_QUERY_TIMEOUT` | int | `120` | Per-query timeout in seconds |
| `MCP_TRANSPORT` | str | `stdio` | `stdio` \| `streamable-http` \| `sse` |
| `MCP_HOST` | str | `127.0.0.1` | Bind host for HTTP/SSE transports |
| `MCP_PORT` | int | `8001` | Bind port for HTTP/SSE transports |
| `MCP_PATH` | str | `/mcp/` | URL path prefix for `streamable-http` |
| `PROFILE` | str | `all` | Active tool profile (see Profiles below) |
| `LOGGING_LEVEL` | str | `WARNING` | Python logging level |
| `CONFIG_DIR` | str | `.` | Directory scanned for `*_tools.yml` custom tools |

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

| Placeholder | Expands to |
| --- | --- |
| `{gcfr_opr_db}` | `GCFR_OPR_DB` setting (e.g. `GDEV1V_OPR`) |
| `{gcfr_view_db}` | `GCFR_VIEW_DB` setting (e.g. `GDEV1V_GCFR`) |
| `{gcfr_utlfw_db}` | `GCFR_UTLFW_DB` setting (e.g. `GDEV1V_UTLFW`) |

Custom tools are zero-argument — they run their SQL directly with `GCFR_MAX_ROWS` row limit.
Tool names must follow the `gcfr_` prefix convention so that profile filtering applies.

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

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `OSError: Teradata connection failed` | Wrong host/port in `DATABASE_URI` | Verify host resolves and port 1025 is reachable |
| `[Error 3524] No access` or similar | Missing `SELECT` grant | Run the `GRANT SELECT ON ...` statements above |
| Tool returns `{"error": "...", "sql": "..."}` | DB error or timeout | Check `GCFR_QUERY_TIMEOUT`; look at the `sql` field for the failing query |
| Claude Desktop shows no tools | Server not running or wrong transport | Confirm `MCP_TRANSPORT=stdio` and restart Claude Desktop |
| `INTERVAL` columns appear as `"0:01:23"` string | Expected — timedelta serialised to string | The `HH:MM:SS` format is correct; parse with `datetime.timedelta` if needed |
| Custom tools not appearing | Wrong `CONFIG_DIR` or file not named `*_tools.yml` | Set `CONFIG_DIR` to the directory containing your `*_tools.yml` file |
