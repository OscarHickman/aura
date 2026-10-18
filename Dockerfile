FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc cron \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN pip install gunicorn

RUN mkdir -p /app/data /app/user_credentials \
    && cp docker/crontab /etc/cron.d/aura-cron \
    && chmod 0644 /etc/cron.d/aura-cron \
    && crontab /etc/cron.d/aura-cron \
    && cp docker/entrypoint.sh /entrypoint.sh \
    && chmod +x /entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "deploy.wsgi:app", "-w", "1", "--threads", "8", "--timeout", "120", "-b", "0.0.0.0:5000"]

