"""RabbitMQ client for backend service using BlockingConnection."""

import threading
import json
import time
from typing import Dict, Optional, Callable, Any
from dataclasses import asdict
import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

from .config import get_config
from .logging import get_logger
from .models import (
    WorkerRegistrationMessage, TaskMessage, ProgressUpdateMessage,
    CompletionMessage, WorkerHeartbeatMessage, serialize_message,
    UploadCompletionMessage
)

logger = get_logger(__name__)

# Thread-local storage for connections
_thread_local = threading.local()


class RabbitMQClient:
    """RabbitMQ client with blocking connection and automatic reconnection.

    Thread-safety note
    ------------------
    Pika ``BlockingConnection`` is NOT thread-safe.  We therefore maintain two
    separate connections:

    * **consume connection** – owned by the consuming thread; used only by
      ``start_consuming / _consume_messages``.
    * **publish connection** – protected by ``_publish_lock``; used by every
      call to ``publish_message`` and ``send_task_assignment``, which may come
      from any thread (e.g. WorkerHealthMonitor daemon thread).

    Never share a single connection / channel between threads.
    """

    def __init__(self, message_handlers: Optional[Dict[str, Callable]] = None):
        self.config = get_config()
        # --- consume-side (owned by the consuming thread) ---
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        # --- publish-side (shared across threads, protected by lock) ---
        self._publish_connection: Optional[pika.BlockingConnection] = None
        self._publish_channel: Optional[pika.channel.Channel] = None
        self._publish_lock = threading.Lock()

        self.message_handlers = message_handlers or {}
        self.consuming_thread: Optional[threading.Thread] = None
        self.consume_stop_event = threading.Event()
        self.max_reconnect_attempts = self.config.app.connection_retry_max_attempts
        self.reconnect_delay = self.config.app.connection_retry_base_delay
        
    def _make_parameters(self) -> pika.ConnectionParameters:
        """Build pika ConnectionParameters from config."""
        credentials = pika.PlainCredentials(
            self.config.rabbitmq.username,
            self.config.rabbitmq.password,
        )
        return pika.ConnectionParameters(
            host=self.config.rabbitmq.host,
            port=self.config.rabbitmq.port,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=10,
            connection_attempts=3,
            retry_delay=1,
            socket_timeout=5,
        )

    def connect(self) -> None:
        """Establish consume *and* publish connections to RabbitMQ."""
        for attempt in range(self.max_reconnect_attempts):
            try:
                parameters = self._make_parameters()

                # Consume connection (used only inside _consume_messages)
                self.connection = pika.BlockingConnection(parameters)
                self.channel = self.connection.channel()
                self._setup_infrastructure()

                # Publish connection (used by all publish_message calls)
                self._publish_connection = pika.BlockingConnection(parameters)
                self._publish_channel = self._publish_connection.channel()

                logger.info("Connected to RabbitMQ",
                            host=self.config.rabbitmq.host,
                            port=self.config.rabbitmq.port,
                            attempt=attempt + 1)
                return

            except Exception as e:
                logger.warning(
                    "RabbitMQ connection attempt failed",
                    error=str(e),
                    attempt=attempt + 1,
                    max_attempts=self.max_reconnect_attempts,
                )

                if attempt < self.max_reconnect_attempts - 1:
                    delay = min(2 ** attempt, 60)
                    time.sleep(delay)
                else:
                    logger.error("Max RabbitMQ connection attempts reached")
                    raise
    
    def disconnect(self) -> None:
        """Disconnect both consume and publish connections from RabbitMQ."""
        try:
            self.stop_consuming()

            if self.channel and not self.channel.is_closed:
                self.channel.close()
            if self.connection and not self.connection.is_closed:
                self.connection.close()

            with self._publish_lock:
                if self._publish_channel and not self._publish_channel.is_closed:
                    self._publish_channel.close()
                if self._publish_connection and not self._publish_connection.is_closed:
                    self._publish_connection.close()

            logger.info("Disconnected from RabbitMQ")
        except Exception as e:
            logger.warning("Error during RabbitMQ disconnect", error=str(e))
    
    def _setup_infrastructure(self) -> None:
        """Setup RabbitMQ exchanges and queues with appropriate persistence settings."""
        if not self.channel:
            raise RuntimeError("No channel available")
        
        # Declare exchanges
        self.channel.exchange_declare(exchange='dashcam_backend', exchange_type='topic', durable=True)
        self.channel.exchange_declare(exchange='dashcam_worker', exchange_type='topic', durable=True)
        
        # Only task completion queue is persistent
        persistent_queues = [
            'task_completion',
        ]
        
        for queue in persistent_queues:
            self.channel.queue_declare(queue=queue, durable=True)
        
        # All other queues: transient with TTL (30 minutes)
        transient_queues = [
            'worker_registration',
            'worker_heartbeat',
            'task_assignment',
            'progress_updates'
        ]
        
        for queue in transient_queues:
            self.channel.queue_declare(
                queue=queue, 
                durable=True,  # Queue survives server restart
                arguments={
                    'x-message-ttl': 30000  # 30 seconds TTL for messages (in milliseconds)
                }
            )
        
        # Bind queues to exchanges  
        self.channel.queue_bind(exchange='dashcam_backend', queue='worker_registration', routing_key='worker.registration')
        self.channel.queue_bind(exchange='dashcam_backend', queue='worker_heartbeat', routing_key='worker.heartbeat')
        self.channel.queue_bind(exchange='dashcam_backend', queue='progress_updates', routing_key='task.progress')
        self.channel.queue_bind(exchange='dashcam_backend', queue='task_completion', routing_key='task.completion')
        
        logger.info("RabbitMQ infrastructure setup complete")
    
    def publish_message(self, queue: str, message: Dict[str, Any], routing_key: str = None) -> None:
        """Publish a message using the dedicated publish connection (thread-safe)."""
        with self._publish_lock:
            if not self._publish_channel:
                logger.error("Cannot publish - no publish channel available")
                return

            # Reconnect publish side if connection dropped
            if (self._publish_connection is None or self._publish_connection.is_closed
                    or self._publish_channel is None or self._publish_channel.is_closed):
                try:
                    self._publish_connection = pika.BlockingConnection(self._make_parameters())
                    self._publish_channel = self._publish_connection.channel()
                    logger.info("Publish connection reconnected")
                except Exception as e:
                    logger.error("Failed to reconnect publish connection", error=str(e))
                    return

            try:
                is_persistent_message = queue in ["task_completion", "upload_completion"]
                delivery_mode = 2 if is_persistent_message else 1

                if routing_key:
                    exchange = 'dashcam_worker' if queue.startswith('task_') else 'dashcam_backend'
                    self._publish_channel.basic_publish(
                        exchange=exchange,
                        routing_key=routing_key,
                        body=json.dumps(message, default=str),
                        properties=pika.BasicProperties(
                            delivery_mode=delivery_mode,
                            content_type='application/json',
                        ),
                    )
                else:
                    self._publish_channel.basic_publish(
                        exchange='',
                        routing_key=queue,
                        body=json.dumps(message, default=str),
                        properties=pika.BasicProperties(
                            delivery_mode=delivery_mode,
                            content_type='application/json',
                        ),
                    )
                logger.debug("Message published", queue=queue, routing_key=routing_key,
                             persistent=is_persistent_message)
            except Exception as e:
                logger.error("Failed to publish message", error=str(e), queue=queue)
    
    def start_consuming(self) -> None:
        """Start consuming messages in a separate thread."""
        if self.consuming_thread and self.consuming_thread.is_alive():
            logger.warning("Already consuming messages")
            return
        
        self.consume_stop_event.clear()
        self.consuming_thread = threading.Thread(target=self._consume_messages, daemon=True)
        self.consuming_thread.start()
        logger.info("Started consuming RabbitMQ messages")
    
    def stop_consuming(self) -> None:
        """Stop consuming messages."""
        if self.consuming_thread:
            self.consume_stop_event.set()
            
            if self.channel:
                try:
                    self.channel.stop_consuming()
                except:
                    pass
                    
            if self.consuming_thread.is_alive():
                self.consuming_thread.join(timeout=5)
            
            logger.info("Stopped consuming RabbitMQ messages")
    
    def _consume_messages(self) -> None:
        """Message consumption loop."""
        try:
            if not self.channel:
                logger.error("No channel available for consuming")
                return
            
            # Setup message handlers
            for queue, handler in self.message_handlers.items():
                self.channel.basic_consume(
                    queue=queue,
                    on_message_callback=self._create_message_callback(handler),
                    auto_ack=False
                )
            
            # Start consuming
            self.channel.start_consuming()
            
        except Exception as e:
            if not self.consume_stop_event.is_set():
                logger.error("Error in message consumption", error=str(e))
    
    def _create_message_callback(self, handler: Callable) -> Callable:
        """Create a message callback wrapper."""
        def callback(channel, method, properties, body):
            try:
                message = json.loads(body.decode('utf-8'))
                handler(message)
                channel.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error("Error processing message", error=str(e))
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        return callback
    
    def send_task_assignment(self, worker_id: str, task: TaskMessage) -> None:
        """Send a task assignment directly to a specific worker's personal queue (thread-safe)."""
        queue_name = f"worker_assignments_{worker_id}"

        # Declare the queue on the publish channel (thread-safe via publish_lock)
        with self._publish_lock:
            if self._publish_channel:
                try:
                    self._publish_channel.queue_declare(
                        queue=queue_name,
                        durable=True,
                        arguments={'x-message-ttl': 30000},
                    )
                except Exception as e:
                    logger.warning("Could not declare worker assignment queue",
                                   queue=queue_name, error=str(e))

        message = asdict(task)
        self.publish_message(queue_name, message)
    
    def register_message_handler(self, queue: str, handler: Callable) -> None:
        """Register a message handler for a specific queue."""
        self.message_handlers[queue] = handler
        logger.info("Registered message handler", queue=queue)
    
    def is_connected(self) -> bool:
        """Check if both consume and publish connections are open."""
        consume_ok = (self.connection is not None
                      and not self.connection.is_closed
                      and self.channel is not None
                      and not self.channel.is_closed)
        publish_ok = (self._publish_connection is not None
                      and not self._publish_connection.is_closed
                      and self._publish_channel is not None
                      and not self._publish_channel.is_closed)
        return consume_ok and publish_ok


def get_rabbitmq_client() -> RabbitMQClient:
    """Get thread-local RabbitMQ client instance."""
    if not hasattr(_thread_local, 'rabbitmq_client'):
        _thread_local.rabbitmq_client = RabbitMQClient()
    return _thread_local.rabbitmq_client
