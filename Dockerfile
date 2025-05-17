# Use the latest official Playwright image with Python
FROM mcr.microsoft.com/playwright/python:latest

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Install Playwright browsers
RUN playwright install --with-deps

# Expose port for Koyeb health check
EXPOSE 8000

# Start the web server
CMD ["python", "main.py"]