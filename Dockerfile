FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    chromium chromium-driver wget unzip curl jq fonts-liberation libnss3 libxss1 libappindicator3-1 libasound2 libatk-bridge2.0-0 libgtk-3-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chromium
ENV CHROMIUM_PATH=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

# Detect Chromium version and install matching ChromeDriver
RUN CHROMIUM_VERSION=$(chromium --version | grep -oP '\d+\.\d+\.\d+') && \
    echo "Detected Chromium version: $CHROMIUM_VERSION" && \
    MAJOR_VERSION=$(echo $CHROMIUM_VERSION | cut -d '.' -f1) && \
    DRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
      jq -r --arg ver "$MAJOR_VERSION" '.versions[] | select(.version | startswith($ver)) | .version' | head -1) && \
    echo "Installing ChromeDriver version: $DRIVER_VERSION" && \
    wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver $CHROMEDRIVER_PATH && \
    chmod +x $CHROMEDRIVER_PATH && \
    rm -rf chromedriver.zip chromedriver-linux64

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . /app
WORKDIR /app

# Default command
CMD ["python", "main.py"]