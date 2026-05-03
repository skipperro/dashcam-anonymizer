"""Test hardware detection module."""

import pytest
from unittest.mock import patch, Mock
import platform

from dashcam_worker.hardware import (
    detect_gpu_capabilities,
    detect_system_memory,
    determine_max_model_size,
    get_worker_capabilities,
    get_current_resource_usage
)
from dashcam_worker.models import WorkerCapabilities


class TestHardwareDetection:
    """Test hardware detection functions."""
    
    @patch('dashcam_worker.hardware.get_config')
    @patch('torch.cuda.is_available')
    @patch('torch.cuda.get_device_properties')
    def test_detect_gpu_cuda_available(self, mock_device_props, mock_cuda_available, mock_config):
        """Test GPU detection when CUDA is available."""
        # Setup mocks
        mock_cuda_available.return_value = True
        
        mock_props = Mock()
        mock_props.total_memory = 10737418240  # 10GB
        mock_device_props.return_value = mock_props
        
        mock_config.return_value.processing.gpu_enabled = "auto"
        
        compute_device, gpu_memory = detect_gpu_capabilities()
        
        assert compute_device == "cuda"
        assert gpu_memory == 10
    
    @patch('dashcam_worker.hardware.get_config')
    @patch('torch.cuda.is_available')
    def test_detect_gpu_cuda_not_available(self, mock_cuda_available, mock_config):
        """Test GPU detection when CUDA is not available."""
        mock_cuda_available.return_value = False
        mock_config.return_value.processing.gpu_enabled = "auto"
        
        compute_device, gpu_memory = detect_gpu_capabilities()
        
        assert compute_device == "cpu"
        assert gpu_memory is None
    
    @patch('dashcam_worker.hardware.get_config')
    def test_detect_gpu_disabled_by_config(self, mock_config):
        """Test GPU detection when disabled by configuration."""
        mock_config.return_value.processing.gpu_enabled = "false"
        
        compute_device, gpu_memory = detect_gpu_capabilities()
        
        assert compute_device == "cpu"
        assert gpu_memory is None
    
    @patch('psutil.virtual_memory')
    def test_detect_system_memory(self, mock_virtual_memory):
        """Test system memory detection."""
        mock_virtual_memory.return_value.total = 16106127360  # 15GB
        
        memory_gb = detect_system_memory()
        
        assert memory_gb == 15
    
    def test_determine_max_model_size_cpu_low_memory(self):
        """Test max model size determination for CPU with low memory."""
        max_size = determine_max_model_size("cpu", None, 4)
        assert max_size == "small"
    
    def test_determine_max_model_size_cpu_medium_memory(self):
        """Test max model size determination for CPU with medium memory."""
        max_size = determine_max_model_size("cpu", None, 8)
        assert max_size == "medium"
    
    def test_determine_max_model_size_cpu_high_memory(self):
        """Test max model size determination for CPU with high memory."""
        max_size = determine_max_model_size("cpu", None, 16)
        assert max_size == "large"
    
    def test_determine_max_model_size_gpu_low_memory(self):
        """Test max model size determination for GPU with low memory."""
        max_size = determine_max_model_size("cuda", 4, 16)
        assert max_size == "medium"
    
    def test_determine_max_model_size_gpu_medium_memory(self):
        """Test max model size determination for GPU with medium memory."""
        max_size = determine_max_model_size("cuda", 8, 16)
        assert max_size == "large"
    
    def test_determine_max_model_size_gpu_high_memory(self):
        """Test max model size determination for GPU with high memory."""
        max_size = determine_max_model_size("cuda", 12, 32)
        assert max_size == "xlarge"
    
    @patch('dashcam_worker.hardware.detect_system_memory')
    @patch('dashcam_worker.hardware.detect_gpu_capabilities')
    def test_get_worker_capabilities(self, mock_gpu, mock_memory):
        """Test worker capabilities determination."""
        mock_gpu.return_value = ("cuda", 8)
        mock_memory.return_value = 16
        
        capabilities = get_worker_capabilities()
        
        assert isinstance(capabilities, WorkerCapabilities)
        assert capabilities.compute_device == "cuda"
        assert capabilities.gpu_memory_gb == 8
        assert capabilities.system_memory_gb == 16
        assert capabilities.max_model_size == "large"
        assert capabilities.supported_formats == ["mp4", "avi", "mov", "mkv"]
    
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_get_current_resource_usage_cpu_only(self, mock_virtual_memory, mock_cpu_percent):
        """Test resource usage monitoring for CPU-only system."""
        mock_cpu_percent.return_value = 45.5
        mock_virtual_memory.return_value.percent = 65.2
        
        with patch('torch.cuda.is_available', return_value=False):
            cpu, memory, gpu = get_current_resource_usage()
        
        assert cpu == 45.5
        assert memory == 65.2
        assert gpu is None
    
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('torch.cuda.is_available')
    @patch('torch.cuda.memory_allocated')
    @patch('torch.cuda.get_device_properties')
    def test_get_current_resource_usage_with_gpu(self, mock_device_props, mock_allocated,
                                                  mock_cuda_available, mock_virtual_memory,
                                                  mock_cpu_percent):
        """Test resource usage monitoring with GPU."""
        mock_cpu_percent.return_value = 35.0
        mock_virtual_memory.return_value.percent = 55.0
        mock_cuda_available.return_value = True
        mock_allocated.return_value = 2147483648  # 2GB
        
        # Mock device properties
        mock_props = Mock()
        mock_props.total_memory = 8589934592  # 8GB
        mock_device_props.return_value = mock_props
        
        cpu, memory, gpu = get_current_resource_usage()
        
        assert cpu == 35.0
        assert memory == 55.0
        assert gpu == 25.0  # 2GB / 8GB * 100
