"""
Hardware detection and capability discovery.

Automatically detects available hardware (CPU, GPU) and determines worker capabilities
as specified in the worker specification.
"""

import psutil
from typing import Optional, Tuple
import structlog

from .models import WorkerCapabilities
from .config import get_config


def detect_gpu_capabilities() -> Tuple[str, Optional[int]]:
    """
    Detect GPU capabilities and memory.
    
    Returns:
        Tuple of (compute_device, gpu_memory_gb)
    """
    config = get_config()
    logger = structlog.get_logger("hardware_detection")
    
    # Check GPU_ENABLED configuration
    gpu_setting = config.processing.gpu_enabled.lower()
    
    if gpu_setting == "false":
        logger.info("GPU disabled by configuration")
        return "cpu", None
    
    # Try to detect CUDA (NVIDIA)
    try:
        import torch
        if torch.cuda.is_available():
            gpu_memory_bytes = torch.cuda.get_device_properties(0).total_memory
            gpu_memory_gb = int(gpu_memory_bytes / (1024**3))
            logger.info("CUDA GPU detected", memory_gb=gpu_memory_gb)
            return "cuda", gpu_memory_gb
    except ImportError:
        logger.debug("PyTorch not available for GPU detection")
    except Exception as e:
        logger.warning("Error detecting CUDA GPU", error=str(e))
    
    # Try to detect Apple Metal Performance Shaders (MPS)
    try:
        import torch
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            # MPS doesn't expose memory info easily, estimate based on system
            system_memory = psutil.virtual_memory().total
            # Rough estimate: assume 25% of system memory available for GPU tasks
            estimated_gpu_memory = int((system_memory / (1024**3)) * 0.25)
            logger.info("Apple MPS detected", estimated_memory_gb=estimated_gpu_memory)
            return "mps", estimated_gpu_memory
    except (ImportError, AttributeError):
        logger.debug("MPS not available")
    except Exception as e:
        logger.warning("Error detecting MPS", error=str(e))
    
    # Default to CPU
    if gpu_setting == "auto":
        logger.info("No GPU detected, using CPU")
    elif gpu_setting == "true":
        logger.warning("GPU requested but not available, falling back to CPU")
    
    return "cpu", None


def detect_system_memory() -> int:
    """
    Detect system memory in GB.
    
    Returns:
        System memory in GB
    """
    memory_bytes = psutil.virtual_memory().total
    memory_gb = int(memory_bytes / (1024**3))
    return memory_gb


def determine_max_model_size(compute_device: str, gpu_memory_gb: Optional[int], 
                           system_memory_gb: int) -> str:
    """
    Determine maximum model size based on available hardware.
    
    Args:
        compute_device: "cuda", "mps", or "cpu"
        gpu_memory_gb: Available GPU memory in GB (if applicable)
        system_memory_gb: Available system memory in GB
    
    Returns:
        Maximum model size: "nano", "small", "medium", "large", or "xlarge"
    """
    logger = structlog.get_logger("hardware_detection")
    
    if compute_device in ["cuda", "mps"] and gpu_memory_gb:
        # GPU-based model size determination for YOLO12
        # Adjusted thresholds - 11GB is sufficient for xlarge models
        if gpu_memory_gb >= 10:
            max_size = "xlarge"  # ~69MB model, 10GB+ should be sufficient
        elif gpu_memory_gb >= 6:
            max_size = "large"   # ~52MB model
        elif gpu_memory_gb >= 4:
            max_size = "medium"  # ~26MB model
        elif gpu_memory_gb >= 2:
            max_size = "small"   # ~11MB model
        else:
            max_size = "nano"    # ~3MB model for very limited GPU
        
        logger.info("GPU model size determined", 
                   device=compute_device, 
                   gpu_memory_gb=gpu_memory_gb, 
                   max_model_size=max_size)
    else:
        # CPU-based model size determination for YOLO12
        if system_memory_gb >= 32:
            max_size = "xlarge"  # High-end systems can handle largest model
        elif system_memory_gb >= 16:
            max_size = "large"   # Standard desktop/laptop
        elif system_memory_gb >= 8:
            max_size = "medium"  # Moderate systems
        elif system_memory_gb >= 4:
            max_size = "small"   # Lower-end systems
        else:
            max_size = "nano"    # Very limited systems
        
        logger.info("CPU model size determined", 
                   system_memory_gb=system_memory_gb, 
                   max_model_size=max_size)
    
    return max_size


def get_worker_capabilities() -> WorkerCapabilities:
    """
    Detect and return complete worker capabilities.
    
    Returns:
        WorkerCapabilities instance with detected hardware info
    """
    logger = structlog.get_logger("hardware_detection")
    
    # Detect hardware
    compute_device, gpu_memory_gb = detect_gpu_capabilities()
    system_memory_gb = detect_system_memory()
    max_model_size = determine_max_model_size(compute_device, gpu_memory_gb, system_memory_gb)
    
    capabilities = WorkerCapabilities(
        compute_device=compute_device,
        gpu_memory_gb=gpu_memory_gb,
        system_memory_gb=system_memory_gb,
        max_model_size=max_model_size,
        supported_formats=["mp4", "avi", "mov", "mkv"]
    )
    
    logger.info("Worker capabilities detected", capabilities=capabilities.__dict__)
    
    return capabilities


def get_current_resource_usage() -> Tuple[float, float, Optional[float]]:
    """
    Get current resource usage percentages.
    
    Returns:
        Tuple of (cpu_percent, memory_percent, gpu_percent)
    """
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # Memory usage
    memory = psutil.virtual_memory()
    memory_percent = memory.percent
    
    # GPU usage (if available)
    gpu_percent = None
    try:
        import torch
        if torch.cuda.is_available():
            # PyTorch doesn't directly provide GPU utilization,
            # but we can get memory usage as a proxy
            memory_allocated = torch.cuda.memory_allocated(0)
            memory_total = torch.cuda.get_device_properties(0).total_memory
            gpu_percent = (memory_allocated / memory_total) * 100
    except (ImportError, Exception):
        pass  # GPU monitoring not available
    
    return cpu_percent, memory_percent, gpu_percent
