FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy dashboard package
COPY . ./dashboard

ENV PYTHONPATH=/app

EXPOSE 8050

# Two workers is a sensible default for a read-mostly reporting dashboard.
# Threads let a single worker handle the blocking httpx calls to the API
# without blocking other requests. Access log goes to stdout so the host
# log stack captures it.
CMD ["gunicorn", "--workers", "2", "--threads", "4", \
     "--bind", "0.0.0.0:8050", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--timeout", "60", \
     "dashboard.app:server"]
