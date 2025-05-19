FROM debian:bookworm

# Install required packages
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    gnupg \
    ca-certificates \
    jq \
    chromium \
    chromium-driver \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Define environment variables
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

# Get Chromium version
RUN CHROMIUM_VERSION=$(chromium --version | grep -oP '\d+\.\d+\.\d+') && \
    echo "Detected Chromium version: $CHROMIUM_VERSION" && \
    MAJOR_VERSION=$(echo $CHROMIUM_VERSION | cut -d '.' -f1) && \
    DRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" | \
      jq -r --arg ver "$CHROMIUM_VERSION" '.versions[] | select(.version == $ver) | .version' | head -1) && \
    echo "Installing ChromeDriver version: $DRIVER_VERSION" && \
    wget -q "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" -O chromedriver.zip && \
    unzip chromedriver.zip && \
    mv chromedriver-linux64/chromedriver ${CHROMEDRIVER_PATH} && \
    chmod +x ${CHROMEDRIVER_PATH} && \
    rm -rf chromedriver.zip chromedriver-linux64

# Optional: Add non-root user if needed
# RUN useradd -m user
# USER user

# Default command (can be changed based on your app)
CMD ["chromium", "--headless", "--no-sandbox", "--disable-gpu"]