"""Test configuration and fixtures for the dashcam backend service."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from typing import Generator, Any

from dashcam_backend.config import reset_config, BackendConfig
from dashcam_backend.models import WorkerCapabilities, ProcessingSettings


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global configuration before each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture
def test_config() -> BackendConfig:
    """Provide test configuration."""
    return BackendConfig(
        mongodb=Mock(uri="mongodb://test", database_name="test_db"),
        rabbitmq=Mock(host="test-rabbitmq", port=5672, username="test", password="test"),
        storage=Mock(
            storage_type="minio",
            endpoint="http://test-storage:9000",
            access_key="test_key",
            secret_key="test_secret",
            bucket_raw="test-raw",
            bucket_processed="test-processed",
            bucket_temp="test-temp",
            bucket_thumbnails="test-thumbnails"
        ),
        upload=Mock(
            service_url="http://test-upload:8001",
            token_expires_minutes=10,
            max_upload_size=1000000,
            allowed_formats=["mp4", "avi"]
        ),
        auth=Mock(
            google_client_id="test_client_id",
            google_client_secret="test_secret",
            session_secret_key="test_session_key",
            session_expires_hours=24
        ),
        payment=Mock(enabled=False),
        app=Mock(
            log_level="DEBUG",
            worker_id="test-worker-123",
            hostname="test-backend",
            default_processing_settings={}
        )
    )


@pytest.fixture
def mock_worker_capabilities() -> WorkerCapabilities:
    """Provide mock worker capabilities."""
    return WorkerCapabilities(
        compute_device="cuda",
        gpu_memory_gb=8,
        system_memory_gb=16,
        max_model_size="large",
        supported_formats=["mp4", "avi", "mov", "mkv"]
    )


@pytest.fixture
def mock_processing_settings() -> ProcessingSettings:
    """Provide mock processing settings."""
    return ProcessingSettings(
        yolo_classes=[0, 2, 3],
        model_size="small",
        detection_type="bbox",
        blur_intensity=15,
        frame_sampling=1,
        processing_resolution=1.0,
        temporal_stability_enabled=True,
        blur_minimum_track_duration=8,
        enable_hood_detection=False,
        debug_mode=False
    )


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB client."""
    mock_client = AsyncMock()
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    
    mock_client.__getitem__.return_value = mock_db
    mock_db.__getitem__.return_value = mock_collection
    
    return mock_client


@pytest.fixture
def mock_rabbitmq():
    """Mock RabbitMQ connection and channel."""
    mock_connection = Mock()
    mock_channel = Mock()
    
    mock_connection.channel.return_value = mock_channel
    mock_channel.is_closed = False
    
    return mock_connection, mock_channel


@pytest.fixture
def mock_storage():
    """Mock storage client."""
    mock_client = Mock()
    
    # Mock common storage operations
    mock_client.generate_presigned_url.return_value = "https://test-signed-url.com/file"
    mock_client.copy_object.return_value = True
    mock_client.delete_object.return_value = True
    
    return mock_client


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Common test data generators

def generate_test_video_id() -> str:
    """Generate a test video ID."""
    return "test-video-123"


def generate_test_user_id() -> str:
    """Generate a test user ID."""
    return "test-user-456"


def generate_test_task_id() -> str:
    """Generate a test task ID."""
    return "test-task-789"


def generate_test_worker_id() -> str:
    """Generate a test worker ID."""
    return "test-worker-abc"
