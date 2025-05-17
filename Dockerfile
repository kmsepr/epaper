# Use the official Playwright base image with Python
FROM mcr.microsoft.com/playwright/python:v1.43.1-jammy

# Set environment
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy your code
COPY main.py /app/

# Install any additional dependencies (if needed)
# RUN pip install -r requirements.txt

# Command to run the scraper
CMD ["python", "main.py"]