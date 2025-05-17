# Use official Python slim image
FROM python:3.11-slim

# Install OS dependencies required for Chromium and Playwright
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

# Copy project files
COPY main.py .
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium)
RUN playwright install chromium

# Expose port
EXPOSE 8000

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

# Run the Flask app
CMD ["python", "main.py"]