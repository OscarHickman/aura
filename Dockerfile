FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

RUN pip install gunicorn

EXPOSE 5000

# Use Gunicorn in production by default. Keep `run.py` for CLI/dev usage.
CMD ["gunicorn", "deploy.wsgi:app", "-w", "4", "-b", "0.0.0.0:5000"]
