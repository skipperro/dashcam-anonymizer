#!/bin/bash

# Stop Test Environment Script
# This script stops and cleans up the docker-compose test environment

set -e  # Exit on any error

echo "🛑 Stopping Dashcam Anonymizer Test Environment"
echo "==============================================="

# Step 1: Stop all services
echo "⏹️  Stopping all services..."
sudo docker-compose -f docker-compose.test.yml down

# Step 2: Show final status
echo "📊 Final status:"
sudo docker-compose -f docker-compose.test.yml ps

echo ""
echo "✅ Test environment stopped successfully!"
echo ""
echo "🧹 To clean up completely (remove volumes and images):"
echo "   docker-compose -f docker-compose.test.yml down -v --rmi all"
echo ""
echo "🔄 To restart the environment:"
echo "   ./start-test-env.sh"
