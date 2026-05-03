"""
Configuration module for the Dashcam Worker.

Handles environment variable loading and validation based on the worker specification.
"""

import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class RabbitMQConfig:
    """RabbitMQ connection configuration."""
    host: str = os.getenv("RABBITMQ_HOST", "localhost")
    port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    user: str = os.getenv("RABBITMQ_USER", "guest")
    password: str = os.getenv("RABBITMQ_PASSWORD", "guest")


@dataclass
class StorageConfig:
    """Object storage configuration."""
    type: str = os.getenv("STORAGE_TYPE", "minio")  # 'minio' or 'r2'
    endpoint: str = os.getenv("STORAGE_ENDPOINT", "http://localhost:9000")
    access_key: str = os.getenv("STORAGE_ACCESS_KEY", "minioadmin")
    secret_key: str = os.getenv("STORAGE_SECRET_KEY", "minioadmin")
    bucket_raw: str = os.getenv("STORAGE_BUCKET_RAW", "raw-videos")
    bucket_processed: str = os.getenv("STORAGE_BUCKET_PROCESSED", "processed-videos")


@dataclass
class ProcessingConfig:
    """Video processing configuration."""
    gpu_enabled: str = os.getenv("GPU_ENABLED", "auto")  # 'true', 'false', or 'auto'
    model_cache_dir: str = os.getenv("MODEL_CACHE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models"))  # Default to worker/models directory
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    checkpoint_interval: float = float(os.getenv("CHECKPOINT_INTERVAL", "5.0"))  # Progress update interval in seconds


@dataclass
class WorkerConfig:
    """Complete worker configuration."""
    rabbitmq: RabbitMQConfig
    storage: StorageConfig
    processing: ProcessingConfig
    worker_id: Optional[str] = None
    hostname: Optional[str] = None

    def __post_init__(self):
        """Initialize computed fields."""
        if self.worker_id is None:
            import uuid
            self.worker_id = str(uuid.uuid4())
        
        if self.hostname is None:
            import socket
            self.hostname = socket.gethostname()


# Global configuration instance
_config = None


def get_config() -> WorkerConfig:
    """Get the global configuration instance, creating it if it doesn't exist."""
    global _config
    if _config is None:
        _config = WorkerConfig(
            rabbitmq=RabbitMQConfig(),
            storage=StorageConfig(),
            processing=ProcessingConfig(),
            worker_id=os.getenv("WORKER_ID")  # Load from environment
        )
    return _config


def reset_config():
    """Reset the global configuration instance. Used for testing."""
    global _config
    _config = None


# COCO Dataset Class Reference
COCO_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane", 5: "bus", 
    6: "train", 7: "truck", 8: "boat", 9: "traffic light", 10: "fire hydrant", 
    11: "stop sign", 12: "parking meter", 13: "bench", 14: "bird", 15: "cat", 
    16: "dog", 17: "horse", 18: "sheep", 19: "cow", 20: "elephant", 21: "bear", 
    22: "zebra", 23: "giraffe", 24: "backpack", 25: "umbrella", 26: "handbag", 
    27: "tie", 28: "suitcase", 29: "frisbee", 30: "skis", 31: "snowboard", 
    32: "sports ball", 33: "kite", 34: "baseball bat", 35: "baseball glove", 
    36: "skateboard", 37: "surfboard", 38: "tennis racket", 39: "bottle", 
    40: "wine glass", 41: "cup", 42: "fork", 43: "knife", 44: "spoon", 45: "bowl", 
    46: "banana", 47: "apple", 48: "sandwich", 49: "orange", 50: "broccoli", 
    51: "carrot", 52: "hot dog", 53: "pizza", 54: "donut", 55: "cake", 56: "chair", 
    57: "couch", 58: "potted plant", 59: "bed", 60: "dining table", 61: "toilet", 
    62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard", 
    67: "cell phone", 68: "microwave", 69: "oven", 70: "toaster", 71: "sink", 
    72: "refrigerator", 73: "book", 74: "clock", 75: "vase", 76: "scissors", 
    77: "teddy bear", 78: "hair drier", 79: "toothbrush"
}
