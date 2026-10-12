# Lightweight Python image for the Flask DIP website
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies separately to improve Docker layer caching
COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the website source
COPY app.py .
COPY templates ./templates
COPY static ./static
COPY uploads ./uploads

# Ensure runtime output directories exist
RUN mkdir -p /app/uploads /app/static/results

EXPOSE 5000

# Production WSGI server; do not use Flask's debug server in Docker
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
