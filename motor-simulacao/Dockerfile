FROM python:3.12-slim

WORKDIR /srv

# Chromium + Xvfb (browser headed virtual) + libs — Akamai bloqueia headless_shell.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    fonts-liberation \
    fonts-noto-color-emoji \
    xvfb \
    xauth \
    dbus-x11 \
    libcairo2 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libxss1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts/worker-entrypoint.sh /srv/scripts/worker-entrypoint.sh
COPY scripts/fly-entrypoint.sh /srv/scripts/fly-entrypoint.sh
COPY scripts/on-demand-worker-entrypoint.sh /srv/scripts/on-demand-worker-entrypoint.sh
RUN chmod +x /srv/scripts/worker-entrypoint.sh /srv/scripts/fly-entrypoint.sh \
    /srv/scripts/on-demand-worker-entrypoint.sh

# Dados de sessão/screenshots (montados em volume no compose do worker).
RUN mkdir -p /srv/data/screenshots /srv/data/storage_state

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
