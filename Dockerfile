# ==============================================================================
# Veloctra Data Platform — Ultra-Lightweight Multi-Stage Dockerfile
# Optimized for small pods, edge micro-VMs, and low-memory environments (< 40MB RSS)
# ==============================================================================

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: Minimal Runtime ──────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user for enterprise container security
RUN addgroup --system veloctra && adduser --system --ingroup veloctra veloctra_user

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application packages and source
COPY packages/ ./packages/
COPY configs/ ./configs/
COPY plugins/ ./plugins/
COPY docs/ ./docs/
COPY .env.example .env.example

# Set PYTHONPATH to include all monorepo packages
ENV PYTHONPATH="/app/packages/veloctra-core:/app/packages/veloctra-security:/app/packages/veloctra-state:/app/packages/veloctra-resilience:/app/packages/veloctra-connectors:/app/packages/veloctra-transformers:/app/packages/veloctra-orchestrator:/app/packages/veloctra-api:/app"
ENV PYTHONUNBUFFERED=1

RUN chown -R veloctra_user:veloctra /app
USER veloctra_user

EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=20s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "veloctra_api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-graceful-shutdown", "15"]
