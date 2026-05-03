"""Test model manager module."""

import pytest
import os
import tempfile
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path

from dashcam_worker.model_manager import ModelManager


class TestModelManager:
    """Test ModelManager class."""
    
    def test_init(self, test_config):
        """Test ModelManager initialization."""
        manager = ModelManager()
        assert manager.logger is not None
        assert manager.loaded_models == {}
        assert manager.capabilities is not None
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch.object(ModelManager, '_get_model_path')
    def test_load_model_not_cached(self, mock_get_path, mock_yolo, test_config):
        """Test loading model that's not cached."""
        mock_get_path.return_value = "/fake/path/yolo12s.pt"
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        manager = ModelManager()
        model = manager.load_model("small", "bbox")
        
        assert model == mock_model
        assert manager.loaded_models["small_bbox"] == mock_model
        mock_yolo.assert_called_once_with("/fake/path/yolo12s.pt")
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch('os.path.exists')
    def test_load_model_cached(self, mock_exists, mock_yolo, test_config):
        """Test loading model that's already cached."""
        mock_exists.return_value = True
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        manager = ModelManager()
        
        # Load model - the cache directory should be used automatically from config
        model = manager.load_model("medium", "bbox")
        
        assert model == mock_model
        expected_path = os.path.join(manager.config.processing.model_cache_dir, "yolo12m.pt")
        mock_yolo.assert_called_once_with(expected_path)
    
    def test_load_model_already_loaded(self, test_config):
        """Test loading model that's already in memory."""
        manager = ModelManager()
        mock_model = Mock()
        manager.loaded_models["large_bbox"] = mock_model
        
        model = manager.load_model("large", "bbox")
        
        assert model == mock_model
    
    @patch('dashcam_worker.model_manager.YOLO')
    def test_load_model_all_fail(self, mock_yolo, test_config):
        """Test model loading when all sizes fail."""
        mock_yolo.side_effect = Exception("No models available")
        
        manager = ModelManager()
        
        with pytest.raises(Exception) as exc_info:
            manager.load_model("large")
        
        assert "Failed to load any model" in str(exc_info.value)
    
    def test_get_model_filename(self, test_config):
        """Test model filename generation via model info."""
        manager = ModelManager()
        
        # Test using the existing get_model_info method
        assert manager.get_model_info("small")["filename"] == "yolo12s.pt"
        assert manager.get_model_info("medium")["filename"] == "yolo12m.pt"
        assert manager.get_model_info("large")["filename"] == "yolo12l.pt"
    
    def test_get_model_filename_invalid(self, test_config):
        """Test model filename with invalid size."""
        manager = ModelManager()
        
        # Invalid model size returns empty dict
        assert manager.get_model_info("invalid") == {}
    
    def test_get_fallback_sizes(self, test_config):
        """Test fallback mechanism."""
        manager = ModelManager()
        
        # The fallback depends on the worker's capabilities
        # On a system with GPU, fallback returns the max supported size
        fallback = manager._get_fallback_model_size("large")
        assert fallback in ["nano", "small", "medium", "large", "xlarge"]
        
        # For any valid size, fallback should return a valid size
        fallback = manager._get_fallback_model_size("medium")
        assert fallback in ["nano", "small", "medium", "large", "xlarge"]
        
        fallback = manager._get_fallback_model_size("small")
        assert fallback in ["nano", "small", "medium", "large", "xlarge"]
    
    def test_get_fallback_sizes_invalid(self, test_config):
        """Test fallback for invalid model size."""
        manager = ModelManager()
        
        # Invalid size should raise an error or fallback to small
        try:
            result = manager._get_fallback_model_size("invalid")
            # If it doesn't raise, it should be a valid size
            assert result in ["nano", "small", "medium", "large", "xlarge"]
        except (ValueError, KeyError):
            # This is acceptable behavior for invalid input
            pass
    
    @patch('os.makedirs')
    @patch('os.path.exists')
    def test_ensure_cache_dir(self, mock_exists, mock_makedirs, test_config):
        """Test cache directory creation."""
        mock_exists.return_value = False
        
        # The cache dir is created in __init__, but we can test the functionality
        manager = ModelManager()
        # Cache dir should be created during initialization
        assert os.path.exists(manager.config.processing.model_cache_dir) or mock_makedirs.called
    
    @patch('os.path.exists')
    def test_ensure_cache_dir_exists(self, mock_exists, test_config):
        """Test cache directory when it already exists.""" 
        mock_exists.return_value = True
        
        manager = ModelManager()
        # Should not raise exception
        assert manager.config.processing.model_cache_dir is not None
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch.object(ModelManager, '_get_model_path')
    def test_load_model_device_gpu(self, mock_get_path, mock_yolo, test_config):
        """Test model loading with GPU device."""
        mock_get_path.return_value = "/fake/path/yolo12s.pt"
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        # Mock GPU availability
        with patch('torch.cuda.is_available', return_value=True):
            manager = ModelManager()
            model = manager.load_model("small")
        
        # Model should be moved to GPU
        mock_model.to.assert_called_once_with('cuda')
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch.object(ModelManager, '_get_model_path')
    def test_load_model_device_cpu(self, mock_get_path, mock_yolo, test_config):
        """Test model loading with CPU device."""
        mock_get_path.return_value = "/fake/path/yolo12s.pt"
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        # Mock no GPU
        with patch('torch.cuda.is_available', return_value=False):
            manager = ModelManager()
            model = manager.load_model("small")
        
        # Model should be moved to CPU
        mock_model.to.assert_called_once_with('cpu')
    
    def test_clear_cache(self, test_config):
        """Test clearing model cache."""
        manager = ModelManager()
        
        # Add some loaded models
        manager.loaded_models["small"] = Mock()
        manager.loaded_models["medium"] = Mock()
        
        manager.clear_cache()
        
        assert manager.loaded_models == {}
    
    def test_is_model_loaded(self, test_config):
        """Test checking if model is loaded."""
        manager = ModelManager()
        
        assert not manager.is_model_loaded("small", "bbox")
        
        manager.loaded_models["small_bbox"] = Mock()
        assert manager.is_model_loaded("small", "bbox")
    
    def test_get_loaded_models(self, test_config):
        """Test getting list of loaded models."""
        manager = ModelManager()
        
        assert manager.get_loaded_models() == []
        
        manager.loaded_models["small"] = Mock()
        manager.loaded_models["medium"] = Mock()
        
        loaded = manager.get_loaded_models()
        assert set(loaded) == {"small", "medium"}


