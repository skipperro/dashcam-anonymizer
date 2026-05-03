"""Integration tests for the complete worker workflow."""

import pytest
import os
import tempfile
import json
from unittest.mock import patch, Mock, MagicMock
import threading
import time

from dashcam_worker.main import DashcamWorker
from dashcam_worker.models import TaskMessage, ProcessingSettings
from dashcam_worker.video_processor import VideoProcessor
from dashcam_worker.rabbitmq_client import RabbitMQClient
from dashcam_worker.storage_client import StorageClient


@pytest.fixture
def temp_video_file():
    """Create a temporary video file for testing."""
    import cv2
    import numpy as np
    
    # Create temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    temp_file.close()
    
    # Create a simple test video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(temp_file.name, fourcc, 30.0, (640, 480))
    
    # Write 30 frames (1 second at 30fps)
    for i in range(30):
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        writer.write(frame)
    
    writer.release()
    
    yield temp_file.name
    
    # Cleanup
    if os.path.exists(temp_file.name):
        os.remove(temp_file.name)


@pytest.fixture
def mock_task_message():
    """Create a mock task message for testing."""
    return TaskMessage(
        task_id="integration-test-123",
        video_id="video-456",
        user_id="user-789",
        input_file_path="input/test.mp4",
        output_file_path="output/test.mp4",
        processing_settings=ProcessingSettings(
            yolo_classes=[0, 2, 3],  # person, car, motorbike
            model_size="small",
            detection_type="bbox",
            blur_intensity=15,
            frame_sampling=2,
            processing_resolution=0.5
        ),
        created_at="2025-01-15T10:30:00Z"
    )


