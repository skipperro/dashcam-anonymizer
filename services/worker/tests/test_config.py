"""Test configuration module."""

import pytest
from unittest.mock import Mock, patch
import os
import tempfile

# Mock environment variables for testing
test_env = {
    'RABBITMQ_HOST': 'test-rabbitmq',
    'RABBITMQ_PORT': '5672',
    'RABBITMQ_USER': 'test',
    'RABBITMQ_PASSWORD': 'test',
    'STORAGE_TYPE': 'minio',
    'STORAGE_ENDPOINT': 'http://test-minio:9000',
    'STORAGE_ACCESS_KEY': 'testkey',
    'STORAGE_SECRET_KEY': 'testsecret',
    'STORAGE_BUCKET_RAW': 'test-raw',
    'STORAGE_BUCKET_PROCESSED': 'test-processed',
    'MONGODB_URI': 'mongodb://test-mongo:27017',
    'MONGODB_DATABASE': 'test_db',
    'GPU_ENABLED': 'false',
    'MODEL_CACHE_DIR': '/tmp/test_models',
    'CHECKPOINT_INTERVAL': '10',
    'LOG_LEVEL': 'INFO'
}


@pytest.fixture(scope='session', autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    for key, value in test_env.items():
        os.environ[key] = value


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    with patch('dashcam_worker.config.get_config') as mock:
        config = Mock()
        config.worker_id = 'test-worker-123'
        config.hostname = 'test-host'
        config.rabbitmq.host = 'test-rabbitmq'
        config.rabbitmq.port = 5672
        config.rabbitmq.user = 'test'
        config.rabbitmq.password = 'test'
        config.storage.type = 'minio'
        config.storage.endpoint = 'http://test-minio:9000'
        config.storage.access_key = 'testkey'
        config.storage.secret_key = 'testsecret'
        config.storage.bucket_raw = 'test-raw'
        config.storage.bucket_processed = 'test-processed'
        config.database.uri = 'mongodb://test-mongo:27017'
        config.database.database = 'test_db'
        config.processing.gpu_enabled = 'false'
        config.processing.model_cache_dir = '/tmp/test_models'
        config.processing.checkpoint_interval = 10
        config.processing.log_level = 'INFO'
        
        mock.return_value = config
        yield config


@pytest.fixture
def sample_task_message():
    """Sample task message for testing."""
    from dashcam_worker.models import TaskMessage, ProcessingSettings
    
    settings = ProcessingSettings(
        yolo_classes=[0, 2, 3, 5, 7],
        model_size="medium",
        detection_type="bbox",
        debug_mode=False,
        blur_intensity=15,
        frame_sampling=1,
        processing_resolution=1.0
    )
    
    return TaskMessage(
        task_id="test-task-123",
        video_id="test-video-456",
        user_id="test-user-789",
        input_file_path="raw-videos/test-user-789/test-video-456.mp4",
        output_file_path="processed-videos/test-user-789/test-video-456/test-task-123/output.mp4",
        processing_settings=settings,
        created_at="2025-01-15T10:30:00Z"
    )
