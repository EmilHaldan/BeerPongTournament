FROM python:3.12-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev --no-editable

# Copy source code
COPY src/ src/

EXPOSE 8000

# Run with uvicorn
CMD ["uv", "run", "--no-dev", "uvicorn", "beerpong_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
