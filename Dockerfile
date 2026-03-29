FROM python:3.11-slim AS base

LABEL maintainer="AgentMarket" \
      description="Multi-agent marketplace with satoshi micropayments"

# Security: non-root user
RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install deps first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# Copy application
COPY backend/ backend/
COPY frontend/ frontend/

# Create data dir
RUN mkdir -p data && chown -R agent:agent /app

USER agent

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
