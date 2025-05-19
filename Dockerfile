# Base image with Python
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget unzip curl gnupg \
    chromium chromium-driver \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the app
COPY . .

# Make sure Chrome binary path is known to Selenium
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="/usr/lib/chromium/:$PATH"

# Expose port
EXPOSE 8000

# Run the app
CMD ["python", "main.py"]