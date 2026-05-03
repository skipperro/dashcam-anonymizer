"""
AI thread module.

Contains the AI thread implementation for video processing pipeline.
Handles frame decoding, YOLO inference, object detection, and detection buffer management.
"""

import os
import threading
import time
import gc
import numpy as np
from typing import Dict, Any
from queue import Queue, Full
import structlog
import cv2

from .models import ProcessingSettings

# Absolute path to the tracker config — resolved relative to this source file so it
# works correctly regardless of the process working directory or Docker WORKDIR.
_TRACKER_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "dashcam_tracker.yaml",
)


def is_hood_detection(detection: Dict[str, Any], frame_width: int, frame_height: int) -> bool:
    """
    Check if a detection is likely a car hood using geometric rules.
    
    Hood detection criteria:
    - Detection touches bottom edge of frame (within 5% margin)
    - Detection touches left OR right edge of frame (within 5% margin)
    - Detection is wider than tall (aspect ratio > 1.0)
    - Only applies to cars (class 2) and trucks (class 7)
    
    Args:
        detection: Detection dictionary with bbox and class_id
        frame_width: Width of the frame
        frame_height: Height of the frame
        
    Returns:
        True if detection is likely a hood, False otherwise
    """
    # Only check cars and trucks
    if detection['class_id'] not in [2, 7]:  # car, truck
        return False
    
    x1, y1, x2, y2 = detection['bbox']
    
    # Calculate margins (5% of frame dimensions)
    margin_w = int(frame_width * 0.05)
    margin_h = int(frame_height * 0.05)
    
    # Check if detection touches bottom edge
    touches_bottom = (y2 >= frame_height - margin_h)
    
    # Check if detection touches left OR right edge
    touches_left = (x1 <= margin_w)
    touches_right = (x2 >= frame_width - margin_w)
    touches_side = touches_left or touches_right
    
    # Check if detection is wider than tall
    width = x2 - x1
    height = y2 - y1
    wider_than_tall = width > height
    
    # Hood detection: must satisfy all criteria
    is_hood = touches_bottom and touches_side and wider_than_tall
    
    return is_hood


