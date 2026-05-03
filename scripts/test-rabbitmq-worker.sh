#!/bin/bash
# Test RabbitMQ + Worker Communication

echo "🧪 Testing RabbitMQ + Worker Communication"
echo "=========================================="

# Build and start services
echo "🚀 Starting RabbitMQ and Worker..."
sudo docker-compose -f docker-compose.test.yml up --build -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 30

# Check service status
echo "📊 Service Status:"
sudo docker-compose -f docker-compose.test.yml ps

# Check RabbitMQ management UI
echo "🔍 RabbitMQ Management UI: http://localhost:15672"
echo "   Username: dashcam"
echo "   Password: dashcam123"

# Check worker logs
echo "📋 Worker Logs (last 20 lines):"
sudo docker-compose -f docker-compose.test.yml logs --tail=20 worker

# Check RabbitMQ logs
echo "📋 RabbitMQ Logs (last 10 lines):"
sudo docker-compose -f docker-compose.test.yml logs --tail=10 rabbitmq

echo ""
echo "✅ Test environment is running!"
echo "   - RabbitMQ Management: http://localhost:15672"
echo "   - Check worker connection success in logs above"
echo ""
echo "To stop: sudo docker-compose -f docker-compose.test.yml down"
