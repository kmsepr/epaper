# Use official Playwright Python image (Ubuntu 20.04 - focal)
FROM mcr.microsoft.com/playwright/python:1.43.1-focal

# Set working directory inside the container
WORKDIR /app

# Copy your application code
COPY main.py /app/main.py

# Create cache directory for persistent storage (optional if mounted)
RUN mkdir -p /app/cache

# Expose port 8000 for the web server
EXPOSE 8000

# Run the Python script
CMD ["python", "main.py"]