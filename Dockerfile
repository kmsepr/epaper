FROM python:3.11-slim

# Install dependencies required by Playwright Chromium
RUN apt-get update && apt-get install -y \
    wget \
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
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libxshmfence1 \
    fonts-liberation \
    libasound2 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy your application files
COPY main.py requirements.txt ./

# Install Python dependencies and Playwright browsers
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

# Create directory for PDFs
RUN mkdir -p pdfs

# Expose port 8000 for Flask
EXPOSE 8000

# Run the Flask app
CMD ["python", "main.py"]