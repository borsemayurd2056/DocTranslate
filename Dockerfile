# ==========================================
# Stage 1: Build Frontend with Node.js
# ==========================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Install frontend dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy frontend source and build to dist
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Python Runtime
# ==========================================
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PORT=7860 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PATH=/home/user/.local/bin:$PATH

# Install system dependencies needed for compiling certain libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (uid 1000) for Hugging Face Spaces
RUN useradd -m -u 1000 user

# Set work directory
WORKDIR /app

# Upgrade pip, install CPU-only torch, then install remaining dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app

# Copy built frontend assets from node stage
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Ensure writable cache and workspace directories with proper ownership for non-root user
RUN mkdir -p /home/user/.cache/huggingface /app/backend/uploads /app/backend/outputs && \
    chown -R 1000:1000 /home/user /app

# Switch to non-root user
USER 1000

# Expose Hugging Face Spaces default port
EXPOSE 7860

# Start Flask application with Gunicorn (1 worker, 2 threads, 600s timeout)
CMD ["gunicorn", "-w", "1", "--threads", "2", "-t", "600", "-b", "0.0.0.0:7860", "backend.app:app"]
