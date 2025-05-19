FROM python:3.11-slim

# Install required dependencies
RUN apt-get update && apt-get install -y \
    wget unzip curl jq gnupg \
    chromium \
    fonts-liberation libnss3 libatk-bridge2.0-0 libxss1 libasound2 libatk1.0-0 libcups2 libdbus-1-3 libx11-xcb1 libxtst6 libgbm1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Get Chromium version
RUN CHROMIUM_VERSION=$(chromium --version | grep -oP '\d+\.\d+\.\d+') && \
    MAJOR_VERSION=$(echo $CHROMIUM_VERSION | cut -d '.' -f1) && \
    DRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
      jq -r --arg ver "$MAJOR_VERSION" '.versions[] | select(.version | startswith($ver)) | .version' | head -1) && \
    echo "Installing ChromeDriver for version $DRIVER_VERSION" && \
    wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm -rf chromedriver.zip chromedriver-linux64

# Set environment variables
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="/usr/lib/chromium/:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set workdir
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app source
COPY . .

# Expose Flask port
EXPOSE 8000

# Run app
CMD ["python", "main.py"]