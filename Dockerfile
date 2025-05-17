# Use latest Playwright image with Python and browser binaries
FROM mcr.microsoft.com/playwright:v1.48.0-focal

# Set working directory inside the container
WORKDIR /app

# Copy app files
COPY main.py requirements.txt ./

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Create cache directory
RUN mkdir -p /app/cache

# Expose the web server port
EXPOSE 8000

# Run the application
CMD ["python3", "main.py"]