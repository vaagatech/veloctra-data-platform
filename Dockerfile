# ────────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder: install Python dependencies
# ────────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libssl-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ────────────────────────────────────────────────────────────────────────────────
# Stage 2 — Runtime: minimal image
# ────────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Non-root user for security
RUN addgroup --system etl && adduser --system --ingroup etl etl_user

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY enterprise_etl_engine/ ./enterprise_etl_engine/
COPY .env.example .env.example

# UI static assets (built separately via npm, copied in CI)
COPY enterprise_etl_engine/ui/dist/ ./enterprise_etl_engine/ui/dist/

RUN chown -R etl_user:etl /app
USER etl_user

EXPOSE 8000

# Graceful shutdown support — uvicorn handles SIGTERM natively
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "enterprise_etl_engine.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-graceful-shutdown", "30"]
