FROM python:3.11-slim

# Install system dependencies including ADB
RUN apt-get update && apt-get install -y \
    android-tools-adb \
    android-tools-fastboot \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Make scripts executable
RUN chmod +x scripts/entrypoint.sh && \
    chmod +x scripts/*.sh

# Create logs directory
RUN mkdir -p /logs

# Set up cron directory
RUN mkdir -p /var/spool/cron/crontabs

# Entrypoint
ENTRYPOINT ["/app/scripts/entrypoint.sh"]

