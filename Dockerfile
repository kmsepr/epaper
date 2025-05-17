FROM python:3.10-slim

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    wget curl gnupg ca-certificates \
    fonts-liberation libnss3 libatk-bridge2.0-0 \
    libxss1 libasound2 libxcomposite1 libxdamage1 libxrandr2 libgtk-3-0 \
    libgbm-dev libx11-xcb1 libxcb1 libx11-6 libxext6 libxfixes3 libegl1 \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /app/cache

EXPOSE 8000

CMD ["python", "main.py"]