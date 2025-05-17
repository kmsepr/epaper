FROM mcr.microsoft.com/playwright/python:v1.48.0-focal

# Set working directory
WORKDIR /app

# Copy files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Create cache dir
RUN mkdir -p /app/cache

EXPOSE 8000

CMD ["python", "main.py"]