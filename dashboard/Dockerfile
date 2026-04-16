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

CMD ["python", "-m", "dashboard.app"]
