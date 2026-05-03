"""
Temporal stability module for video processing.

Provides temporal stability for object detection and tracking to ensure smooth,
consistent blurring across video frames by leveraging YOLO tracking IDs and
motion prediction algorithms.
"""

import time
from collections import deque
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import cv2
import structlog


class TemporalStabilizer:
    """
    Enhanced temporal stability manager with robust validation.
    
    Addresses YOLO tracking issues including:
    - Track ID fragmentation (same object getting multiple IDs)
    - Cross-class interpolation (car -> truck)
    - Spatial drift in interpolated detections
    - Duplicate detections with different classes
    """
    
    def __init__(self, 
                 track_history_length: int = 30,
                 interpolation_max_gap: int = 10,
                 confidence_threshold: float = 0.3,
                 spatial_threshold: float = 100.0,
                 detection_type: str = "bbox"):
        """
        Initialize temporal stabilizer.
        
        Args:
            track_history_length: Number of frames to keep in track history
            interpolation_max_gap: Maximum frames to interpolate missing tracks
            confidence_threshold: Minimum confidence for temporal blending
            spatial_threshold: Maximum pixel distance for spatial matching
            detection_type: "bbox" or "segmentation" - affects interpolation behavior
        """
        self.track_history_length = track_history_length
        self.interpolation_max_gap = interpolation_max_gap
        self.confidence_threshold = confidence_threshold
        self.spatial_threshold = spatial_threshold
        self.detection_type = detection_type
        
        # Trajectory storage for debug visualization
        self.trajectory_history = {}  # track_id -> deque of (frame_number, center_x, center_y)
        self.trajectory_max_length = 30  # Maximum trajectory points to store
        
        self.logger = structlog.get_logger("temporal_stabilizer")
        
        # Track history: track_id -> track data
        self.track_history: Dict[int, Dict[str, Any]] = {}
        
        # Recently lost tracks for interpolation
        self.orphaned_tracks: Dict[int, Dict[str, Any]] = {}
        
        # Spatial tracks for cross-reference (independent of YOLO track IDs)
        self.spatial_tracks: Dict[int, Dict[str, Any]] = {}
        self.next_spatial_id = 1
        
        # Enhanced validation parameters
        self.max_velocity_change = 50.0  # Max pixels per frame velocity change
        self.min_overlap_threshold = 0.1  # Minimum IoU for duplicate detection
        self.max_spatial_drift = 150.0  # Max pixel drift for interpolation
        self.class_consistency_required = True  # Only interpolate within same class
        
        # Hybrid approach parameters for better gap handling
        self.single_frame_gap_confidence = 0.8  # High confidence for single-frame gaps
        self.stationary_velocity_threshold = 10.0  # Pixels per frame for stationary objects
        self.stationary_persistence_frames = 5  # Extra frames to persist stationary objects
        self.immediate_interpolation = True  # Don't wait for orphaning, interpolate immediately
        self.spatial_continuity_threshold = 80.0  # Spatial overlap for immediate interpolation
        
        # Smoothing factors for different detection parameters
        self.smoothing_factors = {
            'bbox': 0.7,     # Bbox coordinate smoothing
            'confidence': 0.8,  # Confidence smoothing
            'position': 0.6,    # Position smoothing
        }
        
        # Track duration tracking for blur flickering prevention
        self.track_durations = {}  # track_id -> first_frame_seen
        self.minimum_blur_duration = 4  # Frames (configurable)
        self.duration_filtering_enabled = True  # Enable/disable feature
        self.large_object_threshold = 0.15  # Objects larger than 15% bypass duration filter
        
        # Statistics
        self.stats = {
            'interpolated_detections': 0,
            'smoothed_detections': 0,
            'track_recoveries': 0,
            'spatial_matches': 0,
            'duplicate_detections_merged': 0,
            'cross_class_interpolations_blocked': 0,
            'spatial_drift_rejections': 0,
            'velocity_outliers_rejected': 0,
            'single_frame_gaps_filled': 0,
            'stationary_objects_persisted': 0,
            'immediate_interpolations': 0,
            'spatial_continuity_matches': 0,
            'short_tracks_filtered': 0,
            'tracks_promoted_to_blur': 0,
            'total_new_tracks': 0,
            'large_objects_bypassed': 0
        }
    
    def stabilize_detections(self, 
                           frame_number: int, 
                           detections: List[Dict[str, Any]],
                           detection_buffer: Dict[int, List[Dict[str, Any]]],
                           mask_stabilizer: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Apply enhanced temporal stability to detections.
        
        Args:
            frame_number: Current frame number
            detections: Current frame detections
            detection_buffer: Buffer of recent detections
            
        Returns:
            List of stabilized detections with robust validation
        """
        try:
            # Step 1: Pre-process detections to handle duplicates
            cleaned_detections = self._merge_duplicate_detections(detections)
            
            # Step 2: Update track duration tracking
            self._update_track_durations(frame_number, cleaned_detections)
            
            # Step 3: Get frame dimensions for size-based filtering
            frame_dims = self._get_frame_dimensions(detection_buffer)
            
            # Step 4: Filter out short-lived tracks to prevent blur flickering
            duration_filtered_detections = [
                detection for detection in cleaned_detections
                if self._should_blur_track(detection, frame_number, frame_dims)
            ]
            
            # Step 5: Update track histories with duration-filtered detections
            self._update_track_histories(frame_number, duration_filtered_detections)
            
            # Step 6: Update spatial tracks for cross-reference
            self._update_spatial_tracks(frame_number, duration_filtered_detections)
            
            # Step 7: Create stabilized detection list
            stabilized_detections = []
            
            # Step 8: Add current detections (with potential smoothing)
            for detection in duration_filtered_detections:
                stabilized_detection = self._smooth_detection(detection, frame_number)
                stabilized_detections.append(stabilized_detection)
            
            # Step 9: Look for missing tracks with robust validation
            interpolated_detections = self._interpolate_missing_tracks_robust(
                frame_number, duration_filtered_detections, detection_buffer, mask_stabilizer
            )
            
            # Step 10: Immediate spatial-based interpolation for single-frame gaps
            if self.immediate_interpolation:
                immediate_interpolations = self._immediate_spatial_interpolation(
                    frame_number, duration_filtered_detections, detection_buffer, mask_stabilizer
                )
                interpolated_detections.extend(immediate_interpolations)
            
            # Step 8: Add validated interpolated detections
            stabilized_detections.extend(interpolated_detections)
            
            # Step 8.5: Update track histories with interpolated detections for temporal continuity
            # This is critical for multi-frame gap handling
            if interpolated_detections:
                self._update_track_histories_with_interpolated(frame_number, interpolated_detections)
            
            # Step 9: Clean up old track data
            self._cleanup_old_tracks(frame_number)
            
            return stabilized_detections
            
        except Exception as e:
            self.logger.error("Enhanced temporal stabilization error", 
                            frame_number=frame_number, error=str(e))
            # Return original detections on error
            return detections
    
    def _merge_duplicate_detections(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge duplicate detections of the same object with different classes.
        
        Uses spatial overlap (IoU) to identify duplicates and keeps highest confidence.
        """
        if len(detections) <= 1:
            return detections
        
        merged_detections = []
        used_indices = set()
        
        for i, detection in enumerate(detections):
            if i in used_indices:
                continue
            
            # Find overlapping detections
            overlapping_detections = [detection]
            overlapping_indices = [i]
            
            for j, other_detection in enumerate(detections):
                if j <= i or j in used_indices:
                    continue
                
                # Calculate IoU
                iou = self._calculate_iou(detection['bbox'], other_detection['bbox'])
                
                if iou > self.min_overlap_threshold:
                    overlapping_detections.append(other_detection)
                    overlapping_indices.append(j)
            
            # If we found overlapping detections, merge them
            if len(overlapping_detections) > 1:
                merged_detection = self._merge_overlapping_detections(overlapping_detections)
                merged_detections.append(merged_detection)
                used_indices.update(overlapping_indices)
                self.stats['duplicate_detections_merged'] += len(overlapping_detections) - 1
            else:
                merged_detections.append(detection)
                used_indices.add(i)
        
        return merged_detections
    
    def _merge_overlapping_detections(self, detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple overlapping detections into a single detection.
        
        Prioritizes highest confidence detection but averages spatial properties.
        """
        # Sort by confidence (descending)
        sorted_detections = sorted(detections, key=lambda d: d.get('confidence', 0.0), reverse=True)
        
        # Use highest confidence detection as base
        merged_detection = sorted_detections[0].copy()
        
        # Average bounding boxes weighted by confidence
        total_confidence = sum(d.get('confidence', 0.0) for d in detections)
        
        if total_confidence > 0:
            weighted_bbox = [0, 0, 0, 0]
            for detection in detections:
                confidence = detection.get('confidence', 0.0)
                weight = confidence / total_confidence
                bbox = detection['bbox']
                for i in range(4):
                    weighted_bbox[i] += bbox[i] * weight
            
            merged_detection['bbox'] = [int(coord) for coord in weighted_bbox]
        
        # Mark as merged
        merged_detection['merged'] = True
        merged_detection['merge_count'] = len(detections)
        
        return merged_detection
    
    def _update_spatial_tracks(self, frame_number: int, detections: List[Dict[str, Any]]):
        """
        Update spatial tracks independent of YOLO track IDs.
        
        Creates robust spatial continuity tracking for cross-referencing.
        """
        for detection in detections:
            bbox = detection['bbox']
            centroid = self._get_bbox_centroid(bbox)
            class_id = detection.get('class_id', -1)
            
            # Find best matching spatial track
            best_spatial_id = None
            best_distance = float('inf')
            
            for spatial_id, spatial_track in self.spatial_tracks.items():
                if spatial_track['last_seen'] < frame_number - 5:  # Skip old tracks
                    continue
                
                if spatial_track['class_id'] != class_id:  # Class must match
                    continue
                
                last_centroid = spatial_track['centroids'][-1]
                distance = np.sqrt((centroid[0] - last_centroid[0])**2 + 
                                 (centroid[1] - last_centroid[1])**2)
                
                if distance < best_distance and distance < self.spatial_threshold:
                    best_distance = distance
                    best_spatial_id = spatial_id
            
            # Update existing spatial track or create new one
            if best_spatial_id is not None:
                spatial_track = self.spatial_tracks[best_spatial_id]
                spatial_track['centroids'].append(centroid)
                spatial_track['bboxes'].append(bbox)
                spatial_track['frame_numbers'].append(frame_number)
                spatial_track['last_seen'] = frame_number
                spatial_track['track_ids'].append(detection.get('track_id'))
            else:
                # Create new spatial track
                self.spatial_tracks[self.next_spatial_id] = {
                    'centroids': deque([centroid], maxlen=self.track_history_length),
                    'bboxes': deque([bbox], maxlen=self.track_history_length),
                    'frame_numbers': deque([frame_number], maxlen=self.track_history_length),
                    'track_ids': deque([detection.get('track_id')], maxlen=self.track_history_length),
                    'class_id': class_id,
                    'first_seen': frame_number,
                    'last_seen': frame_number
                }
                self.next_spatial_id += 1
    
    def _update_track_histories(self, frame_number: int, detections: List[Dict[str, Any]]):
        """Update track histories with current detections."""
        current_track_ids = set()
        
        for detection in detections:
            track_id = detection.get('track_id')
            if track_id is None:
                continue
            
            current_track_ids.add(track_id)
            
            # Initialize track history if needed
            if track_id not in self.track_history:
                self.track_history[track_id] = {
                    'bboxes': deque(maxlen=self.track_history_length),
                    'centroids': deque(maxlen=self.track_history_length),
                    'areas': deque(maxlen=self.track_history_length),
                    'confidences': deque(maxlen=self.track_history_length),
                    'frame_numbers': deque(maxlen=self.track_history_length),
                    'detection_types': deque(maxlen=self.track_history_length),
                    'class_ids': deque(maxlen=self.track_history_length),
                    'last_seen': frame_number,
                    'first_seen': frame_number
                }
            
            # Add detection to history
            track_data = self.track_history[track_id]
            bbox = detection['bbox']
            
            track_data['bboxes'].append(bbox)
            track_data['centroids'].append(self._get_bbox_centroid(bbox))
            track_data['areas'].append(self._get_bbox_area(bbox))
            track_data['confidences'].append(detection.get('confidence', 0.8))
            track_data['frame_numbers'].append(frame_number)
            track_data['detection_types'].append(detection.get('type', 'bbox'))
            track_data['class_ids'].append(detection.get('class_id', -1))
            track_data['last_seen'] = frame_number
            
            # Update trajectory history for debug visualization
            self._update_trajectory_history(track_id, frame_number, bbox)
            
            # Remove from orphaned tracks if recovered
            if track_id in self.orphaned_tracks:
                del self.orphaned_tracks[track_id]
                self.stats['track_recoveries'] += 1
        
        # Move missing tracks to orphaned
        for track_id, track_data in list(self.track_history.items()):
            if track_id not in current_track_ids:
                if track_data['last_seen'] == frame_number - 1:  # Just lost
                    self.orphaned_tracks[track_id] = {
                        'track_data': track_data,
                        'lost_at_frame': frame_number
                    }
    
    def _update_track_histories_with_interpolated(self, frame_number: int, interpolated_detections: List[Dict[str, Any]]):
        """
        Update track histories with interpolated detections.
        
        This ensures temporal continuity for multi-frame gaps by maintaining
        track history even when detections are interpolated.
        """
        for detection in interpolated_detections:
            track_id = detection.get('track_id')
            if track_id is None:
                continue
            
            # Only update if track exists in history
            if track_id not in self.track_history:
                continue
                
            track_data = self.track_history[track_id]
            bbox = detection['bbox']
            
            # Add interpolated detection to history
            track_data['bboxes'].append(bbox)
            track_data['centroids'].append(self._get_bbox_centroid(bbox))
            track_data['areas'].append(self._get_bbox_area(bbox))
            
            # Use reduced confidence for interpolated detections
            interpolated_confidence = detection.get('confidence', 0.6)
            track_data['confidences'].append(interpolated_confidence)
            
            track_data['frame_numbers'].append(frame_number)
            track_data['detection_types'].append(detection.get('type', 'bbox'))
            track_data['class_ids'].append(detection.get('class_id', -1))
            track_data['last_seen'] = frame_number
            
            # Update trajectory history for debug visualization
            self._update_trajectory_history(track_id, frame_number, bbox)
            
            # Remove from orphaned tracks since we're continuing the track
            if track_id in self.orphaned_tracks:
                del self.orphaned_tracks[track_id]
                self.stats['track_recoveries'] += 1
    
    def _update_track_durations(self, frame_number: int, detections: List[Dict[str, Any]]):
        """Update track duration tracking."""
        if not self.duration_filtering_enabled:
            return
            
        current_track_ids = {d.get('track_id') for d in detections if d.get('track_id') is not None}
        
        # Record first appearance of new tracks
        for track_id in current_track_ids:
            if track_id not in self.track_durations:
                self.track_durations[track_id] = frame_number
                self.stats['total_new_tracks'] += 1
                self.logger.debug("New track detected", 
                                track_id=track_id, 
                                first_frame=frame_number)
        
        # Clean up tracks that haven't been seen recently
        tracks_to_remove = []
        
        for track_id in list(self.track_durations.keys()):
            if track_id not in current_track_ids:
                # Check if track has been missing for too long
                last_possible_frame = frame_number - self.minimum_blur_duration - 10  # Grace period
                if self.track_durations[track_id] < last_possible_frame:
                    tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            del self.track_durations[track_id]
            self.logger.debug("Cleaned up old track duration", track_id=track_id)

    def _should_blur_track(self, detection: Dict[str, Any], current_frame: int, frame_dims: Tuple[int, int] = (1920, 1080)) -> bool:
        """Check if track should be blurred based on duration and size."""
        track_id = detection.get('track_id')
        
        if not self.duration_filtering_enabled or track_id is None:
            return True  # Allow all tracks if filtering disabled
        
        # Allow all detections in early frames to prevent startup delay
        if current_frame <= self.minimum_blur_duration:
            self.logger.debug("Allowing track in early frame", 
                             track_id=track_id, 
                             frame=current_frame)
            return True
            
        # Check if object is large enough to bypass duration filter
        if self._is_large_object(detection, frame_dims):
            self.stats['large_objects_bypassed'] += 1
            self.logger.debug("Large object bypassing duration filter", 
                             track_id=track_id,
                             bbox=detection['bbox'])
            return True
            
        if track_id not in self.track_durations:
            return False  # Unknown track, don't blur
            
        duration = current_frame - self.track_durations[track_id] + 1
        should_blur = duration >= self.minimum_blur_duration
        
        if not should_blur:
            self.stats['short_tracks_filtered'] += 1
            self.logger.debug("Track filtered due to short duration", 
                             track_id=track_id, 
                             duration=duration, 
                             required=self.minimum_blur_duration)
        elif duration == self.minimum_blur_duration:
            self.stats['tracks_promoted_to_blur'] += 1
            self.logger.debug("Track promoted to blur", 
                             track_id=track_id, 
                             duration=duration)
        
        return should_blur

    def _is_large_object(self, detection: Dict[str, Any], frame_dims: Tuple[int, int]) -> bool:
        """Check if object is large enough to bypass duration filtering."""
        bbox = detection['bbox']
        frame_width, frame_height = frame_dims
        
        object_width = bbox[2] - bbox[0]
        object_height = bbox[3] - bbox[1]
        
        width_ratio = object_width / frame_width
        height_ratio = object_height / frame_height
        
        # If object is larger than threshold in either dimension, it's considered large
        is_large = width_ratio > self.large_object_threshold or height_ratio > self.large_object_threshold
        
        if is_large:
            self.logger.debug("Large object detected", 
                             width_ratio=f"{width_ratio:.3f}",
                             height_ratio=f"{height_ratio:.3f}",
                             threshold=self.large_object_threshold)
        
        return is_large

    def configure_duration_filtering(self, processing_settings):
        """Configure duration filtering from processing settings."""
        self.minimum_blur_duration = processing_settings.blur_minimum_track_duration
        self.duration_filtering_enabled = processing_settings.blur_duration_filtering_enabled
        self.large_object_threshold = processing_settings.blur_large_object_threshold
        self.logger.info("Duration filtering configured", 
                        enabled=self.duration_filtering_enabled,
                        minimum_duration=self.minimum_blur_duration,
                        large_object_threshold=self.large_object_threshold)

    def _smooth_detection(self, detection: Dict[str, Any], frame_number: int) -> Dict[str, Any]:
        """Apply smoothing to a detection using track history."""
        track_id = detection.get('track_id')
        if track_id is None or track_id not in self.track_history:
            return detection
        
        track_data = self.track_history[track_id]
        
        # Only smooth if we have enough history
        if len(track_data['bboxes']) < 2:
            return detection
        
        # Create smoothed detection
        smoothed_detection = detection.copy()
        
        # Smooth bbox coordinates
        current_bbox = detection['bbox']
        previous_bbox = track_data['bboxes'][-2]  # Second to last
        
        smoothing_factor = self.smoothing_factors['bbox']
        smoothed_bbox = [
            int(current_bbox[i] * (1 - smoothing_factor) + previous_bbox[i] * smoothing_factor)
            for i in range(4)
        ]
        
        smoothed_detection['bbox'] = smoothed_bbox
        smoothed_detection['smoothed'] = True
        
        self.stats['smoothed_detections'] += 1
        
        return smoothed_detection
    
    def _immediate_spatial_interpolation(self, 
                                       frame_number: int, 
                                       current_detections: List[Dict[str, Any]],
                                       detection_buffer: Dict[int, List[Dict[str, Any]]],
                                       mask_stabilizer: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Immediate spatial-based interpolation for single-frame gaps.
        
        This addresses the key issue: objects missing for just one frame
        should be interpolated immediately based on spatial continuity.
        """
        if frame_number <= 1:
            return []
        
        # Get previous frame detections
        prev_frame_detections = detection_buffer.get(frame_number - 1, [])
        if not prev_frame_detections:
            return []
        
        immediate_interpolations = []
        current_positions = {self._get_bbox_centroid(det['bbox']) for det in current_detections}
        
        # Check each detection from previous frame
        for prev_detection in prev_frame_detections:
            prev_bbox = prev_detection['bbox']
            prev_centroid = self._get_bbox_centroid(prev_bbox)
            prev_class = prev_detection.get('class_id', -1)
            
            # Check if this position is covered by current detections
            is_covered = False
            for current_detection in current_detections:
                current_bbox = current_detection['bbox']
                current_class = current_detection.get('class_id', -1)
                
                # Check spatial overlap
                iou = self._calculate_iou(prev_bbox, current_bbox)
                if iou > 0.3:  # Significant overlap
                    is_covered = True
                    break
                
                # Check spatial proximity
                current_centroid = self._get_bbox_centroid(current_bbox)
                distance = np.sqrt((prev_centroid[0] - current_centroid[0])**2 + 
                                 (prev_centroid[1] - current_centroid[1])**2)
                if distance < self.spatial_continuity_threshold and prev_class == current_class:
                    is_covered = True
                    break
            
            # If not covered, create immediate interpolation
            if not is_covered:
                # Check if this is a stationary object
                is_stationary = self._is_stationary_object(prev_detection, frame_number - 1)
                
                # Create interpolation with high confidence for single-frame gaps
                confidence = self.single_frame_gap_confidence
                if is_stationary:
                    confidence = min(0.95, confidence + 0.1)  # Even higher for stationary
                    self.stats['stationary_objects_persisted'] += 1
                
                # Use previous bbox with slight expansion for safety
                expansion = 5 if is_stationary else 2
                interpolated_bbox = [
                    max(0, prev_bbox[0] - expansion),
                    max(0, prev_bbox[1] - expansion),
                    prev_bbox[2] + expansion,
                    prev_bbox[3] + expansion
                ]
                
                # For segmentation mode, mark interpolated detections specially
                detection_type = 'segmentation' if self.detection_type == 'segmentation' else 'bbox'
                
                interpolated_detection = {
                    'bbox': interpolated_bbox,
                    'confidence': confidence,
                    'track_id': prev_detection.get('track_id', -1),
                    'class_id': prev_class,
                    'type': detection_type,
                    'interpolated': True,
                    'gap_size': 1,
                    'spatial_drift': 0,  # No drift for immediate interpolation
                    'immediate_interpolation': True,
                    'stationary': is_stationary,
                    'requires_mask_interpolation': self.detection_type == 'segmentation'
                }
                
                immediate_interpolations.append(interpolated_detection)
                self.stats['immediate_interpolations'] += 1
                self.stats['single_frame_gaps_filled'] += 1
        
        return immediate_interpolations
    
    def _is_stationary_object(self, detection: Dict[str, Any], frame_number: int) -> bool:
        """
        Check if an object is stationary based on recent motion history.
        """
        track_id = detection.get('track_id')
        if track_id is None or track_id not in self.track_history:
            return False
        
        track_data = self.track_history[track_id]
        centroids = list(track_data['centroids'])
        
        # Need at least 3 points to assess motion
        if len(centroids) < 3:
            return False
        
        # Calculate recent velocities
        recent_velocities = []
        for i in range(1, min(4, len(centroids))):  # Last 3 movements
            prev_centroid = centroids[-(i+1)]
            curr_centroid = centroids[-i]
            
            velocity = np.sqrt((curr_centroid[0] - prev_centroid[0])**2 + 
                             (curr_centroid[1] - prev_centroid[1])**2)
            recent_velocities.append(velocity)
        
        # Check if average velocity is below threshold
        avg_velocity = np.mean(recent_velocities)
        return avg_velocity < self.stationary_velocity_threshold
    
    def _interpolate_missing_tracks_robust(self, 
                                         frame_number: int, 
                                         current_detections: List[Dict[str, Any]],
                                         detection_buffer: Dict[int, List[Dict[str, Any]]],
                                         mask_stabilizer: Optional[Any] = None) -> List[Dict[str, Any]]:
        """
        Robustly interpolate missing tracks with enhanced validation.
        
        Prevents cross-class interpolation, spatial drift, and velocity outliers.
        """
        interpolated_detections = []
        current_track_ids = {d.get('track_id') for d in current_detections if d.get('track_id') is not None}
        
        for track_id, orphan_data in list(self.orphaned_tracks.items()):
            track_data = orphan_data['track_data']
            lost_at_frame = orphan_data['lost_at_frame']
            gap_size = frame_number - lost_at_frame + 1
            
            # Skip if gap is too large
            if gap_size > self.interpolation_max_gap:
                continue
            
            # Skip if track was recovered
            if track_id in current_track_ids:
                continue
            
            # Enhanced validation before interpolation
            if not self._validate_interpolation_candidate(track_data, gap_size):
                continue
            
            # Try to interpolate with robust validation
            interpolated_detection = self._predict_detection_robust(track_data, frame_number, gap_size)
            
            if interpolated_detection is not None:
                # Final spatial validation
                if self._validate_interpolated_detection(interpolated_detection, current_detections):
                    # Generate mask data for segmentation detections
                    if (self.detection_type == 'segmentation' and 
                        mask_stabilizer is not None and 
                        track_id in mask_stabilizer.mask_history):
                        
                        # Get frame dimensions from detection buffer
                        frame_width, frame_height = self._get_frame_dimensions(detection_buffer)
                        
                        # Generate interpolated mask
                        interpolated_mask = mask_stabilizer.get_interpolated_mask(
                            track_id, interpolated_detection['bbox'], frame_width, frame_height
                        )
                        
                        if interpolated_mask is not None:
                            interpolated_detection['mask'] = interpolated_mask
                        else:
                            # If mask interpolation fails, fall back to bounding box
                            interpolated_detection['type'] = 'bbox'
                            interpolated_detection['requires_mask_interpolation'] = False
                    
                    interpolated_detections.append(interpolated_detection)
                    self.stats['interpolated_detections'] += 1
                else:
                    self.stats['spatial_drift_rejections'] += 1
        
        return interpolated_detections
    
    def _validate_interpolation_candidate(self, track_data: Dict[str, Any], gap_size: int) -> bool:
        """
        Validate if a track is suitable for interpolation.
        
        Checks class consistency, motion patterns, and reliability.
        """
        # Need minimum history for reliable interpolation
        if len(track_data['bboxes']) < 2:
            return False
        
        # Check class consistency
        if self.class_consistency_required:
            class_ids = list(track_data['class_ids'])
            if len(set(class_ids)) > 1:  # Multiple classes detected
                self.stats['cross_class_interpolations_blocked'] += 1
                return False
        
        # Check velocity consistency (no sudden speed changes)
        if len(track_data['centroids']) >= 3:
            centroids = list(track_data['centroids'])
            velocities = []
            
            for i in range(1, len(centroids)):
                vx = centroids[i][0] - centroids[i-1][0]
                vy = centroids[i][1] - centroids[i-1][1]
                velocities.append(np.sqrt(vx**2 + vy**2))
            
            if len(velocities) >= 2:
                # Check for velocity outliers
                avg_velocity = np.mean(velocities)
                for velocity in velocities[-2:]:  # Check recent velocities
                    if abs(velocity - avg_velocity) > self.max_velocity_change:
                        self.stats['velocity_outliers_rejected'] += 1
                        return False
        
        return True
    
    def _get_frame_dimensions(self, detection_buffer: Dict[int, List[Dict[str, Any]]]) -> Tuple[int, int]:
        """
        Get frame dimensions from detection buffer.
        
        Returns:
            Tuple of (width, height), defaults to (1920, 1080) if not found
        """
        # Try to get dimensions from any detection in the buffer
        for detections in detection_buffer.values():
            for detection in detections:
                if 'frame_width' in detection and 'frame_height' in detection:
                    return detection['frame_width'], detection['frame_height']
        
        # Default to FullHD if not found
        return 1920, 1080
    
    def _predict_detection_robust(self, 
                                track_data: Dict[str, Any], 
                                frame_number: int, 
                                gap_size: int) -> Optional[Dict[str, Any]]:
        """
        Predict detection with enhanced validation and hybrid approach.
        
        Special handling for single-frame gaps and stationary objects.
        """
        bboxes = list(track_data['bboxes'])
        centroids = list(track_data['centroids'])
        class_ids = list(track_data['class_ids'])
        confidences = list(track_data['confidences'])
        
        # Need at least 1 detection for prediction
        if len(bboxes) < 1:
            return None
        
        # Special handling for single-frame gaps
        if gap_size == 1:
            return self._predict_single_frame_gap(track_data, frame_number)
        
        # Check if object is stationary
        is_stationary = len(centroids) >= 3 and self._is_stationary_from_centroids(centroids)
        
        # Use conservative motion prediction for multi-frame gaps
        recent_centroids = centroids[-min(3, len(centroids)):]
        recent_bboxes = bboxes[-min(3, len(bboxes)):]
        
        # Calculate average velocity with damping
        if len(recent_centroids) >= 2:
            velocities = []
            for i in range(1, len(recent_centroids)):
                vx = recent_centroids[i][0] - recent_centroids[i-1][0]
                vy = recent_centroids[i][1] - recent_centroids[i-1][1]
                velocities.append((vx, vy))
            
            # Average velocity with damping for larger gaps
            avg_vx = sum(v[0] for v in velocities) / len(velocities)
            avg_vy = sum(v[1] for v in velocities) / len(velocities)
            
            # Enhanced damping for stationary objects
            if is_stationary:
                damping_factor = max(0.8, 1.0 - (gap_size - 1) * 0.05)  # Less damping for stationary
            else:
                damping_factor = max(0.5, 1.0 - (gap_size - 1) * 0.1)  # More damping for moving
            
            avg_vx *= damping_factor
            avg_vy *= damping_factor
        else:
            avg_vx = avg_vy = 0
        
        # Predict position
        last_bbox = bboxes[-1]
        last_centroid = centroids[-1]
        
        # Apply velocity with conservative gap size
        predicted_centroid = (
            last_centroid[0] + avg_vx * gap_size,
            last_centroid[1] + avg_vy * gap_size
        )
        
        # Check if prediction is reasonable (not too far from last position)
        spatial_drift = np.sqrt((predicted_centroid[0] - last_centroid[0])**2 + 
                              (predicted_centroid[1] - last_centroid[1])**2)
        
        # More lenient drift threshold for stationary objects
        max_drift = self.max_spatial_drift * 1.5 if is_stationary else self.max_spatial_drift
        if spatial_drift > max_drift:
            return None
        
        # Calculate predicted bbox with size stability
        bbox_width = last_bbox[2] - last_bbox[0]
        bbox_height = last_bbox[3] - last_bbox[1]
        
        # Less size reduction for stationary objects
        if is_stationary:
            size_factor = max(0.95, 1.0 - gap_size * 0.02)
        else:
            size_factor = max(0.8, 1.0 - gap_size * 0.05)
        
        bbox_width *= size_factor
        bbox_height *= size_factor
        
        predicted_bbox = [
            int(predicted_centroid[0] - bbox_width / 2),
            int(predicted_centroid[1] - bbox_height / 2),
            int(predicted_centroid[0] + bbox_width / 2),
            int(predicted_centroid[1] + bbox_height / 2)
        ]
        
        # Calculate confidence with enhanced handling
        base_confidence = min(0.8, max(confidences) if confidences else 0.5)
        
        # Less penalty for stationary objects
        if is_stationary:
            gap_penalty = 0.1 * gap_size
            motion_penalty = min(0.1, spatial_drift / 200.0)
        else:
            gap_penalty = 0.15 * gap_size
            motion_penalty = min(0.2, spatial_drift / 100.0)
        
        confidence = max(0.2, base_confidence - gap_penalty - motion_penalty)
        
        # Skip if confidence too low
        if confidence < self.confidence_threshold:
            return None
        
        # Create interpolated detection with consistent class
        most_common_class = max(set(class_ids), key=class_ids.count) if class_ids else -1
        
        # For segmentation mode, mark interpolated detections specially
        detection_type = 'segmentation' if self.detection_type == 'segmentation' else 'bbox'
        
        interpolated_detection = {
            'bbox': predicted_bbox,
            'confidence': confidence,
            'track_id': track_data['class_ids'][-1] if track_data['class_ids'] else -1,
            'class_id': most_common_class,
            'type': detection_type,
            'interpolated': True,
            'gap_size': gap_size,
            'spatial_drift': spatial_drift,
            'stationary': is_stationary,
            'requires_mask_interpolation': self.detection_type == 'segmentation'
        }
        
        return interpolated_detection
    
    def _predict_single_frame_gap(self, track_data: Dict[str, Any], frame_number: int) -> Optional[Dict[str, Any]]:
        """
        Special handling for single-frame gaps - be very aggressive.
        """
        bboxes = list(track_data['bboxes'])
        centroids = list(track_data['centroids'])
        class_ids = list(track_data['class_ids'])
        confidences = list(track_data['confidences'])
        
        if not bboxes:
            return None
        
        # For single-frame gaps, use the last known detection with minimal modification
        last_bbox = bboxes[-1]
        last_confidence = confidences[-1] if confidences else 0.5
        last_class = class_ids[-1] if class_ids else -1
        
        # Check if object appears stationary
        is_stationary = len(centroids) >= 3 and self._is_stationary_from_centroids(centroids)
        
        # Calculate predicted position
        if len(centroids) >= 2:
            # Use recent velocity for slight adjustment
            last_centroid = centroids[-1]
            prev_centroid = centroids[-2]
            
            # Small velocity adjustment
            vx = (last_centroid[0] - prev_centroid[0]) * 0.5  # Reduce velocity
            vy = (last_centroid[1] - prev_centroid[1]) * 0.5
            
            predicted_centroid = (
                last_centroid[0] + vx,
                last_centroid[1] + vy
            )
        else:
            # No motion prediction, use last position
            predicted_centroid = self._get_bbox_centroid(last_bbox)
        
        # Calculate predicted bbox
        bbox_width = last_bbox[2] - last_bbox[0]
        bbox_height = last_bbox[3] - last_bbox[1]
        
        # Slight expansion for safety
        expansion = 3 if is_stationary else 5
        predicted_bbox = [
            int(predicted_centroid[0] - bbox_width / 2 - expansion),
            int(predicted_centroid[1] - bbox_height / 2 - expansion),
            int(predicted_centroid[0] + bbox_width / 2 + expansion),
            int(predicted_centroid[1] + bbox_height / 2 + expansion)
        ]
        
        # High confidence for single-frame gaps
        confidence = self.single_frame_gap_confidence
        if is_stationary:
            confidence = min(0.95, confidence + 0.1)
        
        # Apply minimum confidence from last detection
        confidence = max(confidence, last_confidence * 0.8)
        
        self.stats['single_frame_gaps_filled'] += 1
        if is_stationary:
            self.stats['stationary_objects_persisted'] += 1
        
        # For segmentation mode, mark interpolated detections specially
        detection_type = 'segmentation' if self.detection_type == 'segmentation' else 'bbox'
        
        return {
            'bbox': predicted_bbox,
            'confidence': confidence,
            'track_id': track_data['class_ids'][-1] if track_data['class_ids'] else -1,
            'class_id': last_class,
            'type': detection_type,
            'interpolated': True,
            'gap_size': 1,
            'spatial_drift': 0,
            'single_frame_gap': True,
            'stationary': is_stationary,
            'requires_mask_interpolation': self.detection_type == 'segmentation'
        }
    
    def _is_stationary_from_centroids(self, centroids: List[Tuple[float, float]]) -> bool:
        """Check if object is stationary based on centroid history."""
        if len(centroids) < 3:
            return False
        
        # Calculate recent movements
        recent_movements = []
        for i in range(1, min(4, len(centroids))):
            prev_centroid = centroids[-(i+1)]
            curr_centroid = centroids[-i]
            
            movement = np.sqrt((curr_centroid[0] - prev_centroid[0])**2 + 
                             (curr_centroid[1] - prev_centroid[1])**2)
            recent_movements.append(movement)
        
        # Check if average movement is below threshold
        avg_movement = np.mean(recent_movements)
        return avg_movement < self.stationary_velocity_threshold
    
    def _validate_interpolated_detection(self, 
                                       interpolated_detection: Dict[str, Any], 
                                       current_detections: List[Dict[str, Any]]) -> bool:
        """
        Final validation of interpolated detection against current detections.
        
        Prevents conflicts and ensures spatial consistency.
        """
        interpolated_bbox = interpolated_detection['bbox']
        interpolated_class = interpolated_detection['class_id']
        
        # Check for conflicts with current detections
        for detection in current_detections:
            detection_bbox = detection['bbox']
            detection_class = detection.get('class_id', -1)
            
            # Calculate overlap
            iou = self._calculate_iou(interpolated_bbox, detection_bbox)
            
            # If high overlap with different class, reject
            if iou > 0.3 and detection_class != interpolated_class:
                return False
            
            # If very high overlap with same class, probably duplicate
            if iou > 0.7 and detection_class == interpolated_class:
                return False
        
        return True
    
    def _calculate_iou(self, bbox1: List[int], bbox2: List[int]) -> float:
        """Calculate Intersection over Union (IoU) of two bounding boxes."""
        x1_max = max(bbox1[0], bbox2[0])
        y1_max = max(bbox1[1], bbox2[1])
        x2_min = min(bbox1[2], bbox2[2])
        y2_min = min(bbox1[3], bbox2[3])
        
        if x2_min <= x1_max or y2_min <= y1_max:
            return 0.0
        
        intersection_area = (x2_min - x1_max) * (y2_min - y1_max)
        
        bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union_area = bbox1_area + bbox2_area - intersection_area
        
        if union_area == 0:
            return 0.0
        
        return intersection_area / union_area
    
    def _cleanup_old_tracks(self, frame_number: int):
        """Clean up old track data to prevent memory leaks."""
        # Remove very old tracks from history
        tracks_to_remove = []
        for track_id, track_data in self.track_history.items():
            if frame_number - track_data['last_seen'] > self.track_history_length:
                tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            del self.track_history[track_id]
        
        # Remove very old orphaned tracks
        orphans_to_remove = []
        for track_id, orphan_data in self.orphaned_tracks.items():
            if frame_number - orphan_data['lost_at_frame'] > self.interpolation_max_gap:
                orphans_to_remove.append(track_id)
        
        for track_id in orphans_to_remove:
            del self.orphaned_tracks[track_id]
        
        # Clean up old spatial tracks
        spatial_tracks_to_remove = []
        for spatial_id, spatial_track in self.spatial_tracks.items():
            if frame_number - spatial_track['last_seen'] > self.track_history_length:
                spatial_tracks_to_remove.append(spatial_id)
        
        for spatial_id in spatial_tracks_to_remove:
            del self.spatial_tracks[spatial_id]
    
    def _get_bbox_centroid(self, bbox: List[int]) -> Tuple[float, float]:
        """Get centroid of bounding box."""
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    
    def _get_bbox_area(self, bbox: List[int]) -> float:
        """Get area of bounding box."""
        x1, y1, x2, y2 = bbox
        return (x2 - x1) * (y2 - y1)
    
    def _validate_bbox(self, bbox: List[int], frame_width: int, frame_height: int) -> bool:
        """Validate that bbox is within frame bounds and reasonable."""
        x1, y1, x2, y2 = bbox
        
        # Check bounds
        if x1 < 0 or y1 < 0 or x2 > frame_width or y2 > frame_height:
            return False
        
        # Check size
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            return False
        
        # Check reasonable size (not too small or too large)
        min_size = 10
        max_size = min(frame_width, frame_height) * 0.8
        if width < min_size or height < min_size or width > max_size or height > max_size:
            return False
        
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get enhanced temporal stability statistics."""
        return {
            'active_tracks': len(self.track_history),
            'orphaned_tracks': len(self.orphaned_tracks),
            'spatial_tracks': len(self.spatial_tracks),
            'interpolated_detections': self.stats['interpolated_detections'],
            'smoothed_detections': self.stats['smoothed_detections'],
            'track_recoveries': self.stats['track_recoveries'],
            'spatial_matches': self.stats['spatial_matches'],
            'duplicate_detections_merged': self.stats['duplicate_detections_merged'],
            'cross_class_interpolations_blocked': self.stats['cross_class_interpolations_blocked'],
            'spatial_drift_rejections': self.stats['spatial_drift_rejections'],
            'velocity_outliers_rejected': self.stats['velocity_outliers_rejected'],
            'single_frame_gaps_filled': self.stats['single_frame_gaps_filled'],
            'stationary_objects_persisted': self.stats['stationary_objects_persisted'],
            'immediate_interpolations': self.stats['immediate_interpolations'],
            'spatial_continuity_matches': self.stats['spatial_continuity_matches']
        }
    
    def reset_statistics(self):
        """Reset statistics counters."""
        self.stats = {
            'interpolated_detections': 0,
            'smoothed_detections': 0,
            'track_recoveries': 0,
            'spatial_matches': 0,
            'duplicate_detections_merged': 0,
            'cross_class_interpolations_blocked': 0,
            'spatial_drift_rejections': 0,
            'velocity_outliers_rejected': 0,
            'single_frame_gaps_filled': 0,
            'stationary_objects_persisted': 0,
            'immediate_interpolations': 0,
            'spatial_continuity_matches': 0
        }

    def _update_trajectory_history(self, track_id: int, frame_number: int, bbox: List[float]):
        """Update trajectory history for debug visualization."""
        if track_id not in self.trajectory_history:
            self.trajectory_history[track_id] = deque(maxlen=self.trajectory_max_length)
        
        # Calculate center point
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        
        # Add to trajectory history
        self.trajectory_history[track_id].append((frame_number, center_x, center_y))
    
    def get_trajectory_history(self, track_id: int) -> List[Tuple[int, float, float]]:
        """Get trajectory history for a specific track."""
        if track_id in self.trajectory_history:
            return list(self.trajectory_history[track_id])
        return []
    
    def get_all_trajectories(self) -> Dict[int, List[Tuple[int, float, float]]]:
        """Get all trajectory histories."""
        return {track_id: list(trajectory) for track_id, trajectory in self.trajectory_history.items()}
    
    def cleanup_old_trajectories(self, active_track_ids: set):
        """Clean up trajectories for inactive tracks."""
        tracks_to_remove = []
        for track_id in self.trajectory_history:
            if track_id not in active_track_ids:
                tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            del self.trajectory_history[track_id]


class MaskTemporalStabilizer:
    """
    Specialized temporal stabilizer for segmentation masks.
    
    Provides conservative mask interpolation strategies for temporal stability.
    """
    
    def __init__(self, max_mask_history: int = 3):
        """
        Initialize mask temporal stabilizer.
        
        Args:
            max_mask_history: Maximum number of masks to keep in history
        """
        self.max_mask_history = max_mask_history
        self.logger = structlog.get_logger("mask_temporal_stabilizer")
        
        # Mask history: track_id -> deque of recent masks
        self.mask_history: Dict[int, deque] = {}
    
    def update_mask_history(self, track_id: int, mask: np.ndarray, bbox: List[int]):
        """Update mask history for a track."""
        if track_id not in self.mask_history:
            self.mask_history[track_id] = deque(maxlen=self.max_mask_history)
        
        self.mask_history[track_id].append({
            'mask': mask,
            'bbox': bbox,
            'timestamp': time.time()
        })
    
    def transform_mask_to_position(self, 
                                 mask: np.ndarray, 
                                 old_bbox: List[int], 
                                 new_bbox: List[int],
                                 frame_width: int,
                                 frame_height: int) -> Optional[np.ndarray]:
        """
        Transform mask from old position to new predicted position.
        
        Args:
            mask: Original mask
            old_bbox: Original bounding box
            new_bbox: Target bounding box
            frame_width: Frame width
            frame_height: Frame height
            
        Returns:
            Transformed mask or None if transformation fails
        """
        try:
            # Calculate translation offset
            old_center = ((old_bbox[0] + old_bbox[2]) / 2, (old_bbox[1] + old_bbox[3]) / 2)
            new_center = ((new_bbox[0] + new_bbox[2]) / 2, (new_bbox[1] + new_bbox[3]) / 2)
            
            dx = new_center[0] - old_center[0]
            dy = new_center[1] - old_center[1]
            
            # Apply translation
            transformation_matrix = np.float32([[1, 0, dx], [0, 1, dy]])
            transformed_mask = cv2.warpAffine(
                mask.astype(np.uint8), 
                transformation_matrix, 
                (frame_width, frame_height)
            )
            
            # Apply morphological operations for smoothness
            kernel = np.ones((3, 3), np.uint8)
            smoothed_mask = cv2.morphologyEx(
                transformed_mask, 
                cv2.MORPH_CLOSE, 
                kernel
            )
            
            return smoothed_mask.astype(bool)
            
        except Exception as e:
            self.logger.warning("Mask transformation failed", error=str(e))
            return None
    
    def get_interpolated_mask(self, 
                            track_id: int, 
                            predicted_bbox: List[int],
                            frame_width: int,
                            frame_height: int) -> Optional[np.ndarray]:
        """
        Get interpolated mask for a track.
        
        Args:
            track_id: Track ID
            predicted_bbox: Predicted bounding box
            frame_width: Frame width
            frame_height: Frame height
            
        Returns:
            Interpolated mask or None if not available
        """
        if track_id not in self.mask_history:
            return None
        
        mask_data = list(self.mask_history[track_id])
        if not mask_data:
            return None
        
        # Use most recent mask
        latest_mask_data = mask_data[-1]
        latest_mask = latest_mask_data['mask']
        latest_bbox = latest_mask_data['bbox']
        
        # Transform to predicted position
        return self.transform_mask_to_position(
            latest_mask, 
            latest_bbox, 
            predicted_bbox,
            frame_width,
            frame_height
        )
    
    def cleanup_old_masks(self, active_track_ids: set):
        """Clean up masks for inactive tracks."""
        tracks_to_remove = []
        for track_id in self.mask_history:
            if track_id not in active_track_ids:
                tracks_to_remove.append(track_id)
        
        for track_id in tracks_to_remove:
            del self.mask_history[track_id]
