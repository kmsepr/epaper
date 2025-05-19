FROM python:3.11-slim

# Install dependencies required by Chromium + Selenium
RUN apt-get update && apt-get install -y \
    wget unzip curl gnupg \
    chromium \
    fonts-liberation libnss3 libatk-bridge2.0-0 libxss1 libasound2 libatk1.0-0 libcups2 libdbus-1-3 libx11-xcb1 libxtst6 libgbm1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Download matching ChromeDriver version
ARG CHROMIUM_VERSION=114.0.5735.90
RUN wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${CHROMIUM_VERSION}/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/local/bin/chromedriver

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app source code
COPY . .

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="/usr/lib/chromium/:$PATH"

# Expose Flask port
EXPOSE 8000

# Start the application
CMD ["python", "main.py"]