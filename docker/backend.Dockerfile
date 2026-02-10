###############################################################################
# Stage 1: Build the React frontend
###############################################################################
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend

# Copy dependency files first for caching
COPY frontend/package.json frontend/package-lock.json ./
# Use npm install instead of npm ci because package.json may have
# dependencies not yet reflected in the lock file (e.g. @clerk/clerk-react).
# This updates the lock file in the container and installs everything.
RUN npm install

# Copy frontend source and build
COPY frontend/ ./

# VITE_CLERK_PUBLISHABLE_KEY must be available at build time since Vite
# inlines environment variables into the bundle.
#
# Priority order:
#   1. Render build-arg (if provided and non-empty)
#   2. frontend/.env.production (committed fallback)
#
# IMPORTANT: Do NOT use ENV here. Setting ENV with an empty ARG creates
# VITE_CLERK_PUBLISHABLE_KEY="" in the process environment, which Vite
# treats as "already set" and skips loading from .env.production.
ARG VITE_CLERK_PUBLISHABLE_KEY

# Diagnostic: show which source will provide the Clerk key
RUN echo "==> Build-arg VITE_CLERK_PUBLISHABLE_KEY: $(test -n \"$VITE_CLERK_PUBLISHABLE_KEY\" && echo 'YES (from Render)' || echo 'not set (will use .env.production)')" \
    && if [ -f .env.production ]; then echo "==> .env.production exists: YES"; else echo "==> .env.production exists: NO"; fi

# Build the frontend bundle. If the build-arg is empty, unset it so
# Vite falls through to .env.production.
RUN if [ -z "$VITE_CLERK_PUBLISHABLE_KEY" ]; then \
      echo "==> Unsetting empty VITE_CLERK_PUBLISHABLE_KEY so Vite reads .env.production"; \
      unset VITE_CLERK_PUBLISHABLE_KEY; \
    fi \
    && npx vite build


###############################################################################
# Stage 2: Python backend + built frontend static files
###############################################################################
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps if needed (psycopg2 etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency files first for caching
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY backend /app/backend

# Copy built frontend from stage 1 into backend/static
COPY --from=frontend-build /app/frontend/dist /app/backend/static

# Ensure python can import /app/backend/src
ENV PYTHONPATH=/app/backend

# Change to backend directory and run uvicorn
WORKDIR /app/backend

# Render listens on $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
