# Use a lightweight official Python base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Set work directory inside the container
WORKDIR /app

# Install system dependencies needed for compiling certain libraries (like Cython, regex, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements file and install dependencies
# We install PyTorch CPU version here by default. This makes the Docker image significantly 
# smaller (~1 GB vs ~4 GB) and avoids CUDA driver overheads if running on a CPU-only server.
# If CUDA GPU is available on the target host, replace '--index-url https://download.pytorch.org/whl/cpu' with the standard PyTorch installation.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r backend/requirements.txt

# Copy the entire project code into the container
COPY . .

# Expose port 5000 for Flask
EXPOSE 5000

# Set environment variable for backend routing (optional, handled by python-dotenv or Docker runtime)
ENV FLASK_APP=backend/app.py

# Command to run the Flask application
CMD ["python", "backend/app.py"]
