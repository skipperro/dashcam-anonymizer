"""Test video processor module."""

import pytest
import numpy as np
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import cv2

from dashcam_worker.video_processor import VideoProcessor
from dashcam_worker.models import ProcessingSettings, TaskMessage


@pytest.fixture
def processing_settings():
    """Create test processing settings."""
    return ProcessingSettings(
        yolo_classes=[0, 2, 3],  # person, car, motorbike
        model_size="small",
        detection_type="bbox",
        blur_intensity=15,
        frame_sampling=1,
        processing_resolution=0.5
    )


@pytest.fixture
def mock_storage_client():
    """Mock storage client."""
    storage = Mock()
    storage.download_file.return_value = True
    storage.upload_file.return_value = True
    return storage


@pytest.fixture
def video_processor(mock_storage_client):
    """Create video processor with mocked dependencies."""
    return VideoProcessor(
        storage_client=mock_storage_client,
        local_mode=False
    )


@pytest.fixture
def task_message():
    """Create test task message."""
    return TaskMessage(
        task_id="test-task-123",
        video_id="video-456",
        user_id="user-789",
        input_file_path="input/test.mp4",
        output_file_path="output/test.mp4",
        processing_settings=ProcessingSettings(
            yolo_classes=[0, 2],
            model_size="small",
            detection_type="bbox"
        ),
        created_at="2025-01-15T10:30:00Z"
    )