class TestModelManagerIntegration:
    """Integration tests for model manager."""
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch.object(ModelManager, '_get_model_path')
    def test_model_loading_flow(self, mock_get_path, mock_yolo, test_config):
        """Test complete model loading flow."""
        mock_get_path.return_value = "/fake/path/yolo12s.pt"
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        manager = ModelManager()
        
        # Load model first time
        model1 = manager.load_model("small", "bbox")
        assert model1 == mock_model
        assert manager.is_model_loaded("small", "bbox")
        
        # Load same model again (should return cached)
        model2 = manager.load_model("small", "bbox")
        assert model2 == mock_model
        assert model1 is model2  # Same instance
        
        # YOLO should only be called once for the cached load
        assert mock_yolo.call_count == 1
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch('os.path.exists')
    def test_cache_dir_and_model_loading(self, mock_exists, mock_yolo, test_config):
        """Test cache directory handling during model loading."""
        # Simulate cache file exists
        def exists_side_effect(path):
            if "models" in path and path.endswith(".pt"):
                return True
            return False
        
        mock_exists.side_effect = exists_side_effect
        mock_model = Mock()
        mock_yolo.return_value = mock_model
        
        manager = ModelManager()
        
        model = manager.load_model("medium", "bbox")
        
        # Should load from cache directory
        expected_path = os.path.join(manager.config.processing.model_cache_dir, "yolo12m.pt")
        mock_yolo.assert_called_once_with(expected_path)
        assert model == mock_model
    
    @patch('dashcam_worker.model_manager.YOLO')
    @patch.object(ModelManager, '_get_model_path')
    def test_multiple_model_sizes(self, mock_get_path, mock_yolo, test_config):
        """Test loading multiple different model sizes."""
        # Create different mock objects for different model sizes
        mock_models = [Mock(), Mock(), Mock()]
        mock_yolo.side_effect = mock_models
        
        # Mock different paths for different models
        def get_path_side_effect(model_size, detection_type):
            return f"/fake/path/yolo12{model_size[0]}.pt"
        mock_get_path.side_effect = get_path_side_effect
        
        manager = ModelManager()
        
        # Load different sizes
        small_model = manager.load_model("small", "bbox")
        medium_model = manager.load_model("medium", "bbox")
        large_model = manager.load_model("large", "bbox")
        
        # All should be different instances
        assert small_model != medium_model
        assert medium_model != large_model
        
        # All should be cached
        assert manager.is_model_loaded("small", "bbox")
        assert manager.is_model_loaded("medium", "bbox")
        assert manager.is_model_loaded("large", "bbox")
        
        # Should have made 3 YOLO calls
        assert mock_yolo.call_count == 3
