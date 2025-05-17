# Use official Playwright Python image with dependencies installed
FROM mcr.microsoft.com/playwright/python:v1.43.1-jammy

# Set working directory inside container
WORKDIR /app

# Copy your app code into the container
COPY main.py /app/main.py

# Create cache directory (optional since volume mount will override)
RUN mkdir -p /app/cache

# Expose port 8000 for aiohttp server
EXPOSE 8000

# Run your app
CMD ["python", "main.py"]