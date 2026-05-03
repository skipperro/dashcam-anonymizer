#!/bin/bash

# Start Test Environment Script
# Builds images, starts docker-compose, waits for all services to be healthy.

set -e  # Exit on any error

echo "🚀 Starting Dashcam Anonymizer Test Environment"
echo "================================================"

# Check for NVIDIA Container Toolkit (required for GPU support)
if ! command -v nvidia-smi &>/dev/null; then
  echo "⚠️  nvidia-smi not found — worker will run on CPU only."
else
  echo "✅ NVIDIA GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
  if ! sudo docker info 2>/dev/null | grep -q "nvidia"; then
    echo "⚠️  NVIDIA Container Toolkit may not be configured for Docker."
    echo "   Run: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
  fi
fi

# Step 1: Build all images
echo ""
echo "📦 Building Docker images..."
sudo docker-compose -f docker-compose.test.yml build

# Step 2: Start all services
echo ""
echo "🔄 Starting all services..."
sudo docker-compose -f docker-compose.test.yml up -d

# Step 3: Wait for services to become healthy (polls every 3s, 120s timeout each)
echo ""
echo "⏳ Waiting for services to become healthy..."

wait_for_healthy() {
  local service=$1
  local max_wait=${2:-120}
  local elapsed=0

  echo -n "   $service "
  while [ $elapsed -lt $max_wait ]; do
    status=$(sudo docker-compose -f docker-compose.test.yml ps -q "$service" 2>/dev/null \
      | xargs -r sudo docker inspect --format='{{.State.Health.Status}}' 2>/dev/null \
      || echo "unknown")
    if [ "$status" = "healthy" ]; then
      echo "✅"
      return 0
    fi
    echo -n "."
    sleep 3
    elapsed=$((elapsed + 3))
  done
  echo " ❌ (timed out after ${max_wait}s — check: sudo docker-compose -f docker-compose.test.yml logs $service)"
  return 1
}

wait_for_healthy minio    120
wait_for_healthy mongodb  120
wait_for_healthy rabbitmq 120
wait_for_healthy backend  120
wait_for_healthy worker   120

# Step 4: Show service status
echo ""
echo "📊 Service Status:"
sudo docker-compose -f docker-compose.test.yml ps

echo ""
echo "✅ Test environment is ready!"
echo ""
echo "🌐 Available services:"
echo "   - Frontend UI:           http://localhost:3000"
echo "   - Backend API:           http://localhost:8000"
echo "   - RabbitMQ Management:   http://localhost:15672  (user: dashcam, pass: dashcam123)"
echo "   - MinIO Console:         http://localhost:9001   (user: minioadmin, pass: minioadmin123)"
echo "   - MongoDB:               localhost:27017"
echo ""
echo "📋 Useful commands:"
echo "   - All logs:     sudo docker-compose -f docker-compose.test.yml logs -f"
echo "   - Backend logs: sudo docker-compose -f docker-compose.test.yml logs -f backend"
echo "   - Worker logs:  sudo docker-compose -f docker-compose.test.yml logs -f worker"
echo "   - Stop:         ./stop-test-env.sh"
