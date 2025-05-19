# Use official slim Python image
FROM python:3.11-slim

# Install Tesseract OCR and required languages (Malayalam + English)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-mal \
    tesseract-ocr-eng \
    libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .

# Expose Flask port
EXPOSE 8000

# Run the Flask app
CMD ["python", "main.py"]