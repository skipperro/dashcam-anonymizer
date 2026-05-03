#!/bin/bash
set -e

# Start RabbitMQ in background
rabbitmq-server &
RABBITMQ_PID=$!

# Wait for RabbitMQ to be ready
echo "Waiting for RabbitMQ to start..."
while ! rabbitmq-diagnostics -q ping 2>/dev/null; do
    sleep 2
done

echo "RabbitMQ node is up, waiting for application to be ready..."
# Wait for RabbitMQ application to be fully started
while ! rabbitmqctl status >/dev/null 2>&1; do
    echo "Waiting for RabbitMQ application to start..."
    sleep 2
done

echo "RabbitMQ is ready!"

# Create user and set permissions if environment variables are provided
if [ -n "$RABBITMQ_DEFAULT_USER" ] && [ -n "$RABBITMQ_DEFAULT_PASS" ]; then
    echo "Creating user $RABBITMQ_DEFAULT_USER..."
    
    # Create user with retry logic
    retry_count=0
    max_retries=5
    while [ $retry_count -lt $max_retries ]; do
        if rabbitmqctl add_user "$RABBITMQ_DEFAULT_USER" "$RABBITMQ_DEFAULT_PASS" 2>/dev/null; then
            echo "User $RABBITMQ_DEFAULT_USER created successfully"
            break
        elif rabbitmqctl list_users | grep -q "^$RABBITMQ_DEFAULT_USER"; then
            echo "User $RABBITMQ_DEFAULT_USER already exists"
            break
        else
            retry_count=$((retry_count + 1))
            echo "Failed to create user, attempt $retry_count/$max_retries, retrying in 2 seconds..."
            sleep 2
        fi
    done
    
    # Set user as administrator with retry
    retry_count=0
    while [ $retry_count -lt $max_retries ]; do
        if rabbitmqctl set_user_tags "$RABBITMQ_DEFAULT_USER" administrator; then
            echo "User tags set successfully"
            break
        else
            retry_count=$((retry_count + 1))
            echo "Failed to set user tags, attempt $retry_count/$max_retries, retrying in 2 seconds..."
            sleep 2
        fi
    done
    
    # Grant permissions on default vhost with retry
    retry_count=0
    while [ $retry_count -lt $max_retries ]; do
        if rabbitmqctl set_permissions -p / "$RABBITMQ_DEFAULT_USER" ".*" ".*" ".*"; then
            echo "User permissions set successfully"
            break
        else
            retry_count=$((retry_count + 1))
            echo "Failed to set permissions, attempt $retry_count/$max_retries, retrying in 2 seconds..."
            sleep 2
        fi
    done
    
    echo "User $RABBITMQ_DEFAULT_USER configured with admin permissions"
fi

# Enable management plugin first (required for tracing)
echo "Enabling RabbitMQ management plugin..."
rabbitmq-plugins enable rabbitmq_management

# Enable tracing plugin for message audit trail
echo "Enabling RabbitMQ tracing plugin..."
rabbitmq-plugins enable rabbitmq_tracing

# Wait for management plugin to be ready (needed for tracing)
echo "Waiting for management plugin to be ready..."
retry_count=0
max_retries=30
while [ $retry_count -lt $max_retries ]; do
    if curl -f -s -u "$RABBITMQ_DEFAULT_USER:$RABBITMQ_DEFAULT_PASS" http://localhost:15672/api/overview >/dev/null 2>&1; then
        echo "Management plugin is ready"
        break
    else
        retry_count=$((retry_count + 1))
        echo "Waiting for management plugin, attempt $retry_count/$max_retries..."
        sleep 2
    fi
done

if [ $retry_count -eq $max_retries ]; then
    echo "Warning: Management plugin may not be fully ready, continuing anyway..."
fi

# Import definitions (queues, exchanges, bindings) with retry
if [ -f /etc/rabbitmq/definitions.json ]; then
    echo "Importing RabbitMQ definitions..."
    retry_count=0
    max_retries=5
    while [ $retry_count -lt $max_retries ]; do
        if rabbitmqctl import_definitions /etc/rabbitmq/definitions.json; then
            echo "Definitions imported successfully"
            break
        else
            retry_count=$((retry_count + 1))
            echo "Failed to import definitions, attempt $retry_count/$max_retries, retrying in 3 seconds..."
            sleep 3
        fi
    done
    
    if [ $retry_count -eq $max_retries ]; then
        echo "Warning: Failed to import definitions after $max_retries attempts"
    fi
fi

# Enable firehose tracing (after management plugin is ready)
echo "Enabling firehose tracing..."
retry_count=0
max_retries=5
while [ $retry_count -lt $max_retries ]; do
    if rabbitmqctl trace_on; then
        echo "Tracing enabled successfully"
        break
    else
        retry_count=$((retry_count + 1))
        echo "Failed to enable tracing, attempt $retry_count/$max_retries, retrying in 2 seconds..."
        sleep 2
    fi
done

if [ $retry_count -eq $max_retries ]; then
    echo "Warning: Failed to enable tracing after $max_retries attempts"
fi

echo "RabbitMQ initialization complete with tracing enabled"

# Keep the script running and wait for RabbitMQ
wait $RABBITMQ_PID
