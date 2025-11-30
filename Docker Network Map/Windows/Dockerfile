FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Directories expected by your app
RUN mkdir -p /opt/network_map/logs /opt/network_map/reports
WORKDIR /opt/network_map

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code from the "network_map" folder on the host
COPY network_map/ .

# Non-root user
RUN useradd -u 1000 -r -s /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /opt/network_map
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
