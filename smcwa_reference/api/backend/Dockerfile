# Final Python Application Image
FROM python:3.11-slim-bookworm
WORKDIR /app

# Install necessary runtime dependencies
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y ca-certificates curl gnupg2 && \
    # Add Microsoft SQL Server repository for ODBC drivers (Debian 12 Bookworm)
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql18 unixodbc-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy Python application files
COPY api/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY api/backend/ .
COPY CHANGELOG.json /app/CHANGELOG.json

# Ensure entrypoint is executable
RUN chmod +x /app/docker-entrypoint.sh

# VAPT Hardening: Create a non-root user
RUN addgroup --system lama && adduser --system --group lama

# Change ownership of the app directory
RUN chown -R lama:lama /app

# Switch to non-root user
USER lama

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# We use Gunicorn with Uvicorn workers for process isolation and performance.
CMD ["gunicorn", "app.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
