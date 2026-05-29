#* Use Python 3.12 slim image for better performance
FROM python:3.12-slim

#* Set environment variables for real-time Python outputs
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
#* To inform github_checker.py that the code is running inside Docker
ENV DOCKER_ENV=1

#* Set work directory
WORKDIR /app

#* Install system dependencies (curl needed for healthcheck)
RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/*

#* Copy requirements first for better caching
COPY requirements.txt .

#* Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

#* Copy application code
COPY src/ ./src/
COPY main_bot_onetime_settings.py .
COPY .dockerignore .

#* Copy and set permissions for startup script
COPY docker/docker_entrypoint.sh .
RUN chmod +x docker_entrypoint.sh

#* Expose the default port; runtime mapping remains controlled by .env/compose.
EXPOSE 13360

#* Provide a default healthcheck for direct docker run usage.
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=120s \
    CMD curl -fsS "http://localhost:${FASTAPI_PORT:-13360}/health" || exit 1

#* Start the application with configurable port
ENTRYPOINT ["./docker_entrypoint.sh"]
