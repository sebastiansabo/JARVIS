# Stage 1: Build React frontend
FROM node:22-slim AS frontend-build

WORKDIR /frontend

# Copy package files first for caching
COPY jarvis/frontend/package.json jarvis/frontend/package-lock.json ./
RUN npm ci

# Copy frontend source and build
COPY jarvis/frontend/ ./
RUN npm run build

# Stage 2: Python application
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

# Copy built frontend from Stage 1
# Vite outDir is '../static/react' relative to /frontend, so output lands at /static/react/
COPY --from=frontend-build /static/react/ ./jarvis/static/react/

# Create directories
RUN mkdir -p Invoices

WORKDIR /app/jarvis

# Expose port
EXPOSE 8080

# Gunicorn: 3 workers × 3 threads = 9 concurrent requests
# DB pool: 3 workers × 8 max = 24 connections (DO limit: 47, rest for admin/health/scheduler)
# Timeout: 120s request, 30s graceful shutdown, 5s keep-alive
# Worker recycling: every ~1000 requests with jitter for memory leak prevention
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--threads", "3", "--worker-class", "gthread", "--timeout", "120", "--graceful-timeout", "30", "--keep-alive", "5", "--max-requests", "1000", "--max-requests-jitter", "200", "app:app"]