class AIThread:
    """
    AI thread implementation for video processing pipeline.
    
    Handles frame decoding, YOLO inference, object detection, and flow control.
    """
    
    def __init__(self, config, queue_timeout: float = 0.1):
        """
        Initialize AI thread.
        
        Args:
            config: Configuration object
            queue_timeout: Timeout for queue operations in seconds
        """
        self.config = config
        self.queue_timeout = queue_timeout
        self.logger = structlog.get_logger("ai_thread")
        
        # Timing stats
        self.thread_timings = {
            'ai_time': 0.0,
            'total_inference_time': 0.0,
            'total_frame_decode_time': 0.0
        }
    
    def run(self, input_path: str, output_queue: Queue, model: Any, 
            processing_settings: ProcessingSettings, video_info: Dict[str, Any], 
            stop_event: threading.Event) -> Dict[str, Any]:
        """
        Run the AI thread.
        
        Args:
            input_path: Path to input video file
            output_queue: Queue for detection data to blur thread
            model: YOLO model for inference
            processing_settings: Processing configuration
            video_info: Video information dictionary
            stop_event: Threading event to signal stop
            
        Returns:
            Dictionary containing processing statistics
        """
        start_time = time.time()
        total_inference_time = 0.0
        total_frame_decode_time = 0.0
        
        try:
            objects_detected = 0
            frames_processed = 0
            
            # Open video capture for this thread
            cap = cv2.VideoCapture(input_path)
            total_frames = video_info['frame_count']
            
            self.logger.info("AI thread started", 
                           total_frames=total_frames,
                           frame_sampling=processing_settings.frame_sampling)
            
            frame_number = 0
            while not stop_event.is_set() and frame_number < total_frames:
                # Decode frame
                frame_start = time.time()
                ret, frame = cap.read()
                frame_decode_time = time.time() - frame_start
                total_frame_decode_time += frame_decode_time
                
                if not ret:
                    self.logger.info("AI thread reached end of video", frames_processed=frame_number)
                    break
                
                # Run AI inference on every frame (frame_sampling = 1)
                detections = []
                
                # Apply FullHD limit for AI processing (safety feature for 4K+ videos)
                original_h, original_w = frame.shape[:2]
                
                # Define FullHD limit
                MAX_AI_HEIGHT = 1080
                MAX_AI_WIDTH = 1920
                
                # Calculate AI processing resolution with FullHD limit
                ai_scale_factor = processing_settings.processing_resolution
                
                # If original resolution exceeds FullHD, first scale down to FullHD
                if original_h > MAX_AI_HEIGHT or original_w > MAX_AI_WIDTH:
                    # Calculate scale factor to fit within FullHD while maintaining aspect ratio
                    scale_h = MAX_AI_HEIGHT / original_h
                    scale_w = MAX_AI_WIDTH / original_w
                    fullhd_scale = min(scale_h, scale_w)
                    
                    # Apply both FullHD scaling and processing resolution
                    final_scale = fullhd_scale * ai_scale_factor
                    
                    self.logger.debug("Applying FullHD limit for AI processing", 
                                    original_resolution=f"{original_w}x{original_h}",
                                    fullhd_scale=fullhd_scale,
                                    processing_resolution=ai_scale_factor,
                                    final_scale=final_scale)
                else:
                    # Original is FullHD or smaller, just apply processing resolution
                    final_scale = ai_scale_factor
                
                # Scale frame for AI processing
                if final_scale != 1.0:
                    ai_h = int(original_h * final_scale)
                    ai_w = int(original_w * final_scale)
                    scaled_frame = cv2.resize(frame, (ai_w, ai_h))
                else:
                    scaled_frame = frame
                
                # Calculate inference size based on actual frame dimensions
                inference_h, inference_w = scaled_frame.shape[:2]
                inference_size = max(inference_h, inference_w)
                inference_size = ((inference_size + 31) // 32) * 32  # Round up to nearest 32
                
                # Time the AI inference
                inference_start = time.time()
                results = model.track(scaled_frame, imgsz=inference_size, 
                                    tracker=_TRACKER_CONFIG, 
                                    persist=True, 
                                    verbose=False)
                inference_time = time.time() - inference_start
                total_inference_time += inference_time
                
                # Process results immediately to avoid keeping tensors in memory
                filtered_detections = []
                for result in results:
                    if processing_settings.detection_type == "segmentation":
                        # Handle segmentation masks
                        if hasattr(result, 'masks') and result.masks is not None:
                            boxes = result.boxes
                            masks = result.masks
                            
                            # Check if tracking data is available
                            track_ids = None
                            if hasattr(boxes, 'id') and boxes.id is not None:
                                track_ids = boxes.id.int().cpu().tolist()
                            
                            for i, (box, mask) in enumerate(zip(boxes, masks)):
                                class_id = int(box.cls[0])
                                if class_id in processing_settings.yolo_classes:
                                    # Get mask data
                                    mask_array = mask.data[0].cpu().numpy()  # Shape: (H, W)
                                    
                                    # Scale mask back to original resolution if needed
                                    if final_scale != 1.0:
                                        mask_array = cv2.resize(
                                            mask_array.astype(np.uint8), 
                                            (original_w, original_h), 
                                            interpolation=cv2.INTER_NEAREST
                                        ).astype(bool)
                                    
                                    # Get bounding box for reference
                                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                                    if final_scale != 1.0:
                                        scale_back = 1.0 / final_scale
                                        x1, y1, x2, y2 = x1*scale_back, y1*scale_back, x2*scale_back, y2*scale_back
                                    
                                    # Get track ID if available
                                    track_id = track_ids[i] if track_ids and i < len(track_ids) else None
                                    
                                    filtered_detections.append({
                                        'type': 'segmentation',
                                        'mask': mask_array,
                                        'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                        'class_id': class_id,
                                        'confidence': float(box.conf[0]),
                                        'track_id': track_id
                                    })
                                    objects_detected += 1
                    else:
                        # Handle bounding box detection
                        boxes = result.boxes
                        if boxes is not None:
                            # Check if tracking data is available
                            track_ids = None
                            if hasattr(boxes, 'id') and boxes.id is not None:
                                track_ids = boxes.id.int().cpu().tolist()
                            
                            for i, box in enumerate(boxes):
                                class_id = int(box.cls[0])
                                if class_id in processing_settings.yolo_classes:
                                    # Scale coordinates back to original resolution
                                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                                    if final_scale != 1.0:
                                        scale_back = 1.0 / final_scale
                                        x1, y1, x2, y2 = x1*scale_back, y1*scale_back, x2*scale_back, y2*scale_back
                                    
                                    # Get track ID if available
                                    track_id = track_ids[i] if track_ids and i < len(track_ids) else None
                                    
                                    filtered_detections.append({
                                        'type': 'bbox',
                                        'bbox': [int(x1), int(y1), int(x2), int(y2)],
                                        'class_id': class_id,
                                        'confidence': float(box.conf[0]),
                                        'track_id': track_id
                                    })
                                    objects_detected += 1
                
                # Apply hood detection filter if enabled
                if processing_settings.enable_hood_detection:
                    # Filter out detections that are likely car hoods
                    pre_filter_count = len(filtered_detections)
                    filtered_detections = [
                        detection for detection in filtered_detections
                        if not is_hood_detection(detection, original_w, original_h)
                    ]
                    filtered_count = pre_filter_count - len(filtered_detections)
                    if filtered_count > 0:
                        self.logger.debug("Hood detection filter applied", 
                                        frame_number=frame_number,
                                        detections_filtered=filtered_count,
                                        remaining_detections=len(filtered_detections))
                
                # Use filtered detections directly (after optional hood filtering)
                detections = filtered_detections
                
                # Explicitly clean up YOLO results to free GPU/CPU memory
                if 'results' in locals():
                    for result in results:
                        if hasattr(result, 'boxes') and result.boxes is not None:
                            # Clear boxes tensor data
                            if hasattr(result.boxes, 'data'):
                                del result.boxes.data
                            if hasattr(result.boxes, 'orig_shape'):
                                del result.boxes.orig_shape
                            del result.boxes
                        if hasattr(result, 'masks') and result.masks is not None:
                            # Clear masks tensor data
                            if hasattr(result.masks, 'data'):
                                del result.masks.data
                            if hasattr(result.masks, 'orig_shape'):
                                del result.masks.orig_shape
                            del result.masks
                        # Clear any other tensor data
                        if hasattr(result, 'keypoints') and result.keypoints is not None:
                            del result.keypoints
                        if hasattr(result, 'probs') and result.probs is not None:
                            del result.probs
                        if hasattr(result, 'obb') and result.obb is not None:
                            del result.obb
                    del results
                
                # Explicitly delete frame references to free memory immediately
                del frame
                if 'scaled_frame' in locals():
                    del scaled_frame
                
                # Force garbage collection every 100 frames to free memory more aggressively
                if frames_processed % 100 == 0:
                    gc.collect()
                
                # Flow control: Non-blocking queue operations with immediate feedback
                queue_attempts = 0
                while not stop_event.is_set():
                    try:
                        # Try non-blocking put first
                        if not output_queue.full():
                            output_queue.put((frame_number, detections), block=False)
                            frames_processed += 1
                            
                            # Note: We don't clean up filtered_detections here because
                            # the hood tracker returns references to the same objects.
                            # Masks will be cleaned up by the blur thread after use.
                            del filtered_detections
                            
                            self.logger.info("AI_FRAME", 
                                            thread="AI", 
                                            frame_number=frame_number, 
                                            frames_processed=frames_processed,
                                            objects_detected=objects_detected,
                                            detection_queue_size=output_queue.qsize(),
                                            detections_count=len(detections),
                                            timestamp=time.time())
                            
                            break
                        else:
                            # Queue is full, use adaptive wait with immediate feedback
                            queue_attempts += 1
                            if queue_attempts <= 10:  # Brief waits for first 10 attempts
                                time.sleep(0.01)  # 10ms
                            elif queue_attempts <= 50:  # Medium waits for next 40 attempts
                                time.sleep(0.05)  # 50ms
                            else:  # Longer waits after 50 attempts
                                time.sleep(0.1)  # 100ms
                    except Full:
                        # Explicit queue full handling
                        queue_attempts += 1
                        if queue_attempts <= 10:
                            time.sleep(0.01)  # 10ms
                        elif queue_attempts <= 50:
                            time.sleep(0.05)  # 50ms
                        else:
                            time.sleep(0.1)  # 100ms
                    except Exception as e:
                        # Other exceptions (should be rare)
                        self.logger.warning("AI thread queue put error", error=str(e))
                        time.sleep(0.1)
                
                frame_number += 1
            
            cap.release()
            
            # Signal end of processing with non-blocking approach
            signal_attempts = 0
            while not stop_event.is_set():
                try:
                    if not output_queue.full():
                        output_queue.put((None, None), block=False)
                        break
                    else:
                        signal_attempts += 1
                        if signal_attempts <= 10:
                            time.sleep(0.01)  # 10ms
                        elif signal_attempts <= 50:
                            time.sleep(0.05)  # 50ms
                        else:
                            time.sleep(0.1)  # 100ms
                except Full:
                    signal_attempts += 1
                    if signal_attempts <= 10:
                        time.sleep(0.01)
                    elif signal_attempts <= 50:
                        time.sleep(0.05)
                    else:
                        time.sleep(0.1)
                except Exception as e:
                    self.logger.warning("AI thread signal end error", error=str(e))
                    time.sleep(0.1)
            
            # Store timing results
            total_time = time.time() - start_time
            self.thread_timings['ai_time'] = total_time
            self.thread_timings['total_inference_time'] = total_inference_time
            self.thread_timings['total_frame_decode_time'] = total_frame_decode_time
            
            self.logger.info("AI thread completed", 
                           frames_processed=frames_processed,
                           objects_detected=objects_detected,
                           total_time=total_time,
                           inference_time=total_inference_time,
                           frame_decode_time=total_frame_decode_time)
            
            return {
                'frames_processed': frames_processed,
                'objects_detected': objects_detected,
                'ai_time': total_time,
                'total_inference_time': total_inference_time,
                'total_frame_decode_time': total_frame_decode_time
            }
            
        except Exception as e:
            self.logger.error("AI thread error", error=str(e))
            stop_event.set()
            return {
                'frames_processed': 0,
                'objects_detected': 0,
                'ai_time': 0.0,
                'total_inference_time': 0.0,
                'total_frame_decode_time': 0.0,
                'error': str(e)
            }
        finally:
            if 'cap' in locals():
                cap.release()
