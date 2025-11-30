FROM python:3.12-slim

# Do not run as root
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (if you later need e.g. build tools, add them here)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app directory that matches what your code expects
RUN mkdir -p /opt/network_map/logs /opt/network_map/reports
WORKDIR /opt/network_map

# Copy dependency list first (for better caching)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (Python + static assets)
COPY . .

# Make sure non-root user owns the app paths
RUN useradd -u 1000 -r -s /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /opt/network_map

USER appuser

# Expose the FastAPI port in the container
EXPOSE 8000

# Start FastAPI with uvicorn; main:app is from main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