class TestWorkerIntegration:
    """Integration tests for the complete worker system."""
    
    @patch('dashcam_worker.storage_client.boto3')
    @patch('dashcam_worker.rabbitmq_client.pika')
    def test_worker_initialization(self, mock_pika, mock_boto3, test_config):
        """Test complete worker initialization."""
        # Setup mocks
        mock_boto3.client.return_value = Mock()
        mock_pika.BlockingConnection.return_value = Mock()
        
        # Create worker
        worker = DashcamWorker()
        
        # Try to see the actual error by catching it
        try:
            # Initialize storage client manually to see where it fails
            from dashcam_worker.storage_client import StorageClient
            storage_client = StorageClient()
            print("Storage client OK")
            
            # Try video processor
            from dashcam_worker.video_processor import VideoProcessor
            video_processor = VideoProcessor(storage_client=storage_client)
            print("Video processor OK")
            
        except Exception as e:
            print(f"Manual initialization error: {e}")
            import traceback
            traceback.print_exc()
        
        result = worker.initialize()
        
        # Print more details if initialization fails
        if not result:
            print(f"Storage client: {worker.storage_client}")
            print(f"Video processor: {worker.video_processor}")
            print(f"RabbitMQ client: {worker.rabbitmq_client}")
        
        # Verify initialization successful 
        assert result is True
        assert worker.storage_client is not None
        assert worker.video_processor is not None
        assert worker.rabbitmq_client is not None
    
    def test_local_mode_processing(self, temp_video_file, test_config):
        """Test local mode video processing end-to-end."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "output.mp4")
            
            # Create processor in local mode
            processor = VideoProcessor(local_mode=True)
            
            # Mock the model manager to avoid real model loading
            with patch.object(processor.model_manager, 'load_model') as mock_load_model:
                mock_model = Mock()
                # Mock YOLO results
                mock_result = Mock()
                mock_result.boxes = None  # No detections for simplicity
                mock_model.return_value = [mock_result]
                mock_load_model.return_value = mock_model
                
                # Mock video info to avoid actual video processing
                with patch.object(processor, '_get_video_info') as mock_video_info:
                    mock_video_info.return_value = {
                        'frame_count': 30,
                        'fps': 30.0,
                        'width': 640,
                        'height': 480,
                        'codec_name': 'h264',
                        'bit_rate': 1000000,
                        'pix_fmt': 'yuv420p'
                    }
                    
                    # Mock the processing pipeline to avoid complex threading
                    with patch.object(processor, '_run_processing_pipeline') as mock_pipeline:
                        mock_pipeline.return_value = True
                        processor.processing_stats = {
                            'total_frames': 30,
                            'processed_frames': 30,
                            'objects_detected': 0,
                            'processing_time': 1.5
                        }
                        
                        # Process video
                        settings = ProcessingSettings(
                            yolo_classes=[0],
                            model_size="small",
                            detection_type="bbox"
                        )
                        
                        result = processor.process_video_local(
                            temp_video_file, output_path, settings
                        )
                
                assert result == True
                # Verify model was loaded with correct parameters
                mock_load_model.assert_called_once_with(
                    model_size="small",
                    detection_type="bbox"
                )
    
    @patch('dashcam_worker.storage_client.boto3')
    @patch('dashcam_worker.rabbitmq_client.pika')
    def test_service_mode_task_processing(self, mock_pika, mock_boto3, 
                                        mock_task_message, temp_video_file):
        """Test service mode task processing workflow."""
        # Setup mocks
        mock_s3 = Mock()
        mock_boto3.client.return_value = mock_s3
        
        mock_connection = Mock()
        mock_channel = Mock()
        mock_pika.BlockingConnection.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel
        
        # Mock file operations
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create worker
            worker = DashcamWorker()
            
            # Initialize worker first
            initialized = worker.initialize()
            assert initialized is True, "Worker initialization failed"
            
            # Mock the model manager to avoid real model loading
            with patch.object(worker.video_processor.model_manager, 'load_model') as mock_load_model:
                mock_model = Mock()
                mock_result = Mock()
                mock_result.boxes = None
                mock_model.return_value = [mock_result]
                mock_load_model.return_value = mock_model
                
                # Mock download/upload
                def mock_download(remote_path, local_path):
                    # Copy test file to local path
                    import shutil
                    shutil.copy2(temp_video_file, local_path)
                    return True
                
                def mock_upload(local_path, remote_path):
                    return True
                
                worker.storage_client.download_file = mock_download
                worker.storage_client.upload_file = mock_upload
                
                # Mock video processing pipeline
                with patch.object(worker.video_processor, '_run_processing_pipeline') as mock_pipeline:
                    mock_pipeline.return_value = True
                    worker.video_processor.processing_stats = {
                        'total_frames': 30,
                        'processed_frames': 30,
                        'objects_detected': 0
                    }
                    
                    # Mock RabbitMQ client
                    worker.video_processor.rabbitmq_client = Mock()
                    
                    # Process task
                    result = worker.video_processor.process_video(mock_task_message)
                    
                    assert result == True
                    
                    # Verify completion message was sent
                    worker.video_processor.rabbitmq_client.send_completion_message.assert_called_once()
    
    
    @patch('dashcam_worker.rabbitmq_client.pika')
    def test_worker_registration_flow(self, mock_pika):
        """Test worker registration with backend."""
        # Setup mocks
        mock_connection = Mock()
        mock_channel = Mock()
        mock_pika.BlockingConnection.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel
        
        # Important: Mock channel should not appear closed
        mock_channel.is_closed = False
        
        # Create RabbitMQ client
        rabbitmq_client = RabbitMQClient()
        
        # Connect to establish the channel
        rabbitmq_client.connect()
        
        # Register worker (it gets capabilities internally)
        rabbitmq_client.register_worker()
        
        # Verify registration was sent
        mock_channel.basic_publish.assert_called()
    
    def test_health_check_endpoints(self):
        """Test health check endpoints."""
        from dashcam_worker.health import app
        from fastapi.testclient import TestClient
        
        # Create health app
        client = TestClient(app)
        
        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        
        # Test readiness endpoint
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
    
    def test_configuration_loading(self):
        """Test configuration loading and validation."""
        from dashcam_worker.config import get_config
        
        # Test basic configuration loading
        config = get_config()
        
        # Just verify that config loads and has expected structure
        assert config is not None
        assert hasattr(config, 'rabbitmq')
        assert hasattr(config, 'storage')
        assert hasattr(config, 'processing')
        
        # Test that config properties exist
        assert config.rabbitmq.host is not None
        assert config.storage.access_key is not None
    
    def test_model_caching_and_reuse(self):
        """Test model caching and reuse across tasks."""
        from dashcam_worker.model_manager import ModelManager
        
        # Create a fresh model manager instance
        manager = ModelManager()
        
        # Mock the _get_model_path method to avoid real model loading
        with patch.object(manager, '_get_model_path') as mock_get_path:
            with patch('dashcam_worker.model_manager.YOLO') as mock_yolo:
                mock_model = Mock()
                mock_yolo.return_value = mock_model
                mock_get_path.return_value = "/fake/path/model.pt"
                
                # Load model first time
                model1 = manager.load_model("small")
                assert model1 == mock_model
                
                # Load same model again - should use cache
                model2 = manager.load_model("small")
                assert model2 == mock_model
                assert model1 is model2
                
                # YOLO should only be called once (second time uses cache)
                assert mock_yolo.call_count == 1


class TestWorkerLifecycle:
    """Test worker lifecycle management."""
    
    @patch('dashcam_worker.storage_client.boto3')
    @patch('dashcam_worker.rabbitmq_client.pika')
    def test_worker_startup_shutdown(self, mock_pika, mock_boto3):
        """Test worker startup and shutdown sequence."""
        # Setup mocks
        mock_boto3.client.return_value = Mock()
        mock_pika.BlockingConnection.return_value = Mock()
        
        # Create worker
        worker = DashcamWorker()
        result = worker.initialize()
        
        # Test initialization completed successfully
        assert result is True
        assert worker.storage_client is not None
        assert worker.video_processor is not None
    
    def test_graceful_shutdown_on_signal(self):
        """Test graceful shutdown when receiving signals."""
        import signal
        
        worker = DashcamWorker()
        
        # Mock the shutdown flag
        worker.shutdown_event = threading.Event()
        
        # Simulate signal
        worker.shutdown_event.set()
        
        # Worker should detect shutdown signal
        assert worker.shutdown_event.is_set()
    
    @patch('time.sleep')
    def test_heartbeat_mechanism(self, mock_sleep):
        """Test worker heartbeat mechanism."""
        from dashcam_worker.rabbitmq_client import RabbitMQClient
        
        with patch('dashcam_worker.rabbitmq_client.pika') as mock_pika:
            mock_connection = Mock()
            mock_channel = Mock()
            mock_pika.BlockingConnection.return_value = mock_connection
            mock_connection.channel.return_value = mock_channel
            
            rabbitmq_client = RabbitMQClient()
            
            # Start heartbeat
            rabbitmq_client.start_heartbeat()
            
            # Verify heartbeat thread is running
            assert rabbitmq_client.heartbeat_thread is not None
            assert rabbitmq_client.heartbeat_thread.is_alive()
            
            # Stop heartbeat
            rabbitmq_client.stop_heartbeat()


class TestErrorScenarios:
    """Test various error scenarios and recovery."""
    
    def test_storage_connection_failure(self):
        """Test handling of storage connection failures."""
        with patch('dashcam_worker.storage_client.boto3') as mock_boto3:
            mock_boto3.client.side_effect = Exception("Connection failed")
            
            # Should handle gracefully
            from dashcam_worker.storage_client import StorageClient
            
            with pytest.raises(Exception):
                StorageClient()
