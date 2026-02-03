FROM python:3.11-slim

# Install poppler for PDF processing
RUN apt-get update && apt-get install -y \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy application code
COPY jarvis/ ./jarvis/

# Create directories
RUN mkdir -p Invoices

WORKDIR /app/jarvis

# Expose port
EXPOSE 8080

# Run with gunicorn (3 workers + 3 threads each = 9 concurrent requests)
# Optimized for 1-10 concurrent users
# DigitalOcean DB connection limit: 22 max
# Single unified pool: 3 workers × 6 pool max = 18 connections (4 reserved for admin)
# Timeout settings prevent worker hangs after idle periods:
#   --timeout: Kill worker if no response in 120s
#   --graceful-timeout: Allow 30s for graceful shutdown
#   --keep-alive: Keep HTTP connections open for 5s (reduces reconnects)
# Worker recycling prevents memory accumulation:
#   --max-requests: Recycle worker after N requests
#   --max-requests-jitter: Stagger recycling to avoid simultaneous restarts
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--threads", "3", "--worker-class", "gthread", "--timeout", "120", "--graceful-timeout", "30", "--keep-alive", "5", "--max-requests", "500", "--max-requests-jitter", "50", "app:app"]
