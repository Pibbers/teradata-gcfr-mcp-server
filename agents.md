# agents.md — teradata-gcfr-mcp-server

Notes for AI agents (Claude Code and subagents) working in this repository.
Read this before starting any implementation task.

---

## Before you write a single line of code

1. Read `CLAUDE.md` — it contains the architecture, design decisions, and
   verification gate. This file (agents.md) is about *how* to work here;
   CLAUDE.md is about *what* is here.
2. Read the existing tool module most similar to the one you are about to
   implement. Do not invent patterns — copy them.
3. Run `uv run pytest tests/unit/ -v` to confirm the test suite is green
   before you make any changes.

---

## Verification gate — non-negotiable

Every implementation session ends with:

```bash
uv run ruff check src/
uv run mypy src/
uv run pytest tests/unit/ -v
```

All three must exit 0. Do not declare work done until they do.
If given a narrow task (e.g. "implement loads.py only"), gate on that file
and its test; when asked to do a full-src check, run all three against `src/`.

---

## Implementation checklist for a new tool module

- [ ] Write `_handle_*` sync handler for each tool (DB logic here only)
- [ ] Write `register(mcp, pool, settings)` with `@mcp.tool()` async wrappers
- [ ] Date defaults: `str | None = None`, computed with `date.today()` inside the function body — never in a default argument
- [ ] Date validation: use `_valid_date()` and return an error dict on failure
- [ ] stream_key / ctl_id parsing: use `_parse_stream_key()` / `_parse_ctl_id()` pattern returning `int | dict[str, Any]`
- [ ] SQL params in same order as `?` placeholders
- [ ] Schema names from `settings.*_DB` via f-string; user values via `?` only
- [ ] Add the module to `server.py` imports + call `<mod>.register(...)` inside `main()`
- [ ] Write 3 unit tests per handler: normal / empty / connection_error
- [ ] Patch path: `teradata_gcfr_mcp.tools.<module>.execute_query`

---

## Common mistakes to avoid

### Wrong patch path

```python
# WRONG
with patch("teradata_gcfr_mcp.db.execute_query", ...):

# CORRECT — patch where it is *used*, not where it is *defined*
with patch("teradata_gcfr_mcp.tools.streams.execute_query", ...):
```

### Frozen date default

```python
# WRONG — evaluated once at module import time
def register(...):
    @mcp.tool()
    async def gcfr_xyz(date_from: str = date.today().isoformat()):
        ...

# CORRECT
    @mcp.tool()
    async def gcfr_xyz(date_from: str | None = None):
        eff_from = date_from or date.today().isoformat()
        ...
```

### Duplicate TOP clause

The `gcfr_top_slowest_*` tools bake `TOP {top_n}` directly into the SQL string.
Do **not** also pass `max_rows=settings.GCFR_MAX_ROWS` to `execute_query` for
these — the regex injector would then add a second `TOP`, which Teradata rejects.

### Wrong view name for lineage

```python
# WRONG
f"{settings.GCFR_OPR_DB}.GCFR_RV_Object_Lineage"
f"{settings.GCFR_OPR_DB}.GCFR_RT_Object_Lineage"

# CORRECT
f"{settings.GCFR_OPR_DB}.GCFR_Object_Lineage"
```

### INTERVAL / timedelta serialisation

Teradata driver may return INTERVAL DAY TO SECOND as `datetime.timedelta`.
Apply `_coerce_intervals(rows)` (from sla.py) to any result set that contains
duration columns before returning. `timedelta` is not JSON-serialisable.

---

## mypy strict — what to watch for

- `yaml.safe_load()` returns `Any`. Use `isinstance()` guards before indexing
  into the result. Do not assume structure; log and skip malformed entries.
- `teradatasql.connect()` is untyped — use `# type: ignore[no-untyped-call]`
  on that call site only (do not suppress the whole import).
- FastMCP's `_tool_manager` is private. Use `getattr(mcp, "_tool_manager", None)`
  typed as `Any` to access it — this is how `_apply_profile_filter` works.
- `MCP_TRANSPORT` must be `Literal["stdio", "sse", "streamable-http"]` in
  `config.py` — not `str` — or mypy will reject the `mcp.run(transport=...)` call.

---

## Issues encountered and how they were resolved

### 1. `uv sync` failing: `OSError: Readme file does not exist: README.md`

Hatchling requires the file declared as `readme` in `pyproject.toml` to
physically exist. Fixed by creating a minimal `README.md` placeholder.

### 2. mypy: unused `type: ignore` on `import teradatasql`

Using `# type: ignore[import-untyped]` on the import line caused mypy to
complain because teradatasql ships partial stubs. Removed the comment from the
import line; applied `# type: ignore[no-untyped-call]` only to the
`teradatasql.connect(...)` call.

### 3. mypy: `Argument "transport" incompatible type "str"`

`mcp.run()` expects `Literal["stdio", "sse", "streamable-http"]`. Resolved by
narrowing `MCP_TRANSPORT` from `str` to the appropriate `Literal` type in
`config.py`. This surfaced only when running `mypy src/` across all files
rather than individual modules.

### 4. ruff E501: line-too-long in tool docstrings

`pyproject.toml` enforces `line-length = 100`. Long first lines in triple-quoted
docstrings inside `@mcp.tool()` async functions are caught by ruff. Keep the
summary line (first line of docstring) under 100 characters. Continuation lines
after the blank line are fine.

### 5. Dynamic date defaults freeze at import time

Python evaluates default argument values once when the function is defined.
Since `register()` is called at startup, a default of `date.today()` freezes to
the startup date. Always use `str | None = None` and compute `date.today()`
inside the function body.

---

## Remaining work

See CLAUDE.md § "Pending work". Priority order:
1. Integration tests (`tests/integration/`) — requires GDEV1 network access
2. MCP smoke tests (`tests/run_mcp_tests.py`)
3. Dockerfile + docker-compose.yml
4. Full README.md
5. Profile filtering for custom YAML tools (currently they always register
   regardless of active profile)
