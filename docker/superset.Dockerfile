# Multi-stage build for Apache Superset 3.x
# Production-ready, multi-tenant deployment with JWT embedding
FROM python:3.11-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY docker/superset/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy Superset configuration files
COPY docker/superset/superset_config.py /app/
COPY docker/superset/rls_rules.py /app/
COPY docker/superset/explore_guardrails.py /app/
COPY docker/superset/superset_feature_flags.py /app/
COPY docker/superset/performance_config.py /app/
COPY docker/superset/guards.py /app/
COPY docker/superset/dataset_loader.py /app/
COPY docker/superset/datasets/ /app/datasets/

# Copy JWT security manager
COPY docker/superset/security/ /app/security/

# Superset configuration
ENV SUPERSET_HOME=/app/superset
ENV SUPERSET_CONFIG_PATH=/app/superset_config.py
ENV FLASK_APP=superset.app:create_app()

RUN mkdir -p $SUPERSET_HOME

# Run DB migrations on startup, then serve via gunicorn
CMD superset db upgrade && \
    superset init && \
    gunicorn \
    --workers 4 \
    --worker-class gevent \
    --bind 0.0.0.0:8088 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    superset.app:create_app()

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:8088/health || exit 1

EXPOSE 8088
