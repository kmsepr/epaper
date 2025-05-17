# Use official Python slim image
FROM python:3.11-slim

# Install required OS dependencies for Chromium and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libgbm1 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxss1 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy your Python app code
COPY main.py .

# Install Python dependencies
RUN pip install --no-cache-dir flask playwright

# Install Chromium browser for Playwright
RUN playwright install chromium

# Set environment variable to prevent Python buffering logs (optional)
ENV PYTHONUNBUFFERED=1

# Expose port 8000
EXPOSE 8000

# Run the Flask app
CMD ["python", "main.py"]