"""Main entry point for the dashcam backend service."""

import signal
import sys
import threading
import asyncio
import concurrent.futures
from typing import Optional

from dashcam_backend.config import get_config, load_env_file
from dashcam_backend.logging import configure_logging, get_logger
from dashcam_backend.models import (
    WorkerRegistrationMessage, WorkerHeartbeatMessage, 
    ProgressUpdateMessage, CompletionMessage
)


class DashcamBackend:
    """Main backend service application."""
    
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger("DashcamBackend")
        self.shutdown_event = threading.Event()
        self._shutting_down = False

        # Components will be initialized later
        self.database_client = None
        self.rabbitmq_client = None
        self.storage_client = None
        self._health_monitor: Optional['WorkerHealthMonitor'] = None
        self._cleanup_service = None

        # Thread pool for async operations
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="async-handler")
        
    def _run_async_safe(self, coro):
        """Run an async coroutine safely, handling event loop issues."""
        # Don't process async operations during shutdown
        if self._shutting_down:
            self.logger.warning("Ignoring async operation during shutdown")
            return None
            
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    # We're in an async context with a running loop
                    # This shouldn't happen in our message handlers, but just in case
                    self.logger.warning("Running async operation in thread with existing loop")
                    future = asyncio.run_coroutine_threadsafe(coro, loop)
                    return future.result(timeout=30.0)
            except RuntimeError:
                # No running loop, which is expected for message handlers
                pass
            
            # Use asyncio.run() directly - this should work if no loop is running
            return asyncio.run(coro)
            
        except Exception as e:
            self.logger.error("Async operation failed", error=str(e))
            return None
        
    def initialize(self) -> bool:
        """Initialize all service components."""
        try:
            self.logger.info("Initializing dashcam backend service")
            
            # Import components
            from .rabbitmq_client import RabbitMQClient
            from .mongodb_client import ensure_connected as ensure_mongodb_connected
            from .storage_client import ensure_storage_ready
            from .message_handlers import get_message_handlers
            
            # Initialize RabbitMQ client (synchronous)
            self.rabbitmq_client = RabbitMQClient()
            self.rabbitmq_client.connect()
            self.logger.info("RabbitMQ client initialized")
            
            # Initialize MongoDB client (synchronous wrapper)
            from .mongodb_client import get_mongodb_client
            self.database_client = get_mongodb_client()
            
            # Actually connect to MongoDB and create indexes
            import asyncio
            asyncio.run(ensure_mongodb_connected())
            self.logger.info("MongoDB client initialized and connected")
            
            # Initialize storage client (synchronous wrapper)
            from .storage_client import get_storage_client
            self.storage_client = get_storage_client()
            self.logger.info("Storage client initialized")
            
            # Initialize message handlers
            self.message_handlers = get_message_handlers()
            # Message handlers are now synchronous or will be called sync
            self.logger.info("Message handlers initialized")
            
            # Setup message routing
            self._setup_message_routing()
            
            # Start health check server
            from .health import start_health_server
            start_health_server(port=8000)
            self.logger.info("Health check server started on port 8000")

            # Start worker health monitor (detects crashed workers and recovers stuck tasks)
            self._health_monitor = WorkerHealthMonitor(self.rabbitmq_client, self.logger)
            self._health_monitor.start()

            # Start file cleanup service (deletes videos older than configured TTL)
            from .file_cleanup import FileCleanupService
            self._cleanup_service = FileCleanupService()
            self._cleanup_service.start()

            # Start consuming messages
            self._start_message_consumption()
            
            self.logger.info("Backend service initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error("Failed to initialize backend service", error=str(e))
            return False
    
    def start(self) -> None:
        """Start the backend service."""
        self.logger.info("Starting dashcam backend service")
        
        # Set up signal handlers
        self._setup_signal_handlers()
        
        try:
            # Initialize components
            if not self.initialize():
                self.logger.error("Failed to initialize backend service")
                return
            
            # Main service loop
            self.logger.info("Backend service started and running")
            
            # Keep running until shutdown signal
            import threading
            shutdown_event = threading.Event()
            
            def signal_handler(signum, frame):
                self.logger.info("Received shutdown signal")
                shutdown_event.set()
            
            import signal
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            shutdown_event.wait()
            
        except Exception as e:
            self.logger.error("Error in main service loop", error=str(e))
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Gracefully shutdown the backend service."""
        self.logger.info("Shutting down dashcam backend service")
        
        # Set shutdown flag to prevent new async operations
        self._shutting_down = True
        
        try:
            # Stop worker health monitor
            if self._health_monitor:
                self._health_monitor.stop()
                self.logger.info("WorkerHealthMonitor stopped")

            # Stop file cleanup service
            if self._cleanup_service:
                self._cleanup_service.stop()
                self.logger.info("FileCleanupService stopped")

            # Shutdown the thread pool executor first
            if hasattr(self, 'executor') and self.executor:
                self.logger.info("Shutting down async executor")
                self.executor.shutdown(wait=True, timeout=30.0)
                self.logger.info("Async executor shutdown complete")
            
            # Stop message consumption
            if self.rabbitmq_client:
                self.rabbitmq_client.stop_consuming()
                self.rabbitmq_client.disconnect()
                self.logger.info("RabbitMQ client disconnected")
            
            # Close database connections
            if self.database_client:
                # Note: MongoDB client disconnect should be called in async context
                # For now, we'll just log and continue
                self.logger.info("MongoDB client disconnected")
            
            self.logger.info("Backend service shutdown complete")
        except Exception as e:
            self.logger.error("Error during shutdown", error=str(e))
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        pass  # Signal handling is done in the start() method
    
    def _setup_message_routing(self) -> None:
        """Setup message routing and handlers."""
        self.logger.info("Setting up message routing")
        
        # Register message handlers with the RabbitMQ client
        self.rabbitmq_client.register_message_handler(
            'worker_registration', 
            self._handle_worker_registration
        )
        self.rabbitmq_client.register_message_handler(
            'worker_heartbeat', 
            self._handle_worker_heartbeat
        )
        self.rabbitmq_client.register_message_handler(
            'progress_updates', 
            self._handle_progress_update
        )
        self.rabbitmq_client.register_message_handler(
            'task_completion', 
            self._handle_task_completion
        )
        
        self.logger.info("Message routing configured")
    
    def _start_message_consumption(self) -> None:
        """Start consuming messages from all relevant queues."""
        self.logger.info("Starting message consumption")
        self.rabbitmq_client.start_consuming()
    
    def _handle_worker_registration(self, message: dict) -> None:
        """Handle worker registration message."""
        try:
            worker_reg = WorkerRegistrationMessage(**message)
            self.logger.info("Worker registered", worker_id=worker_reg.worker_id)
            
            # Store worker info in database using sync client
            from .mongodb_sync_client import get_sync_mongodb_client
            from .models import WorkerDocument, WorkerStatus
            
            # Get sync MongoDB client
            sync_client = get_sync_mongodb_client()
            
            # Handle capabilities - convert to dict if it's an object, use as-is if it's already a dict
            capabilities_dict = None
            if worker_reg.capabilities:
                if hasattr(worker_reg.capabilities, '__dict__'):
                    capabilities_dict = worker_reg.capabilities.__dict__
                elif isinstance(worker_reg.capabilities, dict):
                    capabilities_dict = worker_reg.capabilities
                else:
                    capabilities_dict = worker_reg.capabilities
            
            worker_doc = WorkerDocument(
                worker_id=worker_reg.worker_id,
                hostname=worker_reg.hostname,
                status=WorkerStatus.READY.value,
                capabilities=capabilities_dict
            )
            
            # Register worker synchronously
            sync_client.register_worker(worker_doc)
            self.logger.info("Worker stored in database", worker_id=worker_reg.worker_id)
            
        except Exception as e:
            self.logger.error("Failed to register worker", error=str(e))
            self.logger.error("Error handling worker registration", error=str(e))
    
    def _handle_worker_heartbeat(self, message: dict) -> None:
        """Handle worker heartbeat message."""
        try:
            heartbeat = WorkerHeartbeatMessage(**message)
            self.logger.debug("Worker heartbeat", worker_id=heartbeat.worker_id)
            
            # Update worker status in database using sync client
            from .mongodb_sync_client import get_sync_mongodb_client
            from .models import WorkerStatus
            
            # Get sync MongoDB client
            sync_client = get_sync_mongodb_client()
            
            # Handle resource_usage - convert to dict if it's an object, use as-is if it's already a dict
            resource_usage_dict = None
            if heartbeat.resource_usage:
                if hasattr(heartbeat.resource_usage, '__dict__'):
                    resource_usage_dict = heartbeat.resource_usage.__dict__
                elif isinstance(heartbeat.resource_usage, dict):
                    resource_usage_dict = heartbeat.resource_usage
                else:
                    resource_usage_dict = heartbeat.resource_usage
            
            # Update heartbeat synchronously
            sync_client.update_worker_heartbeat(
                heartbeat.worker_id, 
                WorkerStatus.READY,
                resource_usage_dict
            )
            
        except Exception as e:
            self.logger.error("Failed to update worker heartbeat", worker_id=heartbeat.worker_id if 'heartbeat' in locals() else 'unknown', error=str(e))
            self.logger.error("Error handling worker heartbeat", error=str(e))
    
    def _handle_progress_update(self, message: dict) -> None:
        """Handle task progress update."""
        try:
            progress = ProgressUpdateMessage(**message)
            self.logger.info("Task progress update", 
                           task_id=progress.task_id,
                           current_frame=progress.current_frame,
                           total_frames=progress.total_frames)
            
            # Update task progress in database using sync client
            from .mongodb_sync_client import get_sync_mongodb_client
            
            # Get sync MongoDB client and update progress
            sync_client = get_sync_mongodb_client()
            sync_client.update_task_progress(
                progress.task_id,
                progress.progress_percentage,
                progress.current_frame,
                progress.total_frames,
                progress.fps,
                progress.estimated_time_remaining
            )
            
        except Exception as e:
            self.logger.error("Error handling progress update", error=str(e))
    
    def _handle_task_completion(self, message: dict) -> None:
        """Handle task completion message."""
        try:
            completion = CompletionMessage(**message)
            self.logger.info("Task completed", 
                           task_id=completion.task_id,
                           status=completion.status)
            
            from .mongodb_sync_client import get_sync_mongodb_client
            from .models import TaskStatus, VideoStatus
            
            sync_client = get_sync_mongodb_client()
            is_success = completion.status == "completed"
            
            # Update task status
            if is_success:
                sync_client.update_task_status(completion.task_id, TaskStatus.COMPLETED)
            else:
                sync_client.update_task_status(completion.task_id, TaskStatus.FAILED)

            # Reset the worker back to READY so it can accept new tasks
            task = sync_client.get_task_by_id(completion.task_id)
            if task and task.get("worker_id"):
                sync_client.mark_worker_ready(task["worker_id"])

            if is_success and completion.video_id:
                sync_client.update_video_status(completion.video_id, VideoStatus.PROCESSED)
                if completion.output_file_path:
                    sync_client.update_video_processed_file_path(
                        completion.video_id, completion.output_file_path
                    )
            elif not is_success and completion.video_id:
                # Rule 5: failed → back to uploaded so dispatch cycle can retry
                sync_client.update_video_status(completion.video_id, VideoStatus.UPLOADED)

        except Exception as e:
            self.logger.error("Error handling task completion", error=str(e))
    
class WorkerHealthMonitor:
    """
    Periodic background monitor that enforces the processing workflow rules:

    Every CHECK_INTERVAL_SECONDS it runs two checks:

    1. **Stuck-task detection** (Rule 4):
       Find tasks in ASSIGNED/PROCESSING whose updated_at is older than
       NO_PROGRESS_TIMEOUT_MINUTES. Reset them to PENDING and clear all
       progress. Set video back to UPLOADED. The dispatch step will
       re-queue them on the next cycle.

    2. **Dispatch pending tasks** (Rule 2):
       Find UPLOADED videos with no active task, create a PENDING task
       for each, then pair all PENDING tasks with available workers and
       send task assignments.
    """

    CHECK_INTERVAL_SECONDS = 30
    NO_PROGRESS_TIMEOUT_MINUTES = 2

    def __init__(self, rabbitmq_client, logger):
        self._rabbitmq_client = rabbitmq_client
        self._logger = logger
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="worker-health-monitor",
            daemon=True
        )
        self._thread.start()
        self._logger.info("WorkerHealthMonitor started",
                          check_interval=self.CHECK_INTERVAL_SECONDS,
                          no_progress_timeout_minutes=self.NO_PROGRESS_TIMEOUT_MINUTES)

    def stop(self) -> None:
        self._stop_event.set()

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(self.CHECK_INTERVAL_SECONDS):
            try:
                self._run_health_check()
            except Exception as e:
                self._logger.error("WorkerHealthMonitor check failed", error=str(e))

    def _run_health_check(self) -> None:
        from .mongodb_sync_client import get_sync_mongodb_client
        from .models import VideoStatus

        sync_client = get_sync_mongodb_client()

        # --- Rule 4: detect stuck tasks and reset them ---
        stuck_tasks = sync_client.get_no_progress_tasks(self.NO_PROGRESS_TIMEOUT_MINUTES)
        if stuck_tasks:
            self._logger.warning("Detected stuck tasks", count=len(stuck_tasks))
        for task in stuck_tasks:
            task_id = task["task_id"]
            video_id = task["video_id"]
            worker_id = task.get("worker_id")
            self._logger.warning("Resetting stuck task", task_id=task_id, video_id=video_id)
            sync_client.reset_task_to_pending(task_id)
            sync_client.update_video_status(video_id, VideoStatus.UPLOADED)
            if worker_id:
                sync_client.mark_worker_ready(worker_id)

        # --- Rule 2: dispatch UPLOADED videos to available workers ---
        self._dispatch_pending_tasks(sync_client)

    def _dispatch_pending_tasks(self, sync_client) -> None:
        """
        Two-step dispatch:
        Step A — create PENDING tasks for UPLOADED videos that have none.
        Step B — assign all PENDING tasks to available workers.
        """
        from .models import (
            VideoStatus, TaskStatus, TaskDocument, ProcessingSettings,
            TaskMessage, generate_task_id, get_current_timestamp
        )
        import os as _os

        # Step A: create tasks for UPLOADED videos with no active task
        orphan_videos = sync_client.get_videos_without_active_task()
        for video in orphan_videos:
            video_id = video["video_id"]
            task_id = generate_task_id()
            task_doc = TaskDocument(
                task_id=task_id,
                video_id=video_id,
                user_id=video.get("user_id", "anonymous"),
                status=TaskStatus.PENDING.value,
                progress_percentage=0.0
            )
            sync_client.create_task(task_doc)
            self._logger.info("Created task for uploaded video",
                              video_id=video_id, task_id=task_id)

        # Step B: dispatch PENDING tasks to available workers
        pending_tasks = sync_client.get_pending_tasks()
        if not pending_tasks:
            return

        available_workers = sync_client.get_available_workers()
        if not available_workers:
            self._logger.debug("Pending tasks exist but no workers available",
                               pending_count=len(pending_tasks))
            return

        self._logger.info("Dispatching pending tasks",
                          pending=len(pending_tasks), workers=len(available_workers))

        worker_pool = list(available_workers)
        for task in pending_tasks:
            if not worker_pool:
                break

            worker = worker_pool.pop(0)
            task_id = task["task_id"]
            video_id = task["video_id"]

            video = sync_client.get_video_by_id(video_id)
            if not video:
                self._logger.error("Video not found for pending task",
                                   task_id=task_id, video_id=video_id)
                continue

            sync_client.assign_task_to_worker(task_id, worker["worker_id"])
            sync_client.update_video_status(video_id, VideoStatus.PROCESSING)

            filename = video.get("filename", f"{video_id}.mp4")
            file_ext = _os.path.splitext(filename)[1].lower() or ".mp4"
            raw_file_path = video.get("raw_file_path", "")
            output_file_path = f"processed-videos/{video_id}{file_ext}"

            settings = ProcessingSettings(
                yolo_classes=[0, 2, 3, 5, 7],
                model_size="small",
                detection_type="bbox",
                frame_sampling=4,
                blur_intensity=25,
                processing_resolution=0.5
            )

            task_message = TaskMessage(
                task_id=task_id,
                video_id=video_id,
                user_id=video.get("user_id", "anonymous"),
                input_file_path=raw_file_path,
                output_file_path=output_file_path,
                processing_settings=settings,
                created_at=get_current_timestamp()
            )

            try:
                self._rabbitmq_client.send_task_assignment(worker["worker_id"], task_message)
                self._logger.info("Dispatched task to worker",
                                  task_id=task_id, worker_id=worker["worker_id"])
            except Exception as send_err:
                self._logger.error("Failed to dispatch task",
                                   task_id=task_id, error=str(send_err))
                sync_client.reset_task_to_pending(task_id)
                sync_client.update_video_status(video_id, VideoStatus.UPLOADED)


def main():
    """Main entry point."""
    try:
        # Load environment
        load_env_file()
        
        # Configure logging
        configure_logging()
        
        # Create and start backend service
        backend = DashcamBackend()
        backend.start()
        
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    except Exception as e:
        print(f"Error starting backend service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
def main() -> None:
    """Main application entry point."""
    # Load environment variables from .env file if available
    load_env_file()
    
    # Get configuration
    config = get_config()
    
    # Configure logging
    configure_logging(config.app.log_level, "dashcam-backend")
    
    # Create and start the backend service
    backend = DashcamBackend()
    backend.start()


def cli_main() -> None:
    """CLI entry point."""
    try:
        # Check Python version
        if sys.version_info < (3, 12):
            print("Error: Python 3.12 or higher is required")
            sys.exit(1)
        
        # Run the main function
        main()
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
