"""
Test for blur performance optimization to ensure performance improvements are maintained.
"""

import pytest
import numpy as np
import time
from dashcam_worker.video_processor import VideoProcessor
from dashcam_worker.models import ProcessingSettings


class TestBlurPerformance:
    """Test blur operation performance optimizations."""
    
    @pytest.fixture
    def video_processor(self):
        """Create video processor for testing."""
        return VideoProcessor(local_mode=True)
    
    @pytest.fixture
    def test_frame(self):
        """Create a test frame."""
        frame = np.random.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        # Add some patterns
        frame[100:200, 100:200] = [255, 0, 0]  # Red square
        frame[500:600, 500:600] = [0, 255, 0]  # Green square
        return frame
    
    @pytest.fixture
    def processing_settings(self):
        """Create processing settings for testing."""
        return ProcessingSettings(
            yolo_classes=[0, 2],
            model_size="small",
            detection_type="segmentation",
            blur_intensity=15
        )
    
    def create_segmentation_detections(self, frame_shape, count=5):
        """Create test segmentation detections."""
        height, width = frame_shape[:2]
        detections = []
        
        for i in range(count):
            # Create circular mask
            mask = np.zeros((height, width), dtype=bool)
            center_x = 200 + i * 200
            center_y = 200 + i * 100
            radius = 50
            
            if center_x < width - radius and center_y < height - radius:
                y, x = np.ogrid[:height, :width]
                mask_circle = (x - center_x)**2 + (y - center_y)**2 <= radius**2
                mask[mask_circle] = True
                
                detections.append({
                    'type': 'segmentation',
                    'mask': mask,
                    'bbox': [center_x - radius, center_y - radius, 
                            center_x + radius, center_y + radius],
                    'class_id': 0,
                    'confidence': 0.9
                })
        
        return detections
    
    def test_blur_performance_multiple_detections(self, video_processor, test_frame, processing_settings):
        """Test that blur performance is reasonable with multiple detections."""
        # Create multiple segmentation detections
        detections = self.create_segmentation_detections(test_frame.shape, count=10)
        
        # Measure time for multiple blur operations
        start_time = time.time()
        for _ in range(5):  # Run 5 times to average
            result = video_processor._apply_blur(test_frame, detections, processing_settings)
        avg_time = (time.time() - start_time) / 5
        
        # With optimization, 10 detections on FullHD should be under 50ms
        assert avg_time < 0.05, f"Blur operation too slow: {avg_time*1000:.2f}ms (expected < 50ms)"
        
        # Verify result is valid
        assert result.shape == test_frame.shape
        assert result.dtype == test_frame.dtype
        
        # Verify some blurring occurred (frame should be different)
        assert not np.array_equal(result, test_frame)
    
    def test_blur_performance_scaling(self, video_processor, test_frame, processing_settings):
        """Test that blur performance scales better than linear with detection count."""
        detection_counts = [1, 5, 10]
        times = []
        
        for count in detection_counts:
            detections = self.create_segmentation_detections(test_frame.shape, count=count)
            
            start_time = time.time()
            for _ in range(3):
                video_processor._apply_blur(test_frame, detections, processing_settings)
            avg_time = (time.time() - start_time) / 3
            times.append(avg_time)
        
        # With optimization, 10 detections shouldn't be 10x slower than 1 detection
        # It should be closer to constant time due to combined mask approach
        time_ratio_10_to_1 = times[2] / times[0]
        assert time_ratio_10_to_1 < 5.0, f"Poor scaling: 10 detections is {time_ratio_10_to_1:.1f}x slower than 1 (expected < 5x)"
        
        print(f"Blur timing scaling: 1det={times[0]*1000:.1f}ms, 5det={times[1]*1000:.1f}ms, 10det={times[2]*1000:.1f}ms")
        print(f"Scaling ratio (10det/1det): {time_ratio_10_to_1:.1f}x")
    
    def test_blur_mixed_detection_types(self, video_processor, test_frame, processing_settings):
        """Test blur performance with mixed segmentation and bbox detections."""
        # Create mixed detections
        seg_detections = self.create_segmentation_detections(test_frame.shape, count=3)
        bbox_detections = [
            {'type': 'bbox', 'bbox': [100, 100, 200, 200], 'class_id': 0, 'confidence': 0.9},
            {'type': 'bbox', 'bbox': [300, 300, 400, 400], 'class_id': 0, 'confidence': 0.9},
        ]
        
        mixed_detections = seg_detections + bbox_detections
        
        start_time = time.time()
        result = video_processor._apply_blur(test_frame, mixed_detections, processing_settings)
        processing_time = time.time() - start_time
        
        # Mixed detection should still be fast (adjust threshold for real-world performance)
        assert processing_time < 0.03, f"Mixed detection blur too slow: {processing_time*1000:.2f}ms"
        
        # Verify result
        assert result.shape == test_frame.shape
        assert not np.array_equal(result, test_frame)
    
    def test_blur_empty_detections_performance(self, video_processor, test_frame, processing_settings):
        """Test that empty detections are handled efficiently."""
        start_time = time.time()
        result = video_processor._apply_blur(test_frame, [], processing_settings)
        processing_time = time.time() - start_time
        
        # Empty detections should return immediately
        assert processing_time < 0.001, f"Empty detection handling too slow: {processing_time*1000:.2f}ms"
        
        # Should return original frame for empty detections
        assert np.array_equal(result, test_frame)
    
    def test_blur_result_quality(self, video_processor, test_frame, processing_settings):
        """Test that optimized blur produces quality results."""
        detections = self.create_segmentation_detections(test_frame.shape, count=3)
        
        result = video_processor._apply_blur(test_frame, detections, processing_settings)
        
        # Check that detected areas are blurred
        for detection in detections:
            mask = detection['mask']
            # Get pixels in the masked area
            original_masked = test_frame[mask]
            blurred_masked = result[mask]
            
            # Blurred area should be different from original
            assert not np.array_equal(original_masked, blurred_masked)
            
            # Check that blur kernel was applied (adjacent pixels should be more similar)
            if np.sum(mask) > 100:  # Only check if mask is large enough
                # Calculate variance in masked region (should be lower after blur)
                original_variance = np.var(original_masked)
                blurred_variance = np.var(blurred_masked)
                
                # Blurred region should have lower variance (smoother)
                assert blurred_variance <= original_variance, "Blur didn't reduce variance as expected"
