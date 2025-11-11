# Build stage - compile dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (only in this stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libssl-dev \
    libffi-dev \
    python3-dev \
    cargo \
    rustc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies (not build tools!)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application files
COPY backend ./backend
COPY frontend ./frontend
COPY config.yaml .
COPY plugins ./plugins
COPY themes ./themes

# Create data directories
RUN mkdir -p data/notes data/search_index

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

