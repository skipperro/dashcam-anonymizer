"""
Main entry point for the Dashcam Worker application.

Handles worker lifecycle, task processing coordination, and provides
both service mode and local testing mode as specified.
"""

import argparse
import signal
import sys
import os
import time
from typing import Optional
import structlog

from .config import get_config
from .logging import setup_logging, log_worker_event
from .rabbitmq_client import RabbitMQClient
from .storage_client import StorageClient
from .models import TaskMessage
from .video_processor import VideoProcessor
from .health import start_health_server


class DashcamWorker:
    """
    Main worker application class.
    
    Coordinates all worker components and handles task processing workflow.
    """
    
    def __init__(self):
        self.config = get_config()
        self.logger = setup_logging()
        self.rabbitmq_client: Optional[RabbitMQClient] = None
        self.storage_client: Optional[StorageClient] = None
        self.video_processor: Optional[VideoProcessor] = None
        self.shutdown_requested = False
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info("Shutdown signal received", signal=signum)
        self.shutdown_requested = True
    
    def initialize(self) -> bool:
        """
        Initialize all worker components.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            log_worker_event(self.logger, "startup", version="1.0.0")
            
            # Start health check server
            start_health_server(port=8080)
            
            # Initialize storage client
            self.storage_client = StorageClient()
            
            # Initialize video processor
            self.video_processor = VideoProcessor(
                storage_client=self.storage_client
            )
            
            # Initialize RabbitMQ client
            self.rabbitmq_client = RabbitMQClient()
            self.rabbitmq_client.connect()
            
            # Wire rabbitmq_client into video processor so it can send progress and completion messages
            self.video_processor.rabbitmq_client = self.rabbitmq_client
            
            log_worker_event(self.logger, "initialization_complete")
            return True
            
        except Exception as e:
            log_worker_event(self.logger, "initialization_failed", error=str(e))
            return False
    
    def start_service_mode(self) -> None:
        """
        Start worker in service mode.
        
        Registers with backend, starts heartbeat, and listens for tasks.
        """
        try:
            if not self.initialize():
                sys.exit(1)
            
            # Register worker with backend
            self.rabbitmq_client.register_worker()
            
            # Start heartbeat
            self.rabbitmq_client.start_heartbeat()
            
            # Check for incomplete tasks
            self._check_incomplete_tasks()
            
            log_worker_event(self.logger, "service_mode_started")
            
            # Listen for tasks
            self.rabbitmq_client.listen_for_tasks(self._process_task)
            
        except KeyboardInterrupt:
            self.logger.info("Worker interrupted by user")
        except Exception as e:
            log_worker_event(self.logger, "service_mode_error", error=str(e))
        finally:
            self.shutdown()
    
    def start_local_test_mode(self, input_path: str, output_path: str, **settings) -> bool:
        """
        Start worker in local testing mode.
        
        Args:
            input_path: Input video file path
            output_path: Output video file path
            **settings: Processing settings
        
        Returns:
            True if processing successful, False otherwise
        """
        try:
            self.logger.info("Starting local test mode", 
                           input_path=input_path,
                           output_path=output_path)
            
            # Initialize only required components (no RabbitMQ)
            self.storage_client = None  # No storage needed for local mode
            
            self.video_processor = VideoProcessor(
                storage_client=None,
                local_mode=True
            )
            
            # Create task message for local video processing
            from .models import ProcessingSettings
            processing_settings = ProcessingSettings(
                yolo_classes=settings.get('yolo_classes', [0, 2, 3, 5, 7]),
                model_size=settings.get('model_size', 'small'),
                detection_type=settings.get('detection_type', 'segmentation'),
                debug_mode=settings.get('debug_mode', False),
                blur_intensity=settings.get('blur_intensity', 15),
                frame_sampling=settings.get('frame_sampling', 2),
                processing_resolution=settings.get('processing_resolution', 0.5),
                enable_hood_detection=settings.get('enable_hood_detection', False),
                blur_minimum_track_duration=settings.get('blur_minimum_track_duration', 4),
                blur_large_object_threshold=settings.get('blur_large_object_threshold', 0.15),
                blur_duration_filtering_enabled=settings.get('blur_duration_filtering_enabled', True),
                debug_show_trajectories=settings.get('debug_show_trajectories', True),
                debug_trajectory_length=settings.get('debug_trajectory_length', 30),
                debug_trajectory_fade=settings.get('debug_trajectory_fade', True)
                # NOTE: Encoding parameters removed - automatically preserved from source
            )
            
            # Process video locally
            success = self.video_processor.process_video_local(
                input_path=input_path,
                output_path=output_path,
                processing_settings=processing_settings
            )
            
            if success:
                self.logger.info("Local test completed successfully")
                return True
            else:
                self.logger.error("Local test failed")
                return False
                
        except Exception as e:
            self.logger.error("Local test mode error", error=str(e))
            return False
    
    def _process_task(self, task_message: TaskMessage) -> None:
        """
        Process a video task.
        
        Args:
            task_message: Task details from backend
        """
        task_id = task_message.task_id
        
        try:
            log_worker_event(self.logger, "task_start", task_id=task_id)
            
            # Process the video
            success = self.video_processor.process_video(task_message)
            
            if success:
                log_worker_event(self.logger, "task_completed", task_id=task_id)
            else:
                log_worker_event(self.logger, "task_failed", task_id=task_id)
                
        except Exception as e:
            log_worker_event(self.logger, "task_error", task_id=task_id, error=str(e))
    
    def _check_incomplete_tasks(self) -> None:
        """Check for incomplete tasks and handle recovery."""
        # Worker is now stateless - no checkpoint recovery needed
        # Any incomplete tasks will be handled by the backend reassignment logic
        self.logger.info("Worker starting in stateless mode - no task recovery needed")
    
    def shutdown(self) -> None:
        """Graceful shutdown of all components."""
        try:
            log_worker_event(self.logger, "shutdown")
            
            if self.rabbitmq_client:
                self.rabbitmq_client.disconnect()
                
        except Exception as e:
            self.logger.error("Error during shutdown", error=str(e))


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Dashcam Worker - Video Anonymization Service")
    
    # Service mode (default)
    parser.add_argument("--service", action="store_true", default=True,
                       help="Run in service mode (default)")
    
    # Local test mode
    parser.add_argument("--local-test", action="store_true",
                       help="Run in local test mode")
    parser.add_argument("--input", type=str,
                       help="Input video path for local test")
    parser.add_argument("--output", type=str,
                       help="Output video path for local test")
    parser.add_argument("--yolo-classes", type=str, default="0,2,3,5,7",
                       help="Comma-separated COCO class IDs to blur")
    parser.add_argument("--model-size", choices=["nano", "small", "medium", "large", "xlarge"], 
                       default="medium", help="YOLO12 model size")
    parser.add_argument("--detection-type", choices=["bbox", "segmentation"], 
                       default="bbox", help="Detection type")
    parser.add_argument("--blur-intensity", type=int, default=15,
                       help="Blur intensity")
    parser.add_argument("--frame-sampling", type=int, default=1,
                       help="Process every Nth frame")
    parser.add_argument("--processing-resolution", type=float, default=1.0,
                       help="AI processing resolution scale")
    parser.add_argument("--debug-mode", action="store_true",
                       help="Enable debug mode")
    parser.add_argument("--debug-show-trajectories", action="store_true", default=True,
                       help="Show object trajectories in debug mode")
    parser.add_argument("--debug-trajectory-length", type=int, default=30,
                       help="Maximum trajectory points to display")
    parser.add_argument("--debug-trajectory-fade", action="store_true", default=True,
                       help="Fade older trajectory points")
    parser.add_argument("--enable-hood-detection", action="store_true", default=False,
                       help="Enable simple hood detection filtering")
    parser.add_argument("--blur-minimum-track-duration", type=int, default=4,
                       help="Minimum frames before applying blur to prevent flickering")
    parser.add_argument("--blur-large-object-threshold", type=float, default=0.15,
                       help="Objects larger than this fraction of frame bypass duration filter")
    parser.add_argument("--no-blur-duration-filtering", action="store_true", default=False,
                       help="Disable short-track filtering")
    # NOTE: Encoding parameters removed - codec, quality, and bitrate are automatically preserved
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()
    
    worker = DashcamWorker()
    
    if args.local_test:
        if not args.input or not args.output:
            print("Error: --input and --output are required for local test mode")
            sys.exit(1)
        
        # Parse yolo_classes
        yolo_classes = [int(x.strip()) for x in args.yolo_classes.split(',')]
        
        # Local test mode
        success = worker.start_local_test_mode(
            input_path=args.input,
            output_path=args.output,
            yolo_classes=yolo_classes,
            model_size=args.model_size,
            detection_type=args.detection_type,
            debug_mode=args.debug_mode,
            blur_intensity=args.blur_intensity,
            frame_sampling=args.frame_sampling,
            processing_resolution=args.processing_resolution,
            enable_hood_detection=args.enable_hood_detection,
            blur_minimum_track_duration=args.blur_minimum_track_duration,
            blur_large_object_threshold=args.blur_large_object_threshold,
            blur_duration_filtering_enabled=not args.no_blur_duration_filtering,
            debug_show_trajectories=args.debug_show_trajectories,
            debug_trajectory_length=args.debug_trajectory_length,
            debug_trajectory_fade=args.debug_trajectory_fade
            # NOTE: Encoding parameters removed - automatically preserved from source
        )
        
        sys.exit(0 if success else 1)
    else:
        # Service mode
        worker.start_service_mode()


if __name__ == "__main__":
    main()
