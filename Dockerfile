# Stage 1: Build dependencies in a temporary builder image
FROM python:3.14-slim as builder

WORKDIR /app

# Install build dependencies required for compiling certain Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install them into the builder image
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Production image (lean and secure)
FROM python:3.14-slim

WORKDIR /app

# Install only runtime dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app && adduser --system --group app

# Copy installed Python packages from the builder stage to keep the image small
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app ./app
COPY data ./data
COPY scripts ./scripts

# Set Python path to ensure imports work correctly
ENV PYTHONPATH=/app

# Set ownership to the non-root user for security
RUN chown -R app:app /app
USER app

# Expose the port Render expects
EXPOSE 8000

# Health check to ensure the container is running and responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production start command using Gunicorn with Uvicorn workers for concurrency
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]