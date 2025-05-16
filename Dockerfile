FROM python:3.10-slim

# Install system dependencies for PyMuPDF (fitz)
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libxext6 \
    libsm6 \
    libxrender1 \
    gcc \
    && apt-get clean

# Set work directory
WORKDIR /app

# Copy app files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose FastAPI default port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
