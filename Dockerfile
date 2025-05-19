# Use official Python runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies (required for Pillow and Tesseract)
RUN apt-get update && \
    apt-get install -y gcc libjpeg-dev zlib1g-dev tesseract-ocr && \
    apt-get clean

# Copy requirements first and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY main.py .

# Expose the port Flask runs on
EXPOSE 8000

# Run the Flask app
CMD ["python", "main.py"]