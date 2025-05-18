# Use official Python runtime
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY main.py .

# Create /mnt/data directory and make it writable
RUN mkdir -p /mnt/data && chmod 777 /mnt/data

# Expose the port Flask runs on
EXPOSE 8000

# Run the Flask app
CMD ["python", "main.py"]