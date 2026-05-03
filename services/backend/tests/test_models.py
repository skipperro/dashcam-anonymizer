"""Test data models and message serialization."""

import pytest
from datetime import datetime
import json

from dashcam_backend.models import (
    ProcessingSettings,
    TaskMessage,
    WorkerCapabilities,
    WorkerRegistrationMessage,
    ProgressUpdateMessage,
    VideoDocument,
    TaskDocument,
    WorkerDocument,
    UploadSessionDocument,
    TaskStatus,
    WorkerStatus,
    VideoStatus,
    UploadStatus,
    serialize_message,
    deserialize_message,
    generate_task_id,
    generate_video_id,
    get_current_timestamp
)


class TestDataModels:
    """Test data model creation and validation."""
    
    def test_processing_settings_creation(self):
        """Test ProcessingSettings creation with defaults."""
        settings = ProcessingSettings(yolo_classes=[0, 2, 3])
        
        assert settings.yolo_classes == [0, 2, 3]
        assert settings.model_size == "small"
        assert settings.detection_type == "bbox"
        assert settings.blur_intensity == 15
        assert settings.frame_sampling == 1
        assert settings.processing_resolution == 1.0
        assert settings.temporal_stability_enabled is True
    
    def test_worker_capabilities_creation(self):
        """Test WorkerCapabilities creation."""
        capabilities = WorkerCapabilities(
            compute_device="cuda",
            gpu_memory_gb=8,
            system_memory_gb=16,
            max_model_size="large"
        )
        
        assert capabilities.compute_device == "cuda"
        assert capabilities.gpu_memory_gb == 8
        assert capabilities.system_memory_gb == 16
        assert capabilities.max_model_size == "large"
        assert capabilities.supported_formats == ["mp4", "avi", "mov", "mkv"]
    
    def test_worker_capabilities_defaults(self):
        """Test WorkerCapabilities with default supported formats."""
        capabilities = WorkerCapabilities(compute_device="cpu")
        
        assert capabilities.supported_formats == ["mp4", "avi", "mov", "mkv"]
    
    def test_task_message_creation(self):
        """Test TaskMessage creation."""
        settings = ProcessingSettings(yolo_classes=[0])
        message = TaskMessage(
            task_id="test-task-123",
            video_id="test-video-456",
            user_id="test-user-789",
            input_file_path="input/test.mp4",
            output_file_path="output/test.mp4",
            processing_settings=settings,
            created_at="2025-01-15T10:30:00Z"
        )
        
        assert message.task_id == "test-task-123"
        assert message.video_id == "test-video-456"
        assert message.user_id == "test-user-789"
        assert message.processing_settings.yolo_classes == [0]
    
    def test_worker_registration_message_creation(self):
        """Test WorkerRegistrationMessage creation."""
        capabilities = WorkerCapabilities(compute_device="cuda", gpu_memory_gb=8)
        message = WorkerRegistrationMessage(
            worker_id="worker-123",
            hostname="test-worker-01",
            capabilities=capabilities,
            status="ready",
            timestamp="2025-01-15T10:30:00Z"
        )
        
        assert message.worker_id == "worker-123"
        assert message.hostname == "test-worker-01"
        assert message.status == "ready"
        assert message.capabilities.compute_device == "cuda"
    
    def test_progress_update_message_creation(self):
        """Test ProgressUpdateMessage creation with fps field."""
        message = ProgressUpdateMessage(
            task_id="task-123",
            video_id="video-456",
            progress_percentage=75,
            current_frame=750,
            total_frames=1000,
            fps=25.5,
            estimated_time_remaining=30,
            timestamp="2025-01-15T10:30:00Z"
        )
        
        assert message.task_id == "task-123"
        assert message.video_id == "video-456"
        assert message.progress_percentage == 75
        assert message.current_frame == 750
        assert message.total_frames == 1000
        assert message.fps == 25.5
        assert message.estimated_time_remaining == 30
        assert message.message_type == "processing_progress"


