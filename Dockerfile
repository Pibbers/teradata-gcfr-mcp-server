FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user
RUN groupadd -r gcfr && useradd -r -u 1000 -g gcfr gcfr

WORKDIR /app

# Copy dependency manifest and source
COPY pyproject.toml uv.lock* README.md ./
COPY src/ src/

# Install production dependencies only (no dev extras)
RUN uv sync --no-dev --frozen

# Custom tool definitions mount point
VOLUME ["/app/config"]

EXPOSE 8001

USER gcfr

CMD ["uv", "run", "teradata-gcfr-mcp-server"]
