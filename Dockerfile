# Base Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install required tools
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Run the scraper on container start
CMD ["python", "main.py"]