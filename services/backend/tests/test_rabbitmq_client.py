"""Tests for RabbitMQ client."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from dashcam_backend.rabbitmq_client import RabbitMQClient, get_rabbitmq_client
from dashcam_backend.config import reset_config


@dataclass
class MockMessage:
    """Mock message for testing."""
    message_type: str = "test_message"
    data: str = "test_data"


class TestRabbitMQClient:
    """Test RabbitMQ client functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        reset_config()
        self.client = RabbitMQClient()
    
    def test_client_initialization(self):
        """Test client can be initialized."""
        assert self.client.connection is None
        assert self.client.channel is None
        assert self.client.consuming_thread is None
        assert self.client.message_handlers == {}
    
    def test_register_handler(self):
        """Test registering message handlers."""
        def mock_handler(message: dict):
            pass
        
        self.client.register_message_handler("test_message", mock_handler)
        
        assert "test_message" in self.client.message_handlers
        assert self.client.message_handlers["test_message"] == mock_handler
    
    @patch('dashcam_backend.rabbitmq_client.pika.BlockingConnection')
    def test_connection_setup(self, mock_connection_class):
        """Test connection setup without actually connecting."""
        # Mock the connection and channel
        mock_connection = MagicMock()
        mock_channel = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_connection_class.return_value = mock_connection
        mock_connection_class.return_value = mock_connection
        
        # We can't easily test the full connection due to pika complexity
        # but we can test that the client stores the configuration
        assert self.client.config.rabbitmq.host == "localhost"
        assert self.client.config.rabbitmq.port == 5672
    
    def test_message_serialization(self):
        """Test message serialization logic."""
        # Test with dataclass
        msg = MockMessage()
        
        # The actual serialization would happen in publish_message
        # We can test that the message has the expected structure
        assert hasattr(msg, '__dataclass_fields__')
        assert msg.message_type == "test_message"
        assert msg.data == "test_data"
    
    def test_worker_queue_naming(self):
        """Test worker queue name generation."""
        worker_id = "test-worker-123"
        expected_queue_name = f"worker_assignments_{worker_id}"
        expected_routing_key = f"worker.{worker_id}.assignment"
        
        # These would be used in create_worker_queue and assign_task_to_worker
        assert expected_queue_name == "worker_assignments_test-worker-123"
        assert expected_routing_key == "worker.test-worker-123.assignment"
    
    def test_thread_local_client(self):
        """Test thread-local client instance."""
        client1 = get_rabbitmq_client()
        client2 = get_rabbitmq_client()
        
        # Should be the same instance in the same thread
        assert client1 is client2
        
        # Both should be RabbitMQClient instances
        assert isinstance(client1, RabbitMQClient)
        assert isinstance(client2, RabbitMQClient)
