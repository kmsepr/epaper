# Use official Playwright image from Docker Hub
FROM mcr.microsoft.com/playwright:v1.43.1-focal

# Install Python and pip
RUN apt update && apt install -y python3 python3-pip

# Set working directory
WORKDIR /app

# Copy app files
COPY main.py requirements.txt /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Create cache directory
RUN mkdir -p /app/cache

# Expose web server port
EXPOSE 8000

# Run the application
CMD ["python3", "main.py"]