#!/bin/bash
# Deploy core backend infrastructure
echo "🏗️ Deploying backend infrastructure..."
docker-compose -f docker-compose.core.yml up -d
