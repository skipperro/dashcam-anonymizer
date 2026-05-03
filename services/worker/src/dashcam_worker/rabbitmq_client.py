"""
RabbitMQ communication module.

Handles all message queue communication including task assignment workflow,
worker registration, heartbeat, and progress reporting as specified.
"""

import pika
import json
import threading
import time
from typing import Callable, Optional
import structlog

from .config import get_config
from .models import (
    TaskMessage, WorkerRegistrationMessage, WorkerHeartbeatMessage,
    ProgressUpdateMessage, CompletionMessage, serialize_message,
    get_current_timestamp
)

logger = structlog.get_logger(__name__)
from .hardware import get_worker_capabilities, get_current_resource_usage


class RabbitMQClient:
    """
    RabbitMQ client for worker communication.
    
    Handles all message queue operations including task assignment,
    worker registration, heartbeat, and progress reporting.
    
    Uses thread-local connections to ensure thread safety with automatic reconnection.
    """
    
    def __init__(self):
        self.config = get_config()
        self.logger = structlog.get_logger("rabbitmq_client")
        self.main_connection: Optional[pika.BlockingConnection] = None
        self.main_channel: Optional[pika.channel.Channel] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.heartbeat_stop_event = threading.Event()
        self.current_status = "ready"
        self.current_task_id: Optional[str] = None
        self._thread_local = threading.local()  # Thread-local storage for connections
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        
    def _get_thread_connection(self) -> tuple[pika.BlockingConnection, pika.channel.Channel]:
        """Get or create a connection for the current thread with retry logic."""
        if not hasattr(self._thread_local, 'connection') or \
           not self._thread_local.connection or \
           self._thread_local.connection.is_closed:
            
            # Use the retry logic from connect() for thread connections
            for attempt in range(self.max_reconnect_attempts):
                try:
                    credentials = pika.PlainCredentials(
                        self.config.rabbitmq.user,
                        self.config.rabbitmq.password
                    )
                    
                    parameters = pika.ConnectionParameters(
                        host=self.config.rabbitmq.host,
                        port=self.config.rabbitmq.port,
                        credentials=credentials,
                        heartbeat=600,  # Longer heartbeat for stability
                        blocked_connection_timeout=10,
                        connection_attempts=3,
                        retry_delay=1,
                        socket_timeout=5
                    )
                    
                    self._thread_local.connection = pika.BlockingConnection(parameters)
                    self._thread_local.channel = self._thread_local.connection.channel()
                    
                    # Declare queues for this thread
                    self._declare_queues_for_channel(self._thread_local.channel)
                    logger.info(f"Thread-local RabbitMQ connection established", thread_id=threading.current_thread().ident)
                    break
                    
                except Exception as e:
                    logger.warning(f"Thread-local RabbitMQ connection attempt {attempt + 1} failed: {e}")
                    if attempt == self.max_reconnect_attempts - 1:
                        logger.error(f"Failed to establish thread-local RabbitMQ connection after {self.max_reconnect_attempts} attempts")
                        raise
                    
                    # Exponential backoff
                    delay = min(2 ** attempt, 60)
                    time.sleep(delay)
            
        return self._thread_local.connection, self._thread_local.channel
        
    def connect(self) -> None:
        """Establish main connection to RabbitMQ with improved stability and retry logic."""
        for attempt in range(self.max_reconnect_attempts):
            try:
                credentials = pika.PlainCredentials(
                    self.config.rabbitmq.user,
                    self.config.rabbitmq.password
                )
                
                parameters = pika.ConnectionParameters(
                    host=self.config.rabbitmq.host,
                    port=self.config.rabbitmq.port,
                    credentials=credentials,
                    heartbeat=600,  # Longer heartbeat for stability
                    blocked_connection_timeout=10,
                    connection_attempts=3,
                    retry_delay=1,
                    socket_timeout=5
                )
                
                self.main_connection = pika.BlockingConnection(parameters)
                self.main_channel = self.main_connection.channel()
                
                # Declare queues
                self._declare_queues_for_channel(self.main_channel)
                
                self.reconnect_attempts = 0  # Reset on successful connection
                
                self.logger.info("Connected to RabbitMQ", 
                               host=self.config.rabbitmq.host,
                               port=self.config.rabbitmq.port,
                               attempt=attempt + 1)
                return
                
            except Exception as e:
                self.reconnect_attempts = attempt + 1
                self.logger.warning(
                    "RabbitMQ connection attempt failed", 
                    error=str(e),
                    attempt=attempt + 1,
                    max_attempts=self.max_reconnect_attempts
                )
                
                if attempt < self.max_reconnect_attempts - 1:
                    import time
                    delay = min(2 ** attempt, 60)  # Exponential backoff, max 60 seconds
                    time.sleep(delay)
                else:
                    self.logger.error("Max RabbitMQ connection attempts reached")
                    raise
    
    def disconnect(self) -> None:
        """Close RabbitMQ connections."""
        try:
            self.stop_heartbeat()
            
            # Close thread-local connections
            if hasattr(self._thread_local, 'channel') and self._thread_local.channel and not self._thread_local.channel.is_closed:
                self._thread_local.channel.close()
            
            if hasattr(self._thread_local, 'connection') and self._thread_local.connection and not self._thread_local.connection.is_closed:
                self._thread_local.connection.close()
            
            # Close main connection
            if self.main_channel and not self.main_channel.is_closed:
                self.main_channel.close()
            
            if self.main_connection and not self.main_connection.is_closed:
                self.main_connection.close()
                
            self.logger.info("Disconnected from RabbitMQ")
            
        except Exception as e:
            self.logger.error("Error disconnecting from RabbitMQ", error=str(e))
    
    def _declare_queues_for_channel(self, channel: pika.channel.Channel) -> None:
        """Declare all required queues for a channel with appropriate persistence settings."""
        # Only task completion queues are persistent
        persistent_queues = [
            "task_completion",
        ]
        
        for queue in persistent_queues:
            channel.queue_declare(queue=queue, durable=True)
        
        # All other queues: transient with TTL (30 minutes)
        transient_queues = [
            f"worker_assignments_{self.config.worker_id}",
            "worker_registration",
            "worker_heartbeat",
            "progress_updates"
        ]
        
        for queue in transient_queues:
            channel.queue_declare(
                queue=queue, 
                durable=True,  # Queue survives server restart
                arguments={
                    'x-message-ttl': 30000  # 30 seconds TTL for messages (in milliseconds)
                }
            )
    
    def register_worker(self) -> None:
        """Register worker capabilities with the backend."""
        capabilities = get_worker_capabilities()
        
        registration_message = WorkerRegistrationMessage(
            worker_id=self.config.worker_id,
            hostname=self.config.hostname,
            capabilities=capabilities,
            status="ready",
            timestamp=get_current_timestamp()
        )
        
        self._publish_message("worker_registration", registration_message)
        self.logger.info("Worker registered", worker_id=self.config.worker_id)
    
    def start_heartbeat(self) -> None:
        """Start heartbeat thread."""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        
        self.heartbeat_stop_event.clear()
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        self.logger.info("Heartbeat started")
    
    def stop_heartbeat(self) -> None:
        """Stop heartbeat thread."""
        if self.heartbeat_thread:
            self.heartbeat_stop_event.set()
            self.heartbeat_thread.join(timeout=5)
            self.logger.info("Heartbeat stopped")
    
    def _heartbeat_loop(self) -> None:
        """Heartbeat loop - sends heartbeat every 30 seconds with automatic reconnection."""
        consecutive_failures = 0
        max_failures = 3
        
        while not self.heartbeat_stop_event.wait(30):  # 30 second interval
            try:
                cpu_percent, memory_percent, gpu_percent = get_current_resource_usage()
                
                from .models import ResourceUsage
                resource_usage = ResourceUsage(
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    gpu_percent=gpu_percent
                )
                
                heartbeat_message = WorkerHeartbeatMessage(
                    worker_id=self.config.worker_id,
                    status=self.current_status,
                    current_task_id=self.current_task_id,
                    resource_usage=resource_usage,
                    timestamp=get_current_timestamp()
                )
                
                # Use thread-local connection for heartbeat
                self._publish_message_with_thread_connection("worker_heartbeat", heartbeat_message)
                
                consecutive_failures = 0  # Reset on successful heartbeat
                
            except Exception as e:
                consecutive_failures += 1
                self.logger.error(
                    "Error sending heartbeat", 
                    error=str(e),
                    consecutive_failures=consecutive_failures
                )
                
                # If too many consecutive failures, try to reconnect main connection
                if consecutive_failures >= max_failures:
                    self.logger.warning(
                        "Too many heartbeat failures, attempting to reconnect main connection"
                    )
                    try:
                        self.connect()  # Try to reconnect main connection
                        self.register_worker()  # Re-register after reconnection
                        consecutive_failures = 0
                    except Exception as reconnect_error:
                        self.logger.error("Failed to reconnect during heartbeat", error=str(reconnect_error))
    
    def listen_for_tasks(self, task_callback: Callable[[TaskMessage], None]) -> None:
        """
        Listen for task assignments.
        
        Args:
            task_callback: Function to call when a task is received
        """
        queue_name = f"worker_assignments_{self.config.worker_id}"
        
        def message_callback(ch, method, properties, body):
            try:
                # Parse task message
                task_data = json.loads(body)
                task_message = TaskMessage.from_dict(task_data)
                
                self.logger.info("Task received", task_id=task_message.task_id)
                
                # Update status
                self.current_status = "busy"
                self.current_task_id = task_message.task_id
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
                # Call task callback
                task_callback(task_message)
                
                # Reset status
                self.current_status = "ready"
                self.current_task_id = None
                
            except Exception as e:
                self.logger.error("Error processing task message", error=str(e))
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Set up consumer on main connection
        self.main_channel.basic_qos(prefetch_count=1)
        self.main_channel.basic_consume(
            queue=queue_name,
            on_message_callback=message_callback
        )
        
        self.logger.info("Listening for tasks", queue=queue_name)
        
        try:
            # Start consuming with proper error handling
            while True:
                try:
                    self.main_connection.process_data_events(time_limit=1)
                except Exception as e:
                    self.logger.error("Error in message processing", error=str(e))
                    if self.main_connection.is_closed:
                        break
                    time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Task listening interrupted")
        finally:
            try:
                if self.main_channel and not self.main_channel.is_closed:
                    self.main_channel.stop_consuming()
            except Exception:
                pass
    
    def send_progress_update(self, task_id: str, video_id: str, progress_percentage: int,
                           current_frame: int, total_frames: int, fps: float,
                           estimated_time_remaining: int) -> None:
        """Send progress update message."""
        progress_message = ProgressUpdateMessage(
            task_id=task_id,
            video_id=video_id,
            progress_percentage=progress_percentage,
            current_frame=current_frame,
            total_frames=total_frames,
            fps=fps,
            estimated_time_remaining=estimated_time_remaining,
            timestamp=get_current_timestamp()
        )
        
        self._publish_message("progress_updates", progress_message)
    
    def send_completion_message(self, task_id: str, video_id: str, status: str,
                              output_file_path: Optional[str], processing_time: float,
                              total_frames: int, objects_detected: int,
                              error_message: Optional[str] = None) -> None:
        """Send task completion message."""
        completion_message = CompletionMessage(
            task_id=task_id,
            video_id=video_id,
            status=status,
            output_file_path=output_file_path,
            processing_time=processing_time,
            total_frames=total_frames,
            objects_detected=objects_detected,
            timestamp=get_current_timestamp(),
            error_message=error_message
        )
        
        # Always publish to task_completion queue — backend reads status field to determine success/failure
        self._publish_message("task_completion", completion_message)
    
    def _publish_message(self, queue: str, message) -> None:
        """Publish message to specified queue using main connection with appropriate persistence."""
        try:
            if not self.main_channel or self.main_channel.is_closed:
                self.logger.warning("Main channel not available for publishing", queue=queue)
                return
                
            message_body = serialize_message(message)
            
            # Only task completion messages are persistent
            is_persistent_message = queue in ["task_completion"]
            delivery_mode = 2 if is_persistent_message else 1  # 2=persistent, 1=transient
            
            self.main_channel.basic_publish(
                exchange='',
                routing_key=queue,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=delivery_mode,
                )
            )
            
        except Exception as e:
            self.logger.error("Error publishing message", queue=queue, error=str(e))
            raise
    
    def _publish_message_with_thread_connection(self, queue: str, message) -> None:
        """Publish message to specified queue using thread-local connection with appropriate persistence."""
        try:
            connection, channel = self._get_thread_connection()
            
            message_body = serialize_message(message)
            
            # Only task completion messages are persistent
            is_persistent_message = queue in ["task_completion"]
            delivery_mode = 2 if is_persistent_message else 1  # 2=persistent, 1=transient
            
            channel.basic_publish(
                exchange='',
                routing_key=queue,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=delivery_mode,
                )
            )
            
        except Exception as e:
            self.logger.error("Error publishing message", queue=queue, error=str(e))
            # Don't re-raise in heartbeat thread to prevent crashes
            if threading.current_thread() == self.heartbeat_thread:
                return
            raise