class TestVideoProcessor:
    """Test VideoProcessor class."""
    
    def test_init(self, video_processor):
        """Test VideoProcessor initialization."""
        assert video_processor.storage_client is not None
        assert video_processor.storage_client is not None
        assert video_processor.local_mode == False
        assert video_processor.current_task_id is None
        assert video_processor.max_buffer_size == 10  # Updated to match current implementation
    
    def test_init_local_mode(self):
        """Test VideoProcessor initialization in local mode."""
        processor = VideoProcessor(local_mode=True)
        assert processor.storage_client is None
        assert processor.local_mode == True
    
    @patch('dashcam_worker.video_processor.VideoProcessor._process_video_file')
    @patch('dashcam_worker.video_processor.VideoProcessor._cleanup_temp_files')
    @patch('os.path.exists')
    def test_process_video_success(self, mock_exists, mock_cleanup, mock_process, 
                                 video_processor, task_message):
        """Test successful video processing."""
        # Setup mocks
        mock_exists.return_value = True
        mock_process.return_value = True
        video_processor.rabbitmq_client = Mock()
        
        # Mock processing stats
        video_processor.processing_stats = {
            'total_frames': 100,
            'objects_detected': 5
        }
        
        # Execute
        result = video_processor.process_video(task_message)
        
        # Verify
        assert result == True
        assert video_processor.current_task_id == "test-task-123"
        video_processor.storage_client.download_file.assert_called_once()
        video_processor.storage_client.upload_file.assert_called_once()
        video_processor.rabbitmq_client.send_completion_message.assert_called_once()
    
    @patch('dashcam_worker.video_processor.VideoProcessor._process_video_file')
    def test_process_video_failure(self, mock_process, video_processor, task_message):
        """Test video processing failure handling."""
        # Setup mocks
        mock_process.return_value = False
        video_processor.rabbitmq_client = Mock()
        
        # Execute
        result = video_processor.process_video(task_message)
        
        # Verify
        assert result == False
        # Should send failure message
        video_processor.rabbitmq_client.send_completion_message.assert_called_once()
        call_args = video_processor.rabbitmq_client.send_completion_message.call_args
        assert call_args[1]['status'] == 'failed'
    
    @patch('dashcam_worker.video_processor.VideoProcessor._process_video_file')
    def test_process_video_local(self, mock_process, processing_settings):
        """Test local video processing."""
        processor = VideoProcessor(local_mode=True)
        mock_process.return_value = True
        
        # Mock processing stats
        processor.processing_stats = {
            'total_frames': 100,
            'processed_frames': 100,
            'objects_detected': 5,
            'processing_time': 30.5
        }
        
        result = processor.process_video_local(
            "/path/to/input.mp4",
            "/path/to/output.mp4", 
            processing_settings
        )
        
        assert result == True
        mock_process.assert_called_once()
    
    def test_apply_blur(self, video_processor, processing_settings):
        """Test blur application to detected regions.""" 
        # Ensure blur intensity is odd for Gaussian kernel
        processing_settings.blur_intensity = 15
        
        # Create test frame with some variation
        frame = np.ones((480, 640, 3), dtype=np.uint8) * 128  # Gray background
        frame[100:200, 100:200] = 255  # White rectangle
        frame[110:190, 110:190] = 200  # Inner variation
        
        # Create test detections with proper coordinates
        detections = [
            {
                'bbox': [100, 100, 200, 200],  # x1, y1, x2, y2
                'class_id': 0,
                'confidence': 0.8
            }
        ]
        
        # Apply blur
        blurred_frame = video_processor._apply_blur(frame, detections, processing_settings)
        
        # Verify blur was applied to the detection region
        original_region = frame[100:200, 100:200]
        blurred_region = blurred_frame[100:200, 100:200]
        
        # The blurred region should be different from the original (check pixel differences)
        pixel_diff = np.abs(original_region.astype(float) - blurred_region.astype(float)).mean()
        assert pixel_diff > 0, "Blur should change pixel values"
        
        # The rest of the frame should be unchanged
        unchanged_region = frame[:100, :100]  # Top-left corner
        unchanged_blurred_region = blurred_frame[:100, :100]
        assert np.array_equal(unchanged_region, unchanged_blurred_region)
    
    def test_apply_blur_empty_detections(self, video_processor, processing_settings):
        """Test blur application with no detections."""
        frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
        detections = []
        
        blurred_frame = video_processor._apply_blur(frame, detections, processing_settings)
        
        # Should return identical frame
        assert np.array_equal(frame, blurred_frame)
    
    @patch('ffmpeg.probe')
    @patch('cv2.VideoCapture')
    def test_get_video_info(self, mock_capture, mock_probe, video_processor):
        """Test video info extraction with encoding details."""
        # Setup mock for OpenCV
        mock_cap = Mock()
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_COUNT: 1000,
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_WIDTH: 1920,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080
        }[prop]
        mock_capture.return_value = mock_cap
        
        # Setup mock for FFmpeg probe
        mock_probe.return_value = {
            'streams': [{
                'codec_type': 'video',
                'codec_name': 'h264',
                'codec_long_name': 'H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10',
                'profile': 'High',
                'level': 40,
                'bit_rate': '2000000',
                'pix_fmt': 'yuv420p',
                'duration': '33.333333'
            }]
        }
        
        # Execute
        info = video_processor._get_video_info("/path/to/video.mp4")
        
        # Verify - now includes encoding info
        expected = {
            'frame_count': 1000,
            'fps': 30.0,
            'width': 1920,
            'height': 1080,
            'codec_name': 'h264',
            'codec_long_name': 'H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10',
            'profile': 'High',
            'level': 40,
            'bit_rate': 2000000,
            'avg_frame_rate': '',
            'pix_fmt': 'yuv420p',
            'duration': 33.333333
        }
        assert info == expected
        mock_cap.release.assert_called_once()
        mock_probe.assert_called_once_with("/path/to/video.mp4")
    
    def test_get_source_preserving_encoding_params(self, video_processor):
        """Test source-preserving encoding parameters."""
        # Test with H.264 video
        video_info = {
            'codec_name': 'h264',
            'bit_rate': 2000000,
            'profile': 'High',
            'pix_fmt': 'yuv420p'
        }
        
        params = video_processor.encoder_thread._get_source_preserving_encoding_params(video_info)
        
        # Verify codec preservation
        assert params['vcodec'] == 'libx264'
        assert params['profile:v'] == 'high'
        assert params['pix_fmt'] == 'yuv420p'
        assert 'b:v' in params  # Should preserve bitrate
        
        # Test with unknown codec
        video_info_unknown = {
            'codec_name': 'unknown',
            'bit_rate': None,
            'profile': 'unknown',
            'pix_fmt': 'unknown'
        }
        
        params = video_processor.encoder_thread._get_source_preserving_encoding_params(video_info_unknown)
        
        # Should use defaults
        assert params['vcodec'] == 'libx264'
        assert params['crf'] == 23
        assert params['pix_fmt'] == 'yuv420p'
        assert params['preset'] == 'fast'
    
    def test_update_progress_local_mode(self, video_processor):
        """Test progress update in local mode."""
        video_processor.local_mode = True
        
        # Should not raise exception
        video_processor._update_progress("test-task", 50, 100)
        
        # Local mode should not send progress updates
        # (no RabbitMQ client in local mode)
    
    def test_update_progress_service_mode(self, video_processor):
        """Test progress update in service mode."""
        video_processor.rabbitmq_client = Mock()
        
        video_processor._update_progress("test-task", 25, 100)
        
        # Should send progress update via RabbitMQ
        video_processor.rabbitmq_client.send_progress_update.assert_called_once()
    
    @patch('os.path.exists')
    @patch('os.remove')
    def test_cleanup_temp_files(self, mock_remove, mock_exists, video_processor):
        """Test temporary file cleanup."""
        mock_exists.return_value = True
        
        files = ["/tmp/file1.mp4", "/tmp/file2.mp4"]
        video_processor._cleanup_temp_files(files)
        
        assert mock_exists.call_count == 2
        assert mock_remove.call_count == 2
    
    @patch('os.path.exists')
    @patch('os.remove')
    def test_cleanup_temp_files_missing(self, mock_remove, mock_exists, video_processor):
        """Test cleanup when files don't exist."""
        mock_exists.return_value = False
        
        files = ["/tmp/missing.mp4"]
        video_processor._cleanup_temp_files(files)
        
        mock_exists.assert_called_once()
        mock_remove.assert_not_called()