class TestEnumerations:
    """Test enumeration values."""
    
    def test_task_status_values(self):
        """Test TaskStatus enumeration."""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.ASSIGNED == "assigned"
        assert TaskStatus.PROCESSING == "processing"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"
    
    def test_worker_status_values(self):
        """Test WorkerStatus enumeration."""
        assert WorkerStatus.READY == "ready"
        assert WorkerStatus.BUSY == "busy"
        assert WorkerStatus.OFFLINE == "offline"
        assert WorkerStatus.ERROR == "error"
    
    def test_video_status_values(self):
        """Test VideoStatus enumeration."""
        assert VideoStatus.UPLOADING == "uploading"
        assert VideoStatus.UPLOADED == "uploaded"
        assert VideoStatus.PROCESSING == "processing"
        assert VideoStatus.COMPLETED == "completed"
        assert VideoStatus.FAILED == "failed"


class TestDocumentModels:
    """Test MongoDB document models."""
    
    def test_video_document_creation(self):
        """Test VideoDocument creation with defaults."""
        doc = VideoDocument(
            video_id="video-123",
            user_id="user-456",
            filename="test.mp4",
            file_size=1000000
        )
        
        assert doc.video_id == "video-123"
        assert doc.user_id == "user-456"
        assert doc.filename == "test.mp4"
        assert doc.file_size == 1000000
        assert doc.status == VideoStatus.UPLOADING
        assert doc.upload_progress == 0.0
        assert isinstance(doc.upload_date, datetime)
    
    def test_task_document_creation(self):
        """Test TaskDocument creation with defaults."""
        doc = TaskDocument(
            task_id="task-123",
            video_id="video-456",
            user_id="user-789"
        )
        
        assert doc.task_id == "task-123"
        assert doc.video_id == "video-456"
        assert doc.user_id == "user-789"
        assert doc.status == TaskStatus.PENDING
        assert doc.progress_percentage == 0.0
        assert doc.priority == 0
        assert isinstance(doc.created_at, datetime)
        assert isinstance(doc.last_updated, datetime)
    
    def test_worker_document_creation(self):
        """Test WorkerDocument creation with defaults."""
        doc = WorkerDocument(
            worker_id="worker-123",
            hostname="test-host"
        )
        
        assert doc.worker_id == "worker-123"
        assert doc.hostname == "test-host"
        assert doc.status == WorkerStatus.OFFLINE
        assert isinstance(doc.registered_at, datetime)
        assert doc.capabilities.compute_device == "cpu"  # default


class TestMessageSerialization:
    """Test message serialization and deserialization."""
    
    def test_serialize_processing_settings(self):
        """Test serializing ProcessingSettings to JSON."""
        settings = ProcessingSettings(
            yolo_classes=[0, 2, 3],
            model_size="medium",
            detection_type="segmentation"
        )
        
        json_str = serialize_message(settings)
        data = json.loads(json_str)
        
        assert data["yolo_classes"] == [0, 2, 3]
        assert data["model_size"] == "medium"
        assert data["detection_type"] == "segmentation"
        assert data["blur_intensity"] == 15  # default
    
    def test_serialize_task_message(self):
        """Test serializing TaskMessage to JSON."""
        settings = ProcessingSettings(yolo_classes=[0])
        message = TaskMessage(
            task_id="test-task",
            video_id="test-video",
            user_id="test-user",
            input_file_path="input/test.mp4",
            output_file_path="output/test.mp4",
            processing_settings=settings,
            created_at="2025-01-15T10:30:00Z"
        )
        
        json_str = serialize_message(message)
        data = json.loads(json_str)
        
        assert data["task_id"] == "test-task"
        assert data["video_id"] == "test-video"
        assert data["processing_settings"]["yolo_classes"] == [0]
    
    def test_deserialize_processing_settings(self):
        """Test deserializing ProcessingSettings from JSON."""
        json_str = json.dumps({
            "yolo_classes": [0, 2],
            "model_size": "large",
            "detection_type": "bbox",
            "blur_intensity": 20,
            "frame_sampling": 2,
            "processing_resolution": 0.5,
            "temporal_stability_enabled": False,
            "blur_minimum_track_duration": 10,
            "enable_hood_detection": True,
            "debug_mode": True
        })
        
        settings = deserialize_message(json_str, ProcessingSettings)
        
        assert settings.yolo_classes == [0, 2]
        assert settings.model_size == "large"
        assert settings.detection_type == "bbox"
        assert settings.blur_intensity == 20
        assert settings.frame_sampling == 2
        assert settings.processing_resolution == 0.5
        assert settings.temporal_stability_enabled is False
        assert settings.blur_minimum_track_duration == 10
        assert settings.enable_hood_detection is True
        assert settings.debug_mode is True


