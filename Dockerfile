# Stage 1: Build Next.js frontend
FROM node:20-slim AS frontend-builder
WORKDIR /frontend

# Copy package.json (no package-lock.json — use npm install)
COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build
# Output is in /frontend/out/

# Stage 2: Python backend runtime
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install curl (used by Docker healthcheck) and clean up apt cache
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy backend project files and lock file (README.md required by hatchling build)
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./

# Sync production dependencies only
RUN uv sync --frozen --no-dev

# Copy backend source
COPY backend/ ./

# Copy frontend build output — FastAPI serves this from /app/static/
COPY --from=frontend-builder /frontend/out ./static

# Create db directory (bind-mount target for SQLite database)
RUN mkdir -p /app/db

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