@pytest.mark.integration
class TestVideoProcessorIntegration:
    """Integration tests for video processing pipeline."""
    
    def test_processing_pipeline_structure(self):
        """Test that processing pipeline is properly structured."""
        processor = VideoProcessor(local_mode=True)
        
        # Verify required methods exist
        assert hasattr(processor, '_run_ai_thread') 
        assert hasattr(processor, '_run_blur_thread')
        assert hasattr(processor, '_run_encoder_thread')
        assert hasattr(processor, '_run_processing_pipeline')
        assert hasattr(processor, 'encoder_thread')  # New encoder thread instance
        assert hasattr(processor, 'blur_thread')  # New blur thread instance
        assert hasattr(processor, 'ai_thread')  # New AI thread instance
    
    @patch('dashcam_worker.video_processor.VideoProcessor._get_video_info')
    @patch('dashcam_worker.video_processor.VideoProcessor._run_processing_pipeline')
    def test_process_video_file_flow(self, mock_pipeline, mock_video_info, processing_settings):
        """Test the complete video file processing flow."""
        processor = VideoProcessor(local_mode=True)
        
        # Setup mocks
        mock_video_info.return_value = {
            'frame_count': 100,
            'fps': 30.0,
            'width': 1920,
            'height': 1080
        }
        mock_pipeline.return_value = True
        
        # Mock model manager
        with patch.object(processor.model_manager, 'load_model') as mock_load:
            mock_load.return_value = Mock()
            
            result = processor._process_video_file(
                "/input.mp4", "/output.mp4", processing_settings, "test-task"
            )
        
        assert result == True
        mock_video_info.assert_called_once()
        mock_pipeline.assert_called_once()
        mock_load.assert_called_once_with(model_size="small", detection_type="bbox")
        
        # Check processing stats were set
        assert processor.processing_stats['total_frames'] == 100
        assert 'processing_time' in processor.processing_stats
    
    @patch('dashcam_worker.video_processor.VideoProcessor._run_processing_pipeline')
    @patch('dashcam_worker.video_processor.VideoProcessor._get_video_info')
    @patch('dashcam_worker.video_processor.ModelManager')
    def test_fullhd_safety_feature_4k_video(self, mock_model_manager, mock_video_info, mock_pipeline):
        """Test FullHD safety feature with 4K input video."""
        processor = VideoProcessor(local_mode=True)
        mock_load = Mock()
        mock_model_manager.return_value.load_model = mock_load
        mock_pipeline.return_value = True
        
        # Mock 4K video info (3840x2160)
        mock_video_info.return_value = {
            'frame_count': 100,
            'fps': 30.0,
            'width': 3840,
            'height': 2160
        }
        
        processing_settings = ProcessingSettings(
            yolo_classes=[0, 2],
            model_size="small", 
            detection_type="bbox",
            processing_resolution=1.0  # Full resolution requested
        )
        
        result = processor._process_video_file(
            "/fake/input.mp4", "/fake/output.mp4", 
            processing_settings, "test-task"
        )
        
        assert result == True
        
        # Verify FullHD limit was applied
        stats = processor.processing_stats
        assert stats['original_resolution'] == "3840x2160"
        assert stats['encoding_resolution'] == "3840x2160"  # Encoding still at original
        assert stats['fullhd_limit_applied'] == True
        
        # AI processing should be limited to FullHD proportions
        # 4K aspect ratio is 16:9, so FullHD limit gives us 1920x1080
        expected_ai_resolution = "1920x1080"
        assert stats['processing_resolution'] == expected_ai_resolution
    
    @patch('dashcam_worker.video_processor.VideoProcessor._run_processing_pipeline') 
    @patch('dashcam_worker.video_processor.VideoProcessor._get_video_info')
    @patch('dashcam_worker.video_processor.ModelManager')
    def test_fullhd_safety_feature_4k_with_half_resolution(self, mock_model_manager, mock_video_info, mock_pipeline):
        """Test FullHD safety feature with 4K input and 0.5 processing resolution."""
        processor = VideoProcessor(local_mode=True)
        mock_load = Mock()
        mock_model_manager.return_value.load_model = mock_load
        mock_pipeline.return_value = True
        
        # Mock 4K video info (3840x2160)
        mock_video_info.return_value = {
            'frame_count': 100,
            'fps': 30.0,
            'width': 3840,
            'height': 2160
        }
        
        processing_settings = ProcessingSettings(
            yolo_classes=[0, 2],
            model_size="small",
            detection_type="bbox", 
            processing_resolution=0.5  # Half resolution requested
        )
        
        result = processor._process_video_file(
            "/fake/input.mp4", "/fake/output.mp4",
            processing_settings, "test-task"
        )
        
        assert result == True
        
        # Verify FullHD limit + processing resolution was applied
        stats = processor.processing_stats
        assert stats['original_resolution'] == "3840x2160"
        assert stats['encoding_resolution'] == "3840x2160"
        assert stats['fullhd_limit_applied'] == True
        
        # AI should be at half of FullHD: 960x540
        expected_ai_resolution = "960x540"
        assert stats['processing_resolution'] == expected_ai_resolution
    
    @patch('dashcam_worker.video_processor.VideoProcessor._run_processing_pipeline')
    @patch('dashcam_worker.video_processor.VideoProcessor._get_video_info') 
    @patch('dashcam_worker.video_processor.ModelManager')
    def test_fullhd_safety_feature_hd_video_no_limit(self, mock_model_manager, mock_video_info, mock_pipeline):
        """Test that FullHD safety feature doesn't affect HD videos."""
        processor = VideoProcessor(local_mode=True)
        mock_load = Mock()
        mock_model_manager.return_value.load_model = mock_load
        mock_pipeline.return_value = True
        
        # Mock HD video info (1280x720)
        mock_video_info.return_value = {
            'frame_count': 100,
            'fps': 30.0,
            'width': 1280,
            'height': 720
        }
        
        processing_settings = ProcessingSettings(
            yolo_classes=[0, 2],
            model_size="small",
            detection_type="bbox",
            processing_resolution=1.0  # Full resolution requested
        )
        
        result = processor._process_video_file(
            "/fake/input.mp4", "/fake/output.mp4",
            processing_settings, "test-task"
        )
        
        assert result == True
        
        # Verify NO FullHD limit was applied
        stats = processor.processing_stats
        assert stats['original_resolution'] == "1280x720"
        assert stats['encoding_resolution'] == "1280x720"
        assert stats['fullhd_limit_applied'] == False
        
        # AI processing should be at original resolution
        assert stats['processing_resolution'] == "1280x720"
    
    @patch('dashcam_worker.video_processor.VideoProcessor._run_processing_pipeline')
    @patch('dashcam_worker.video_processor.VideoProcessor._get_video_info')
    @patch('dashcam_worker.video_processor.ModelManager') 
    def test_fullhd_safety_feature_ultra_wide_4k(self, mock_model_manager, mock_video_info, mock_pipeline):
        """Test FullHD safety feature with ultra-wide 4K video (different aspect ratio)."""
        processor = VideoProcessor(local_mode=True)
        mock_load = Mock()
        mock_model_manager.return_value.load_model = mock_load
        mock_pipeline.return_value = True
        
        # Mock ultra-wide 4K video info (5120x1440 - 32:9 aspect ratio)
        mock_video_info.return_value = {
            'frame_count': 100,
            'fps': 30.0,
            'width': 5120,
            'height': 1440
        }
        
        processing_settings = ProcessingSettings(
            yolo_classes=[0, 2],
            model_size="small",
            detection_type="bbox",
            processing_resolution=1.0
        )
        
        result = processor._process_video_file(
            "/fake/input.mp4", "/fake/output.mp4",
            processing_settings, "test-task"
        )
        
        assert result == True
        
        # Verify FullHD limit was applied
        stats = processor.processing_stats
        assert stats['original_resolution'] == "5120x1440"
        assert stats['encoding_resolution'] == "5120x1440"
        assert stats['fullhd_limit_applied'] == True
        
        # AI processing should maintain aspect ratio but fit within FullHD
        # 5120x1440 aspect ratio is 32:9 = 3.56:1
        # To fit in 1920x1080 max: height limited by 1440 > 1080
        # Scale factor: 1080/1440 = 0.75
        # So: 5120 * 0.75 = 3840, 1440 * 0.75 = 1080
        # But we need to fit in 1920 width too: 1920/3840 = 0.5
        # Final: 5120 * 0.5 = 2560, 1440 * 0.5 = 720
        # Wait, let me recalculate properly...
        # min(1920/5120, 1080/1440) = min(0.375, 0.75) = 0.375
        # So: 5120 * 0.375 = 1920, 1440 * 0.375 = 540
        expected_ai_resolution = "1920x540"
        assert stats['processing_resolution'] == expected_ai_resolution

    def test_thread_timing_initialization(self):
        """Test that thread timing tracking is properly initialized."""
        processor = VideoProcessor(local_mode=True)
        
        # Check that all timing fields are initialized
        expected_keys = [
            'ai_time', 'blur_time', 'encoder_time',
            'total_inference_time', 'total_frame_decode_time', 
            'total_frame_blur_time', 'total_frame_encode_time'
        ]
        
        for key in expected_keys:
            assert key in processor.thread_timings
            assert processor.thread_timings[key] == 0.0
    
    @patch('dashcam_worker.video_processor.VideoProcessor._process_video_file')
    def test_local_processing_results_include_timing(self, mock_process):
        """Test that local processing results include detailed timing breakdowns."""
        processor = VideoProcessor(local_mode=True)
        mock_process.return_value = True
        
        # Mock processing stats and timings
        processor.processing_stats = {
            'total_frames': 100,
            'processed_frames': 100,
            'objects_detected': 5,
            'processing_time': 30.5,
            'original_resolution': '1920x1080',
            'processing_resolution': '1920x1080',
            'encoding_resolution': '1920x1080',
            'fullhd_limit_applied': False
        }
        
        processor.thread_timings = {
            'decoder_time': 5.2,
            'ai_time': 15.8,
            'blur_time': 3.1,
            'encoder_time': 6.4,
            'total_inference_time': 12.3,
            'total_frame_decode_time': 4.8,
            'total_frame_blur_time': 2.9,
            'total_frame_encode_time': 5.7
        }
        
        # Capture print output
        import io
        import sys
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        result = processor.process_video_local(
            "/fake/input.mp4", "/fake/output.mp4",
            ProcessingSettings(yolo_classes=[0, 2], model_size="small", detection_type="bbox")
        )
        
        # Restore stdout
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
        
        assert result == True
        
        # Verify timing information is in output
        assert 'thread_timings' in output
        assert 'ai_time' in output
        assert 'blur_time' in output
        assert 'encoder_time' in output
        assert 'total_inference_time' in output
        assert 'performance_metrics' in output
        assert 'fullhd_limit_applied' in output
        
        # Verify performance metrics are calculated
        assert 'avg_inference_time_per_frame' in output
        assert 'avg_decode_time_per_frame' in output
        assert 'processing_fps' in output

    @patch('dashcam_worker.video_processor.cv2.VideoCapture')
    def test_timing_stats_reset_between_processing_runs(self, mock_capture):
        """Test that timing stats are properly reset between processing runs."""
        processor = VideoProcessor(local_mode=True)
        
        # Simulate some existing timing data
        processor.thread_timings['decoder_time'] = 10.0
        processor.thread_timings['ai_time'] = 20.0
        
        # Mock video info
        mock_cap = Mock()
        mock_cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_COUNT: 100,
            cv2.CAP_PROP_FPS: 30.0,
            cv2.CAP_PROP_FRAME_WIDTH: 1920,
            cv2.CAP_PROP_FRAME_HEIGHT: 1080
        }[prop]
        mock_capture.return_value = mock_cap
        
        # Call _process_video_file to trigger timing reset
        with patch.object(processor, '_run_processing_pipeline', return_value=True):
            with patch.object(processor.model_manager, 'load_model', return_value=Mock()):
                processor._process_video_file(
                    "/fake/input.mp4", "/fake/output.mp4",
                    ProcessingSettings(yolo_classes=[0], model_size="small", detection_type="bbox"),
                    "test-task"
                )
        
        # Verify all timing stats were reset to 0.0
        for key in processor.thread_timings:
            assert processor.thread_timings[key] == 0.0
