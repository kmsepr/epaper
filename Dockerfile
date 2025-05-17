FROM python:3.10-slim

# Install Chromium and system dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    wget curl gnupg ca-certificates \
    libnss3 libatk-bridge2.0-0 libxss1 libasound2 \
    libxcomposite1 libxdamage1 libxrandr2 libgtk-3-0 \
    libgbm-dev libx11-xcb1 libxcb1 libx11-6 libxext6 libxfixes3 libegl1 \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /app/cache

EXPOSE 8000

CMD ["python", "main.py"]