"""Test models module."""

def test_processing_settings():
    """Test ProcessingSettings model."""
    from dashcam_worker.models import ProcessingSettings
    
    settings = ProcessingSettings(
        yolo_classes=[0, 2, 3],
        model_size="medium",
        detection_type="bbox"
    )
    
    assert settings.yolo_classes == [0, 2, 3]
    assert settings.model_size == "medium"
    assert settings.detection_type == "bbox"
    assert settings.debug_mode == False  # default
    assert settings.blur_intensity == 15  # default


def test_task_message_from_dict():
    """Test TaskMessage creation from dictionary."""
    from dashcam_worker.models import TaskMessage
    
    data = {
        "task_id": "test-123",
        "video_id": "video-456", 
        "user_id": "user-789",
        "input_file_path": "input.mp4",
        "output_file_path": "output.mp4",
        "processing_settings": {
            "yolo_classes": [0, 2],
            "model_size": "small",
            "detection_type": "bbox",
            "debug_mode": True,
            "blur_intensity": 20,
            "frame_sampling": 2,
            "processing_resolution": 0.5
        },
        "created_at": "2025-01-15T10:30:00Z"
    }
    
    task = TaskMessage.from_dict(data)
    
    assert task.task_id == "test-123"
    assert task.processing_settings.yolo_classes == [0, 2]
    assert task.processing_settings.model_size == "small"
    assert task.processing_settings.debug_mode == True


def test_worker_capabilities():
    """Test WorkerCapabilities model.""" 
    from dashcam_worker.models import WorkerCapabilities
    
    capabilities = WorkerCapabilities(
        compute_device="cuda",
        gpu_memory_gb=8,
        system_memory_gb=16,
        max_model_size="large"
    )
    
    assert capabilities.compute_device == "cuda"
    assert capabilities.gpu_memory_gb == 8
    assert capabilities.supported_formats == ["mp4", "avi", "mov", "mkv"]  # default


def test_message_serialization():
    """Test message serialization to JSON."""
    from dashcam_worker.models import (
        WorkerRegistrationMessage, WorkerCapabilities, 
        serialize_message, get_current_timestamp
    )
    
    capabilities = WorkerCapabilities(
        compute_device="cpu",
        system_memory_gb=8,
        max_model_size="medium"
    )
    
    message = WorkerRegistrationMessage(
        worker_id="test-worker",
        hostname="test-host",
        capabilities=capabilities,
        status="ready",
        timestamp=get_current_timestamp()
    )
    
    json_str = serialize_message(message)
    
    assert isinstance(json_str, str)
    assert "test-worker" in json_str
    assert "test-host" in json_str
    assert "ready" in json_str


def test_progress_update_serialization():
    """Test ProgressUpdateMessage serialization with fps field."""
    from dashcam_worker.models import (
        ProgressUpdateMessage, serialize_message, get_current_timestamp
    )
    
    progress_msg = ProgressUpdateMessage(
        task_id="task-123",
        video_id="video-456", 
        progress_percentage=75,
        current_frame=750,
        total_frames=1000,
        fps=24.5,
        estimated_time_remaining=120,
        timestamp=get_current_timestamp()
    )
    
    json_str = serialize_message(progress_msg)
    
    assert isinstance(json_str, str)
    assert "task-123" in json_str
    assert "video-456" in json_str
    assert "75" in json_str
    assert "750" in json_str
    assert "1000" in json_str
    assert "24.5" in json_str
    assert "120" in json_str
    assert "processing_progress" in json_str
