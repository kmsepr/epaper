FROM python:3.10-slim

# Install Chrome & dependencies
RUN apt-get update && apt-get install -y \
    wget unzip curl gnupg2 fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libgdk-pixbuf2.0-0 libnspr4 libnss3 libx11-xcb1 \
    libxcomposite1 libxdamage1 libxrandr2 xdg-utils libgbm1 libu2f-udev libvulkan1 \
    chromium chromium-driver && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables for Chrome
ENV CHROME_BIN="/usr/bin/chromium" \
    CHROMEDRIVER_PATH="/usr/bin/chromedriver"

# Create app directory
WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose FastAPI port
EXPOSE 8000

# Run FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]