# Build stage - install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install Python dependencies to a virtual environment
# (Most packages have pre-built wheels for amd64, no compilation needed!)
COPY requirements.txt .
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Final stage - minimal runtime image (no build tools!)
FROM python:3.11-slim

WORKDIR /app

# Copy only the virtual environment from builder (no bloat!)
COPY --from=builder /opt/venv /opt/venv

# Use the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

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

