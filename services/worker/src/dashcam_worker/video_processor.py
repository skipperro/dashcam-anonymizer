"""
Video processing module.

Core video processing pipeline implementing the hybrid approach with multithreaded
processing, YOLO detection, and blurring as specified in the worker specification.
"""

from typing import Dict, List, Optional, Any
import threading
import time
import os
import uuid
import json
import gc
import structlog
import numpy as np
import cv2
import ffmpeg
from queue import Queue, Empty, Full

from .config import get_config
from .model_manager import ModelManager
from .models import TaskMessage, ProcessingSettings
from .storage_client import StorageClient
from .rabbitmq_client import RabbitMQClient
from .encoder_thread import EncoderThread
from .blur_thread import BlurThread
from .ai_thread import AIThread


class VideoProcessor:
    """
    Core video processing pipeline.
    
    Implements hybrid processing approach with multithreaded pipeline
    for optimal performance as specified in the worker specification.
    """
    
    def __init__(self, storage_client: Optional[StorageClient] = None,
                 local_mode: bool = False):
        self.storage_client = storage_client
        self.local_mode = local_mode
        self.config = get_config()
        self.logger = structlog.get_logger("video_processor")
        self.model_manager = ModelManager()
        
        # RabbitMQ client — injected by DashcamWorker after initialization
        self.rabbitmq_client: Optional[RabbitMQClient] = None
        
        # Processing state
        self.current_task_id: Optional[str] = None
        self.processing_stats = {}
        self.stop_processing = threading.Event()
        
        # Progress tracking for FPS calculation
        self.processing_start_time: Optional[float] = None
        self.last_progress_time: Optional[float] = None
        self.last_frame_count: int = 0
        
        # Thread timing stats
        self.thread_timings = {
            'ai_time': 0.0,
            'blur_time': 0.0,
            'encoder_time': 0.0,
            'total_inference_time': 0.0,
            'total_frame_decode_time': 0.0,
            'total_frame_blur_time': 0.0,
            'total_frame_encode_time': 0.0
        }
        
        # Memory tracking for leak detection
        self.memory_tracking = {
            'ai_thread_baseline': 0.0,
            'blur_thread_baseline': 0.0,
            'encoder_thread_baseline': 0.0,
            'last_memory_check': 0.0
        }
        
        # Buffer management - Reduced for low memory usage
        self.max_buffer_size = 10 # For blur queues
        self.detection_buffer_size = 30 # AI thread output and blur thread input
        self.queue_full_sleep = 0.5
        self.queue_timeout = 0.5
        
        # Temporal stability settings
        self.temporal_lookahead_frames = 20  # Number of frames to look ahead for temporal stability
        
        # Initialize encoder thread after queue_timeout is defined
        self.encoder_thread = EncoderThread(self.config, self.queue_timeout)
        
        # Initialize blur thread after temporal_lookahead_frames is defined
        self.blur_thread = BlurThread(self.config, self.queue_timeout, self.temporal_lookahead_frames)
        
        # Initialize AI thread
        self.ai_thread = AIThread(self.config, self.queue_timeout)
    
    def process_video(self, task_message: TaskMessage) -> bool:
        """
        Process video task from backend.
        
        Args:
            task_message: Task details from backend
        
        Returns:
            True if processing successful, False otherwise
        """
        self.current_task_id = task_message.task_id
        start_time = time.time()
        
        # Initialize progress tracking
        self.processing_start_time = start_time
        self.last_progress_time = start_time
        self.last_frame_count = 0
        
        try:
            self.logger.info("Starting video processing", 
                           task_id=task_message.task_id,
                           input_path=task_message.input_file_path)
            
            # Download input video
            local_input_path = f"/tmp/{task_message.task_id}_input.mp4"
            if not self.storage_client.download_file(
                task_message.input_file_path, local_input_path):
                raise Exception("Failed to download input video")
            
            # Process video
            local_output_path = f"/tmp/{task_message.task_id}_output.mp4"
            success = self._process_video_file(
                local_input_path, local_output_path, 
                task_message.processing_settings, task_message.task_id
            )
            
            if not success:
                raise Exception("Video processing failed")
            
            # Upload output video
            if not self.storage_client.upload_file(
                local_output_path, task_message.output_file_path):
                raise Exception("Failed to upload output video")
            
            # Send completion message
            processing_time = time.time() - start_time
            
            if hasattr(self, 'rabbitmq_client'):
                self.rabbitmq_client.send_completion_message(
                    task_id=task_message.task_id,
                    video_id=task_message.video_id,
                    status="completed",
                    output_file_path=task_message.output_file_path,
                    processing_time=processing_time,
                    total_frames=self.processing_stats.get('total_frames', 0),
                    objects_detected=self.processing_stats.get('objects_detected', 0)
                )
            
            # Clean up temporary files
            self._cleanup_temp_files([local_input_path, local_output_path])
            
            # Task completed successfully (stateless - no checkpoint cleanup needed)
            
            return True
            
        except Exception as e:
            self.logger.error("Video processing failed", 
                            task_id=task_message.task_id, error=str(e))
            
            # Send error message
            if hasattr(self, 'rabbitmq_client'):
                self.rabbitmq_client.send_completion_message(
                    task_id=task_message.task_id,
                    video_id=task_message.video_id,
                    status="failed",
                    output_file_path=None,
                    processing_time=time.time() - start_time,
                    total_frames=0,
                    objects_detected=0,
                    error_message=str(e)
                )
            
            return False
    
    def process_video_local(self, input_path: str, output_path: str, 
                          processing_settings: ProcessingSettings) -> bool:
        """
        Process video in local test mode.
        
        Args:
            input_path: Local input video path
            output_path: Local output video path
            processing_settings: Processing configuration
        
        Returns:
            True if processing successful, False otherwise
        """
        import uuid
        try:
            self.logger.info("Starting local video processing", 
                           input_path=input_path, output_path=output_path)
            
            # Generate unique task ID for concurrent safety
            unique_task_id = f"local_test_{str(uuid.uuid4())[:8]}"
            
            success = self._process_video_file(
                input_path, output_path, processing_settings, unique_task_id
            )
            
            if success:
                # Print processing statistics
                stats = self.processing_stats
                result = {
                    "input_file": input_path,
                    "output_file": output_path,
                    "processing_time": stats.get('processing_time', 0),
                    "total_frames": stats.get('total_frames', 0),
                    "processed_frames": stats.get('processed_frames', 0),
                    "objects_detected": stats.get('objects_detected', 0),
                    "audio_preserved": True,
                    "original_resolution": stats.get('original_resolution', ''),
                    "ai_processing_resolution": stats.get('processing_resolution', ''),
                    "encoding_resolution": stats.get('encoding_resolution', ''),
                    "fullhd_limit_applied": stats.get('fullhd_limit_applied', False),
                    "encoding_info": {
                        "source_codec": stats.get('source_codec', 'unknown'),
                        "output_codec_used": stats.get('output_codec', 'unknown'),
                        "source_bitrate": stats.get('source_bitrate'),
                        "bitrate_preserved": stats.get('bitrate_preserved', False),
                        "source_pixel_format": stats.get('source_pixel_format', 'unknown'),
                        "codec_preserved": stats.get('codec_preserved', False)
                    },
                    "thread_timings": {
                        "ai_time": self.thread_timings.get('ai_time', 0),
                        "blur_time": self.thread_timings.get('blur_time', 0),
                        "encoder_time": self.thread_timings.get('encoder_time', 0),
                        "total_inference_time": self.thread_timings.get('total_inference_time', 0),
                        "total_frame_decode_time": self.thread_timings.get('total_frame_decode_time', 0),
                        "total_frame_blur_time": self.thread_timings.get('total_frame_blur_time', 0),
                        "total_frame_encode_time": self.thread_timings.get('total_frame_encode_time', 0)
                    },
                    "performance_metrics": {
                        "avg_inference_time_per_frame": self.thread_timings.get('total_inference_time', 0) / max(1, stats.get('processed_frames', 1)),
                        "avg_decode_time_per_frame": self.thread_timings.get('total_frame_decode_time', 0) / max(1, stats.get('total_frames', 1)),
                        "avg_blur_time_per_frame": self.thread_timings.get('total_frame_blur_time', 0) / max(1, stats.get('total_frames', 1)),
                        "avg_encode_time_per_frame": self.thread_timings.get('total_frame_encode_time', 0) / max(1, stats.get('total_frames', 1)),
                        "processing_fps": stats.get('total_frames', 0) / max(0.001, stats.get('processing_time', 0.001))
                    },
                    "settings_used": {
                        "yolo_classes": processing_settings.yolo_classes,
                        "model_size": processing_settings.model_size,
                        "frame_sampling": processing_settings.frame_sampling,
                        "processing_resolution": processing_settings.processing_resolution
                    },
                    "encoding_info": {
                        "source_codec": stats.get('source_codec', 'unknown'),
                        "source_bitrate_mbps": stats.get('source_bitrate_mbps', 'unknown'),
                        "source_pixel_format": stats.get('source_pix_fmt', 'unknown'),
                        "output_codec_used": stats.get('output_codec', 'unknown'),
                        "bitrate_preserved": stats.get('bitrate_preserved', False)
                    }
                }
                
                import json
                print("\n" + "="*50)
                print("PROCESSING RESULTS:")
                print("="*50)
                print(json.dumps(result, indent=2))
                print("="*50)
            
            return success
            
        except Exception as e:
            self.logger.error("Local video processing failed", error=str(e))
            return False
    
    def _process_video_file(self, input_path: str, output_path: str, 
                          processing_settings: ProcessingSettings, 
                          task_id: str) -> bool:
        """
        Core video processing implementation.
        
        Implements the multithreaded processing pipeline as specified.
        """
        start_time = time.time()
        
        # Initialize progress tracking for local mode too
        if not hasattr(self, 'processing_start_time') or self.processing_start_time is None:
            self.processing_start_time = start_time
            self.last_progress_time = start_time
            self.last_frame_count = 0
        
        try:
            # Load YOLO model with detection type
            model = self.model_manager.load_model(
                model_size=processing_settings.model_size,
                detection_type=processing_settings.detection_type
            )
            
            # Get video info
            video_info = self._get_video_info(input_path)
            total_frames = video_info['frame_count']
            fps = video_info['fps']
            width = video_info['width']
            height = video_info['height']
            
            # Calculate actual AI processing resolution with FullHD safety limit
            MAX_AI_HEIGHT = 1080
            MAX_AI_WIDTH = 1920
            
            # Check if FullHD limit applies
            if height > MAX_AI_HEIGHT or width > MAX_AI_WIDTH:
                # Calculate scale factor to fit within FullHD while maintaining aspect ratio
                scale_h = MAX_AI_HEIGHT / height
                scale_w = MAX_AI_WIDTH / width
                fullhd_scale = min(scale_h, scale_w)
                
                # Apply both FullHD scaling and processing resolution
                final_scale = fullhd_scale * processing_settings.processing_resolution
                
                actual_ai_width = int(width * final_scale)
                actual_ai_height = int(height * final_scale)
                
                self.logger.info("FullHD safety limit applied for AI processing", 
                               original_resolution=f"{width}x{height}",
                               fullhd_scale=fullhd_scale,
                               processing_resolution_setting=processing_settings.processing_resolution,
                               final_scale=final_scale,
                               actual_ai_resolution=f"{actual_ai_width}x{actual_ai_height}")
            else:
                # Original is FullHD or smaller, just apply processing resolution
                final_scale = processing_settings.processing_resolution
                actual_ai_width = int(width * final_scale)
                actual_ai_height = int(height * final_scale)
            
            self.processing_stats = {
                'total_frames': total_frames,
                'processed_frames': 0,
                'objects_detected': 0,
                'original_resolution': f"{width}x{height}",
                'processing_resolution': f"{actual_ai_width}x{actual_ai_height}",
                'fullhd_limit_applied': height > MAX_AI_HEIGHT or width > MAX_AI_WIDTH,
                'encoding_resolution': f"{width}x{height}",  # Always encode at original resolution
                'source_codec': video_info.get('codec_name', 'unknown'),
                'source_bitrate_mbps': video_info.get('bit_rate', 0) / 1000000 if video_info.get('bit_rate') else 0,
                'source_pix_fmt': video_info.get('pix_fmt', 'unknown'),
                'output_codec': 'unknown',  # Will be set during encoding
                'bitrate_preserved': False  # Will be set during encoding
            }
            
            # Reset thread timings for this processing run
            self.thread_timings = {
                'ai_time': 0.0,
                'blur_time': 0.0,
                'encoder_time': 0.0,
                'total_inference_time': 0.0,
                'total_frame_decode_time': 0.0,
                'total_frame_blur_time': 0.0,
                'total_frame_encode_time': 0.0
            }
            
            self.logger.info("Video info extracted", 
                           total_frames=total_frames, fps=fps, 
                           resolution=f"{width}x{height}")
            
            # Set up multithreaded processing pipeline
            success = self._run_processing_pipeline(
                input_path, output_path, model, processing_settings,
                video_info, task_id
            )
            
            self.processing_stats['processing_time'] = time.time() - start_time
            
            return success
            
        except Exception as e:
            self.logger.error("Video processing pipeline failed", error=str(e))
            return False
    
    def _run_processing_pipeline(self, input_path: str, output_path: str,
                               model: Any, processing_settings: ProcessingSettings,
                               video_info: Dict[str, Any], task_id: str) -> bool:
        """
        Run the multithreaded processing pipeline.
        
        Implements the new threading architecture:
        - AI Thread: Decodes frames and runs YOLO inference, builds detection buffer
        - Blur Thread: Decodes frames and applies blurring with temporal stability
        - Encoder Thread: FFmpeg encoding
        """
        try:
            self.logger.info("Starting processing pipeline", 
                           total_frames=video_info['frame_count'],
                           fps=video_info['fps'],
                           temporal_lookahead=self.temporal_lookahead_frames)
            
            # Create queue for detection data (frame_number -> detection data)
            detection_queue = Queue(maxsize=self.detection_buffer_size)
            blur_queue = Queue(maxsize=self.max_buffer_size)
            
            # Threading control
            threads = []
            stop_event = threading.Event()
            
            # Start AI inference thread
            ai_thread = threading.Thread(
                target=self._run_ai_thread,
                args=(input_path, detection_queue, model, processing_settings, video_info, stop_event),
                name="AIThread"
            )
            threads.append(ai_thread)
            
            # Start blur thread
            blur_thread = threading.Thread(
                target=self._run_blur_thread,
                args=(input_path, detection_queue, blur_queue, processing_settings, video_info, stop_event),
                name="BlurThread"
            )
            threads.append(blur_thread)
            
            # Start encoder thread
            encoder_stats = {}
            encoder_thread = threading.Thread(
                target=self._run_encoder_thread,
                args=(blur_queue, input_path, output_path, video_info, processing_settings, task_id, stop_event),
                name="EncoderThread"
            )
            threads.append(encoder_thread)
            
            # Start all threads
            for thread in threads:
                thread.start()
                self.logger.info("Started thread", thread_name=thread.name)
            
            # Wait for completion with periodic status checks
            all_completed = False
            check_interval = 5  # Check every 5 seconds
            
            while not all_completed:
                time.sleep(check_interval)
                
                # Check if all threads are still alive or have completed normally
                alive_threads = [t for t in threads if t.is_alive()]
                dead_threads = [t for t in threads if not t.is_alive()]
                
                if dead_threads:
                    self.logger.info("Thread status check", 
                                   alive=len(alive_threads), 
                                   dead=len(dead_threads),
                                   dead_thread_names=[t.name for t in dead_threads])
                
                # If all threads are dead, we're done
                if not alive_threads:
                    all_completed = True
                    break
                
                # Check for stop event (error condition)
                if stop_event.is_set():
                    self.logger.warning("Stop event detected, terminating remaining threads")
                    break
            
            # Join all threads with timeout
            for thread in threads:
                thread.join(timeout=30)  # 30 second timeout
                if thread.is_alive():
                    self.logger.error("Thread did not complete within timeout", thread_name=thread.name)
            
            # Get encoder thread stats
            encoder_stats = getattr(self, '_encoder_stats', {})
            if encoder_stats:
                # Update main thread timings with encoder stats
                self.thread_timings['encoder_time'] = encoder_stats.get('encoder_time', 0.0)
                self.thread_timings['total_frame_encode_time'] = encoder_stats.get('total_frame_encode_time', 0.0)
                self.processing_stats['processed_frames'] = encoder_stats.get('processed_frames', 0)
            
            # Get blur thread stats
            blur_stats = getattr(self, '_blur_stats', {})
            if blur_stats:
                # Update main thread timings with blur stats
                self.thread_timings['blur_time'] = blur_stats.get('blur_time', 0.0)
                self.thread_timings['total_frame_blur_time'] = blur_stats.get('total_frame_blur_time', 0.0)
                self.thread_timings['total_frame_decode_time'] += blur_stats.get('total_frame_decode_time', 0.0)
            
            # Get AI thread stats
            ai_stats = getattr(self, '_ai_stats', {})
            if ai_stats:
                # Update main thread timings with AI stats
                self.thread_timings['ai_time'] = ai_stats.get('ai_time', 0.0)
                self.thread_timings['total_inference_time'] = ai_stats.get('total_inference_time', 0.0)
                self.thread_timings['total_frame_decode_time'] += ai_stats.get('total_frame_decode_time', 0.0)
                self.processing_stats['objects_detected'] = ai_stats.get('objects_detected', 0)
            
            # Check if we completed successfully
            if stop_event.is_set():
                self.logger.error("Pipeline completed with errors")
                return False
            
            self.logger.info("Processing pipeline completed successfully")
            return True
            
        except Exception as e:
            self.logger.error("Processing pipeline error", error=str(e))
            stop_event.set()
            return False
    
    def _run_ai_thread(self, input_path: str, output_queue: Queue, model: Any, 
                      processing_settings: ProcessingSettings, video_info: Dict[str, Any], 
                      stop_event: threading.Event):
        """Wrapper method to run the AI thread."""
        try:
            # Run AI thread
            ai_stats = self.ai_thread.run(
                input_path=input_path,
                output_queue=output_queue,
                model=model,
                processing_settings=processing_settings,
                video_info=video_info,
                stop_event=stop_event
            )
            
            # Store stats for retrieval by main thread
            self._ai_stats = ai_stats
            
        except Exception as e:
            self.logger.error("AI thread wrapper error", error=str(e))
            stop_event.set()
            self._ai_stats = {
                'frames_processed': 0,
                'objects_detected': 0,
                'ai_time': 0.0,
                'total_inference_time': 0.0,
                'total_frame_decode_time': 0.0,
                'error': str(e)
            }
    
    def _run_blur_thread(self, input_path: str, input_queue: Queue, output_queue: Queue,
                        processing_settings: ProcessingSettings, video_info: Dict[str, Any], 
                        stop_event: threading.Event):
        """Wrapper method to run the blur thread."""
        try:
            # Run blur thread
            blur_stats = self.blur_thread.run(
                input_path=input_path,
                input_queue=input_queue,
                output_queue=output_queue,
                processing_settings=processing_settings,
                video_info=video_info,
                stop_event=stop_event
            )
            
            # Store stats for retrieval by main thread
            self._blur_stats = blur_stats
            
        except Exception as e:
            self.logger.error("Blur thread wrapper error", error=str(e))
            stop_event.set()
            self._blur_stats = {
                'frames_processed': 0,
                'blur_time': 0.0,
                'total_frame_blur_time': 0.0,
                'total_frame_decode_time': 0.0,
                'error': str(e)
            }
    
    def _run_encoder_thread(self, input_queue: Queue, input_path: str, output_path: str,
                           video_info: Dict[str, Any], processing_settings: ProcessingSettings, 
                           task_id: str, stop_event: threading.Event):
        """Wrapper method to run the encoder thread."""
        try:
            # Run encoder thread with progress callback
            encoder_stats = self.encoder_thread.run(
                input_queue=input_queue,
                input_path=input_path,
                output_path=output_path,
                video_info=video_info,
                processing_settings=processing_settings,
                task_id=task_id,
                stop_event=stop_event,
                progress_callback=self._update_progress
            )
            
            # Store stats for retrieval by main thread
            self._encoder_stats = encoder_stats
            
            # Update processing stats with encoder stats
            self.processing_stats.update(self.encoder_thread.processing_stats)
            
        except Exception as e:
            self.logger.error("Encoder thread wrapper error", error=str(e))
            stop_event.set()
            self._encoder_stats = {
                'processed_frames': 0,
                'encoder_time': 0.0,
                'total_frame_encode_time': 0.0,
                'error': str(e)
            }
    
    def _apply_blur(self, frame: np.ndarray, detections: List[Dict[str, Any]],
                   processing_settings: ProcessingSettings) -> np.ndarray:
        """Apply blurring to detected objects using either bounding boxes or segmentation masks.
        
        Optimized implementation that minimizes blur operations:
        - Single blur operation for all segmentation masks combined
        - Individual blur operations only for bounding boxes
        - Up to 4x performance improvement for multiple detections
        - Debug mode adds visual annotations (bounding boxes, labels, confidence scores)
        """
        if not detections:
            return frame
        
        blur_kernel = (processing_settings.blur_intensity, processing_settings.blur_intensity)
        
        # Create a unified blur mask to prevent double blurring
        height, width = frame.shape[:2]
        blur_mask = np.zeros((height, width), dtype=bool)
        
        # Build combined mask from all detections
        for detection in detections:
            if detection.get('type') == 'segmentation' and 'mask' in detection:
                # Use segmentation mask
                mask = detection['mask']
                
                # Ensure mask is correct size
                if mask.shape[:2] != (height, width):
                    mask = cv2.resize(mask.astype(np.uint8), 
                                    (width, height), 
                                    interpolation=cv2.INTER_NEAREST).astype(bool)
                
                blur_mask |= mask
            else:
                # Use bounding box as mask
                x1, y1, x2, y2 = detection['bbox']
                
                # Clamp coordinates to frame boundaries
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(width, x2), min(height, y2)
                
                # Add bounding box region to mask
                blur_mask[y1:y2, x1:x2] = True
        
        # Apply blur only once to all masked regions
        if np.any(blur_mask):
            # Create a copy of the frame to avoid modifying the original
            blurred_frame = frame.copy()
            # Create blurred version of the entire frame
            blurred_full_frame = cv2.GaussianBlur(frame, blur_kernel, 0)
            # Apply blur only to masked regions
            blurred_frame[blur_mask] = blurred_full_frame[blur_mask]
            # Clean up intermediate blurred frame
            del blurred_full_frame
        else:
            # No blur needed, but still need to copy for consistency
            blurred_frame = frame.copy()
        
        # Add debug annotations if enabled
        if processing_settings.debug_mode:
            blurred_frame = self._add_debug_annotations(blurred_frame, detections)
        
        return blurred_frame
    
    def _add_debug_annotations(self, frame: np.ndarray, detections: List[Dict[str, Any]]) -> np.ndarray:
        """Add debug annotations to frame showing detected objects.
        
        Adds bounding boxes, class labels, confidence scores, and track IDs for debugging.
        """
        annotated_frame = frame.copy()
        
        # COCO class names for display
        COCO_CLASSES = {
            0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane', 5: 'bus',
            6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light', 10: 'fire hydrant',
            11: 'stop sign', 12: 'parking meter', 13: 'bench', 14: 'bird', 15: 'cat',
            16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow', 20: 'elephant', 21: 'bear',
            22: 'zebra', 23: 'giraffe', 24: 'backpack', 25: 'umbrella', 26: 'handbag',
            27: 'tie', 28: 'suitcase', 29: 'frisbee', 30: 'skis', 31: 'snowboard',
            32: 'sports ball', 33: 'kite', 34: 'baseball bat', 35: 'baseball glove',
            36: 'skateboard', 37: 'surfboard', 38: 'tennis racket', 39: 'bottle',
            40: 'wine glass', 41: 'cup', 42: 'fork', 43: 'knife', 44: 'spoon',
            45: 'bowl', 46: 'banana', 47: 'apple', 48: 'sandwich', 49: 'orange',
            50: 'broccoli', 51: 'carrot', 52: 'hot dog', 53: 'pizza', 54: 'donut',
            55: 'cake', 56: 'chair', 57: 'couch', 58: 'potted plant', 59: 'bed',
            60: 'dining table', 61: 'toilet', 62: 'tv', 63: 'laptop', 64: 'mouse',
            65: 'remote', 66: 'keyboard', 67: 'cell phone', 68: 'microwave', 69: 'oven',
            70: 'toaster', 71: 'sink', 72: 'refrigerator', 73: 'book', 74: 'clock',
            75: 'vase', 76: 'scissors', 77: 'teddy bear', 78: 'hair drier', 79: 'toothbrush'
        }
        
        # Define colors for different detection types
        BBOX_COLOR = (0, 255, 0)  # Green for bbox
        SEG_COLOR = (255, 0, 0)   # Blue for segmentation
        TEXT_COLOR = (255, 255, 255)  # White text
        
        for i, detection in enumerate(detections):
            x1, y1, x2, y2 = detection['bbox']
            class_id = detection.get('class_id', -1)
            confidence = detection.get('confidence', 0.0)
            track_id = detection.get('track_id')
            detection_type = detection.get('type', 'bbox')
            
            # Choose color based on detection type
            color = SEG_COLOR if detection_type == 'segmentation' else BBOX_COLOR
            
            # Draw bounding box
            cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            
            # Prepare label text
            class_name = COCO_CLASSES.get(class_id, f'class_{class_id}')
            label_parts = [class_name]
            
            if confidence > 0:
                label_parts.append(f'{confidence:.2f}')
            
            if track_id is not None:
                label_parts.append(f'ID:{track_id}')
            
            if detection_type == 'segmentation':
                label_parts.append('SEG')
            
            label = ' '.join(label_parts)
            
            # Calculate text size and position
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)
            
            # Position label above bounding box
            label_x = int(x1)
            label_y = int(y1) - 10
            
            # Ensure label stays within frame
            if label_y - text_height < 0:
                label_y = int(y1) + text_height + 10
            
            # Draw label background
            cv2.rectangle(annotated_frame, 
                         (label_x, label_y - text_height - baseline),
                         (label_x + text_width, label_y + baseline),
                         color, -1)
            
            # Draw label text
            cv2.putText(annotated_frame, label, (label_x, label_y - baseline),
                       font, font_scale, TEXT_COLOR, thickness)
        
        return annotated_frame
    
    def _get_video_info(self, input_path: str) -> Dict[str, Any]:
        """Extract comprehensive video information using both OpenCV and FFmpeg."""
        # Get basic info from OpenCV
        cap = cv2.VideoCapture(input_path)
        
        basic_info = {
            'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            'fps': cap.get(cv2.CAP_PROP_FPS),
            'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        }
        
        cap.release()
        
        # Get detailed encoding info from FFmpeg probe
        try:
            probe = ffmpeg.probe(input_path)
            
            # Find video stream
            video_stream = None
            for stream in probe['streams']:
                if stream['codec_type'] == 'video':
                    video_stream = stream
                    break
            
            if video_stream:
                # Extract encoding parameters
                encoding_info = {
                    'codec_name': video_stream.get('codec_name', 'unknown'),
                    'codec_long_name': video_stream.get('codec_long_name', 'unknown'),
                    'profile': video_stream.get('profile', 'unknown'),
                    'level': video_stream.get('level', 'unknown'),
                    'bit_rate': video_stream.get('bit_rate'),
                    'avg_frame_rate': video_stream.get('avg_frame_rate', ''),
                    'pix_fmt': video_stream.get('pix_fmt', 'unknown'),
                    'duration': float(video_stream.get('duration', 0))
                }
                
                # Calculate estimated bitrate if not available
                if not encoding_info['bit_rate'] and probe.get('format', {}).get('bit_rate'):
                    encoding_info['bit_rate'] = probe['format']['bit_rate']
                
                # Convert bit_rate to int if it's a string
                if encoding_info['bit_rate']:
                    try:
                        encoding_info['bit_rate'] = int(encoding_info['bit_rate'])
                    except (ValueError, TypeError):
                        encoding_info['bit_rate'] = None
                
                # Merge with basic info
                basic_info.update(encoding_info)
                
                self.logger.debug("Video encoding info extracted", 
                                codec=encoding_info['codec_name'],
                                bitrate=encoding_info['bit_rate'],
                                profile=encoding_info['profile'])
        
        except Exception as e:
            self.logger.warning("Could not extract detailed encoding info", error=str(e))
            # Add default encoding info
            basic_info.update({
                'codec_name': 'unknown',
                'bit_rate': None,
                'profile': 'unknown',
                'pix_fmt': 'unknown'
            })
        
        return basic_info
    
    def _update_progress(self, task_id: str, current_frame: int, total_frames: int):
        """Update progress and send checkpoint."""
        progress_percentage = int((current_frame / total_frames) * 100)
        current_time = time.time()
        
        # Calculate FPS (frames per second processing rate)
        fps = 0.0
        estimated_time_remaining = 0
        
        if self.processing_start_time and current_frame > 0:
            elapsed_time = current_time - self.processing_start_time
            if elapsed_time > 0:
                fps = current_frame / elapsed_time
                # Estimate remaining time based on current processing rate
                remaining_frames = total_frames - current_frame
                if fps > 0:
                    estimated_time_remaining = int(remaining_frames / fps)
        
        # Send progress update (service mode only)
        if hasattr(self, 'rabbitmq_client') and not self.local_mode:
            self.rabbitmq_client.send_progress_update(
                task_id=task_id,
                video_id="",  # Would need to be passed through
                progress_percentage=progress_percentage,
                current_frame=current_frame,
                total_frames=total_frames,
                fps=fps,
                estimated_time_remaining=estimated_time_remaining
            )
        
        # Log progress milestones
        if progress_percentage % 25 == 0:
            self.logger.info("Progress milestone", 
                           task_id=task_id, progress=progress_percentage)
    
    def _cleanup_temp_files(self, file_paths: List[str]):
        """Clean up temporary files."""
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                self.logger.warning("Failed to clean up temp file", 
                                  file_path=file_path, error=str(e))