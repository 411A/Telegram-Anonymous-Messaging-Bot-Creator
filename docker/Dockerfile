#* Use Python 3.12 slim image for better performance
FROM python:3.12-slim

#* Set environment variables for real-time Python outputs
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

#* Set work directory
WORKDIR /app

#* Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

#* Copy requirements first for better caching
COPY ../requirements.txt .

#* Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

#* Copy application code
COPY ../src/ ./src/
COPY ../main_bot_onetime_settings.py .

#* Copy and set permissions for startup script
COPY docker/docker_entrypoint.sh .
RUN chmod +x docker_entrypoint.sh

#* Expose the port (will be configurable via environment)
EXPOSE ${FASTAPI_PORT:-8000}

#* Start the application with configurable port
ENTRYPOINT ["./docker_entrypoint.sh"]