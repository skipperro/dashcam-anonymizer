#!/bin/bash
# MinIO entrypoint script with secure initialization

# Start MinIO server in background
minio server /data --console-address ":9001" &
MINIO_PID=$!

# Wait for MinIO to be ready and run secure initialization
/usr/local/bin/init-buckets.sh

# Wait for MinIO process
wait $MINIO_PID
