"""Test configuration loading and validation."""

import pytest
from unittest.mock import patch, Mock
import os

from dashcam_backend.config import (
    get_config, 
    reset_config,
    MongoDBConfig,
    RabbitMQConfig,
    StorageConfig,
    BackendConfig
)


class TestConfiguration:
    """Test configuration management."""
    
    def test_mongodb_config_defaults(self):
        """Test MongoDB configuration with default values."""
        config = MongoDBConfig()
        
        assert config.uri == "mongodb://admin:dashcam123@localhost:27017/dashcam_db"
        assert config.database_name == "dashcam_db"
    
    def test_mongodb_config_from_env(self):
        """Test MongoDB configuration from environment variables."""
        with patch.dict(os.environ, {
            'MONGODB_URI': 'mongodb://test:test@testhost:27017/testdb',
            'DATABASE_NAME': 'test_database'
        }):
            config = MongoDBConfig.from_env()
            
            assert config.uri == 'mongodb://test:test@testhost:27017/testdb'
            assert config.database_name == 'test_database'
    
    def test_rabbitmq_config_defaults(self):
        """Test RabbitMQ configuration with default values."""
        config = RabbitMQConfig()
        
        assert config.host == "localhost"
        assert config.port == 5672
        assert config.username == "dashcam"
        assert config.password == "dashcam123"
        assert config.connection_timeout == 30
    
    def test_rabbitmq_config_from_env(self):
        """Test RabbitMQ configuration from environment variables."""
        with patch.dict(os.environ, {
            'RABBITMQ_HOST': 'test-rabbitmq',
            'RABBITMQ_PORT': '5673',
            'RABBITMQ_USER': 'test_user',
            'RABBITMQ_PASSWORD': 'test_pass'
        }):
            config = RabbitMQConfig.from_env()
            
            assert config.host == 'test-rabbitmq'
            assert config.port == 5673
            assert config.username == 'test_user'
            assert config.password == 'test_pass'
    
    def test_storage_config_defaults(self):
        """Test storage configuration with default values."""
        config = StorageConfig()
        
        assert config.storage_type == "minio"
        assert config.endpoint == "http://localhost:9000"
        assert config.bucket_raw == "dashcam-raw-videos"
        assert config.bucket_processed == "dashcam-processed-videos"
    
    def test_storage_config_from_env(self):
        """Test storage configuration from environment variables."""
        with patch.dict(os.environ, {
            'STORAGE_TYPE': 'r2',
            'STORAGE_ENDPOINT': 'https://test-storage.com',
            'STORAGE_ACCESS_KEY': 'test_key',
            'STORAGE_SECRET_KEY': 'test_secret'
        }):
            config = StorageConfig.from_env()
            
            assert config.storage_type == 'r2'
            assert config.endpoint == 'https://test-storage.com'
            assert config.access_key == 'test_key'
            assert config.secret_key == 'test_secret'
    
    def test_complete_config_loading(self):
        """Test complete configuration loading."""
        config = BackendConfig.from_env()
        
        assert config.mongodb is not None
        assert config.rabbitmq is not None
        assert config.storage is not None
        assert config.upload is not None
        assert config.auth is not None
        assert config.payment is not None
        assert config.app is not None
    
    def test_global_config_singleton(self):
        """Test global configuration singleton behavior."""
        # Reset first
        reset_config()
        
        # Get config twice
        config1 = get_config()
        config2 = get_config()
        
        # Should be the same instance
        assert config1 is config2
    
    def test_config_reset(self):
        """Test configuration reset functionality."""
        # Get initial config
        config1 = get_config()
        
        # Reset
        reset_config()
        
        # Get new config
        config2 = get_config()
        
        # Should be different instances
        assert config1 is not config2
    
    def test_allowed_video_formats_parsing(self):
        """Test parsing of allowed video formats from environment."""
        with patch.dict(os.environ, {
            'ALLOWED_VIDEO_FORMATS': 'mp4,avi,mov'
        }):
            config = BackendConfig.from_env()
            
            assert config.upload.allowed_formats == ['mp4', 'avi', 'mov']
    
    def test_boolean_environment_variables(self):
        """Test boolean environment variable parsing."""
        with patch.dict(os.environ, {
            'GOOGLE_PAY_ENABLED': 'true'
        }):
            config = BackendConfig.from_env()
            
            assert config.payment.enabled is True
        
        with patch.dict(os.environ, {
            'GOOGLE_PAY_ENABLED': 'false'
        }):
            config = BackendConfig.from_env()
            
            assert config.payment.enabled is False
    
    def test_numeric_environment_variables(self):
        """Test numeric environment variable parsing."""
        with patch.dict(os.environ, {
            'MAX_UPLOAD_SIZE': '1000000000',
            'SESSION_EXPIRES_HOURS': '48'
        }):
            config = BackendConfig.from_env()
            
            assert config.upload.max_upload_size == 1000000000
            assert config.auth.session_expires_hours == 48
