"""Test configuration for pytest."""

import os
import sys
import pytest
import tempfile
import shutil
from unittest.mock import patch

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture
def temp_model_dir():
    """Create a temporary directory for model cache during tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_config(temp_model_dir):
    """Mock configuration for tests."""
    with patch.dict(os.environ, {
        'WORKER_ID': 'test-worker',
        'HOSTNAME': 'test-host',
        'MODEL_CACHE_DIR': temp_model_dir,  # Ensure we use temp dir for tests
        'RABBITMQ_HOST': 'test-rabbit',
        'RABBITMQ_PORT': '5672',
        'RABBITMQ_USERNAME': 'guest',
        'RABBITMQ_PASSWORD': 'guest',
        'S3_ENDPOINT': 'http://localhost:9000',
        'S3_ACCESS_KEY': 'testkey',
        'S3_SECRET_KEY': 'testsecret',
        'S3_BUCKET_NAME': 'test-bucket',
        'GPU_ENABLED': 'auto',
        'MAX_WORKERS': '2',
        'MODEL_SIZE': 'medium',
        'DETECTION_CONFIDENCE': '0.5',
        'BLUR_STRENGTH': '51'
    }):
        # Reset config to pick up new environment variables
        from dashcam_worker.config import reset_config
        reset_config()
        yield