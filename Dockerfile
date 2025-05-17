FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxshmfence1 \
    fonts-liberation \
    libasound2 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY main.py .

RUN pip install --no-cache-dir playwright && \
    playwright install --with-deps chromium

CMD ["python", "main.py"]