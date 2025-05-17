# Use official Playwright Python image with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:1.43.1

# Set working directory
WORKDIR /app

# Copy script
COPY main.py /app/main.py

# Create persistent cache directory
RUN mkdir -p /app/cache

# Expose server port
EXPOSE 8000

# Run the script
CMD ["python", "main.py"]