class TestUtilityFunctions:
    """Test utility functions."""
    
    def test_generate_ids(self):
        """Test ID generation functions."""
        task_id1 = generate_task_id()
        task_id2 = generate_task_id()
        video_id1 = generate_video_id()
        video_id2 = generate_video_id()
        
        # IDs should be unique
        assert task_id1 != task_id2
        assert video_id1 != video_id2
        assert task_id1 != video_id1
        
        # IDs should be valid UUIDs (basic format check)
        assert len(task_id1) == 36
        assert len(video_id1) == 36
        assert "-" in task_id1
        assert "-" in video_id1
    
    def test_get_current_timestamp(self):
        """Test timestamp generation."""
        timestamp = get_current_timestamp()
        
        assert isinstance(timestamp, str)
        assert timestamp.endswith("Z")
        assert "T" in timestamp
        
        # Should be parseable as ISO format
        from datetime import datetime
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)


class TestUploadSessionDocument:
    """Test UploadSessionDocument creation and functionality."""
    
    def test_upload_session_document_creation(self):
        """Test UploadSessionDocument creation with all fields."""
        session = UploadSessionDocument(
            session_id="test-session-123",
            video_id="test-video-456",
            user_id="test-user-789",
            filename="test_video.mp4",
            total_size=1000000,
            chunk_size=50000,
            total_chunks=20,
            uploaded_chunks=[0, 1, 2],
            multipart_upload_id="test-multipart-123",
            storage_key="uploads/test-video-456.mp4",
            status=UploadStatus.IN_PROGRESS
        )
        
        assert session.session_id == "test-session-123"
        assert session.video_id == "test-video-456"
        assert session.user_id == "test-user-789"
        assert session.filename == "test_video.mp4"
        assert session.total_size == 1000000
        assert session.chunk_size == 50000
        assert session.total_chunks == 20
        assert session.uploaded_chunks == [0, 1, 2]
        assert session.multipart_upload_id == "test-multipart-123"
        assert session.storage_key == "uploads/test-video-456.mp4"
        assert session.status == UploadStatus.IN_PROGRESS
        assert session.parts == {}  # Should be initialized as empty dict
        assert session.created_at is not None
        assert session.expires_at is not None
        
    def test_upload_session_document_with_parts(self):
        """Test UploadSessionDocument creation with parts field."""
        parts = {
            "0": {"ETag": "etag1", "PartNumber": 1},
            "1": {"ETag": "etag2", "PartNumber": 2}
        }
        
        session = UploadSessionDocument(
            session_id="test-session-123",
            video_id="test-video-456", 
            user_id="test-user-789",
            filename="test_video.mp4",
            total_size=1000000,
            chunk_size=50000,
            total_chunks=20,
            uploaded_chunks=[0, 1],
            parts=parts
        )
        
        assert session.parts == parts
        assert session.parts["0"]["ETag"] == "etag1"
        assert session.parts["1"]["PartNumber"] == 2
