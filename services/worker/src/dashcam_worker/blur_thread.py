"""
Blur thread module.

Contains the blur thread implementation for video processing pipeline.
Handles frame decoding, blur application with temporal stability, and detection buffer management.
"""

import threading
import time
import gc
import numpy as np
from typing import Dict, Any, List, Tuple
from queue import Queue, Empty
import structlog
import cv2

from .models import ProcessingSettings
from .temporal_stability import TemporalStabilizer, MaskTemporalStabilizer


class BlurThread:
    """
    Blur thread implementation for video processing pipeline.
    
    Handles frame decoding, blur application with temporal stability, and flow control.
    """
    
    def __init__(self, config, queue_timeout: float = 0.1, temporal_lookahead_frames: int = 60):
        """
        Initialize blur thread.
        
        Args:
            config: Configuration object
            queue_timeout: Timeout for queue operations in seconds
            temporal_lookahead_frames: Number of frames to look ahead for temporal stability
        """
        self.config = config
        self.queue_timeout = queue_timeout
        self.temporal_lookahead_frames = temporal_lookahead_frames
        self.logger = structlog.get_logger("blur_thread")
        
        # Initialize temporal stabilizers (will be configured per-task)
        self.temporal_stabilizer = None
        self.mask_stabilizer = None
        
        # Timing stats
        self.thread_timings = {
            'blur_time': 0.0,
            'total_frame_blur_time': 0.0,
            'total_frame_decode_time': 0.0
        }
    
    def run(self, input_path: str, input_queue: Queue, output_queue: Queue,
            processing_settings: ProcessingSettings, video_info: Dict[str, Any], 
            stop_event: threading.Event) -> Dict[str, Any]:
        """
        Run the blur thread.
        
        Args:
            input_path: Path to input video file
            input_queue: Queue containing detection data from AI thread
            output_queue: Queue for blurred frames to encoder thread
            processing_settings: Processing configuration
            video_info: Video information dictionary
            stop_event: Threading event to signal stop
            
        Returns:
            Dictionary containing processing statistics
        """
        start_time = time.time()
        total_frame_blur_time = 0.0
        total_frame_decode_time = 0.0
        
        try:
            frames_processed = 0
            total_frames = video_info['frame_count']
            
            # Initialize temporal stabilizers based on processing settings
            if processing_settings.temporal_stability_enabled:
                self.temporal_stabilizer = TemporalStabilizer(
                    track_history_length=min(self.temporal_lookahead_frames, 30),
                    interpolation_max_gap=processing_settings.temporal_stability_max_gap,
                    confidence_threshold=processing_settings.temporal_stability_confidence_threshold,
                    spatial_threshold=processing_settings.temporal_stability_spatial_threshold,
                    detection_type=processing_settings.detection_type
                )
                
                # Configure enhanced validation parameters
                self.temporal_stabilizer.max_velocity_change = processing_settings.temporal_stability_max_velocity_change
                self.temporal_stabilizer.max_spatial_drift = processing_settings.temporal_stability_max_spatial_drift
                self.temporal_stabilizer.class_consistency_required = processing_settings.temporal_stability_class_consistency
                self.temporal_stabilizer.min_overlap_threshold = processing_settings.temporal_stability_duplicate_merge_threshold
                
                # Configure hybrid approach parameters for single-frame gaps
                self.temporal_stabilizer.single_frame_gap_confidence = 0.85  # High confidence for single-frame gaps
                self.temporal_stabilizer.stationary_velocity_threshold = 8.0  # Pixels per frame for stationary objects
                self.temporal_stabilizer.stationary_persistence_frames = 5  # Extra frames to persist stationary objects
                self.temporal_stabilizer.immediate_interpolation = True  # Enable immediate interpolation
                self.temporal_stabilizer.spatial_continuity_threshold = 60.0  # Spatial overlap for immediate interpolation
                
                # Configure duration filtering for blur flickering prevention
                self.temporal_stabilizer.configure_duration_filtering(processing_settings)
                
                self.mask_stabilizer = MaskTemporalStabilizer(
                    max_mask_history=3  # Keep memory usage low
                )
                
                self.logger.info("Enhanced temporal stability enabled", 
                               max_gap=processing_settings.temporal_stability_max_gap,
                               confidence_threshold=processing_settings.temporal_stability_confidence_threshold,
                               spatial_threshold=processing_settings.temporal_stability_spatial_threshold,
                               max_velocity_change=processing_settings.temporal_stability_max_velocity_change,
                               max_spatial_drift=processing_settings.temporal_stability_max_spatial_drift,
                               class_consistency=processing_settings.temporal_stability_class_consistency,
                               duplicate_merge_threshold=processing_settings.temporal_stability_duplicate_merge_threshold)
            else:
                self.temporal_stabilizer = None
                self.mask_stabilizer = None
                self.logger.info("Temporal stability disabled")
            
            # Open video capture for this thread
            cap = cv2.VideoCapture(input_path)
            
            # Detection buffer: frame_number -> detections
            detection_buffer = {}
            ai_finished = False
            
            self.logger.info("Blur thread started", 
                           total_frames=total_frames,
                           temporal_lookahead=self.temporal_lookahead_frames)
            
            # First, collect detection data from AI thread
            while not stop_event.is_set():
                try:
                    frame_number, detections = input_queue.get(timeout=self.queue_timeout)
                    
                    if frame_number is None:  # AI thread finished
                        ai_finished = True
                        self.logger.info("Blur thread: AI processing finished", 
                                       detection_buffer_size=len(detection_buffer))
                        break
                    
                    detection_buffer[frame_number] = detections
                    
                    # Clean up old detection buffer entries during initial collection
                    if len(detection_buffer) > self.temporal_lookahead_frames + 20:
                        oldest_frame = min(detection_buffer.keys())
                        # Just remove the entry - masks will be cleaned up after blur operation
                        del detection_buffer[oldest_frame]
                    
                    # Check if we have enough lookahead frames or if we have all frames
                    current_frame = min(detection_buffer.keys()) if detection_buffer else 0
                    max_buffered_frame = max(detection_buffer.keys()) if detection_buffer else 0
                    
                    # Start processing when we have enough lookahead or AI is done
                    if (max_buffered_frame - current_frame >= self.temporal_lookahead_frames) or ai_finished:
                        break
                        
                except Empty:
                    continue
                except Exception as e:
                    self.logger.error("Blur thread buffer collection error", error=str(e))
                    break
            
            # Process all frames with sequential reading (like AI thread)
            frame_number = 0
            while not stop_event.is_set() and frame_number < total_frames:
                # Decode frame sequentially (no seeking)
                frame_start = time.time()
                ret, frame = cap.read()
                frame_decode_time = time.time() - frame_start
                total_frame_decode_time += frame_decode_time
                
                if not ret:
                    self.logger.warning("Blur thread: Could not decode frame", frame_number=frame_number)
                    frame_number += 1
                    continue
                
                # If we don't have detection data for this frame and AI is not finished, wait
                while frame_number not in detection_buffer and not ai_finished and not stop_event.is_set():
                    try:
                        new_frame_number, detections = input_queue.get(timeout=self.queue_timeout)
                        if new_frame_number is None:
                            ai_finished = True
                            break
                        else:
                            detection_buffer[new_frame_number] = detections
                    except Empty:
                        continue
                
                # Get detections for this frame (or empty if none)
                detections = detection_buffer.get(frame_number, [])
                
                # Apply temporal stability to detections if enabled
                if self.temporal_stabilizer is not None:
                    # Pass mask stabilizer reference to temporal stabilizer for mask generation
                    stabilized_detections = self.temporal_stabilizer.stabilize_detections(
                        frame_number, detections, detection_buffer, self.mask_stabilizer
                    )
                    
                    # Update mask history for segmentation detections
                    for detection in stabilized_detections:
                        track_id = detection.get('track_id')
                        if (track_id is not None and 
                            detection.get('type') == 'segmentation' and 
                            'mask' in detection):
                            # Update history with both real and interpolated detections
                            # This ensures temporal continuity for multi-frame gaps
                            self.mask_stabilizer.update_mask_history(
                                track_id, detection['mask'], detection['bbox']
                            )
                else:
                    # No temporal stability, use original detections
                    stabilized_detections = detections
                
                # Apply blurring with stabilized detections
                blur_start = time.time()
                if stabilized_detections:
                    blurred_frame = self._apply_blur(frame, stabilized_detections, processing_settings)
                else:
                    blurred_frame = frame.copy()  # Always create a copy for consistency
                blur_time = time.time() - blur_start
                total_frame_blur_time += blur_time
                
                # Clean up detection masks AFTER blur operation is complete
                if stabilized_detections:
                    for detection in stabilized_detections:
                        if 'mask' in detection:
                            del detection['mask']
                
                # Flow control: Non-blocking queue operations with immediate feedback
                queue_attempts = 0
                while not stop_event.is_set():
                    try:
                        # Try non-blocking put first
                        if not output_queue.full():
                            output_queue.put((frame_number, blurred_frame), block=False)
                            frames_processed += 1
                            
                            self.logger.info("BLUR_FRAME", 
                                            thread="Blur", 
                                            frame_number=frame_number, 
                                            frames_processed=frames_processed,
                                            input_queue_size=input_queue.qsize(),
                                            output_queue_size=output_queue.qsize(),
                                            detections_count=len(stabilized_detections),
                                            original_detections=len(detections),
                                            interpolated_count=sum(1 for d in stabilized_detections if d.get('interpolated', False)) if self.temporal_stabilizer else 0,
                                            smoothed_count=sum(1 for d in stabilized_detections if d.get('smoothed', False)) if self.temporal_stabilizer else 0,
                                            temporal_stability_enabled=self.temporal_stabilizer is not None,
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
                    except Exception as e:
                        # Other exceptions (should be rare)
                        self.logger.warning("Blur thread queue put error", error=str(e))
                        time.sleep(0.1)
                
                # Clean up detection buffer entries that are no longer needed
                # Remove detection data for frames that are far behind current frame
                if frame_number % 10 == 0:  # Cleanup every 10 frames instead of every frame
                    frames_to_remove = [f for f in detection_buffer.keys() if f < frame_number - 5]
                    for f in frames_to_remove:
                        # Just remove the entry - masks were already cleaned up after blur operation
                        del detection_buffer[f]
                    
                    # Clean up mask stabilizer for inactive tracks
                    if self.mask_stabilizer is not None:
                        active_track_ids = {d.get('track_id') for d in stabilized_detections if d.get('track_id') is not None}
                        self.mask_stabilizer.cleanup_old_masks(active_track_ids)
                    
                    # Clean up trajectory histories for inactive tracks
                    if self.temporal_stabilizer is not None:
                        active_track_ids = {d.get('track_id') for d in stabilized_detections if d.get('track_id') is not None}
                        self.temporal_stabilizer.cleanup_old_trajectories(active_track_ids)
                
                # Explicitly delete frame references to free memory immediately
                del frame
                if 'blurred_frame' in locals():
                    del blurred_frame
                
                # Force garbage collection every 100 frames to free memory
                if frames_processed % 100 == 0:
                    gc.collect()
                
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
                except Exception as e:
                    self.logger.warning("Blur thread signal end error", error=str(e))
                    time.sleep(0.1)
            
            # Store timing results
            total_time = time.time() - start_time
            self.thread_timings['blur_time'] = total_time
            self.thread_timings['total_frame_blur_time'] = total_frame_blur_time
            self.thread_timings['total_frame_decode_time'] = total_frame_decode_time
            
            # Get temporal stability statistics
            stability_stats = self.temporal_stabilizer.get_statistics() if self.temporal_stabilizer else {}
            
            self.logger.info("Blur thread completed", 
                           frames_processed=frames_processed,
                           total_time=total_time,
                           frame_blur_time=total_frame_blur_time,
                           frame_decode_time=total_frame_decode_time,
                           temporal_stability_enabled=self.temporal_stabilizer is not None,
                           temporal_stability_stats=stability_stats)
            
            return {
                'frames_processed': frames_processed,
                'blur_time': total_time,
                'total_frame_blur_time': total_frame_blur_time,
                'total_frame_decode_time': total_frame_decode_time,
                'temporal_stability_stats': stability_stats
            }
            
        except Exception as e:
            self.logger.error("Blur thread error", error=str(e))
            stop_event.set()
            return {
                'frames_processed': 0,
                'blur_time': 0.0,
                'total_frame_blur_time': 0.0,
                'total_frame_decode_time': 0.0,
                'error': str(e)
            }
        finally:
            if 'cap' in locals():
                cap.release()
    
    def _apply_blur(self, frame: np.ndarray, detections: List[Dict[str, Any]],
                   processing_settings: ProcessingSettings) -> np.ndarray:
        """Apply blurring to detected objects using either bounding boxes or segmentation masks.
        
        Enhanced implementation with size-dependent blur and temporal stability support:
        - New: Size-dependent blur where smaller objects get less blur, larger objects get more blur
        - Handles interpolated detections from temporal stabilizer
        - Supports mask transformation for interpolated segmentation
        - Single blur operation with alpha blending for size-dependent approach
        - Legacy boolean mask approach available as fallback
        - Debug mode adds visual annotations with blur intensity info
        
        Size-dependent blur approach:
        - Creates grayscale mask where blur intensity depends on object height
        - 0 height = 0 blur, 10% of frame height = full blur (configurable)
        - Overlapping objects use maximum blur intensity
        - Alpha blending between original and fully blurred frame
        """
        if not detections:
            return frame
        
        height, width = frame.shape[:2]
        blur_kernel = (processing_settings.blur_intensity, processing_settings.blur_intensity)
        
        # Check if size-dependent blur is enabled
        size_scaling_enabled = getattr(processing_settings, 'blur_size_scaling_enabled', True)
        
        if size_scaling_enabled:
            # Use new size-dependent blur approach
            blur_mask = self._build_size_dependent_mask(detections, (height, width), processing_settings)
            
            # Log blur intensity statistics
            if np.any(blur_mask):
                unique_intensities = np.unique(blur_mask[blur_mask > 0])
                max_height_ratio = getattr(processing_settings, 'blur_size_scaling_max_height_ratio', 0.10)
                
                self.logger.debug("Size-dependent blur applied",
                                total_detections=len(detections),
                                unique_blur_intensities=len(unique_intensities),
                                max_blur_intensity=int(np.max(blur_mask)),
                                min_blur_intensity=int(np.min(blur_mask[blur_mask > 0])) if np.any(blur_mask) else 0,
                                max_height_ratio=max_height_ratio,
                                blur_pixel_count=int(np.sum(blur_mask > 0)))
            
            # Apply blending if there are any pixels to blur
            if np.any(blur_mask):
                # Smooth the mask edges to prevent hard transitions
                smoothed_blur_mask = cv2.GaussianBlur(blur_mask.astype(np.float32), (25, 25), 0)
                # Convert back to uint8 range
                smoothed_blur_mask = (smoothed_blur_mask).astype(np.uint8)
                
                # Create blurred version of the entire frame
                blurred_full_frame = cv2.GaussianBlur(frame, blur_kernel, 0)
                # Apply alpha blending based on smoothed grayscale mask
                blurred_frame = self._apply_alpha_blending(frame, blurred_full_frame, smoothed_blur_mask)
                # Clean up intermediate blurred frame
                del blurred_full_frame
            else:
                # No blur needed, but still create a copy for consistency
                blurred_frame = frame.copy()
        else:
            # Legacy approach: boolean mask with size filtering
            detections_to_blur = []
            small_objects_filtered = 0
            
            # Check if size filtering is enabled
            if getattr(processing_settings, 'blur_size_filtering_enabled', True):
                # Get minimum size threshold (default 3% of frame height)
                min_height_threshold = getattr(processing_settings, 'blur_minimum_object_height_ratio', 0.03)
                min_height_pixels = height * min_height_threshold
                
                for detection in detections:
                    bbox = detection['bbox']
                    object_height = bbox[3] - bbox[1]  # y2 - y1
                    
                    if object_height >= min_height_pixels:
                        detections_to_blur.append(detection)
                    else:
                        small_objects_filtered += 1
                
                # Log size filtering if any objects were filtered
                if small_objects_filtered > 0:
                    self.logger.debug("Legacy size filtering applied", 
                                    total_detections=len(detections),
                                    detections_to_blur=len(detections_to_blur),
                                    small_objects_filtered=small_objects_filtered,
                                    min_height_threshold=min_height_threshold,
                                    min_height_pixels=min_height_pixels)
            else:
                # Size filtering disabled, blur all detections
                detections_to_blur = detections
            
            # Create boolean blur mask (legacy approach)
            blur_mask = np.zeros((height, width), dtype=bool)
            
            # Build combined mask from detections that meet size threshold
            for detection in detections_to_blur:
                track_id = detection.get('track_id')
                is_interpolated = detection.get('interpolated', False)
                
                if detection.get('type') == 'segmentation' and 'mask' in detection:
                    # Use provided segmentation mask
                    mask = detection['mask']
                    
                    # Ensure mask is correct size
                    if mask.shape[:2] != (height, width):
                        mask = cv2.resize(mask.astype(np.uint8), 
                                        (width, height), 
                                        interpolation=cv2.INTER_NEAREST).astype(bool)
                    
                    blur_mask |= mask
                    
                elif (detection.get('type') == 'segmentation' and 
                      is_interpolated and 
                      track_id is not None and
                      self.mask_stabilizer is not None):
                    # Try to get interpolated mask from mask stabilizer
                    interpolated_mask = self.mask_stabilizer.get_interpolated_mask(
                        track_id, detection['bbox'], width, height
                    )
                    
                    if interpolated_mask is not None:
                        # Use interpolated mask
                        blur_mask |= interpolated_mask
                    else:
                        # In segmentation mode, skip interpolated detections without mask data
                        continue
                else:
                    # Use bounding box as mask
                    x1, y1, x2, y2 = detection['bbox']
                    
                    # Clamp coordinates to frame boundaries
                    x1, y1 = max(0, int(x1)), max(0, int(y1))
                    x2, y2 = min(width, int(x2)), min(height, int(y2))
                    
                    # Add bounding box region to mask
                    if x2 > x1 and y2 > y1:  # Valid bounding box
                        blur_mask[y1:y2, x1:x2] = True
            
            # Apply blur only once to all masked regions (legacy approach)
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
                # No blur needed, but still create a copy for consistency
                blurred_frame = frame.copy()
        
        # Add debug annotations if enabled
        if processing_settings.debug_mode:
            # For size-dependent blur, calculate blur intensities for debug annotations
            if size_scaling_enabled:
                # Calculate blur intensities for all detections for debug display
                max_height_ratio = getattr(processing_settings, 'blur_size_scaling_max_height_ratio', 0.10)
                debug_blur_intensities = {}
                for detection in detections:
                    track_id = detection.get('track_id')
                    if track_id is not None:
                        bbox = detection['bbox']
                        object_height = bbox[3] - bbox[1]  # y2 - y1
                        blur_intensity = self._calculate_blur_intensity(object_height, height, max_height_ratio)
                        debug_blur_intensities[track_id] = blur_intensity
                
                blurred_frame = self._add_debug_annotations(blurred_frame, detections, processing_settings, 
                                                          debug_blur_intensities=debug_blur_intensities)
            else:
                # Legacy debug annotations with blur/no-blur indication
                blurred_track_ids = {d.get('track_id') for d in detections_to_blur if d.get('track_id') is not None}
                blurred_frame = self._add_debug_annotations(blurred_frame, detections, processing_settings, 
                                                          blurred_track_ids=blurred_track_ids)
        
        return blurred_frame
    
    def _calculate_blur_intensity(self, object_height: float, frame_height: float, max_height_ratio: float) -> int:
        """Calculate blur intensity (0-255) based on object height.
        
        Args:
            object_height: Height of the object in pixels
            frame_height: Height of the frame in pixels
            max_height_ratio: Height ratio for full blur intensity (default 0.10)
            
        Returns:
            Blur intensity value from 0 to 255
        """
        if frame_height <= 0 or max_height_ratio <= 0:
            return 255  # Full blur as fallback
        
        height_ratio = object_height / frame_height
        blur_intensity = min(255, int((height_ratio / max_height_ratio) * 255))
        return max(0, blur_intensity)  # Ensure non-negative
    
    def _build_size_dependent_mask(self, detections: List[Dict[str, Any]], frame_shape: Tuple[int, int], 
                                 processing_settings: ProcessingSettings) -> np.ndarray:
        """Build grayscale mask where blur intensity depends on object size.
        
        Args:
            detections: List of detection dictionaries
            frame_shape: (height, width) of the frame
            processing_settings: Processing configuration
            
        Returns:
            Grayscale mask (uint8) where 0=no blur, 255=full blur
        """
        height, width = frame_shape
        blur_mask = np.zeros((height, width), dtype=np.uint8)
        
        # Get configuration
        max_height_ratio = getattr(processing_settings, 'blur_size_scaling_max_height_ratio', 0.10)
        
        for detection in detections:
            bbox = detection['bbox']
            object_height = bbox[3] - bbox[1]  # y2 - y1
            track_id = detection.get('track_id')
            is_interpolated = detection.get('interpolated', False)
            
            # Calculate blur intensity based on object size
            blur_intensity = self._calculate_blur_intensity(object_height, height, max_height_ratio)
            
            if blur_intensity == 0:
                continue  # Skip objects that don't need any blur
            
            if detection.get('type') == 'segmentation' and 'mask' in detection:
                # Use provided segmentation mask
                mask = detection['mask']
                
                # Ensure mask is correct size
                if mask.shape[:2] != (height, width):
                    mask = cv2.resize(mask.astype(np.uint8), 
                                    (width, height), 
                                    interpolation=cv2.INTER_NEAREST).astype(bool)
                
                # Fill mask regions with blur intensity, using maximum for overlaps
                blur_mask[mask] = np.maximum(blur_mask[mask], blur_intensity)
                
            elif (detection.get('type') == 'segmentation' and 
                  is_interpolated and 
                  track_id is not None and
                  self.mask_stabilizer is not None):
                # Try to get interpolated mask from mask stabilizer
                interpolated_mask = self.mask_stabilizer.get_interpolated_mask(
                    track_id, detection['bbox'], width, height
                )
                
                if interpolated_mask is not None:
                    # Use interpolated mask with calculated blur intensity
                    blur_mask[interpolated_mask] = np.maximum(blur_mask[interpolated_mask], blur_intensity)
                else:
                    # In segmentation mode, skip interpolated detections without mask data
                    continue
            else:
                # Use bounding box as mask
                x1, y1, x2, y2 = bbox
                
                # Clamp coordinates to frame boundaries
                x1, y1 = max(0, int(x1)), max(0, int(y1))
                x2, y2 = min(width, int(x2)), min(height, int(y2))
                
                if x2 > x1 and y2 > y1:  # Valid bounding box
                    # Fill bounding box region with blur intensity, using maximum for overlaps
                    blur_mask[y1:y2, x1:x2] = np.maximum(blur_mask[y1:y2, x1:x2], blur_intensity)
        
        return blur_mask
    
    def _apply_alpha_blending(self, original_frame: np.ndarray, blurred_frame: np.ndarray, 
                            blur_mask: np.ndarray) -> np.ndarray:
        """Apply alpha blending between original and blurred frames based on grayscale mask.
        
        Args:
            original_frame: Original frame
            blurred_frame: Fully blurred frame
            blur_mask: Grayscale mask (0-255) where 0=no blur, 255=full blur
            
        Returns:
            Blended frame
        """
        # Normalize mask to 0-1 range for blending
        normalized_mask = blur_mask.astype(np.float32) / 255.0
        
        # Add channel dimension if needed (for broadcasting)
        if len(normalized_mask.shape) == 2:
            normalized_mask = normalized_mask[:, :, np.newaxis]
        
        # Apply alpha blending: result = original * (1 - alpha) + blurred * alpha
        blended_frame = (original_frame.astype(np.float32) * (1.0 - normalized_mask) + 
                        blurred_frame.astype(np.float32) * normalized_mask)
        
        return blended_frame.astype(np.uint8)
    
    def _add_debug_annotations(self, frame: np.ndarray, detections: List[Dict[str, Any]], 
                             processing_settings, blurred_track_ids: set = None, 
                             debug_blur_intensities: Dict[int, int] = None) -> np.ndarray:
        """Add debug annotations to frame showing detected objects.
        
        Enhanced to show temporal stability information and blur intensity:
        - Bounding boxes, class labels, confidence scores, and track IDs
        - Interpolated detections marked with different colors
        - Smoothed detections marked with different colors
        - Gap size for interpolated detections
        - Object trajectory visualization
        - Size filtering indicators (objects tracked but not blurred)
        - Blur intensity values for size-dependent blur
        """
        if blurred_track_ids is None:
            blurred_track_ids = set()
        if debug_blur_intensities is None:
            debug_blur_intensities = {}
            
        annotated_frame = frame.copy()
        
        # Draw trajectories first (behind bounding boxes)
        if processing_settings.debug_show_trajectories and self.temporal_stabilizer is not None:
            annotated_frame = self._draw_trajectories(annotated_frame, processing_settings)
        
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
        BBOX_COLOR = (0, 255, 0)      # Green for normal bbox
        SEG_COLOR = (255, 0, 0)       # Blue for segmentation
        INTERPOLATED_COLOR = (0, 255, 255)  # Yellow for interpolated
        SMOOTHED_COLOR = (255, 0, 255)      # Magenta for smoothed
        SIZE_FILTERED_COLOR = (128, 128, 128)  # Gray for size-filtered objects
        TEXT_COLOR = (255, 255, 255)  # White text
        
        for i, detection in enumerate(detections):
            x1, y1, x2, y2 = detection['bbox']
            class_id = detection.get('class_id', -1)
            confidence = detection.get('confidence', 0.0)
            track_id = detection.get('track_id')
            detection_type = detection.get('type', 'bbox')
            is_interpolated = detection.get('interpolated', False)
            is_smoothed = detection.get('smoothed', False)
            gap_size = detection.get('gap_size', 0)
            
            # Get blur intensity for this detection
            blur_intensity = debug_blur_intensities.get(track_id, None) if track_id is not None else None
            
            # Check if this object was filtered by size (tracked but not blurred) - for legacy mode
            is_size_filtered = track_id is not None and track_id not in blurred_track_ids
            
            # Choose color based on detection type and temporal stability
            if debug_blur_intensities and blur_intensity is not None:
                # Size-dependent blur mode: color-code by blur intensity
                if blur_intensity == 0:
                    color = SIZE_FILTERED_COLOR  # No blur
                elif blur_intensity < 85:  # < 33% intensity
                    color = (0, 255, 0)  # Green for light blur
                elif blur_intensity < 170:  # < 67% intensity
                    color = (0, 255, 255)  # Yellow for medium blur
                else:  # >= 67% intensity
                    color = (0, 0, 255)  # Red for heavy blur
            elif is_size_filtered:
                color = SIZE_FILTERED_COLOR
            elif is_interpolated:
                color = INTERPOLATED_COLOR
            elif is_smoothed:
                color = SMOOTHED_COLOR
            elif detection_type == 'segmentation':
                color = SEG_COLOR
            else:
                color = BBOX_COLOR
            
            # Draw bounding box with thicker line for interpolated detections
            line_thickness = 3 if is_interpolated else 2
            cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, line_thickness)
            
            # Prepare label text
            class_name = COCO_CLASSES.get(class_id, f'class_{class_id}')
            label_parts = [class_name]
            
            if confidence > 0:
                label_parts.append(f'{confidence:.2f}')
            
            if track_id is not None:
                label_parts.append(f'ID:{track_id}')
            
            # Add temporal stability indicators
            if is_interpolated:
                if detection.get('single_frame_gap', False):
                    label_parts.append('SFG')  # Single Frame Gap
                elif detection.get('immediate_interpolation', False):
                    label_parts.append('IMMED')  # Immediate interpolation
                else:
                    label_parts.append('INTERP')  # Regular interpolation
                    
                if gap_size > 0:
                    label_parts.append(f'G:{gap_size}')
                
                # Show spatial drift for interpolated detections
                spatial_drift = detection.get('spatial_drift', 0)
                if spatial_drift > 0:
                    label_parts.append(f'D:{spatial_drift:.0f}')
                
                # Show if object is stationary
                if detection.get('stationary', False):
                    label_parts.append('STAT')
                    
            elif is_smoothed:
                label_parts.append('SMOOTH')
            
            # Show if detection was merged from duplicates
            if detection.get('merged', False):
                merge_count = detection.get('merge_count', 0)
                label_parts.append(f'M:{merge_count}')
            
            # Show if object was filtered by size (tracked but not blurred) - for legacy mode
            if is_size_filtered:
                object_height = y2 - y1
                label_parts.append(f'SIZE_FILT:{object_height}px')
            
            # Show blur intensity for size-dependent blur mode
            if debug_blur_intensities and blur_intensity is not None:
                label_parts.append(f'BLUR:{blur_intensity}')
            
            if detection_type == 'segmentation':
                label_parts.append('SEG')
            
            label = ' '.join(label_parts)
            
            # Calculate text size and position
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
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

    def _draw_trajectories(self, frame: np.ndarray, processing_settings) -> np.ndarray:
        """Draw object trajectories on the frame."""
        if self.temporal_stabilizer is None:
            return frame
        
        # Get all trajectory data
        trajectories = self.temporal_stabilizer.get_all_trajectories()
        
        if not trajectories:
            return frame
        
        # Generate colors for each track
        trajectory_colors = self._generate_trajectory_colors(list(trajectories.keys()))
        
        for track_id, trajectory in trajectories.items():
            if len(trajectory) < 2:
                continue  # Need at least 2 points for a line
            
            # Limit trajectory length for performance and visual clarity
            max_points = processing_settings.debug_trajectory_length
            if len(trajectory) > max_points:
                trajectory = trajectory[-max_points:]
            
            color = trajectory_colors[track_id]
            
            # Draw trajectory lines
            for i in range(1, len(trajectory)):
                prev_frame, prev_x, prev_y = trajectory[i-1]
                curr_frame, curr_x, curr_y = trajectory[i]
                
                # Apply fade effect if enabled
                if processing_settings.debug_trajectory_fade:
                    # Fade based on how old the point is
                    fade_factor = i / len(trajectory)
                    faded_color = tuple(int(c * fade_factor) for c in color)
                else:
                    faded_color = color
                
                # Draw line segment
                cv2.line(frame, 
                        (int(prev_x), int(prev_y)), 
                        (int(curr_x), int(curr_y)), 
                        faded_color, 2)
            
            # Draw trajectory end point (current position)
            if trajectory:
                _, end_x, end_y = trajectory[-1]
                cv2.circle(frame, (int(end_x), int(end_y)), 4, color, -1)
        
        return frame
    
    def _generate_trajectory_colors(self, track_ids: List[int]) -> Dict[int, Tuple[int, int, int]]:
        """Generate distinct colors for trajectory visualization."""
        colors = {}
        
        # Predefined color palette for better visibility
        color_palette = [
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (255, 255, 0),  # Cyan
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Yellow
            (128, 0, 128),  # Purple
            (255, 165, 0),  # Orange
            (0, 128, 128),  # Teal
            (128, 128, 0),  # Olive
            (255, 192, 203), # Pink
            (173, 216, 230), # Light Blue
            (144, 238, 144), # Light Green
            (255, 182, 193), # Light Pink
            (221, 160, 221), # Plum
        ]
        
        # Assign colors to tracks based on track ID (not list index)
        for track_id in track_ids:
            # Use track ID modulo palette length for consistent color assignment
            color_index = track_id % len(color_palette)
            colors[track_id] = color_palette[color_index]
        
        return colors
