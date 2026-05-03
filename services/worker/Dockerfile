# Dashcam Worker Dockerfile
FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
# Install PyTorch with CUDA 12.1 support first.
# The default PyTorch wheels on PyPI are CPU-only; we need the CUDA build.
# NVIDIA Container Toolkit mounts the CUDA driver libs at runtime when --gpus is passed.
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cu121
# Install remaining requirements (torch/torchvision already satisfied above)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY models/ ./models/
COPY config/ ./config/

# Create model cache directory
RUN mkdir -p /models

# Set Python path
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Create non-root user
RUN useradd -m -u 1000 worker
RUN chown -R worker:worker /app /models
USER worker

# Expose health check port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command
CMD ["python", "-m", "dashcam_worker.main"]
