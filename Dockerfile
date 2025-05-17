# Use official Python slim image
FROM python:3.11-slim

# Environment config
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install required system packages for Playwright
RUN apt-get update && apt-get install -y \
    curl wget gnupg ca-certificates \
    fonts-liberation \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libxcomposite1 libxdamage1 libxrandr2 xdg-utils \
    libu2f-udev libvulkan1 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install Playwright and its browser binaries
RUN python -m playwright install --with-deps

# Copy all app files
COPY . .

# Create the persistent cache folder if it doesn't exist
RUN mkdir -p /app/cache

# Expose the port your app runs on
EXPOSE 8000

# Run your script (replace with your script name if different)
CMD ["python", "your_script.py"]