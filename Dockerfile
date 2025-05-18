FROM python:3.11-slim

# Install system dependencies for Playwright, Pillow, Tesseract OCR
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    tesseract-ocr \
    tesseract-ocr-mal \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements.txt first for better caching
COPY requirements.txt /app/

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (only Firefox)
RUN python -m playwright install firefox

# Copy the rest of the app source code
COPY . /app

# Expose port 8000
EXPOSE 8000

# Run the app
CMD ["python", "main.py"]