FROM python:3.11-slim

WORKDIR /app

# Create non-root user for application
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install system dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --no-warn-script-location -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser app/ app/
COPY --chown=appuser:appuser .env.example .env

# Create data directory with proper permissions
RUN mkdir -p /data && chown -R appuser:appuser /data

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
