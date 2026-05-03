# RabbitMQ with required plugins for Dashcam Worker
FROM rabbitmq:3.12-management

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy custom configuration
COPY config/rabbitmq.conf /etc/rabbitmq/rabbitmq.conf
COPY config/definitions.json /etc/rabbitmq/definitions.json

# Enable required plugins including tracing
RUN rabbitmq-plugins enable rabbitmq_management rabbitmq_web_stomp rabbitmq_stomp rabbitmq_tracing

# Create custom entrypoint to ensure proper initialization
COPY config/init-rabbitmq.sh /usr/local/bin/init-rabbitmq.sh
RUN chmod +x /usr/local/bin/init-rabbitmq.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD rabbitmq-diagnostics -q ping

# Expose ports
# 5672: AMQP port
# 15672: Management UI
# 15674: Web-STOMP (for frontend WebSocket)
EXPOSE 5672 15672 15674

CMD ["/usr/local/bin/init-rabbitmq.sh"]
