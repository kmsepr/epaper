# Use the Playwright base image
FROM mcr.microsoft.com/playwright:v1.48.0-focal

# Set the working directory inside the container
WORKDIR /app

# Install Python and pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy application files
COPY main.py requirements.txt ./

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Create a directory for cache or temporary files if needed
RUN mkdir -p /app/cache

# Set the default command to run your script
CMD ["python3", "main.py"]