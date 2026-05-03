#!/bin/bash
# Deploy GPU workers with auto-detection
SERVER_NAME=${1:-"worker-server"}

echo "🔍 Detecting GPUs..."
GPU_COUNT=$(nvidia-smi --list-gpus 2>/dev/null | wc -l)

if [ $GPU_COUNT -eq 0 ]; then
    echo "❌ No GPUs detected. Deploying CPU-only worker..."
    docker run -d \
        --name "${SERVER_NAME}-cpu" \
        -m 8g \
        -e WORKER_ID="${SERVER_NAME}-cpu" \
        dashcam-worker:latest
else
    echo "✅ Found $GPU_COUNT GPUs. Deploying $GPU_COUNT workers..."
    
    for i in $(seq 0 $((GPU_COUNT-1))); do
        echo "🚀 Starting worker ${SERVER_NAME}-gpu${i} on GPU $i"
        docker run -d \
            --name "${SERVER_NAME}-gpu${i}" \
            --gpus "device=${i}" \
            -m 8g \
            -e WORKER_ID="${SERVER_NAME}-gpu${i}" \
            -e CUDA_VISIBLE_DEVICES="${i}" \
            dashcam-worker:latest
    done
fi

echo "✅ Worker deployment complete!"
